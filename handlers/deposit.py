# handlers/deposit.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
import logging
from handlers.time_utils import get_damascus_time_now, format_damascus_time, DAMASCUS_TZ
from datetime import datetime
from handlers.keyboards import get_back_keyboard, get_main_menu_keyboard, get_cancel_keyboard
from database.users import is_admin_user
from database.core import get_exchange_rate, set_exchange_rate
from utils import get_formatted_damascus_time, format_amount, is_valid_positive_number, parse_number

# ✅ استيراد config مباشرة
import config

logger = logging.getLogger(__name__)
router = Router()

class DepStates(StatesGroup):
    waiting_amount = State()
    waiting_tx = State()
    waiting_photo = State()

# ✅ دوال مساعدة - تجلب من config مباشرة
def get_current_exchange_rate():
    """جلب سعر الصرف من config مباشرة (فوري)"""
    return config.USD_TO_SYP

def get_current_syriatel_numbers():
    """جلب أرقام سيرياتل من config مباشرة (فوري)"""
    return config.SYRIATEL_NUMS

def get_payment_methods():
    """جلب طرق الدفع المتاحة"""
    return [
        {"name": "Syriatel Cash (ل.س)", "callback": "m_syr"},
        {"name": "Sham Cash (ل.س)", "callback": "m_sham_syp"},
        {"name": "Sham Cash ($)", "callback": "m_sham_usd"},
        {"name": "USDT BEP20 ($)", "callback": "m_usdt"},
    ]

# ============= معالج الرجوع الموحد =============

@router.message(F.text.in_(["🔙 رجوع للقائمة", "/رجوع", "/cancel", "❌ إلغاء"]))
async def deposit_back_handler(message: types.Message, state: FSMContext, db_pool):
    """الرجوع من عملية الشحن"""
    current_state = await state.get_state()
    
    if current_state is not None:
        await state.clear()
    
    is_admin = await is_admin_user(db_pool, message.from_user.id)
    
    await message.answer(
        "✅ تم إلغاء عملية الشحن" if current_state else "👋 أنت في القائمة الرئيسية",
        reply_markup=get_main_menu_keyboard(is_admin)
    )

# ============= قائمة طرق الدفع =============

@router.message(F.text == "💰 شحن المحفظة")
async def choose_meth(message: types.Message, db_pool):
    """عرض قائمة طرق الدفع"""
    is_admin = await is_admin_user(db_pool, message.from_user.id)
    
    # ✅ استخدام الدالة المساعدة مباشرة (بدون كاش)
    methods = get_payment_methods()
    
    kb = []
    for method in methods:
        kb.append([types.InlineKeyboardButton(
            text=method["name"], 
            callback_data=method["callback"]
        )])
    kb.append([types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_main")])
    
    await message.answer(
        "💳 **اختر وسيلة الدفع المناسبة:**", 
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )

@router.callback_query(F.data == "back_to_main")
async def back_from_deposit(callback: types.CallbackQuery, db_pool):
    """العودة للقائمة الرئيسية"""
    await callback.answer()
    await callback.message.delete()
    
    is_admin = await is_admin_user(db_pool, callback.from_user.id)
    
    await callback.message.answer(
        "تم العودة للقائمة الرئيسية.",
        reply_markup=get_main_menu_keyboard(is_admin)
    )

# ============= بدء عملية الشحن =============

@router.callback_query(F.data.startswith("m_"))
async def start_dep(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء عملية الشحن - مع جلب سعر الصرف من config"""
    method = callback.data
    
    await callback.answer()
    
    # ✅ جلب سعر الصرف من config مباشرة (فوري)
    current_rate = get_current_exchange_rate()
    logger.info(f"💰 سعر الصرف الحالي للشحن: {current_rate}")
    
    # ✅ جلب أرقام سيرياتل من config مباشرة (فوري)
    syriatel_nums = get_current_syriatel_numbers()
    
    # تحديد اسم المحفظة حسب الطريقة
    if method == "m_sham_syp":
        method_name = "شام كاش (ل.س)"
        wallet = config.SHAM_CASH_NUM
    elif method == "m_sham_usd":
        method_name = "شام كاش ($)"
        wallet = config.SHAM_CASH_NUM_USD
    elif method == "m_syr":
        method_name = "سيرياتل كاش"
        wallet = syriatel_nums[0] if syriatel_nums else "غير محدد"
    elif method == "m_usdt":
        method_name = "USDT BEP20"
        wallet = config.USDT_BEP20_WALLET
    else:
        await callback.answer("❌ طريقة دفع غير معروفة", show_alert=True)
        return
    
    await state.update_data(
        method=method,
        method_name=method_name,
        wallet=wallet,
        current_rate=current_rate,
        syriatel_nums=syriatel_nums
    )
    
    await state.set_state(DepStates.waiting_amount)
    
    msg = f"💸 **{method_name}**\n\n"
    msg += f"💰 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n\n"
    
    if method in ["m_syr", "m_sham_syp"]:
        msg += "أدخل المبلغ بالليرة السورية (مثال: 5000):"
    else:
        msg += "أدخل المبلغ بالدولار (مثال: 50):"
    
    await callback.message.answer(
        msg,
        reply_markup=get_cancel_keyboard()
    )

# ============= استلام المبلغ =============

@router.message(DepStates.waiting_amount)
async def get_amount(message: types.Message, state: FSMContext):
    """استلام المبلغ والتحقق من صحته"""
    if message.text in ["🔙 رجوع للقائمة", "/رجوع", "/cancel", "❌ إلغاء"]:
        await state.clear()
        from database.users import is_admin_user
        is_admin = await is_admin_user(None, message.from_user.id)
        await message.answer(
            "✅ تم إلغاء عملية الشحن.",
            reply_markup=get_main_menu_keyboard(is_admin)
        )
        return
    
    # تنظيف النص من الفواصل والمسافات
    text = message.text.replace(',', '').replace(' ', '')
    
    # التحقق من صحة الرقم
    try:
        # السماح بالأرقام العشرية
        if '.' in text:
            if not text.replace('.', '').isdigit() or text.count('.') > 1:
                raise ValueError
        else:
            if not text.isdigit():
                raise ValueError
        
        amt = float(text)
        
        # التحقق من أن المبلغ أكبر من 0
        if amt <= 0:
            return await message.answer(
                "⚠️ المبلغ يجب أن يكون أكبر من 0.\n"
                "الرجاء إدخال مبلغ صحيح:",
                reply_markup=get_cancel_keyboard()
            )
        
        # التحقق من الحد الأدنى للمبلغ
        if amt < 1:
            return await message.answer(
                "⚠️ الحد الأدنى للمبلغ هو 1.\n"
                "الرجاء إدخال مبلغ أكبر:",
                reply_markup=get_cancel_keyboard()
            )
        
    except ValueError:
        return await message.answer(
            "⚠️ خطأ في الصيغة!\n"
            "الرجاء إدخال رقم صحيح (مثال: 5000 أو 50.5):",
            reply_markup=get_cancel_keyboard()
        )
    
    data = await state.get_data()
    current_rate = data.get('current_rate', 118)
    
    # حساب المبلغ بالليرة
    if data['method'] in ["m_usdt", "m_sham_usd"]:
        amount_syp = amt * current_rate
        display_amount = f"{amt:,.2f}$ ≈ {amount_syp:,.0f} ل.س"
    else:
        amount_syp = amt
        display_amount = f"{amt:,.0f} ل.س"
    
    await state.update_data(
        amt=amt,
        amount_syp=amount_syp,
        display_amount=display_amount
    )
    
    # عرض تعليمات التحويل حسب الطريقة
    if data['method'] == "m_syr":
        # ✅ جلب الأرقام المحدثة من config مباشرة
        syriatel_nums = get_current_syriatel_numbers()
        
        nums_text = ""
        for i, num in enumerate(syriatel_nums, 1):
            nums_text += f"📞 **رقم {i}:** `{num}`\n"
        
        await message.answer(
            f"📤 **تحويل {display_amount}**\n\n"
            f"{nums_text}\n"
            f"✅ **بعد التحويل، أرسل رقم العملية:**\n"
            f"💡 *اضغط على الرقم لنسخه*",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(DepStates.waiting_tx)
    
    elif data['method'] in ["m_sham_syp", "m_sham_usd"]:
        currency = "ل.س" if data['method'] == "m_sham_syp" else "$"
        
        await message.answer(
            f"📤 **تحويل {display_amount}**\n\n"
            f"👛 **إلى محفظة شام كاش ({currency}):**\n"
            f"`{data['wallet']}`\n\n"
            f"✅ **بعد التحويل، أرسل رقم العملية:**\n"
            f"💡 *اضغط على رقم المحفظة لنسخه*",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(DepStates.waiting_tx)
    
    elif data['method'] == "m_usdt":
        await message.answer(
            f"📤 **تحويل {display_amount}**\n\n"
            f"👛 **إلى عنوان USDT (BEP20):**\n"
            f"`{data['wallet']}`\n\n"
            f"📸 **بعد التحويل، أرسل لقطة شاشة للتحويل:**\n"
            f"💡 *اضغط على العنوان لنسخه*",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(DepStates.waiting_photo)

# ============= إرسال الطلب للمجموعة =============

async def send_to_group(bot: Bot, data: dict, tx_info: str = None, photo_file_id: str = None):
    """إرسال طلب الشحن للمجموعة مع أزرار - بتوقيت دمشق"""
    try:
        user_info = f"👤 المستخدم: @{data.get('username', 'غير معروف')}\n"
        user_info += f"🆔 الآيدي: `{data['user_id']}`\n"
        
        amount_info = f"💰 المبلغ: {data['display_amount']}\n"
        amount_info += f"💸 المبلغ بالليرة: {data['amount_syp']:,.0f} ل.س\n"
        
        method_info = f"📱 الطريقة: {data['method_name']}\n"
        
        tx_info_text = f"🔢 رقم العملية: `{tx_info}`\n" if tx_info else ""
        
        # استخدام توقيت دمشق
        current_time = get_formatted_damascus_time()
        
        caption = (
            "🆕 **طلب شحن جديد**\n\n"
            f"{user_info}"
            f"{amount_info}"
            f"{method_info}"
            f"{tx_info_text}"
            f"⏰ الوقت: {current_time}\n\n"
            "🔹 **الإجراءات:**"
        )
        
        # أزرار الموافقة والرفض
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(
                text="✅ موافقة", 
                callback_data=f"appr_dep_{data['user_id']}_{data['amount_syp']:.0f}"
            ),
            types.InlineKeyboardButton(
                text="❌ رفض", 
                callback_data=f"reje_dep_{data['user_id']}"
            ),
            width=2
        )
        
        if photo_file_id:
            msg = await bot.send_photo(
                chat_id=config.DEPOSIT_GROUP,
                photo=photo_file_id,
                caption=caption,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
        else:
            msg = await bot.send_message(
                chat_id=config.DEPOSIT_GROUP,
                text=caption,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
        
        logger.info(f"✅ تم إرسال طلب الشحن للمجموعة، message_id: {msg.message_id}")
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال للمجموعة: {e}")
        return None

# ============= معالجة رقم العملية =============

@router.message(DepStates.waiting_tx)
async def process_tx(message: types.Message, state: FSMContext, bot: Bot, db_pool):
    """معالجة رقم العملية"""
    if message.text in ["🔙 رجوع للقائمة", "/رجوع", "/cancel", "❌ إلغاء"]:
        await state.clear()
        is_admin = await is_admin_user(db_pool, message.from_user.id)
        await message.answer(
            "✅ تم إلغاء عملية الشحن.",
            reply_markup=get_main_menu_keyboard(is_admin)
        )
        return
    
    data = await state.get_data()
    tx = message.text.strip()
    
    # التحقق من صحة رقم العملية لسيرياتل كاش
    if data['method'] == "m_syr":
        # إزالة أي مسافات أو شرطات
        clean_tx = tx.replace(' ', '').replace('-', '')
        if not clean_tx.isdigit() or len(clean_tx) < 8:
            return await message.answer(
                "❌ **خطأ:** رقم عملية سيرياتل كاش يجب أن يكون أرقام فقط وطوله 8 أرقام على الأقل.\n"
                "📝 يرجى إدخال رقم صحيح:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown"
            )
    
    # حفظ الطلب في قاعدة البيانات
    async with db_pool.acquire() as conn:
        # إضافة أو تحديث المستخدم
        await conn.execute('''
            INSERT INTO users (user_id, username, balance, created_at) 
            VALUES ($1, $2, 0, CURRENT_TIMESTAMP) 
            ON CONFLICT (user_id) DO UPDATE SET 
                username = EXCLUDED.username,
                last_activity = CURRENT_TIMESTAMP
        ''', message.from_user.id, message.from_user.username)
        
        # إنشاء طلب الشحن
        deposit_id = await conn.fetchval('''
            INSERT INTO deposit_requests 
            (user_id, username, method, amount, amount_syp, tx_info, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'pending', CURRENT_TIMESTAMP)
            RETURNING id
        ''', 
        message.from_user.id, 
        message.from_user.username,
        data['method'],
        data['amt'],
        data['amount_syp'],
        tx
        )
        
        # تجهيز بيانات الإرسال للمجموعة
        channel_data = {
            'user_id': message.from_user.id,
            'username': message.from_user.username or 'غير معروف',
            'display_amount': data['display_amount'],
            'amount_syp': data['amount_syp'],
            'method_name': data['method_name'],
        }
        
        # إرسال للمجموعة
        group_msg_id = await send_to_group(bot, channel_data, tx)
        
        # تحديث معرف رسالة المجموعة
        if group_msg_id:
            await conn.execute(
                "UPDATE deposit_requests SET group_message_id = $1 WHERE id = $2",
                group_msg_id, deposit_id
            )
    
    is_admin = await is_admin_user(db_pool, message.from_user.id)
    
    await message.answer(
        f"✅ **تم إرسال طلب الشحن بنجاح!**\n\n"
        f"💰 **المبلغ:** {data['display_amount']}\n"
        f"🆔 **رقم الطلب:** #{deposit_id}\n"
        f"⏳ **بانتظار موافقة الإدارة.**\n"
        f"📋 **الوقت المتوقع: 5-10 دقائق.**\n\n"
        f"👋 يمكنك العودة للقائمة الرئيسية من الأزرار أدناه:",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown"
    )
    
    await state.clear()

# ============= معالجة الصور =============

@router.message(DepStates.waiting_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext, bot: Bot, db_pool):
    """معالجة لقطة الشاشة"""
    if message.text in ["🔙 رجوع للقائمة", "/رجوع", "/cancel", "❌ إلغاء"]:
        await state.clear()
        is_admin = await is_admin_user(db_pool, message.from_user.id)
        await message.answer(
            "✅ تم إلغاء عملية الشحن.",
            reply_markup=get_main_menu_keyboard(is_admin)
        )
        return
    
    data = await state.get_data()
    
    # استخدام أعلى جودة للصورة
    photo_file_id = message.photo[-1].file_id
    
    async with db_pool.acquire() as conn:
        # إضافة أو تحديث المستخدم
        await conn.execute('''
            INSERT INTO users (user_id, username, balance, created_at) 
            VALUES ($1, $2, 0, CURRENT_TIMESTAMP) 
            ON CONFLICT (user_id) DO UPDATE SET 
                username = EXCLUDED.username,
                last_activity = CURRENT_TIMESTAMP
        ''', message.from_user.id, message.from_user.username)
        
        # إنشاء طلب الشحن مع الصورة
        deposit_id = await conn.fetchval('''
            INSERT INTO deposit_requests 
            (user_id, username, method, amount, amount_syp, tx_info, photo_file_id, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', CURRENT_TIMESTAMP)
            RETURNING id
        ''', 
        message.from_user.id, 
        message.from_user.username,
        data['method'],
        data['amt'],
        data['amount_syp'],
        "USDT Transfer",
        photo_file_id
        )
        
        # تجهيز بيانات الإرسال للمجموعة
        channel_data = {
            'user_id': message.from_user.id,
            'username': message.from_user.username or 'غير معروف',
            'display_amount': data['display_amount'],
            'amount_syp': data['amount_syp'],
            'method_name': data['method_name'],
        }
        
        # إرسال للمجموعة مع الصورة
        group_msg_id = await send_to_group(bot, channel_data, photo_file_id=photo_file_id)
        
        # تحديث معرف رسالة المجموعة
        if group_msg_id:
            await conn.execute(
                "UPDATE deposit_requests SET group_message_id = $1 WHERE id = $2",
                group_msg_id, deposit_id
            )
    
    is_admin = await is_admin_user(db_pool, message.from_user.id)
    
    await message.answer(
        f"✅ **تم إرسال لقطة الشاشة بنجاح!**\n\n"
        f"💰 **المبلغ:** {data['display_amount']}\n"
        f"🆔 **رقم الطلب:** #{deposit_id}\n"
        f"⏳ **بانتظار موافقة الإدارة.**\n"
        f"📋 **الوقت المتوقع: 5-10 دقائق.**\n\n"
        f"👋 يمكنك العودة للقائمة الرئيسية من الأزرار أدناه:",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown"
    )
    
    await state.clear()

# ============= معالج الصور غير الصالحة =============

@router.message(DepStates.waiting_photo)
async def invalid_photo(message: types.Message):
    """معالج إذا أرسل المستخدم نص بدل صورة"""
    await message.answer(
        "❌ **خطأ:** يرجى إرسال صورة للتحويل (لقطة شاشة).\n"
        "📸 أرسل الصورة الآن، أو اضغط على زر الإلغاء.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
