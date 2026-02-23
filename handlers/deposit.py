# handlers/deposit.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import SYRIATEL_NUMS, SHAM_CASH_NUM, SHAM_CASH_NUM_USD, USDT_BEP20_WALLET, DEPOSIT_GROUP
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import asyncio
import logging
from handlers.time_utils import get_damascus_time_now, DAMASCUS_TZ
from datetime import datetime
from handlers.keyboards import get_back_keyboard, get_main_menu_keyboard

# ضبط المنطقة الزمنية لدمشق
DAMASCUS_TZ = pytz.timezone('Asia/Damascus')

logger = logging.getLogger(__name__)
router = Router()

class DepStates(StatesGroup):
    waiting_amount = State()
    waiting_tx = State()
    waiting_photo = State()


def get_damascus_time():
    """الحصول على الوقت الحالي بتوقيت دمشق"""
    return datetime.now(DAMASCUS_TZ).strftime('%Y-%m-%d %H:%M:%S')

@router.message(F.text == "💰 شحن المحفظة")
async def choose_meth(message: types.Message):
    kb = [
        [types.InlineKeyboardButton(text="Syriatel Cash (ل.س)", callback_data="m_syr")],
        [types.InlineKeyboardButton(text="Sham Cash (ل.س)", callback_data="m_sham_syp")],
        [types.InlineKeyboardButton(text="Sham Cash ($)", callback_data="m_sham_usd")],
        [types.InlineKeyboardButton(text="USDT BEP20 ($)", callback_data="m_usdt")],
        [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_main")]
    ]
    await message.answer(
        "💳 **اختر وسيلة الدفع المناسبة:**", 
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )

@router.callback_query(F.data == "back_to_main")
async def back_from_deposit(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "تم العودة للقائمة الرئيسية.",
        reply_markup=get_main_menu_keyboard()  # 👈 استخدم الدالة المستوردة
    )
@router.message(F.text.in_(["🔙 رجوع للقائمة", "/رجوع", "/cancel"]))
async def deposit_back_handler(message: types.Message, state: FSMContext):
    """الرجوع من عملية الشحن"""
    current_state = await state.get_state()
    
    if current_state is not None:
        await state.clear()
        await message.answer(
            "✅ تم إلغاء عملية الشحن",
            reply_markup=get_back_keyboard()  # 👈 استخدم الدالة المستوردة
        )
    else:
        await message.answer(
            "👋 أنت في القائمة الرئيسية",
            reply_markup=get_main_menu_keyboard()  # 👈 استخدم الدالة المستوردة
        )

@router.callback_query(F.data.startswith("m_"))
async def start_dep(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء عملية الشحن - مع جلب سعر الصرف من قاعدة البيانات"""
    method = callback.data
    
    # جلب سعر الصرف الحالي من قاعدة البيانات
    from database import get_exchange_rate, get_syriatel_numbers
    current_rate = await get_exchange_rate(db_pool)
    logger.info(f"💰 سعر الصرف الحالي للشحن: {current_rate}")
    
    # جلب أرقام سيرياتل من قاعدة البيانات
    syriatel_nums = await get_syriatel_numbers(db_pool)
    
    if method == "m_sham_syp":
        method_name = "شام كاش (ل.س)"
        wallet = SHAM_CASH_NUM
    elif method == "m_sham_usd":
        method_name = "شام كاش ($)"
        wallet = SHAM_CASH_NUM_USD
    elif method == "m_syr":
        method_name = "سيرياتل كاش"
        wallet = syriatel_nums[0] if syriatel_nums else "غير محدد"
    elif method == "m_usdt":
        method_name = "USDT BEP20"
        wallet = USDT_BEP20_WALLET
    else:
        method_name = "غير معروف"
        wallet = "غير محدد"
    
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
        msg += "أدخل المبلغ بالليرة السورية:"
    else:
        msg += "أدخل المبلغ بالدولار ($):"
    
    await callback.message.answer(
        msg,
        reply_markup=get_back_keyboard()
    )

@router.message(DepStates.waiting_amount)
async def get_amount(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع للقائمة":
        await state.clear()
        await message.answer("تم إلغاء عملية الشحن.")
        return
    
    # تنظيف النص من الفواصل
    text = message.text.replace(',', '').replace(' ', '')
    if not text.replace('.', '').isdigit():
        return await message.answer(
            "يرجى إدخال رقم صحيح",
            reply_markup=get_back_keyboard()
        )
    
    amt = float(text)
    data = await state.get_data()
    current_rate = data.get('current_rate', 25000)

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
    
    if data['method'] == "m_syr":
        # جلب أرقام سيرياتل
        syriatel_nums = data.get('syriatel_nums', ["74091109", "63826779"])
        
        # بناء نص الأرقام
        nums_text = ""
        for i, num in enumerate(syriatel_nums, 1):
            nums_text += f"📞 **رقم {i}:** `{num}`\n"
        
        await message.answer(
            f"📤 **تحويل {display_amount}**\n\n"
            f"{nums_text}\n"
            f"✅ **بعد التحويل، أرسل رقم العملية:**\n"
            f"💡 *اضغط على الرقم لنسخه*",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(DepStates.waiting_tx)
    
    elif data['method'] in ["m_sham_syp", "m_sham_usd"]:
        # تحديد نوع العملة
        currency = "ل.س" if data['method'] == "m_sham_syp" else "$"
        
        await message.answer(
            f"📤 **تحويل {display_amount}**\n\n"
            f"👛 **إلى محفظة شام كاش ({currency}):**\n"
            f"`{data['wallet']}`\n\n"
            f"✅ **بعد التحويل، أرسل رقم العملية:**\n"
            f"💡 *اضغط على رقم المحفظة لنسخه*",
            reply_markup=get_back_keyboard(),
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
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(DepStates.waiting_photo)

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
        current_time = get_damascus_time()
        
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
                callback_data=f"appr_dep_{data['user_id']}_{data['amount_syp']}"
            ),
            types.InlineKeyboardButton(
                text="❌ رفض", 
                callback_data=f"reje_dep_{data['user_id']}"
            ),
            width=2
        )
        
        if photo_file_id:
            msg = await bot.send_photo(
                chat_id=DEPOSIT_GROUP,
                photo=photo_file_id,
                caption=caption,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
        else:
            msg = await bot.send_message(
                chat_id=DEPOSIT_GROUP,
                text=caption,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
        
        return msg.message_id
    except Exception as e:
        print(f"خطأ في إرسال للمجموعة: {e}")
        return None

@router.message(DepStates.waiting_tx)
async def process_tx(message: types.Message, state: FSMContext, bot: Bot, db_pool):
    if message.text == "🔙 رجوع للقائمة":
        await state.clear()
        await message.answer("تم إلغاء عملية الشحن.")
        return
    
    data = await state.get_data()
    tx = message.text.strip()
    
    if data['method'] == "m_syr" and len(tx) < 12:
        return await message.answer(
            "❌ **خطأ:** رقم عملية سيرياتل كاش يجب أن يكون 12 رقم على الأقل.\n"
            "📝 يرجى إدخال رقم صحيح:",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, username, balance, created_at) 
            VALUES ($1, $2, 0, CURRENT_TIMESTAMP) 
            ON CONFLICT (user_id) DO UPDATE SET username = $2
        ''', message.from_user.id, message.from_user.username)
        
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
        
        channel_data = {
            'user_id': message.from_user.id,
            'username': message.from_user.username or 'غير معروف',
            'display_amount': data['display_amount'],
            'amount_syp': data['amount_syp'],
            'method_name': data['method_name'],
        }
        
        group_msg_id = await send_to_group(bot, channel_data, tx)
        
        if group_msg_id:
            await conn.execute(
                "UPDATE deposit_requests SET group_message_id = $1 WHERE id = $2",
                group_msg_id, deposit_id
            )
    
    await message.answer(
        "✅ **تم إرسال طلب الشحن بنجاح!**\n\n"
        "⏳ **بانتظار موافقة الإدارة.**\n"
        "📋 **الوقت المتوقع 5 دقائق.**",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    await state.clear()

@router.message(DepStates.waiting_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext, bot: Bot, db_pool):
    data = await state.get_data()
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, username, balance, created_at) 
            VALUES ($1, $2, 0, CURRENT_TIMESTAMP) 
            ON CONFLICT (user_id) DO UPDATE SET username = $2
        ''', message.from_user.id, message.from_user.username)
        
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
        message.photo[-1].file_id
        )
        
        channel_data = {
            'user_id': message.from_user.id,
            'username': message.from_user.username or 'غير معروف',
            'display_amount': data['display_amount'],
            'amount_syp': data['amount_syp'],
            'method_name': data['method_name'],
        }
        
        group_msg_id = await send_to_group(bot, channel_data, photo_file_id=message.photo[-1].file_id)
        
        if group_msg_id:
            await conn.execute(
                "UPDATE deposit_requests SET group_message_id = $1 WHERE id = $2",
                group_msg_id, deposit_id
            )
    
    await message.answer(
        "✅ **تم إرسال لقطة الشاشة بنجاح!**\n\n"
        "⏳ **بانتظار موافقة الإدارة.**\n"
        "📋 **الوقت المتوقع 5 دقائق.**",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    await state.clear()
