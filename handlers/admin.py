# handlers/admin.py
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from config import ADMIN_ID, MODERATORS, DEPOSIT_GROUP, ORDERS_GROUP
import config
from datetime import datetime
import asyncio
import logging
import re
import random
import string

from handlers.time_utils import get_damascus_time_now
from handlers.keyboards import get_main_menu_keyboard, get_back_keyboard, get_cancel_keyboard

# إعداد logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

# ============= دوال مساعدة =============

def is_admin(user_id):
    """التحقق من صلاحيات المشرف"""
    return user_id == ADMIN_ID or user_id in MODERATORS

def format_message_text(text):
    """تحويل النص من Markdown إلى HTML"""
    if not text:
        return text
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    text = re.sub(r'__(.*?)__', r'<u>\1</u>', text)
    return text

async def safe_edit_message(message, text, reply_markup=None):
    """تعديل الرسالة بأمان مع معالجة الأخطاء"""
    try:
        if message.photo:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text=text, reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.error(f"خطأ في تعديل الرسالة: {e}")
        return False

# ============= حالات FSM =============

class AdminStates(StatesGroup):
    # الإعدادات العامة
    waiting_new_rate = State()
    waiting_maintenance_msg = State()
    waiting_new_syriatel_numbers = State()
    
    # إدارة المستخدمين
    waiting_user_id = State()
    waiting_balance_amount = State()
    waiting_user_info = State()
    waiting_points_amount = State()
    
    # إدارة النقاط
    waiting_points_settings = State()
    waiting_redeem_action = State()
    waiting_redeem_notes = State()
    
    # إدارة المنتجات
    waiting_product_name = State()
    waiting_product_price = State()
    waiting_product_min = State()
    waiting_product_profit = State()
    waiting_product_category = State()
    waiting_product_id = State()
    
    # إدارة الخيارات
    waiting_option_name = State()
    waiting_option_quantity = State()
    waiting_option_supplier_price = State()
    waiting_option_profit = State()
    waiting_option_description = State()
    waiting_edit_option_field = State()
    waiting_edit_option_value = State()
    
    # إدارة الألعاب الجديدة
    waiting_new_game_name = State()
    waiting_new_game_type = State()
    
    # إدارة المشرفين
    waiting_admin_id = State()
    waiting_admin_info = State()
    waiting_admin_remove = State()
    
    # إدارة VIP
    waiting_vip_user_id = State()
    waiting_vip_level = State()
    waiting_vip_discount = State()
    waiting_vip_downgrade_reason = State()
    
    # الرسائل
    waiting_broadcast_msg = State()
    waiting_custom_message_user = State()
    waiting_custom_message_text = State()
    
    # التصفير
    waiting_reset_rate = State()

    waiting_category_name = State()
    waiting_category_display_name = State()
    waiting_category_icon = State()
    waiting_category_sort = State()
    waiting_category_id = State()
    waiting_edit_category_field = State()
    waiting_edit_category_value = State()
# ============= معالج الإلغاء العام =============

@router.message(F.text.in_(["❌ إلغاء", "/cancel", "/الغاء", "/رجوع"]))
async def global_cancel_handler(message: types.Message, state: FSMContext, db_pool):
    """معالج الإلغاء الموحد"""
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    
    from database import is_admin_user
    is_admin_user_flag = await is_admin_user(db_pool, message.from_user.id)
    
    await message.answer(
        "✅ تم إلغاء العملية",
        reply_markup=get_main_menu_keyboard(is_admin_user_flag)
    )

# ============= لوحة التحكم الرئيسية =============

@router.message(Command("admin"))
async def admin_panel(message: types.Message, db_pool):
    """عرض لوحة تحكم الإدارة"""
    if not is_admin(message.from_user.id):
        return

    from database import get_bot_status
    bot_status = await get_bot_status(db_pool)
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"

    kb = [
        [types.InlineKeyboardButton(text="📈 سعر الصرف", callback_data="edit_rate"),
         types.InlineKeyboardButton(text="📊 الإحصائيات", callback_data="bot_stats")],
        
        [types.InlineKeyboardButton(text="📢 رسالة للكل", callback_data="broadcast"),
         types.InlineKeyboardButton(text="👤 معلومات مستخدم", callback_data="user_info")],
        
        
        [types.InlineKeyboardButton(text="⭐ إدارة النقاط", callback_data="manage_points")],
        
        [types.InlineKeyboardButton(text="💳 الأكثر إيداعاً", callback_data="top_deposits"),
         types.InlineKeyboardButton(text="🛒 الأكثر طلبات", callback_data="top_orders")],
        
        [types.InlineKeyboardButton(text="🔗 الأكثر إحالة", callback_data="top_referrals"),
         types.InlineKeyboardButton(text="⭐ الأكثر نقاط", callback_data="top_points")],
        
        [types.InlineKeyboardButton(text="👥 إحصائيات VIP", callback_data="vip_stats"),
         types.InlineKeyboardButton(text="📊 تقارير ونسخ احتياطي", callback_data="reports_menu")],
        
        [types.InlineKeyboardButton(text="➕ إضافة منتج", callback_data="add_product"),
         types.InlineKeyboardButton(text="✏️ تعديل منتج", callback_data="edit_product")],
        
        [types.InlineKeyboardButton(text="🗑️ حذف منتج", callback_data="delete_product"),
         types.InlineKeyboardButton(text="📱 عرض المنتجات", callback_data="list_products")],
        
        [types.InlineKeyboardButton(text="📞 أرقام سيرياتل", callback_data="edit_syriatel"),
         types.InlineKeyboardButton(text="🔄 تشغيل/إيقاف", callback_data="toggle_bot")],
        
        [types.InlineKeyboardButton(text="⚠️ تصفير البوت", callback_data="reset_bot"),
         types.InlineKeyboardButton(text="👑 إدارة المشرفين", callback_data="manage_admins")],
        
        [types.InlineKeyboardButton(text="✏️ رسالة الصيانة", callback_data="edit_maintenance"),
         types.InlineKeyboardButton(text="✉️ رسالة لمستخدم", callback_data="send_custom_message")],
        
        [types.InlineKeyboardButton(text="🔄 تفعيل/إيقاف التطبيقات", callback_data="manage_apps_status"),
         types.InlineKeyboardButton(text="🎮 إدارة خيارات الألعاب", callback_data="manage_options")],

        [types.InlineKeyboardButton(text="📁 إدارة الأقسام", callback_data="manage_categories"),
         types.InlineKeyboardButton(text="➕ إضافة قسم", callback_data="add_category")],
    ]
    
    await message.answer(
        f"🛠 **لوحة تحكم الإدارة**\n\n"
        f"حالة البوت: {status_text}\n\n"
        f"🔸 **اختر الإجراء المطلوب:**",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

# ============= العودة للوحة التحكم =============

@router.callback_query(F.data == "back_to_admin")
@router.callback_query(F.data == "back_to_admin_panel")
async def back_to_admin_panel(callback: types.CallbackQuery, db_pool):
    """العودة للوحة التحكم الرئيسية"""
    from database import get_bot_status
    
    bot_status = await get_bot_status(db_pool)
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"
    
    await admin_panel(callback.message, db_pool)

# ============= تشغيل/إيقاف البوت =============

@router.callback_query(F.data == "toggle_bot")
async def toggle_bot(callback: types.CallbackQuery, db_pool):
    """تشغيل أو إيقاف البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_bot_status, set_bot_status
    
    current_status = await get_bot_status(db_pool)
    new_status = not current_status
    
    await set_bot_status(db_pool, new_status)
    
    from handlers.middleware import refresh_bot_status_cache
    await refresh_bot_status_cache(db_pool)
    
    status_text = "🟢 يعمل" if new_status else "🔴 متوقف"
    action_text = "تشغيل" if new_status else "إيقاف"
    
    await callback.message.edit_text(
        f"✅ تم {action_text} البوت بنجاح\n\n"
        f"الحالة الآن: {status_text}\n\n"
        f"{'⚠️ البوت متوقف عن العمل للمستخدمين العاديين' if not new_status else '✅ البوت يعمل بشكل طبيعي'}"
    )
    
    # إرسال إشعار للمشرفين
    admin_ids = [ADMIN_ID] + MODERATORS
    for admin_id in admin_ids:
        if admin_id and admin_id != callback.from_user.id:
            try:
                await callback.bot.send_message(
                    admin_id,
                    f"ℹ️ تم {action_text} البوت بواسطة @{callback.from_user.username or 'مشرف'}"
                )
            except:
                pass

# ============= رسالة الصيانة =============

@router.callback_query(F.data == "edit_maintenance")
async def edit_maintenance_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تعديل رسالة الصيانة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.answer(
        "📝 أرسل رسالة الصيانة الجديدة:\n\n"
        "(هذه الرسالة ستظهر للمستخدمين عند إيقاف البوت)\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_maintenance_msg)

@router.message(AdminStates.waiting_maintenance_msg)
async def save_maintenance_message(message: types.Message, state: FSMContext, db_pool):
    """حفظ رسالة الصيانة الجديدة"""
    if not is_admin(message.from_user.id):
        return
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE bot_settings SET value = $1, updated_at = CURRENT_TIMESTAMP WHERE key = 'maintenance_message'",
            message.text
        )
    
    await message.answer("✅ تم تحديث رسالة الصيانة بنجاح")
    await state.clear()

# ============= إدارة أرقام سيرياتل =============

@router.callback_query(F.data == "edit_syriatel")
async def edit_syriatel_start(callback: types.CallbackQuery, state: FSMContext):
    """تعديل أرقام سيرياتل كاش"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from config import SYRIATEL_NUMS
    current_nums = "\n".join([f"{i+1}. `{num}`" for i, num in enumerate(SYRIATEL_NUMS)])
    
    text = (
        f"📞 **أرقام سيرياتل كاش الحالية:**\n\n"
        f"{current_nums}\n\n"
        f"**أدخل الأرقام الجديدة** (كل رقم في سطر منفصل):\n"
        f"مثال:\n"
        f"74091109\n"
        f"63826779\n"
        f"0912345678\n\n"
        f"أو أرسل /cancel للإلغاء"
    )
    
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=get_cancel_keyboard())
    await state.set_state(AdminStates.waiting_new_syriatel_numbers)

@router.message(AdminStates.waiting_new_syriatel_numbers)
async def save_syriatel_numbers(message: types.Message, state: FSMContext, db_pool):
    """حفظ أرقام سيرياتل الجديدة"""
    if not is_admin(message.from_user.id):
        return
    
    numbers = [line.strip() for line in message.text.split('\n') if line.strip()]
    
    from database import set_syriatel_numbers
    success = await set_syriatel_numbers(db_pool, numbers)
    
    if success:
        import config
        config.SYRIATEL_NUMS = numbers
        
        text = "✅ **تم تحديث أرقام سيرياتل كاش بنجاح!**\n\nالأرقام الجديدة:\n"
        for i, num in enumerate(numbers, 1):
            text += f"{i}. `{num}`\n"
    else:
        text = "❌ **فشل تحديث الأرقام**"
    
    await message.answer(text, parse_mode="Markdown")
    await state.clear()

# ============= إرسال رسالة لمستخدم محدد =============

@router.callback_query(F.data == "send_custom_message")
async def send_custom_message_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء إرسال رسالة لمستخدم محدد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.answer(
        "✉️ **إرسال رسالة لمستخدم محدد**\n\n"
        "أدخل آيدي المستخدم (ID) أو اليوزر نيم:\n"
        "مثال: `123456789` أو `@username`\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_custom_message_user)

@router.message(AdminStates.waiting_custom_message_user)
async def get_custom_message_user(message: types.Message, state: FSMContext, db_pool):
    """استقبال آيدي المستخدم"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    search_term = message.text.strip()
    
    async with db_pool.acquire() as conn:
        try:
            user_id = int(search_term)
            user = await conn.fetchrow(
                "SELECT user_id, username, first_name FROM users WHERE user_id = $1",
                user_id
            )
        except ValueError:
            username = search_term.replace('@', '')
            user = await conn.fetchrow(
                "SELECT user_id, username, first_name FROM users WHERE username = $1",
                username
            )
    
    if not user:
        await message.answer(
            "❌ **المستخدم غير موجود**\n\n"
            "تأكد من الآيدي أو اليوزر نيم وحاول مرة أخرى.\n"
            "أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(
        target_user=user['user_id'],
        target_username=user['username'] or user['first_name'] or str(user['user_id'])
    )
    
    await message.answer(
        f"👤 **المستخدم المستهدف:** @{user['username'] or 'غير معروف'}\n"
        f"🆔 **الآيدي:** `{user['user_id']}`\n\n"
        f"📝 **أدخل الرسالة التي تريد إرسالها:**\n\n"
        f"✏️ يمكنك استخدام Markdown للتنسيق:\n"
        f"• **نص عريض**\n"
        f"• *نص مائل*\n"
        f"• `كود`\n\n"
        f"أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_custom_message_text)

@router.message(AdminStates.waiting_custom_message_text)
async def send_custom_message_text(message: types.Message, state: FSMContext, bot: Bot):
    """إرسال الرسالة للمستخدم المحدد"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    custom_text = message.text
    data = await state.get_data()
    target_user = data['target_user']
    target_username = data['target_username']
    
    try:
        await bot.send_message(
            target_user,
            f"✉️ **رسالة خاصة من الإدارة**\n\n{custom_text}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await message.answer(
            f"✅ **تم إرسال الرسالة بنجاح!**\n\n"
            f"👤 إلى: @{target_username}\n"
            f"🆔 الآيدي: `{target_user}`\n\n"
            f"📝 نص الرسالة:\n{custom_text}"
        )
        
    except Exception as e:
        try:
            await bot.send_message(
                target_user,
                f"✉️ رسالة خاصة من الإدارة:\n\n{custom_text}"
            )
            
            await message.answer(
                f"✅ **تم إرسال الرسالة (كنص عادي) بنجاح!**\n\n"
                f"👤 إلى: @{target_username}\n"
                f"🆔 الآيدي: `{target_user}`\n\n"
                f"📝 نص الرسالة:\n{custom_text}"
            )
            
        except Exception as e2:
            await message.answer(
                f"❌ **فشل إرسال الرسالة**\n\n"
                f"الخطأ: {str(e2)}\n\n"
                f"تأكد من أن المستخدم لم يحظر البوت."
            )
    
    await state.clear()

# ============= إدارة المنتجات =============

@router.callback_query(F.data == "add_product")
async def add_product_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إضافة منتج جديد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT id, display_name FROM categories ORDER BY sort_order")
    
    if not categories:
        await callback.answer("❌ لا توجد أقسام. أضف قسماً أولاً.", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(types.InlineKeyboardButton(
            text=cat['display_name'],
            callback_data=f"sel_cat_{cat['id']}"
        ))
    
    await callback.message.answer(
        "📱 **إضافة منتج جديد**\n\n"
        "اختر القسم أولاً:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AdminStates.waiting_product_category)

@router.callback_query(F.data.startswith("sel_cat_"))
async def select_category_for_product(callback: types.CallbackQuery, state: FSMContext):
    """اختيار القسم للمنتج"""
    cat_id = int(callback.data.split("_")[2])
    await state.update_data(category_id=cat_id)
    
    await callback.message.edit_text(
        "📝 **أدخل اسم المنتج:**"
    )
    await state.set_state(AdminStates.waiting_product_name)

@router.message(AdminStates.waiting_product_name)
async def get_product_name(message: types.Message, state: FSMContext):
    """استلام اسم المنتج"""
    await state.update_data(product_name=message.text)
    await message.answer(
        "💰 **أدخل سعر الوحدة بالدولار:**\n"
        "مثال: 0.001\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_product_price)

@router.message(AdminStates.waiting_product_price)
async def get_product_price(message: types.Message, state: FSMContext):
    """استلام سعر المنتج"""
    try:
        price = float(message.text)
        await state.update_data(product_price=price)
        await message.answer(
            "📦 **أدخل الحد الأدنى للكمية:**\n"
            "مثال: 100\n\n"
            "أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(AdminStates.waiting_product_min)
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 0.001):", reply_markup=get_cancel_keyboard())

@router.message(AdminStates.waiting_product_min)
async def get_product_min(message: types.Message, state: FSMContext):
    """استلام الحد الأدنى"""
    try:
        min_units = int(message.text)
        
        if min_units <= 0:
            return await message.answer("⚠️ الحد الأدنى يجب أن يكون أكبر من 0:", reply_markup=get_cancel_keyboard())
        
        await state.update_data(product_min=min_units)
        await message.answer(
            "📈 **أدخل نسبة الربح (%):**\n"
            "مثال: 10\n\n"
            "أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(AdminStates.waiting_product_profit)
        
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 100):", reply_markup=get_cancel_keyboard())

@router.message(AdminStates.waiting_product_profit)
async def get_product_profit(message: types.Message, state: FSMContext, db_pool):
    """استلام نسبة الربح وحفظ المنتج"""
    try:
        profit = float(message.text)
        
        data = await state.get_data()
        
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, category_id, type)
                VALUES ($1, $2, $3, $4, $5, 'service')
            ''', 
            data['product_name'],
            data['product_price'],
            data['product_min'],
            profit,
            data['category_id']
            )
        
        await message.answer(
            f"✅ **تم إضافة المنتج بنجاح!**\n\n"
            f"📱 الاسم: {data['product_name']}\n"
            f"💰 السعر: ${data['product_price']}\n"
            f"📦 الحد الأدنى: {data['product_min']}\n"
            f"📈 الربح: {profit}%"
        )
        await state.clear()
        
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 10):", reply_markup=get_cancel_keyboard())
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

@router.callback_query(F.data == "edit_product")
async def edit_product_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المنتجات للتعديل"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.id, a.name, c.display_name 
            FROM applications a
            LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    if not products:
        await callback.answer("❌ لا توجد منتجات", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(types.InlineKeyboardButton(
            text=f"{p['name']} ({p['display_name']})",
            callback_data=f"edit_prod_{p['id']}"
        ))
    
    await callback.message.edit_text(
        "✏️ **اختر المنتج للتعديل:**",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("edit_prod_"))
async def edit_product_form(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض نموذج تعديل المنتج"""
    prod_id = int(callback.data.split("_")[2])
    
    async with db_pool.acquire() as conn:
        product = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", prod_id)
    
    if not product:
        await callback.answer("❌ المنتج غير موجود", show_alert=True)
        return
    
    await state.update_data(product_id=prod_id)
    
    text = (
        f"✏️ **تعديل المنتج:** {product['name']}\n\n"
        f"السعر الحالي: ${product['unit_price_usd']}\n"
        f"الحد الأدنى: {product['min_units']}\n"
        f"الربح: {product['profit_percentage']}%\n\n"
        f"📝 أرسل البيانات الجديدة بالصيغة:\n"
        f"`الاسم|السعر|الحد_الأدنى|الربح`\n\n"
        f"مثال: `اسم جديد|0.002|200|15`\n\n"
        f"أو أرسل /cancel للإلغاء"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_product_id)

@router.message(AdminStates.waiting_product_id)
async def update_product(message: types.Message, state: FSMContext, db_pool):
    """تحديث بيانات المنتج"""
    try:
        parts = message.text.split('|')
        if len(parts) != 4:
            return await message.answer("❌ صيغة غير صحيحة. استخدم: `الاسم|السعر|الحد_الأدنى|الربح`")
        
        name, price, min_units, profit = [p.strip() for p in parts]
        
        data = await state.get_data()
        prod_id = data['product_id']
        
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE applications 
                SET name = $1, unit_price_usd = $2, min_units = $3, profit_percentage = $4
                WHERE id = $5
            ''', name, float(price), int(min_units), float(profit), prod_id)
        
        await message.answer(f"✅ **تم تحديث المنتج بنجاح!**")
        await state.clear()
        
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

@router.callback_query(F.data == "delete_product")
async def delete_product_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المنتجات للحذف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.id, a.name, c.display_name 
            FROM applications a
            LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    if not products:
        await callback.answer("❌ لا توجد منتجات", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(types.InlineKeyboardButton(
            text=f"🗑️ {p['name']} ({p['display_name']})",
            callback_data=f"del_prod_{p['id']}"
        ))
    
    await callback.message.edit_text(
        "🗑️ **اختر المنتج للحذف:**",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("del_prod_"))
async def confirm_delete_product(callback: types.CallbackQuery, db_pool):
    """تأكيد حذف المنتج"""
    prod_id = int(callback.data.split("_")[2])
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم", callback_data=f"conf_del_{prod_id}"),
        types.InlineKeyboardButton(text="❌ لا", callback_data="cancel_del")
    )
    
    await callback.message.edit_text(
        "⚠️ **هل أنت متأكد من حذف هذا المنتج؟**",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("conf_del_"))
async def execute_delete_product(callback: types.CallbackQuery, db_pool):
    """تنفيذ حذف المنتج"""
    prod_id = int(callback.data.split("_")[2])
    
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM applications WHERE id = $1", prod_id)
    
    await callback.message.edit_text("✅ **تم حذف المنتج بنجاح!**")

@router.callback_query(F.data == "list_products")
async def list_products(callback: types.CallbackQuery, db_pool):
    """عرض جميع المنتجات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.*, c.display_name 
            FROM applications a
            LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    if not products:
        await callback.answer("❌ لا توجد منتجات", show_alert=True)
        return
    
    text = "📱 **قائمة المنتجات**\n\n"
    for p in products:
        text += (
            f"**{p['name']}**\n"
            f"• القسم: {p['display_name']}\n"
            f"• السعر: ${p['unit_price_usd']}\n"
            f"• الحد الأدنى: {p['min_units']}\n"
            f"• الربح: {p['profit_percentage']}%\n"
            f"• النوع: {p['type']}\n"
            f"• الحالة: {'✅ نشط' if p['is_active'] else '❌ غير نشط'}\n\n"
        )
    
    await callback.message.edit_text(text, parse_mode="Markdown")

# ============= إدارة الأقسام =============

@router.callback_query(F.data == "manage_categories")
async def manage_categories_menu(callback: types.CallbackQuery, db_pool):
    """عرض قائمة الأقسام"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    
    text = "📁 **إدارة الأقسام**\n\n"
    
    if not categories:
        text += "⚠️ لا توجد أقسام حالياً."
    else:
        for cat in categories:
            text += f"{cat['icon']} **{cat['display_name']}**\n"
            text += f"   🆔: {cat['id']} | ترتيب: {cat['sort_order']}\n"
            text += f"   الاسم الداخلي: `{cat['name']}`\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة قسم جديد", callback_data="add_category"))
    builder.row(types.InlineKeyboardButton(text="✏️ تعديل قسم", callback_data="edit_category"))
    builder.row(types.InlineKeyboardButton(text="🗑️ حذف قسم", callback_data="delete_category"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "add_category")
async def add_category_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء إضافة قسم جديد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text(
        "➕ **إضافة قسم جديد - الخطوة 1/4**\n\n"
        "📝 **أدخل الاسم الداخلي للقسم:**\n"
        "(يستخدم في البرمجة، بدون مسافات)\n"
        "مثال: `games`\n"
        "مثال: `chat_apps`\n\n"
        "❌ أرسل /cancel للإلغاء"
    )
    await state.set_state(AdminStates.waiting_category_name)

@router.message(AdminStates.waiting_category_name)
async def add_category_step_name(message: types.Message, state: FSMContext):
    """استلام الاسم الداخلي للقسم"""
    if not is_admin(message.from_user.id):
        return
    
    name = message.text.strip()
    if not name or ' ' in name:
        await message.answer(
            "❌ الاسم يجب أن يكون بدون مسافات. استخدم شرطة سفلية `_` بدلاً من المسافة.\n"
            "مثال: `games` أو `chat_apps`\n\n"
            "أدخل اسم داخلي صحيح:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(category_name=name)
    
    await message.answer(
        "➕ **إضافة قسم جديد - الخطوة 2/4**\n\n"
        "📝 **أدخل الاسم المعروض للقسم:**\n"
        "(الاسم الذي سيظهر للمستخدمين)\n"
        f"الاسم الداخلي: **{name}**\n\n"
        "مثال: `🎮 ألعاب`\n"
        "مثال: `💬 تطبيقات دردشة`\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_category_display_name)

@router.message(AdminStates.waiting_category_display_name)
async def add_category_step_display_name(message: types.Message, state: FSMContext):
    """استلام الاسم المعروض للقسم"""
    if not is_admin(message.from_user.id):
        return
    
    display_name = message.text.strip()
    if len(display_name) < 2:
        await message.answer("❌ الاسم المعروض قصير جداً. أدخل اسم أطول:", reply_markup=get_cancel_keyboard())
        return
    
    await state.update_data(category_display_name=display_name)
    
    await message.answer(
        "➕ **إضافة قسم جديد - الخطوة 3/4**\n\n"
        "🎨 **أدخل الأيقونة للقسم:**\n"
        f"الاسم الداخلي: **{await get_state_data_field(state, 'category_name')}**\n"
        f"الاسم المعروض: **{display_name}**\n\n"
        "مثال: `🎮` للألعاب\n"
        "مثال: `💬` للدردشة\n"
        "أو اتركه فارغاً للايقونة الافتراضية `📁`\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_category_icon)

async def get_state_data_field(state, field):
    """دالة مساعدة لجلب بيانات من state"""
    data = await state.get_data()
    return data.get(field, '')

@router.message(AdminStates.waiting_category_icon)
async def add_category_step_icon(message: types.Message, state: FSMContext):
    """استلام الأيقونة للقسم"""
    if not is_admin(message.from_user.id):
        return
    
    icon = message.text.strip() if message.text and message.text != "-" else "📁"
    
    await state.update_data(category_icon=icon)
    
    await message.answer(
        "➕ **إضافة قسم جديد - الخطوة 4/4**\n\n"
        "🔢 **أدخل ترتيب القسم (رقم):**\n"
        "الأقسام تظهر حسب الترتيب تصاعدياً\n"
        "مثال: `1` (يظهر أولاً)\n"
        "مثال: `5` (يظهر خامساً)\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_category_sort)

@router.message(AdminStates.waiting_category_sort)
async def add_category_step_sort(message: types.Message, state: FSMContext, db_pool):
    """استلام ترتيب القسم وحفظه"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        sort_order = int(message.text.strip())
    except ValueError:
        await message.answer("❌ يرجى إدخال رقم صحيح للترتيب:", reply_markup=get_cancel_keyboard())
        return
    
    data = await state.get_data()
    name = data['category_name']
    display_name = data['category_display_name']
    icon = data.get('category_icon', '📁')
    
    async with db_pool.acquire() as conn:
        # التحقق من عدم وجود اسم مكرر
        existing = await conn.fetchval("SELECT id FROM categories WHERE name = $1", name)
        if existing:
            await message.answer(
                f"❌ قسم باسم **{name}** موجود مسبقاً.\n"
                "الرجاء استخدام اسم داخلي مختلف.",
                reply_markup=get_cancel_keyboard()
            )
            await state.clear()
            return
        
        await conn.execute('''
            INSERT INTO categories (name, display_name, icon, sort_order)
            VALUES ($1, $2, $3, $4)
        ''', name, display_name, icon, sort_order)
    
    await message.answer(
        f"✅ **تم إضافة القسم بنجاح!**\n\n"
        f"• الاسم الداخلي: `{name}`\n"
        f"• الاسم المعروض: {display_name}\n"
        f"• الأيقونة: {icon}\n"
        f"• الترتيب: {sort_order}"
    )
    await state.clear()

# ============= إدارة الأقسام - تعديل وحذف =============

@router.callback_query(F.data == "edit_category")
async def edit_category_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة الأقسام للتعديل"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    
    if not categories:
        await callback.answer("❌ لا توجد أقسام", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(types.InlineKeyboardButton(
            text=f"✏️ {cat['icon']} {cat['display_name']}",
            callback_data=f"edit_cat_{cat['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_categories"))
    
    await callback.message.edit_text(
        "✏️ **اختر القسم للتعديل:**",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# ===== دوال التعديل (الأكثر تحديداً أولاً) =====

@router.callback_query(F.data.startswith("edit_cat_display_"))
async def edit_category_display_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تعديل الاسم المعروض"""
    try:
        cat_id = int(callback.data.split("_")[3])
        await state.update_data(edit_field='display_name', category_id=cat_id)
        
        await callback.message.answer(
            "📝 **أدخل الاسم المعروض الجديد:**\n\n"
            "مثال: `🎮 ألعاب جديدة`\n"
            "مثال: `💬 تطبيقات دردشة`\n\n"
            "أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(AdminStates.waiting_edit_category_value)
        await callback.answer()
    except Exception as e:
        logger.error(f"خطأ في edit_category_display_start: {e}")
        await callback.answer("❌ حدث خطأ", show_alert=True)

@router.callback_query(F.data.startswith("edit_cat_icon_"))
async def edit_category_icon_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تعديل الأيقونة"""
    try:
        cat_id = int(callback.data.split("_")[3])
        await state.update_data(edit_field='icon', category_id=cat_id)
        
        await callback.message.answer(
            "🎨 **أدخل الأيقونة الجديدة:**\n\n"
            "مثال: `🎮`\n"
            "مثال: `💬`\n"
            "مثال: `📱`\n"
            "مثال: `🎯`\n\n"
            "أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(AdminStates.waiting_edit_category_value)
        await callback.answer()
    except Exception as e:
        logger.error(f"خطأ في edit_category_icon_start: {e}")
        await callback.answer("❌ حدث خطأ", show_alert=True)

@router.callback_query(F.data.startswith("edit_cat_sort_"))
async def edit_category_sort_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تعديل الترتيب"""
    try:
        cat_id = int(callback.data.split("_")[3])
        await state.update_data(edit_field='sort_order', category_id=cat_id)
        
        await callback.message.answer(
            "🔢 **أدخل الترتيب الجديد (رقم):**\n\n"
            "مثال: `1` (يظهر أولاً)\n"
            "مثال: `5` (يظهر خامساً)\n\n"
            "📌 الأرقام الأصغر تظهر أولاً\n\n"
            "أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(AdminStates.waiting_edit_category_value)
        await callback.answer()
    except Exception as e:
        logger.error(f"خطأ في edit_category_sort_start: {e}")
        await callback.answer("❌ حدث خطأ", show_alert=True)

@router.callback_query(F.data.startswith("edit_cat_"))
async def edit_category_menu(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض قائمة تعديل القسم (للأقل تحديداً)"""
    try:
        # التأكد أن هذا ليس نمط edit_cat_display_ وغيرها
        parts = callback.data.split("_")
        if len(parts) > 3:  # إذا كان edit_cat_display_123 أو edit_cat_icon_123
            return  # نتركها للدوال المحددة أعلاه
        
        cat_id = int(parts[2])
        
        async with db_pool.acquire() as conn:
            category = await conn.fetchrow("SELECT * FROM categories WHERE id = $1", cat_id)
        
        if not category:
            await callback.answer("❌ القسم غير موجود", show_alert=True)
            return
        
        await state.update_data(category_id=cat_id)
        
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(
            text=f"📝 تعديل الاسم المعروض (الحالي: {category['display_name']})", 
            callback_data=f"edit_cat_display_{cat_id}"
        ))
        builder.row(types.InlineKeyboardButton(
            text=f"🎨 تعديل الأيقونة (الحالية: {category['icon']})", 
            callback_data=f"edit_cat_icon_{cat_id}"
        ))
        builder.row(types.InlineKeyboardButton(
            text=f"🔢 تعديل الترتيب (الحالي: {category['sort_order']})", 
            callback_data=f"edit_cat_sort_{cat_id}"
        ))
        builder.row(types.InlineKeyboardButton(
            text="🔙 رجوع", 
            callback_data="edit_category"
        ))
        
        text = (
            f"✏️ **تعديل القسم**\n\n"
            f"**البيانات الحالية:**\n"
            f"• الاسم الداخلي: `{category['name']}`\n"
            f"• الاسم المعروض: {category['display_name']}\n"
            f"• الأيقونة: {category['icon']}\n"
            f"• الترتيب: {category['sort_order']}\n\n"
            f"اختر ما تريد تعديله:"
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"خطأ في edit_category_menu: {e}")
        await callback.answer("❌ حدث خطأ", show_alert=True)

@router.message(AdminStates.waiting_edit_category_value)
async def edit_category_save(message: types.Message, state: FSMContext, db_pool):
    """حفظ التعديل على القسم"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    data = await state.get_data()
    if not data or 'category_id' not in data or 'edit_field' not in data:
        await state.clear()
        await message.answer("❌ انتهت صلاحية الجلسة. ابدأ من جديد.")
        return
    
    cat_id = data['category_id']
    field = data['edit_field']
    value = message.text.strip()
    
    try:
        # التحقق من صحة المدخلات
        if field == 'display_name':
            if len(value) < 2:
                await message.answer("❌ الاسم قصير جداً. أدخل اسم أطول (حرفين على الأقل):", 
                                    reply_markup=get_cancel_keyboard())
                return
            if len(value) > 50:
                await message.answer("❌ الاسم طويل جداً. الحد الأقصى 50 حرف:", 
                                    reply_markup=get_cancel_keyboard())
                return
            update_value = value
            field_name = "الاسم المعروض"
            
        elif field == 'icon':
            if len(value) > 10:
                await message.answer("❌ الأيقونة طويلة جداً. استخدم رمز واحد أو رمزين:", 
                                    reply_markup=get_cancel_keyboard())
                return
            update_value = value if value else "📁"
            field_name = "الأيقونة"
            
        elif field == 'sort_order':
            try:
                sort_val = int(value)
                if sort_val < 0 or sort_val > 999:
                    await message.answer("❌ الرقم خارج النطاق المسموح (0-999):", 
                                        reply_markup=get_cancel_keyboard())
                    return
                update_value = sort_val
                field_name = "الترتيب"
            except ValueError:
                await message.answer("❌ يرجى إدخال رقم صحيح:", 
                                    reply_markup=get_cancel_keyboard())
                return
        
        else:
            await message.answer("❌ حقل غير معروف")
            await state.clear()
            return
        
        # تنفيذ التحديث في قاعدة البيانات
        async with db_pool.acquire() as conn:
            # التحقق من وجود القسم
            category_check = await conn.fetchval("SELECT id FROM categories WHERE id = $1", cat_id)
            if not category_check:
                await message.answer("❌ القسم غير موجود!")
                await state.clear()
                return
            
            # تنفيذ التحديث
            await conn.execute(
                f"UPDATE categories SET {field} = $1 WHERE id = $2",
                update_value, cat_id
            )
            
            # جلب البيانات المحدثة
            category = await conn.fetchrow(
                "SELECT * FROM categories WHERE id = $1",
                cat_id
            )
        
        await message.answer(
            f"✅ **تم التحديث بنجاح!**\n\n"
            f"• {field_name} تم تحديثه إلى: **{update_value}**\n"
            f"• القسم: {category['icon']} {category['display_name']}"
        )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"خطأ في تعديل القسم: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# ===== دوال الحذف =====

@router.callback_query(F.data == "delete_category")
async def delete_category_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة الأقسام للحذف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    
    if not categories:
        await callback.answer("❌ لا توجد أقسام", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        # منع حذف القسم الافتراضي إذا كان موجوداً
        if cat['name'] == 'chat_apps':
            text = f"🔒 {cat['icon']} {cat['display_name']} (افتراضي)"
            callback_data = "cannot_delete_default"
        else:
            text = f"🗑️ {cat['icon']} {cat['display_name']}"
            callback_data = f"del_cat_{cat['id']}"
        
        builder.row(types.InlineKeyboardButton(text=text, callback_data=callback_data))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_categories"))
    
    await callback.message.edit_text(
        "🗑️ **اختر القسم للحذف:**\n\n"
        "⚠️ تحذير: حذف القسم سيؤدي إلى حذف جميع المنتجات المرتبطة به!\n"
        "🔒 الأقسام المقفلة لا يمكن حذفها.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "cannot_delete_default")
async def cannot_delete_default(callback: types.CallbackQuery):
    """منع حذف القسم الافتراضي"""
    await callback.answer("❌ لا يمكن حذف القسم الافتراضي", show_alert=True)

@router.callback_query(F.data.startswith("del_cat_"))
async def delete_category_confirm(callback: types.CallbackQuery, db_pool):
    """تأكيد حذف القسم"""
    try:
        cat_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            category = await conn.fetchrow("SELECT * FROM categories WHERE id = $1", cat_id)
            
            if not category:
                await callback.answer("❌ القسم غير موجود", show_alert=True)
                return
            
            # التحقق من وجود منتجات في هذا القسم
            products_count = await conn.fetchval(
                "SELECT COUNT(*) FROM applications WHERE category_id = $1",
                cat_id
            )
            
            # جلب أسماء المنتجات (للإظهار)
            products = []
            if products_count > 0:
                products = await conn.fetch(
                    "SELECT name FROM applications WHERE category_id = $1 LIMIT 5",
                    cat_id
                )
        
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ نعم، احذف نهائياً", callback_data=f"confirm_del_cat_{cat_id}"),
            types.InlineKeyboardButton(text="❌ لا، تراجع", callback_data="delete_category")
        )
        
        # بناء رسالة التحذير
        warning = ""
        products_list = ""
        if products_count > 0:
            warning = f"\n\n⚠️ **تحذير شديد:** هذا القسم يحتوي على **{products_count} منتج**!"
            if products:
                products_list = "\n\nمنتجات ستُحذف:\n"
                for p in products:
                    products_list += f"• {p['name']}\n"
                if products_count > 5:
                    products_list += f"• ... و{products_count - 5} منتجات أخرى"
        
        await callback.message.edit_text(
            f"⚠️ **تأكيد حذف القسم**\n\n"
            f"هل أنت متأكد من حذف هذا القسم نهائياً؟\n\n"
            f"• **القسم:** {category['icon']} {category['display_name']}\n"
            f"• **المعرف:** {cat_id}"
            f"{warning}"
            f"{products_list}\n\n"
            f"**هذا الإجراء لا يمكن التراجع عنه!**",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"خطأ في delete_category_confirm: {e}")
        await callback.answer("❌ حدث خطأ", show_alert=True)

@router.callback_query(F.data.startswith("confirm_del_cat_"))
async def delete_category_execute(callback: types.CallbackQuery, db_pool):
    """تنفيذ حذف القسم"""
    try:
        cat_id = int(callback.data.split("_")[3])
        
        async with db_pool.acquire() as conn:
            async with conn.transaction():  # استخدام transaction لضمان التكامل
                # جلب معلومات القسم للتأكيد
                category = await conn.fetchrow(
                    "SELECT * FROM categories WHERE id = $1",
                    cat_id
                )
                
                if not category:
                    await callback.answer("❌ القسم غير موجود", show_alert=True)
                    return
                
                # منع حذف القسم الافتراضي
                if category['name'] == 'chat_apps':
                    await callback.answer("❌ لا يمكن حذف القسم الافتراضي", show_alert=True)
                    return
                
                # حذف جميع المنتجات المرتبطة أولاً (لضمان تنظيف كامل)
                await conn.execute(
                    "DELETE FROM applications WHERE category_id = $1",
                    cat_id
                )
                
                # حذف القسم
                await conn.execute(
                    "DELETE FROM categories WHERE id = $1",
                    cat_id
                )
        
        await callback.answer(f"✅ تم حذف القسم {category['display_name']} وجميع منتجاته بنجاح")
        
        # العودة لقائمة الأقسام
        await delete_category_list(callback, db_pool)
        
    except Exception as e:
        logger.error(f"خطأ في delete_category_execute: {e}")
        await callback.answer(f"❌ حدث خطأ: {str(e)}", show_alert=True)

# ============= إدارة حالة التطبيقات =============

@router.callback_query(F.data == "manage_apps_status")
async def manage_apps_status_menu(callback: types.CallbackQuery, db_pool):
    """قائمة إدارة حالة التطبيقات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    
    builder = InlineKeyboardBuilder()
    
    for cat in categories:
        builder.row(types.InlineKeyboardButton(
            text=f"{cat['icon']} {cat['display_name']}",
            callback_data=f"app_status_cat_{cat['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data="back_to_admin"
    ))
    
    await callback.message.edit_text(
        "📱 **إدارة حالة التطبيقات**\n\n"
        "اختر القسم لعرض التطبيقات والتحكم بحالتها:\n"
        "• ✅ نشط\n"
        "• ❌ غير نشط",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("app_status_cat_"))
async def show_apps_for_status(callback: types.CallbackQuery, db_pool):
    """عرض تطبيقات قسم معين للتحكم بحالتها"""
    cat_id = int(callback.data.split("_")[3])
    
    async with db_pool.acquire() as conn:
        category = await conn.fetchrow("SELECT * FROM categories WHERE id = $1", cat_id)
        apps = await conn.fetch('''
            SELECT * FROM applications 
            WHERE category_id = $1 
            ORDER BY is_active DESC, name
        ''', cat_id)
    
    if not apps:
        return await callback.answer("لا توجد تطبيقات في هذا القسم", show_alert=True)
    
    text = f"{category['icon']} **{category['display_name']}**\n\nاختر التطبيق لتغيير حالته:\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for app in apps:
        status_icon = "✅" if app['is_active'] else "❌"
        button_text = f"{status_icon} {app['name']}"
        builder.row(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"toggle_app_{app['id']}_{'1' if app['is_active'] else '0'}"
        ))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للأقسام", callback_data="manage_apps_status"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("toggle_app_"))
async def toggle_app_status(callback: types.CallbackQuery, db_pool):
    """تغيير حالة التطبيق"""
    parts = callback.data.split("_")
    app_id = int(parts[2])
    current_status = bool(int(parts[3]))
    new_status = not current_status
    
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE applications SET is_active = $1 WHERE id = $2", new_status, app_id)
        app = await conn.fetchrow("SELECT name FROM applications WHERE id = $1", app_id)
    
    status_text = "✅ مفعل" if new_status else "❌ معطل"
    await callback.answer(f"تم تغيير حالة {app['name']} إلى {status_text}")
    
    # العودة لقائمة التطبيقات
    async with db_pool.acquire() as conn:
        app_info = await conn.fetchrow("SELECT category_id FROM applications WHERE id = $1", app_id)
    
    await show_apps_for_status(
        types.CallbackQuery(
            id=callback.id,
            from_user=callback.from_user,
            chat_instance="dummy",
            message=callback.message,
            data=f"app_status_cat_{app_info['category_id']}"
        ), 
        db_pool
    )

# ============= إدارة خيارات الألعاب =============

@router.callback_query(F.data == "manage_options")
async def manage_options_start(callback: types.CallbackQuery, db_pool):
    """عرض جميع المنتجات لإدارة خياراتها"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.id, a.name, c.display_name, a.type
            FROM applications a
            LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    text = "📦 **إدارة خيارات المنتجات**\n\n"
    
    if not products:
        text += "⚠️ لا توجد منتجات حالياً."
    else:
        text += "**جميع المنتجات:**\n\n"
        type_icons = {
            'game': '🎮',
            'subscription': '📅',
            'service': '📱'
        }
        for p in products:
            icon = type_icons.get(p['type'], '📦')
            text += f"{icon} **{p['name']}** - {p['display_name'] or 'بدون قسم'}\n"
    
    builder = InlineKeyboardBuilder()
    
    for product in products:
        type_icon = "🎮" if product['type'] == 'game' else "📅" if product['type'] == 'subscription' else "📱"
        builder.row(types.InlineKeyboardButton(
            text=f"{type_icon} {product['name']}",
            callback_data=f"prod_options_{product['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(text="➕ إضافة منتج جديد", callback_data="add_product"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="back_to_admin"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("prod_options_"))
async def show_product_options(callback: types.CallbackQuery, db_pool):
    """عرض خيارات منتج معين - مع تمييز المعطل"""
    product_id = int(callback.data.split("_")[2])
    
    async with db_pool.acquire() as conn:
        product = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", product_id)
        # جلب جميع الخيارات (المفعلة والمعطلة) مع ترتيبها
        options = await conn.fetch(
            "SELECT * FROM product_options WHERE product_id = $1 ORDER BY is_active DESC, sort_order, price_usd",
            product_id
        )
    
    # تحديد نوع المنتج
    type_icon = "🎮" if product['type'] == 'game' else "📅" if product['type'] == 'subscription' else "📱"
    
    text = f"{type_icon} **{product['name']}**\n"
    text += f"📝 **النوع:** {product['type']}\n"
    if product.get('description'):
        text += f"📄 {product['description']}\n"
    text += "➖➖➖➖➖➖\n\n"
    
    if not options:
        text += "⚠️ لا توجد خيارات لهذا المنتج."
    else:
        text += f"**الخيارات الحالية ({len(options)}):**\n\n"
        for i, opt in enumerate(options, 1):
            status_icon = "✅" if opt['is_active'] else "🔒"
            status_text = "" if opt['is_active'] else " (متوقف)"
            
            text += f"**{i}. {status_icon} {opt['name']}{status_text}**\n"
            text += f"   🆔 `{opt['id']}`\n"
            text += f"   📦 الكمية: {opt['quantity']}\n"
            text += f"   💰 سعر المورد: ${float(opt['price_usd']):.3f}\n"
            if opt.get('description'):
                text += f"   📝 {opt['description']}\n"
            text += "   ➖➖➖➖\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة خيار جديد", callback_data=f"add_option_{product_id}"))
    
    for opt in options:
        # زر تعديل
        builder.row(
            types.InlineKeyboardButton(text=f"✏️ تعديل {opt['name']}", callback_data=f"edit_option_{opt['id']}"),
            # زر تشغيل/إيقاف
            types.InlineKeyboardButton(
                text=f"{'🔒 تعطيل' if opt['is_active'] else '✅ تفعيل'} {opt['name']}", 
                callback_data=f"toggle_option_{opt['id']}_{'1' if opt['is_active'] else '0'}"
            ),
            types.InlineKeyboardButton(text=f"🗑️ حذف {opt['name']}", callback_data=f"delete_option_{opt['id']}")
        )
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للقائمة", callback_data="manage_options"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ============= إضافة خيار جديد =============

@router.callback_query(F.data.startswith("add_option_"))
async def add_option_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء إضافة خيار جديد"""
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    
    await callback.message.edit_text(
        "➕ **إضافة خيار جديد - الخطوة 1/5**\n\n"
        "📝 **أدخل اسم الخيار:**\n"
        "مثال: `60 UC`\n"
        "مثال: `570 ماسة`\n\n"
        "❌ اضغط على زر الإلغاء للرجوع",
        reply_markup=None
    )
    
    await callback.message.answer(
        "أدخل اسم الخيار:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_option_name)

@router.message(AdminStates.waiting_option_name)
async def add_option_step_name(message: types.Message, state: FSMContext):
    """استلام اسم الخيار"""
    if not is_admin(message.from_user.id):
        return
    
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❌ الاسم قصير جداً. أدخل اسم مناسب:", reply_markup=get_cancel_keyboard())
        return
    
    await state.update_data(option_name=name)
    
    await message.answer(
        "➕ **إضافة خيار جديد - الخطوة 2/5**\n\n"
        f"📦 **أدخل الكمية:** (رقم فقط)\n"
        f"مثال: `60` لـ 60 UC\n"
        f"الاسم: **{name}**\n\n"
        f"❌ اضغط على زر الإلغاء للرجوع",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_option_quantity)

@router.message(AdminStates.waiting_option_quantity)
async def add_option_step_quantity(message: types.Message, state: FSMContext):
    """استلام الكمية"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        quantity = int(message.text.strip())
        
        if quantity <= 0:
            return await message.answer("❌ الكمية يجب أن تكون أكبر من 0:", reply_markup=get_cancel_keyboard())
        
        await state.update_data(option_quantity=quantity)
        
        data = await state.get_data()
        option_name = data.get('option_name', '')
        
        await message.answer(
            "➕ **إضافة خيار جديد - الخطوة 3/5**\n\n"
            "💰 **أدخل سعر المورد (بالدولار):**\n"
            f"مثال: `0.99` لـ {quantity} وحدة\n"
            f"الاسم: **{option_name}**\n"
            f"الكمية: **{quantity}**\n\n"
            f"❌ اضغط على زر الإلغاء للرجوع",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(AdminStates.waiting_option_supplier_price)
        
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح للكمية:", reply_markup=get_cancel_keyboard())

@router.message(AdminStates.waiting_option_supplier_price)
async def add_option_step_supplier_price(message: types.Message, state: FSMContext, db_pool):
    """استلام سعر المورد"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        supplier_price = float(message.text.strip())
    except ValueError:
        return await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح للسعر:", reply_markup=get_cancel_keyboard())
    
    if supplier_price <= 0:
        return await message.answer("❌ السعر يجب أن يكون أكبر من 0:", reply_markup=get_cancel_keyboard())
    
    await state.update_data(supplier_price=supplier_price)
    
    data = await state.get_data()
    product_id = data['product_id']
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow(
            "SELECT profit_percentage FROM applications WHERE id = $1",
            product_id
        )
        default_profit = float(app['profit_percentage'] or 10) if app else 10
    
    option_name = data.get('option_name', '')
    quantity = data.get('option_quantity', 0)
    
    await message.answer(
        "➕ **إضافة خيار جديد - الخطوة 4/5**\n\n"
        "📈 **أدخل نسبة الربح (%):**\n"
        f"النسبة الافتراضية: **{default_profit}%**\n"
        f"الاسم: **{option_name}**\n"
        f"الكمية: **{quantity}**\n"
        f"سعر المورد: **${supplier_price:.3f}**\n\n"
        f"❌ اضغط على زر الإلغاء للرجوع",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_option_profit)

@router.message(AdminStates.waiting_option_profit)
async def add_option_step_profit(message: types.Message, state: FSMContext):
    """استلام نسبة الربح"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        profit_percent = float(message.text.strip())
        
        if profit_percent < 0:
            return await message.answer("❌ نسبة الربح لا يمكن أن تكون سالبة:", reply_markup=get_cancel_keyboard())
        
        await state.update_data(profit_percent=profit_percent)
        
        data = await state.get_data()
        option_name = data.get('option_name', '')
        quantity = data.get('option_quantity', 0)
        supplier_price = data.get('supplier_price', 0)
        
        await message.answer(
            "➕ **إضافة خيار جديد - الخطوة 5/5**\n\n"
            "📝 **أدخل وصف الخيار:**\n"
            "أدخل الوصف (أو أرسل `-` لتخطي):\n\n"
            f"الاسم: **{option_name}**\n"
            f"الكمية: **{quantity}**\n"
            f"سعر المورد: **${supplier_price:.3f}**\n"
            f"نسبة الربح: **{profit_percent}%**\n\n"
            f"❌ اضغط على زر الإلغاء للرجوع",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(AdminStates.waiting_option_description)
        
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح لنسبة الربح:", reply_markup=get_cancel_keyboard())

@router.message(AdminStates.waiting_option_description)
async def add_option_step_description(message: types.Message, state: FSMContext, db_pool):
    """استلام الوصف وحفظ الخيار"""
    if not is_admin(message.from_user.id):
        return
    
    description = None
    if message.text and message.text != "-":
        description = message.text.strip()
    
    data = await state.get_data()
    product_id = data['product_id']
    option_name = data['option_name']
    quantity = data['option_quantity']
    supplier_price = data['supplier_price']
    profit_percent = data['profit_percent']
    
    from database import get_exchange_rate
    exchange_rate = await get_exchange_rate(db_pool)
    
    final_price_usd = supplier_price * (1 + profit_percent / 100)
    final_price_syp = final_price_usd * exchange_rate
    
    async with db_pool.acquire() as conn:
        # التحقق من نوع المنتج
        product = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", product_id)
        
        option_id = await conn.fetchval('''
            INSERT INTO product_options 
            (product_id, name, quantity, price_usd, description, sort_order, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, TRUE)
            RETURNING id
        ''', product_id, option_name, quantity, supplier_price, description, 0)
        
        # جلب جميع الخيارات بعد الإضافة
        options = await conn.fetch(
            "SELECT * FROM product_options WHERE product_id = $1 AND is_active = TRUE ORDER BY sort_order, price_usd",
            product_id
        )
    
    confirm_text = (
        f"✅ **تم إضافة الخيار بنجاح!**\n\n"
        f"📦 **الخيار:** {option_name}\n"
        f"🔢 **الكمية:** {quantity}\n\n"
        f"💰 **تفاصيل السعر:**\n"
        f"• سعر المورد: **${supplier_price:.3f}**\n"
        f"• نسبة الربح: **{profit_percent}%**\n"
        f"• سعر البيع: **${final_price_usd:.3f}**\n"
        f"• سعر البيع (ل.س): **{final_price_syp:,.0f} ل.س**\n\n"
    )
    
    if description:
        confirm_text += f"📝 **الوصف:**\n{description}\n\n"
    
    await message.answer(confirm_text, reply_markup=None)
    await state.clear()
    
    # عرض الخيارات المحدثة مع تحديد نوع المنتج
    type_icon = "🎮" if product['type'] == 'game' else "📅" if product['type'] == 'subscription' else "📱"
    type_name = "لعبة" if product['type'] == 'game' else "اشتراك" if product['type'] == 'subscription' else "خدمة"
    
    text = f"{type_icon} **{product['name']}**\n"
    text += f"📝 **النوع:** {type_name}\n"
    if product.get('description'):
        text += f"📄 {product['description']}\n"
    text += "➖➖➖➖➖➖\n\n"
    
    if not options:
        text += "⚠️ لا توجد خيارات لهذا المنتج."
    else:
        text += f"**الخيارات الحالية ({len(options)}):**\n\n"
        for i, opt in enumerate(options, 1):
            text += f"**{i}. {opt['name']}**\n"
            text += f"   🆔 `{opt['id']}`\n"
            text += f"   📦 الكمية: {opt['quantity']}\n"
            text += f"   💰 سعر المورد: ${float(opt['price_usd']):.3f}\n"
            if opt.get('description'):
                text += f"   📝 {opt['description']}\n"
            text += "   ➖➖➖➖\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة خيار جديد", callback_data=f"add_option_{product_id}"))
    
    for opt in options:
        builder.row(
            types.InlineKeyboardButton(text=f"✏️ تعديل {opt['name']}", callback_data=f"edit_option_{opt['id']}"),
            types.InlineKeyboardButton(text=f"🗑️ حذف {opt['name']}", callback_data=f"delete_option_{opt['id']}")
        )
    
    # أزرار إضافية حسب نوع المنتج
    if product['type'] == 'game':
        builder.row(types.InlineKeyboardButton(text="🎮 قوالب ألعاب", callback_data=f"templates_menu_{product_id}"))
    elif product['type'] == 'subscription':
        builder.row(types.InlineKeyboardButton(text="📅 قوالب اشتراكات", callback_data=f"templates_menu_{product_id}"))
    else:  # service
        builder.row(types.InlineKeyboardButton(text="📱 قوالب خدمات", callback_data=f"templates_menu_{product_id}"))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للقائمة", callback_data="manage_options"))
    
    await message.answer(text, reply_markup=builder.as_markup())

# ============= تعديل خيار =============
@router.callback_query(F.data.startswith("edit_option_"))
async def edit_option_menu(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض قائمة تعديل الخيار"""
    try:
        parts = callback.data.split("_")
        if len(parts) >= 3 and parts[2].isdigit():
            option_id = int(parts[2])
        else:
            await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
            return
        
        from database import get_product_option
        option = await get_product_option(db_pool, option_id)
        
        if not option:
            return await callback.answer("❌ الخيار غير موجود", show_alert=True)
        
        await state.update_data(option_id=option_id, product_id=option['product_id'])
        
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📝 تعديل الاسم", callback_data=f"edit_fld_name_{option_id}"))
        builder.row(types.InlineKeyboardButton(text="🔢 تعديل الكمية", callback_data=f"edit_fld_quantity_{option_id}"))
        builder.row(types.InlineKeyboardButton(text="💰 تعديل سعر المورد", callback_data=f"edit_fld_price_{option_id}"))
        builder.row(types.InlineKeyboardButton(text="📈 تعديل نسبة الربح", callback_data=f"edit_fld_profit_{option_id}"))
        builder.row(types.InlineKeyboardButton(text="📝 تعديل الوصف", callback_data=f"edit_fld_desc_{option_id}"))
        
        # إضافة زر لتشغيل/إيقاف الخيار
        status_text = "🔒 تعطيل" if option['is_active'] else "✅ تفعيل"
        builder.row(types.InlineKeyboardButton(
            text=f"{status_text} الخيار", 
            callback_data=f"toggle_option_{option_id}_{'1' if option['is_active'] else '0'}"
        ))
        
        builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"prod_options_{option['product_id']}"))
        
        status_icon = "✅" if option['is_active'] else "🔒"
        status_text = "نشط" if option['is_active'] else "معطل"
        
        text = (
            f"✏️ **تعديل الخيار**\n\n"
            f"**البيانات الحالية:**\n"
            f"• الاسم: {option['name']}\n"
            f"• الكمية: {option['quantity']}\n"
            f"• سعر المورد: ${option['price_usd']:.3f}\n"
            f"• الحالة: {status_icon} {status_text}\n"
        )
        
        if option.get('description'):
            text += f"• الوصف: {option['description']}\n"
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ خطأ في edit_option_menu: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("edit_fld_"))
async def edit_field_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تعديل حقل معين"""
    try:
        parts = callback.data.split("_")
        if len(parts) != 4:
            await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
            return
        
        field_type = parts[2]
        option_id = int(parts[3])
        
        field_names = {'name': 'الاسم', 'quantity': 'الكمية', 'price': 'سعر المورد', 'profit': 'نسبة الربح', 'desc': 'الوصف'}
        field_name = field_names.get(field_type, field_type)
        
        await state.update_data(edit_field=field_type, option_id=option_id)
        
        instructions = {
            'name': "أدخل الاسم الجديد:",
            'quantity': "أدخل الكمية الجديدة (رقم فقط):",
            'price': "أدخل سعر المورد الجديد (بالدولار):",
            'profit': "أدخل نسبة الربح الجديدة (%):",
            'desc': "أدخل الوصف الجديد (أو - لحذف الوصف):"
        }
        
        await callback.message.answer(
            f"✏️ **تعديل {field_name}**\n\n"
            f"{instructions.get(field_type, 'أدخل القيمة الجديدة:')}\n\n"
            f"📝 أرسل القيمة الجديدة الآن\n"
            f"❌ أو أرسل /cancel للإلغاء"
        )
        
        await state.set_state(AdminStates.waiting_edit_option_value)
        await callback.answer("📝 جاري انتظار الإدخال...")
        
    except Exception as e:
        logger.error(f"❌ خطأ في edit_field_start: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.message(AdminStates.waiting_edit_option_value)
async def save_edited_value(message: types.Message, state: FSMContext, db_pool):
    """حفظ القيمة المعدلة"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    data = await state.get_data()
    option_id = data.get('option_id')
    field = data.get('edit_field')
    
    if not option_id or not field:
        await message.answer("❌ بيانات غير صالحة. الرجاء البدء من جديد.")
        await state.clear()
        return
    
    value = message.text.strip()
    
    try:
        update_value = None
        field_name = ""
        db_column = ""
        
        if field == 'name':
            if len(value) < 2:
                await message.answer("❌ الاسم قصير جداً. أدخل اسم أطول:", reply_markup=get_cancel_keyboard())
                return
            update_value = value
            field_name = "الاسم"
            db_column = "name"
            
        elif field == 'quantity':
            try:
                quantity = int(value)
                if quantity <= 0:
                    await message.answer("❌ الكمية يجب أن تكون أكبر من 0:", reply_markup=get_cancel_keyboard())
                    return
                update_value = quantity
                field_name = "الكمية"
                db_column = "quantity"
            except ValueError:
                await message.answer("❌ يرجى إدخال رقم صحيح للكمية:", reply_markup=get_cancel_keyboard())
                return
            
        elif field == 'price':
            try:
                price = float(value)
                if price <= 0:
                    await message.answer("❌ السعر يجب أن يكون أكبر من 0:", reply_markup=get_cancel_keyboard())
                    return
                update_value = price
                field_name = "سعر المورد"
                db_column = "price_usd"
            except ValueError:
                await message.answer("❌ يرجى إدخال رقم صحيح للسعر (مثال: 0.99):", reply_markup=get_cancel_keyboard())
                return
            
        elif field == 'profit':
            try:
                profit = float(value)
                if profit < 0:
                    await message.answer("❌ نسبة الربح لا يمكن أن تكون سالبة:", reply_markup=get_cancel_keyboard())
                    return
                update_value = profit
                field_name = "نسبة الربح"
                db_column = "profit_percentage"
            except ValueError:
                await message.answer("❌ يرجى إدخال رقم صحيح لنسبة الربح (مثال: 10):", reply_markup=get_cancel_keyboard())
                return
            
        elif field == 'desc':
            update_value = None if value == '-' else value
            field_name = "الوصف"
            db_column = "description"
        
        else:
            await message.answer("❌ حقل غير معروف")
            await state.clear()
            return
        
        async with db_pool.acquire() as conn:
            if field == 'profit':
                option = await conn.fetchrow("SELECT product_id FROM product_options WHERE id = $1", option_id)
                if option:
                    await conn.execute(f"UPDATE applications SET {db_column} = $1 WHERE id = $2", update_value, option['product_id'])
                    product = await conn.fetchrow("SELECT name FROM applications WHERE id = $1", option['product_id'])
                    product_name = product['name'] if product else "المنتج"
                    await message.answer(f"✅ تم تحديث {field_name} للمنتج **{product_name}** بنجاح!")
                else:
                    await message.answer("❌ لم يتم العثور على الخيار")
                    await state.clear()
                    return
            else:
                query = f'UPDATE product_options SET "{db_column}" = $1 WHERE id = $2'
                await conn.execute(query, update_value, option_id)
                
                updated_option = await conn.fetchrow(
                    "SELECT po.*, a.name as product_name FROM product_options po JOIN applications a ON po.product_id = a.id WHERE po.id = $1",
                    option_id
                )
                
                if updated_option:
                    await message.answer(
                        f"✅ **تم التحديث بنجاح!**\n\n"
                        f"📦 المنتج: **{updated_option['product_name']}**\n"
                        f"🔧 الخيار: **{updated_option['name']}**\n"
                        f"📝 الحقل المعدل: **{field_name}**\n"
                        f"📊 القيمة الجديدة: **{update_value}**"
                    )
                else:
                    await message.answer(f"✅ تم تحديث {field_name} بنجاح!")
        
        await state.clear()
        
        # العودة لقائمة الخيارات
        if 'updated_option' in locals() and updated_option:
            product_id = updated_option['product_id']
        else:
            async with db_pool.acquire() as conn:
                opt = await conn.fetchrow("SELECT product_id FROM product_options WHERE id = $1", option_id)
                product_id = opt['product_id'] if opt else None
        
        if product_id:
            builder = InlineKeyboardBuilder()
            builder.row(types.InlineKeyboardButton(text="🔙 العودة لقائمة الخيارات", callback_data=f"prod_options_{product_id}"))
            await message.answer("🔍 اختر ما تريد فعله الآن:", reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ التعديل: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# ============= حذف خيار =============

@router.callback_query(F.data.startswith("delete_option_"))
async def delete_option_confirm(callback: types.CallbackQuery, db_pool):
    """تأكيد حذف خيار"""
    option_id = int(callback.data.split("_")[2])
    
    from database import get_product_option
    option = await get_product_option(db_pool, option_id)
    
    if not option:
        return await callback.answer("❌ الخيار غير موجود", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم، احذف", callback_data=f"confirm_delete_option_{option_id}"),
        types.InlineKeyboardButton(text="❌ لا", callback_data=f"prod_options_{option['product_id']}")
    )
    
    await callback.message.edit_text(
        f"⚠️ **تأكيد حذف الخيار**\n\n"
        f"هل أنت متأكد من حذف هذا الخيار؟\n\n"
        f"📦 **الاسم:** {option['name']}\n"
        f"🔢 **الكمية:** {option['quantity']}\n"
        f"💰 **السعر:** ${option['price_usd']:.2f}",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("confirm_delete_option_"))
async def delete_option_execute(callback: types.CallbackQuery, db_pool):
    """تنفيذ حذف الخيار"""
    option_id = int(callback.data.split("_")[3])
    
    from database import get_product_option
    option = await get_product_option(db_pool, option_id)
    
    if not option:
        return await callback.answer("❌ الخيار غير موجود", show_alert=True)
    
    product_id = option['product_id']
    
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE product_options SET is_active = FALSE WHERE id = $1", option_id)
    
    await callback.answer("✅ تم حذف الخيار بنجاح")
    
    # العودة لقائمة الخيارات
    fake_callback = types.CallbackQuery(
        id='0',
        from_user=callback.from_user,
        message=callback.message,
        data=f"prod_options_{product_id}",
        bot=callback.bot
    )
    await show_product_options(fake_callback, db_pool)

# ============= تشغيل/إيقاف الخيارات =============

@router.callback_query(F.data.startswith("toggle_option_"))
async def toggle_option_status(callback: types.CallbackQuery, db_pool):
    """تشغيل أو إيقاف خيار معين"""
    try:
        parts = callback.data.split("_")
        option_id = int(parts[2])
        current_status = bool(int(parts[3]))
        new_status = not current_status
        
        async with db_pool.acquire() as conn:
            # جلب معلومات الخيار والمنتج المرتبط به
            option = await conn.fetchrow(
                "SELECT po.*, a.name as product_name FROM product_options po JOIN applications a ON po.product_id = a.id WHERE po.id = $1",
                option_id
            )
            
            if not option:
                await callback.answer("❌ الخيار غير موجود", show_alert=True)
                return
            
            # تحديث حالة الخيار
            await conn.execute(
                "UPDATE product_options SET is_active = $1 WHERE id = $2",
                new_status, option_id
            )
            
            # جلب جميع الخيارات المحدثة لنفس المنتج
            options = await conn.fetch(
                "SELECT * FROM product_options WHERE product_id = $1 ORDER BY is_active DESC, sort_order, price_usd",
                option['product_id']
            )
        
        status_text = "✅ مفعل" if new_status else "🔒 معطل"
        await callback.answer(f"تم تغيير حالة الخيار '{option['name']}' إلى {status_text}")
        
        # العودة لقائمة الخيارات المحدثة
        fake_callback = types.CallbackQuery(
            id='0',
            from_user=callback.from_user,
            message=callback.message,
            data=f"prod_options_{option['product_id']}",
            bot=callback.bot
        )
        await show_product_options(fake_callback, db_pool)
        
    except Exception as e:
        logger.error(f"❌ خطأ في toggle_option_status: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# ============= إضافة لعبة أو اشتراك جديد =============

@router.callback_query(F.data == "add_new_game")
async def add_new_game_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إضافة لعبة أو اشتراك جديد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT id, display_name FROM categories ORDER BY sort_order")
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(types.InlineKeyboardButton(text=cat['display_name'], callback_data=f"new_game_cat_{cat['id']}"))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_options"))
    
    await callback.message.edit_text(
        "➕ **إضافة لعبة أو اشتراك جديد**\n\nاختر القسم أولاً:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("new_game_cat_"))
async def new_game_get_name(callback: types.CallbackQuery, state: FSMContext):
    """استلام اسم اللعبة الجديدة"""
    cat_id = int(callback.data.split("_")[3])
    await state.update_data(category_id=cat_id)
    
    await callback.message.edit_text(
        "📝 **أدخل اسم اللعبة أو الاشتراك:**\n\n"
        "مثال: `PUBG Mobile`\n"
        "مثال: `Netflix Premium`\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    await state.set_state(AdminStates.waiting_new_game_name)

@router.message(AdminStates.waiting_new_game_name)
async def new_game_get_type(message: types.Message, state: FSMContext):
    """اختيار نوع اللعبة"""
    if not is_admin(message.from_user.id):
        return
    
    name = message.text.strip()
    await state.update_data(game_name=name)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🎮 لعبة", callback_data="new_game_type_game"),
        types.InlineKeyboardButton(text="📅 اشتراك", callback_data="new_game_type_subscription")
    )
    
    await message.answer(f"📱 **الاسم:** {name}\n\nاختر النوع:", reply_markup=builder.as_markup())
    await state.set_state(AdminStates.waiting_new_game_type)

@router.callback_query(F.data.startswith("new_game_type_"))
async def new_game_save(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """حفظ اللعبة الجديدة في قاعدة البيانات"""
    game_type = callback.data.replace("new_game_type_", "")
    
    data = await state.get_data()
    name = data['game_name']
    category_id = data['category_id']
    
    try:
        async with db_pool.acquire() as conn:
            existing = await conn.fetchval("SELECT id FROM applications WHERE name = $1", name)
            if existing:
                await callback.message.edit_text(
                    f"❌ **فشل الإضافة**\n\nتطبيق باسم **{name}** موجود مسبقاً.\nالرجاء استخدام اسم مختلف."
                )
                await state.clear()
                return
            
            game_id = await conn.fetchval('''
                INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, category_id, type, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                RETURNING id
            ''', name, 0.01, 1, 10, category_id, game_type)
        
        await callback.message.edit_text(
            f"✅ **تم إضافة {name} بنجاح!**\n\n"
            f"📱 النوع: {'🎮 لعبة' if game_type == 'game' else '📅 اشتراك'}\n"
            f"🆔 المعرف: {game_id}\n\n"
            f"🔹 الآن يمكنك إضافة خيارات لهذا التطبيق."
        )
        await state.clear()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ **حدث خطأ:** {str(e)}\n\nيرجى المحاولة مرة أخرى.")
        await state.clear()

# ============= إدارة النقاط =============

@router.callback_query(F.data == "manage_points")
async def manage_points(callback: types.CallbackQuery, db_pool):
    """قائمة إدارة النقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        points_per_order = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_per_order'")
        points_per_referral = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_per_referral'")
        points_to_usd = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_to_usd'")
        pending_redemptions = await conn.fetch("SELECT * FROM redemption_requests WHERE status = 'pending' ORDER BY created_at")
    
    kb = [
        [types.InlineKeyboardButton(text="⚙️ تعديل إعدادات النقاط", callback_data="edit_points_settings")],
        [types.InlineKeyboardButton(text="📋 طلبات الاسترداد", callback_data="view_redemptions")],
        [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin")]
    ]
    
    text = (
        "⭐ **إدارة النقاط**\n\n"
        f"**الإعدادات الحالية:**\n"
        f"• نقاط لكل طلب: {points_per_order or 5}\n"
        f"• نقاط لكل إحالة: {points_per_referral or 5}\n"
        f"• {points_to_usd or 100} نقطة = 1 دولار\n\n"
        f"**طلبات الاسترداد المعلقة:** {len(pending_redemptions)}"
    )
    
    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "edit_points_settings")
async def edit_points_settings(callback: types.CallbackQuery, state: FSMContext):
    """تعديل إعدادات النقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.answer(
        "⚙️ **تعديل إعدادات النقاط**\n\n"
        "أدخل القيم الجديدة بالصيغة التالية:\n"
        "`نقاط_الطلب نقاط_الإحالة نقاط_الدولار`\n\n"
        "مثال: `1 1 100`\n\n"
        "أو أرسل /cancel للإلغاء",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_points_settings)

@router.message(AdminStates.waiting_points_settings)
async def save_points_settings(message: types.Message, state: FSMContext, db_pool):
    """حفظ إعدادات النقاط"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            return await message.answer("❌ صيغة غير صحيحة. استخدم: `نقاط_الطلب نقاط_الإحالة نقاط_الدولار`")
        
        points_order, points_referral, points_usd = parts
        
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'points_per_order'", points_order)
            await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'points_per_referral'", points_referral)
            await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'points_to_usd'", points_usd)
        
        await message.answer("✅ **تم تحديث إعدادات النقاط بنجاح**")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ **حدث خطأ:** {str(e)}")
        await state.clear()

@router.callback_query(F.data == "view_redemptions")
async def view_redemptions(callback: types.CallbackQuery, db_pool):
    """عرض طلبات الاسترداد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        redemptions = await conn.fetch("SELECT * FROM redemption_requests WHERE status = 'pending' ORDER BY created_at")
    
    if not redemptions:
        await callback.answer("لا توجد طلبات استرداد معلقة", show_alert=True)
        return
    
    for r in redemptions:
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ موافقة", callback_data=f"appr_red_{r['id']}"),
            types.InlineKeyboardButton(text="❌ رفض", callback_data=f"reje_red_{r['id']}")
        )
        
        await callback.message.answer(
            f"🆔 **طلب استرداد #{r['id']}**\n\n"
            f"👤 **المستخدم:** @{r['username'] or 'غير معروف'}\n"
            f"🆔 **الآيدي:** `{r['user_id']}`\n"
            f"⭐ **النقاط:** {r['points']}\n"
            f"💰 **المبلغ:** {r['amount_usd']}$ ({r['amount_syp']:,.0f} ل.س)\n"
            f"📅 **التاريخ:** {r['created_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
            f"**الإجراء:**",
            reply_markup=builder.as_markup()
        )

@router.callback_query(F.data.startswith("appr_red_"))
async def approve_redemption(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    """الموافقة على طلب استرداد نقاط"""
    try:
        req_id = int(callback.data.split("_")[2])
        
        from database import approve_redemption, get_exchange_rate
        
        current_rate = await get_exchange_rate(db_pool)
        success, error = await approve_redemption(db_pool, req_id, callback.from_user.id)
        
        if success:
            async with db_pool.acquire() as conn:
                req = await conn.fetchrow("SELECT * FROM redemption_requests WHERE id = $1", req_id)
            
            await callback.answer("✅ تمت الموافقة على الطلب")
            await callback.message.edit_text(
                callback.message.text + f"\n\n✅ **تمت الموافقة على الطلب**\n💰 بسعر صرف: {current_rate:,.0f} ل.س",
                reply_markup=None
            )
            
            try:
                await bot.send_message(
                    req['user_id'],
                    f"✅ **تمت الموافقة على طلب استرداد النقاط!**\n\n"
                    f"⭐ النقاط: {req['points']}\n"
                    f"💰 المبلغ: {req['amount_syp']:,.0f} ل.س\n"
                    f"💵 بسعر صرف: {current_rate:,.0f} ل.س\n\n"
                    f"تم إضافة المبلغ إلى رصيدك."
                )
            except:
                pass
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
            
    except Exception as e:
        logger.error(f"❌ خطأ في الموافقة على الاسترداد: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reje_red_"))
async def reject_redemption(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    """رفض طلب استرداد نقاط"""
    try:
        req_id = int(callback.data.split("_")[2])
        
        from database import reject_redemption
        success, error = await reject_redemption(db_pool, req_id, callback.from_user.id, "رفض من قبل الإدارة")
        
        if success:
            await callback.answer("❌ تم رفض الطلب")
            await callback.message.edit_text(
                callback.message.text + "\n\n❌ **تم رفض الطلب**",
                reply_markup=None
            )
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
            
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الاسترداد: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# ============= تصفير البوت =============

# ============= تصفير البوت =============

@router.callback_query(F.data == "reset_bot")
async def reset_bot_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء عملية تصفير البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="⚠️ نعم، تصفير البوت", callback_data="confirm_reset"),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_del")
    )
    
    await callback.message.edit_text(
        "⚠️ **تحذير: تصفير البوت** ⚠️\n\n"
        "هذا الإجراء سيقوم بحذف:\n"
        "• جميع المستخدمين\n"
        "• جميع طلبات الشحن\n"
        "• جميع طلبات التطبيقات\n"
        "• جميع النقاط وسجل النقاط\n"
        "• جميع الإحالات\n\n"
        "**سيتم الاحتفاظ بالمشرفين فقط.**\n\n"
        "هل أنت متأكد؟",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "confirm_reset")
async def reset_bot_ask_rate(callback: types.CallbackQuery, state: FSMContext):
    """طلب سعر الصرف الجديد بعد التصفير"""
    await callback.message.edit_text(
        "💰 **أدخل سعر الصرف الجديد**\n"
        "مثال: 118\n\n"
        "سيتم استخدام هذا السعر بعد تصفير البوت.\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    await state.set_state(AdminStates.waiting_reset_rate)

@router.message(AdminStates.waiting_reset_rate)
async def execute_reset_bot(message: types.Message, state: FSMContext, db_pool):
    """تنفيذ تصفير البوت - مع نظام VIP الجديد"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_rate = float(message.text)
    except ValueError:
        return await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 118):", reply_markup=get_cancel_keyboard())
    
    from config import ADMIN_ID, MODERATORS
    admin_ids = [ADMIN_ID] + MODERATORS
    admin_ids_str = ','.join([str(id) for id in admin_ids if id])
    
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM points_history")
        await conn.execute("DELETE FROM redemption_requests")
        await conn.execute("DELETE FROM deposit_requests")
        await conn.execute("DELETE FROM orders")
        await conn.execute("ALTER SEQUENCE orders_id_seq RESTART WITH 1")
        
        if admin_ids_str:
            await conn.execute(f"DELETE FROM users WHERE user_id NOT IN ({admin_ids_str})")
            
            for admin_id in admin_ids:
                if admin_id:
                    await conn.execute('''
                        UPDATE users 
                        SET balance = 0, total_points = 0, total_deposits = 0, total_orders = 0,
                            referral_count = 0, referral_earnings = 0, total_points_earned = 0,
                            total_points_redeemed = 0, vip_level = 0, total_spent = 0,
                            discount_percent = 0, manual_vip = FALSE, last_activity = CURRENT_TIMESTAMP
                        WHERE user_id = $1
                    ''', admin_id)
        else:
            await conn.execute("DELETE FROM users")
        
        await conn.execute('''
            INSERT INTO bot_settings (key, value, description) 
            VALUES ('usd_to_syp', $1, 'سعر صرف الدولار مقابل الليرة')
            ON CONFLICT (key) DO UPDATE SET value = $1
        ''', str(new_rate))
        
        await conn.execute("UPDATE bot_settings SET value = '1' WHERE key IN ('points_per_order', 'points_per_referral')")
        await conn.execute("UPDATE bot_settings SET value = '100' WHERE key = 'redemption_rate'")
        
        # ========== نظام VIP الجديد بعد التصفير ==========
        await conn.execute('''
            INSERT INTO vip_levels (level, name, min_spent, discount_percent, icon) 
            VALUES 
                (0, 'VIP 0', 0, 0, '⚪'),
                (1, 'VIP 1', 3500, 1, '🔵'),
                (2, 'VIP 2', 6500, 2, '🟣'),
                (3, 'VIP 3', 12000, 3, '🟡')
            ON CONFLICT (level) DO UPDATE SET 
                min_spent = EXCLUDED.min_spent,
                discount_percent = EXCLUDED.discount_percent,
                icon = EXCLUDED.icon;
        ''')
    
    await message.answer(
        f"✅ **تم تصفير البوت بنجاح!**\n\n"
        f"💰 سعر الصرف الجديد: {new_rate} ل.س\n"
        f"⭐ نقاط لكل طلب: 1\n"
        f"🔗 نقاط لكل إحالة: 1\n"
        f"🎁 100 نقطة = 1 دولار\n"
        f"👑 **نظام VIP الجديد:**\n"
        f"• VIP 1: 3500 ل.س - خصم 1%\n"
        f"• VIP 2: 6500 ل.س - خصم 2%\n"
        f"• VIP 3: 12000 ل.س - خصم 4%\n\n"
        f"البوت الآن جاهز للبدء من جديد!"
    )
    await state.clear()
@router.callback_query(F.data == "cancel_del")
async def cancel_action(callback: types.CallbackQuery):
    """إلغاء أي عملية"""
    await callback.message.edit_text("✅ تم الإلغاء.")

# ============= إدارة المشرفين =============

@router.callback_query(F.data == "manage_admins")
async def manage_admins_menu(callback: types.CallbackQuery, db_pool):
    """قائمة إدارة المشرفين"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_all_admins
    admins = await get_all_admins(db_pool)
    
    admins_text = "👑 **قائمة المشرفين**\n\n"
    for admin in admins:
        role_icon = "👑" if admin['role'] == 'owner' else "🛡️"
        username = f"@{admin['username']}" if admin['username'] else f"ID: {admin['user_id']}"
        name = admin['first_name'] or ""
        admins_text += f"{role_icon} {username}\n   🆔 `{admin['user_id']}`\n   📝 {name}\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة مشرف", callback_data="add_admin"),
                types.InlineKeyboardButton(text="❌ إزالة مشرف", callback_data="remove_admin"))
    builder.row(types.InlineKeyboardButton(text="📋 معلومات مشرف", callback_data="admin_info"),
                types.InlineKeyboardButton(text="📊 سجل النشاطات", callback_data="admin_logs"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="back_to_admin"))
    
    await callback.message.edit_text(admins_text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "add_admin")
async def add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء إضافة مشرف جديد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text(
        "👤 **إضافة مشرف جديد**\n\n"
        "أدخل الآيدي (ID) الخاص بالمستخدم الذي تريد إضافته كمشرف:\n\n"
        "💡 يمكن للمستخدم الحصول على آيديه عبر إرسال /id للبوت\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    await state.set_state(AdminStates.waiting_admin_id)

@router.message(AdminStates.waiting_admin_id)
async def add_admin_confirm(message: types.Message, state: FSMContext, db_pool):
    """تأكيد إضافة مشرف"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_admin_id = int(message.text.strip())
        
        from database import add_admin, get_user_by_id
        user = await get_user_by_id(db_pool, new_admin_id)
        
        if not user:
            return await message.answer(
                "❌ المستخدم غير موجود في قاعدة البيانات.\n"
                "يجب على المستخدم استخدام البوت مرة واحدة على الأقل.\n\n"
                "أو أرسل /cancel للإلغاء",
                reply_markup=get_cancel_keyboard()
            )
        
        success, msg = await add_admin(db_pool, new_admin_id, message.from_user.id)
        
        if success:
            await message.answer(
                f"✅ **تمت إضافة المشرف بنجاح!**\n\n"
                f"👤 المستخدم: @{user['username'] or 'غير معروف'}\n"
                f"🆔 الآيدي: `{new_admin_id}`\n\n"
                f"🔸 ملاحظة: قد تحتاج إلى إعادة تشغيل البوت لتفعيل الصلاحيات."
            )
            
            try:
                await message.bot.send_message(
                    new_admin_id,
                    f"🎉 **مبروك! تمت إضافتك كمشرف في البوت**\n\n"
                    f"🔸 يمكنك الآن استخدام لوحة التحكم عبر إرسال /admin\n"
                    f"👤 تمت الإضافة بواسطة: @{message.from_user.username}"
                )
            except:
                pass
        else:
            await message.answer(f"❌ {msg}")
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ يرجى إدخال آيدي صحيح (أرقام فقط):", reply_markup=get_cancel_keyboard())
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# ============= الإحصائيات =============

@router.callback_query(F.data == "bot_stats")
async def show_bot_stats(callback: types.CallbackQuery, db_pool):
    """عرض إحصائيات البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_bot_stats, get_bot_status, get_exchange_rate
    
    stats = await get_bot_stats(db_pool)
    bot_status = await get_bot_status(db_pool)
    current_rate = await get_exchange_rate(db_pool)
    
    if not stats:
        return await callback.answer("❌ خطأ في جلب الإحصائيات", show_alert=True)
    
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"
    
    stats_text = (
        "📊 **إحصائيات البوت**\n\n"
        f"🤖 **حالة البوت:** {status_text}\n\n"
        "👥 **المستخدمين:**\n"
        f"• 📈 الإجمالي: {stats['users'].get('total_users', 0)}\n"
        f"• 💰 إجمالي الأرصدة: {stats['users'].get('total_balance', 0):,.0f} ل.س\n"
        f"• 🚫 المحظورين: {stats['users'].get('banned_users', 0)}\n"
        f"• 🆕 الجدد اليوم: {stats['users'].get('new_users_today', 0)}\n"
        f"• ⭐ إجمالي النقاط: {stats['users'].get('total_points', 0)}\n\n"
        "💰 **الإيداعات:**\n"
        f"• 📋 الإجمالي: {stats['deposits'].get('total_deposits', 0)}\n"
        f"• 💸 إجمالي المبالغ: {stats['deposits'].get('total_deposit_amount', 0):,.0f} ل.س\n"
        f"• ⏳ المعلقة: {stats['deposits'].get('pending_deposits', 0)}\n"
        f"• ✅ المنجزة: {stats['deposits'].get('approved_deposits', 0)}\n\n"
        "🛒 **الطلبات:**\n"
        f"• 📋 الإجمالي: {stats['orders'].get('total_orders', 0)}\n"
        f"• 💸 إجمالي المبالغ: {stats['orders'].get('total_order_amount', 0):,.0f} ل.س\n"
        f"• ⏳ المعلقة: {stats['orders'].get('pending_orders', 0)}\n"
        f"• ✅ المكتملة: {stats['orders'].get('completed_orders', 0)}\n"
        f"• ⭐ نقاط ممنوحة: {stats['orders'].get('total_points_given', 0)}\n\n"
        "🎁 **نظام النقاط:**\n"
        f"• 💰 عمليات استرداد: {stats['points'].get('total_redemptions', 0)}\n"
        f"• ⭐ نقاط مستردة: {stats['points'].get('total_points_redeemed', 0)}\n"
        f"• 💵 قيمة المستردة: {stats['points'].get('total_redemption_amount', 0):,.0f} ل.س\n\n"
        f"💵 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n"
    )
    
    await callback.message.answer(stats_text, parse_mode="Markdown")

@router.callback_query(F.data == "top_deposits")
async def show_top_deposits(callback: types.CallbackQuery, db_pool):
    """أكثر المستخدمين إيداعاً"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_deposits
    users = await get_top_users_by_deposits(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "💳 **أكثر المستخدمين إيداعاً**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{i}. {username}\n   💰 {user['total_deposits']:,.0f} ل.س\n"
    
    try:
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطأ في تنسيق Markdown: {e}")
        plain_text = text.replace('**', '').replace('*', '').replace('`', '')
        await callback.message.answer(plain_text)

@router.callback_query(F.data == "top_orders")
async def show_top_orders(callback: types.CallbackQuery, db_pool):
    """أكثر المستخدمين طلبات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_orders
    users = await get_top_users_by_orders(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "🛒 **أكثر المستخدمين طلبات**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{i}. {username}\n   📦 {user['total_orders']} طلب\n"
    
    try:
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطأ في تنسيق Markdown: {e}")
        plain_text = text.replace('**', '').replace('*', '').replace('`', '')
        await callback.message.answer(plain_text)

@router.callback_query(F.data == "top_referrals")
async def show_top_referrals(callback: types.CallbackQuery, db_pool):
    """أكثر المستخدمين إحالة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_referrals
    users = await get_top_users_by_referrals(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "🔗 **أكثر المستخدمين إحالة**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{i}. {username}\n   👥 {user['referral_count']} إحالة | 💰 {user['referral_earnings']:,.0f} ل.س\n"
    
    try:
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطأ في تنسيق Markdown: {e}")
        plain_text = text.replace('**', '').replace('*', '').replace('`', '')
        await callback.message.answer(plain_text)

@router.callback_query(F.data == "top_points")
async def show_top_points(callback: types.CallbackQuery, db_pool):
    """أكثر المستخدمين نقاط - مع تجنب أخطاء Markdown"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_points
    users = await get_top_users_by_points(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "⭐ **أكثر المستخدمين نقاط**\n\n"
    
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        
        # إصلاح: استخدام علامات Markdown بشكل صحيح
        # نضيف كل سطر بشكل منفصل لتجنب الأخطاء
        line = f"{i}. {username}\n   ⭐ {user['total_points']} نقطة\n"
        
        # التأكد من عدم وجود علامات غير مغلقة
        text += line
    
    # محاولة الإرسال مع Markdown، إذا فشل نرسل بدون تنسيق
    try:
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        # إذا فشل Markdown، نرسل نص عادي
        logger.error(f"خطأ في تنسيق Markdown: {e}")
        # إزالة علامات Markdown
        plain_text = text.replace('**', '').replace('*', '').replace('`', '')
        await callback.message.answer(plain_text)

@router.callback_query(F.data == "vip_stats")
async def show_vip_stats(callback: types.CallbackQuery, db_pool):
    """إحصائيات VIP"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        vip_counts = await conn.fetch("SELECT vip_level, COUNT(*) as count FROM users GROUP BY vip_level ORDER BY vip_level")
        vip_spent = await conn.fetch("SELECT vip_level, SUM(total_spent) as total FROM users WHERE vip_level > 0 GROUP BY vip_level ORDER BY vip_level")
    
    vip_names = ["VIP 0 ⚪", "VIP 1 🔵", "VIP 2 🟣", "VIP 3 🟡"]
    text = "👥 **إحصائيات VIP**\n\n**عدد المستخدمين:**\n"
    
    for row in vip_counts:
        level = row['vip_level']
        if level <= 5:
            text += f"• {vip_names[level]}: {row['count']} مستخدم\n"
    
    if vip_spent:
        text += "\n**إجمالي الإنفاق:**\n"
        for row in vip_spent:
            level = row['vip_level']
            if level <= 5:
                text += f"• {vip_names[level]}: {row['total']:,.0f} ل.س\n"
    
    await callback.message.answer(text, parse_mode="Markdown")

# ============= معلومات المستخدم =============

@router.callback_query(F.data == "user_info")
async def user_info_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء البحث عن معلومات مستخدم"""
    await callback.message.answer(
        "👤 **أدخل آيدي المستخدم للحصول على معلوماته:**\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_user_info)

@router.message(AdminStates.waiting_user_info)
async def user_info_show(message: types.Message, state: FSMContext, db_pool):
    """عرض معلومات المستخدم"""
    try:
        user_id = int(message.text)
        
        from database import get_user_profile
        profile = await get_user_profile(db_pool, user_id)
        
        if not profile:
            await message.answer("⚠️ **المستخدم غير موجود**")
            await state.clear()
            return
        
        user = profile['user']
        deposits = profile['deposits']
        orders = profile['orders']
        
        join_date = user['created_at'].strftime("%Y-%m-%d %H:%M") if user.get('created_at') else "غير معروف"
        last_active = user['last_activity'].strftime("%Y-%m-%d %H:%M") if user.get('last_activity') else "غير معروف"
        manual_status = " (يدوي)" if user.get('manual_vip') else ""
        
        info_text = (
            f"👤 **معلومات المستخدم**\n\n"
            f"🆔 **الآيدي:** `{user['user_id']}`\n"
            f"👤 **اليوزر:** @{user['username'] or 'غير موجود'}\n"
            f"📝 **الاسم:** {user.get('first_name', '')} {user.get('last_name', '')}\n"
            f"💰 **الرصيد:** {user.get('balance', 0):,.0f} ل.س\n"
            f"⭐ **النقاط:** {user.get('total_points', 0)}\n"
            f"👑 **مستوى VIP:** {user.get('vip_level', 0)}{manual_status}\n"
            f"💰 **إجمالي الإنفاق:** {user.get('total_spent', 0):,.0f} ل.س\n"
            f"🔒 **الحالة:** {'🚫 محظور' if user.get('is_banned') else '✅ نشط'}\n"
            f"📅 **تاريخ التسجيل:** {join_date}\n"
            f"⏰ **آخر نشاط:** {last_active}\n"
            f"🔗 **كود الإحالة:** `{user.get('referral_code', 'لا يوجد')}`\n"
            f"👥 **تمت إحالته بواسطة:** {user.get('referred_by', 'لا يوجد')}\n\n"
            
            f"📊 **إحصائيات الإيداعات:**\n"
            f"• إجمالي الإيداعات: {deposits.get('total_count', 0)} عملية\n"
            f"• إجمالي المبالغ: {deposits.get('total_amount', 0):,.0f} ل.س\n"
            f"• الإيداعات المقبولة: {deposits.get('approved_count', 0)} عملية\n"
            f"• قيمة المقبولة: {deposits.get('approved_amount', 0):,.0f} ل.س\n\n"
            
            f"📊 **إحصائيات الطلبات:**\n"
            f"• إجمالي الطلبات: {orders.get('total_count', 0)} طلب\n"
            f"• إجمالي المبالغ: {orders.get('total_amount', 0):,.0f} ل.س\n"
            f"• الطلبات المكتملة: {orders.get('completed_count', 0)} طلب\n"
            f"• قيمة المكتملة: {orders.get('completed_amount', 0):,.0f} ل.س\n"
            f"• نقاط مكتسبة من الطلبات: {orders.get('total_points_earned', 0)}\n"
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔓 فك الحظر" if user.get('is_banned') else "🔒 حظر",
                                               callback_data=f"toggle_ban_{user['user_id']}"),
                    types.InlineKeyboardButton(text="💰 تعديل الرصيد", callback_data=f"edit_bal_{user['user_id']}"))
        builder.row(types.InlineKeyboardButton(text="⭐ إضافة نقاط", callback_data=f"add_points_{user['user_id']}"),
                    types.InlineKeyboardButton(text="👑 رفع مستوى VIP", callback_data=f"upgrade_vip_{user['user_id']}"))
        builder.row(types.InlineKeyboardButton(text="⬇️ خفض مستوى VIP", callback_data=f"downgrade_vip_{user['user_id']}"))
        
        await message.answer(info_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await state.clear()
        
    except ValueError:
        await message.answer("⚠️ **الرجاء إدخال آيدي صحيح (أرقام فقط)**")
        await state.clear()
    except Exception as e:
        logger.error(f"خطأ في معلومات المستخدم: {e}")
        await message.answer(f"❌ **حدث خطأ:** {str(e)}")
        await state.clear()

# ============= إدارة النقاط والرصيد =============

@router.callback_query(F.data.startswith("add_points_"))
async def add_points_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء إضافة نقاط لمستخدم"""
    try:
        user_id = int(callback.data.split("_")[2])
        await state.update_data(target_user=user_id)
        await callback.message.answer(f"⭐ **أدخل عدد النقاط لإضافتها للمستخدم {user_id}:**\n\nأو أرسل /cancel للإلغاء",
                                      reply_markup=get_cancel_keyboard())
        await state.set_state(AdminStates.waiting_points_amount)
    except Exception as e:
        logger.error(f"خطأ في بدء إضافة نقاط: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.message(AdminStates.waiting_points_amount)
async def add_points_finalize(message: types.Message, state: FSMContext, db_pool):
    """إضافة النقاط للمستخدم"""
    try:
        points = int(message.text)
        
        if points <= 0:
            return await message.answer("⚠️ يرجى إدخال رقم موجب:", reply_markup=get_cancel_keyboard())
        
        data = await state.get_data()
        user_id = data['target_user']
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT username, total_points FROM users WHERE user_id = $1", user_id)
            if not user:
                return await message.answer("❌ المستخدم غير موجود")
            
            await conn.execute("UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2", points, user_id)
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ''', user_id, points, 'admin_add', f'إضافة نقاط من الأدمن: {points}')
            
            new_total = await conn.fetchval("SELECT total_points FROM users WHERE user_id = $1", user_id)
        
        await message.answer(f"✅ تم إضافة {points} نقطة للمستخدم @{user['username']}\n⭐ الرصيد الجديد: {new_total}")
        
        try:
            await message.bot.send_message(user_id, f"✅ تم إضافة {points} نقطة إلى رصيدك!\n⭐ رصيدك الحالي: {new_total}")
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمستخدم {user_id}: {e}")
        
        await state.clear()
        
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 100):", reply_markup=get_cancel_keyboard())
    except Exception as e:
        logger.error(f"خطأ في إضافة نقاط: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

@router.callback_query(F.data.startswith("edit_bal_"))
async def edit_balance_from_info(callback: types.CallbackQuery, state: FSMContext):
    """تعديل الرصيد"""
    try:
        user_id = int(callback.data.split("_")[2])
        await state.update_data(target_user=user_id)
        await callback.message.answer(f"💰 **أدخل الرصيد الجديد للمستخدم {user_id}:**\n\nأو أرسل /cancel للإلغاء",
                                      reply_markup=get_cancel_keyboard())
        await state.set_state(AdminStates.waiting_balance_amount)
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.message(AdminStates.waiting_balance_amount)
async def finalize_add_balance(message: types.Message, state: FSMContext, db_pool):
    """إضافة رصيد يدوي"""
    try:
        amount = float(message.text)
    except ValueError:
        return await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 5000):", reply_markup=get_cancel_keyboard())
    
    data = await state.get_data()
    user_id = data['target_user']
    
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1, total_deposits = total_deposits + $1 WHERE user_id = $2", amount, user_id)
        user = await conn.fetchrow("SELECT username, balance, total_points FROM users WHERE user_id = $1", user_id)
    
    await message.answer(
        f"✅ **تمت إضافة الرصيد بنجاح**\n\n"
        f"👤 **المستخدم:** {user['username'] or 'بدون اسم'}\n"
        f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
        f"💳 **الرصيد الجديد:** {user['balance']:,.0f} ل.س\n"
        f"⭐ **النقاط:** {user['total_points']}",
        parse_mode="Markdown"
    )
    
    try:
        await message.bot.send_message(
            user_id,
            f"✅ **تم إضافة رصيد إلى حسابك!**\n\n"
            f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
            f"💳 **الرصيد الحالي:** {user['balance']:,.0f} ل.س",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"فشل إرسال إشعار للمستخدم {user_id}: {e}")
    
    await state.clear()

@router.callback_query(F.data.startswith("toggle_ban_"))
async def toggle_ban_from_info(callback: types.CallbackQuery, db_pool):
    """تبديل حالة الحظر"""
    try:
        user_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT is_banned FROM users WHERE user_id = $1", user_id)
            
            if user:
                new_status = not user['is_banned']
                await conn.execute("UPDATE users SET is_banned = $1 WHERE user_id = $2", new_status, user_id)
                
                status_text = "محظور" if new_status else "نشط"
                await callback.message.answer(f"✅ تم تغيير حالة المستخدم إلى: {status_text}")
                
                try:
                    await callback.bot.send_message(
                        user_id,
                        f"⚠️ **تم تغيير حالة حسابك**\n\n"
                        f"الحالة الجديدة: {'🚫 محظور' if new_status else '✅ نشط'}"
                    )
                except:
                    pass
            else:
                await callback.answer("المستخدم غير موجود", show_alert=True)
                
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# ============= تعديل سعر الصرف =============

@router.callback_query(F.data == "edit_rate")
async def start_edit_rate(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل سعر الصرف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_exchange_rate
    current_rate = await get_exchange_rate(db_pool)
    
    await callback.message.answer(
        f"💵 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س\n\n"
        f"📝 **أدخل السعر الجديد:**\n\n"
        f"أو أرسل /cancel للإلغاء",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_new_rate)

@router.message(AdminStates.waiting_new_rate)
async def save_new_rate(message: types.Message, state: FSMContext, db_pool):
    """حفظ سعر الصرف الجديد"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_rate = float(message.text)
        
        if new_rate <= 0:
            return await message.answer("⚠️ يرجى إدخال رقم موجب:", reply_markup=get_cancel_keyboard())
        
        from database import set_exchange_rate
        await set_exchange_rate(db_pool, new_rate)
        
        import config
        config.USD_TO_SYP = new_rate
        
        await message.answer(f"✅ تم تحديث سعر الصرف إلى {new_rate}")
        
        for mod_id in MODERATORS:
            if mod_id and mod_id != message.from_user.id:
                try:
                    await message.bot.send_message(mod_id, f"ℹ️ تم تغيير السعر إلى {new_rate}")
                except:
                    pass
        
        await state.clear()
        
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 118):", reply_markup=get_cancel_keyboard())
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# ============= إرسال رسالة جماعية =============

@router.callback_query(F.data == "broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """بدء إرسال رسالة للجميع"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.answer(
        "📢 **إرسال رسالة للجميع**\n\n"
        "أدخل الرسالة التي تريد إرسالها لجميع المستخدمين:\n\n"
        "✏️ يمكنك استخدام Markdown للتنسيق:\n"
        "• **نص عريض**\n"
        "• *نص مائل*\n"
        "• `كود`\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminStates.waiting_broadcast_msg)
# ============= إرسال رسالة جماعية (تابع) =============

@router.message(AdminStates.waiting_broadcast_msg)
async def send_broadcast(message: types.Message, state: FSMContext, db_pool, bot: Bot):
    """إرسال رسالة لجميع المستخدمين مع إمكانية الإلغاء"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء الإرسال.")
        return
    
    broadcast_text = message.text
    
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users WHERE NOT is_banned")
        total_users = len(users)
        banned_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned")
    
    if total_users == 0:
        await message.answer("⚠️ لا يوجد مستخدمين في قاعدة البيانات")
        await state.clear()
        return
    
    try:
        await bot.send_message(
            message.from_user.id,
            f"📢 **معاينة الرسالة:**\n\n{broadcast_text}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="✅ تأكيد الإرسال", callback_data="confirm_broadcast"),
                    types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_broadcast"))
        builder.row(types.InlineKeyboardButton(text="📝 تعديل الرسالة", callback_data="edit_broadcast"))
        
        await message.answer(
            f"📊 **معلومات الإرسال**\n\n"
            f"👥 عدد المستلمين: {total_users} مستخدم\n"
            f"🚫 المحظورين: {banned_count} (لن يستلموا)\n\n"
            f"هل أنت متأكد من إرسال الرسالة؟",
            reply_markup=builder.as_markup()
        )
        
        await state.update_data(broadcast_text=broadcast_text, total_users=total_users)
        
    except Exception as e:
        await message.answer(
            f"❌ **خطأ في تنسيق Markdown**\n\n"
            f"الخطأ: {str(e)}\n\n"
            f"تأكد من إغلاق جميع الرموز بشكل صحيح:\n"
            f"• `**نص**` للنص العريض\n"
            f"• `*نص*` للنص المائل\n"
            f"• `` `نص` `` للكود"
        )

@router.callback_query(F.data == "edit_broadcast")
async def edit_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """تعديل رسالة البث"""
    await callback.message.edit_text(
        "📝 **أدخل الرسالة الجديدة:**\n\n"
        "✏️ يمكنك استخدام Markdown للتنسيق:\n"
        "• **نص عريض**\n"
        "• *نص مائل*\n"
        "• `كود`\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_broadcast")
async def confirm_broadcast(callback: types.CallbackQuery, state: FSMContext, bot: Bot, db_pool):
    """تأكيد إرسال البث"""
    data = await state.get_data()
    broadcast_text = data.get('broadcast_text')
    total_users = data.get('total_users', 0)
    
    if not broadcast_text:
        await callback.answer("❌ لا توجد رسالة للإرسال", show_alert=True)
        await state.clear()
        return
    
    await callback.message.edit_text("⏳ **جاري الإرسال...**\nقد يستغرق هذا بعض الوقت.")
    
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users WHERE NOT is_banned")
    
    success_count = 0
    failed_count = 0
    failed_users = []
    
    for i, user in enumerate(users):
        user_id = user['user_id']
        
        if user_id == callback.from_user.id:
            continue
        
        try:
            await bot.send_message(
                user_id,
                f"📢 **رسالة من الإدارة:**\n\n{broadcast_text}",
                parse_mode=ParseMode.MARKDOWN
            )
            success_count += 1
            
        except Exception:
            try:
                await bot.send_message(
                    user_id,
                    f"📢 رسالة من الإدارة:\n\n{broadcast_text}"
                )
                success_count += 1
            except Exception:
                failed_count += 1
                failed_users.append(str(user_id))
        
        if (i + 1) % 10 == 0:
            await callback.message.edit_text(
                f"⏳ **جاري الإرسال...**\n"
                f"✅ تم: {success_count}\n"
                f"❌ فشل: {failed_count}\n"
                f"📊 المتبقي: {total_users - (i + 1)}"
            )
        
        await asyncio.sleep(0.05)
    
    result_text = (
        f"✅ **تم إرسال الرسالة**\n\n"
        f"📊 **نتيجة الإرسال:**\n"
        f"• ✅ نجح: {success_count}\n"
        f"• ❌ فشل: {failed_count}\n"
        f"• 👥 الإجمالي: {total_users}\n\n"
    )
    
    if failed_users:
        failed_sample = failed_users[:10]
        result_text += f"⚠️ أمثلة على المستخدمين الذين فشل الإرسال لهم:\n"
        result_text += f"`{', '.join(failed_sample)}`\n"
        if len(failed_users) > 10:
            result_text += f"... و{len(failed_users) - 10} آخرين\n"
    
    await callback.message.edit_text(result_text)
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO logs (user_id, action, details, created_at)
            VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
        ''', callback.from_user.id, 'broadcast', 
           f'إرسال رسالة جماعية - نجح: {success_count}, فشل: {failed_count}')
    
    await state.clear()

@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """إلغاء البث"""
    await state.clear()
    await callback.message.edit_text("✅ تم إلغاء الإرسال.")

# ============= معالجة طلبات الشحن من المجموعة =============

@router.callback_query(F.data.startswith("appr_dep_"))
async def approve_deposit_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """موافقة على طلب شحن من المجموعة"""
    try:
        logger.info(f"📩 استقبال موافقة شحن: {callback.data}")
        
        parts = callback.data.split("_")
        if len(parts) >= 4:
            _, _, uid, amt = parts
            user_id = int(uid)
            amount = float(amt)
        else:
            await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
            return
        
        logger.info(f"✅ موافقة على شحن: user={user_id}, amount={amount}")
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT username, balance FROM users WHERE user_id = $1", user_id)
            
            if not user:
                await conn.execute("INSERT INTO users (user_id, balance, created_at) VALUES ($1, 0, CURRENT_TIMESTAMP)", user_id)
                user = {'username': None, 'balance': 0}
            
            new_balance = user['balance'] + amount
            await conn.execute(
                "UPDATE users SET balance = $1, total_deposits = total_deposits + $2, last_activity = CURRENT_TIMESTAMP WHERE user_id = $3",
                new_balance, amount, user_id
            )
            
            await conn.execute('''
                UPDATE deposit_requests 
                SET status = 'approved', updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM deposit_requests 
                    WHERE user_id = $1 AND status = 'pending' AND amount_syp = $2
                    ORDER BY created_at DESC 
                    LIMIT 1
                )
            ''', user_id, amount)
        
        damascus_time = get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            await bot.send_message(
                user_id,
                f"✅ **تم تأكيد عملية الشحن بنجاح!**\n\n"
                f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
                f"💳 **الرصيد الحالي:** {new_balance:,.0f} ل.س\n"
                f"📅 **التاريخ:** {damascus_time}\n\n"
                f"🔸 **شكراً لاستخدامك خدماتنا**",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة للمستخدم {user_id}: {e}")
        
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text + f"\n\n✅ **تمت الموافقة على الطلب**\n📅 **بتاريخ:** {damascus_time}"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None)
        except Exception as e:
            logger.error(f"❌ فشل تحديث رسالة المجموعة: {e}")
        
        await callback.answer("✅ تمت الموافقة بنجاح")
        
    except Exception as e:
        logger.error(f"❌ خطأ عام في موافقة الشحن: {e}")
        import traceback
        traceback.print_exc()
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reje_dep_"))
async def reject_deposit_from_group(callback: types.CallbackQuery, bot: Bot, db_pool):
    """رفض طلب شحن من المجموعة"""
    try:
        logger.info(f"📩 استقبال رفض شحن: {callback.data}")
        user_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE deposit_requests 
                SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM deposit_requests 
                    WHERE user_id = $1 AND status = 'pending'
                    ORDER BY created_at DESC 
                    LIMIT 1
                )
            ''', user_id)
        
        damascus_time = get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            await bot.send_message(
                user_id,
                f"❌ **نعتذر، تم رفض طلب الشحن الخاص بك.**\n\n"
                f"📅 **تاريخ الرفض:** {damascus_time}\n"
                f"🔸 **الأسباب المحتملة:**\n"
                f"• بيانات التحويل غير صحيحة\n"
                f"• لم يتم العثور على التحويل\n"
                f"• المشكلة فنية\n\n"
                f"📞 **للمساعدة تواصل مع الدعم.**",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة الرفض للمستخدم {user_id}: {e}")
        
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text + f"\n\n❌ **تم رفض الطلب**\n📅 **بتاريخ:** {damascus_time}"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None)
        except Exception as e:
            logger.error(f"❌ فشل تحديث رسالة المجموعة: {e}")
        
        await callback.answer("❌ تم رفض الطلب")
        
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الشحن: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# ============= معالجة طلبات التطبيقات من المجموعة =============

@router.callback_query(F.data.startswith("appr_order_"))
async def approve_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """موافقة على طلب تطبيق من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.id = $1
            ''', order_id)
            
            if order:
                await conn.execute("UPDATE orders SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
                
                points = order['points_earned'] or 0
                
                try:
                    message_text = (
                        f"✅ تمت الموافقة على طلبك #{order_id}\n\n"
                        f"📱 التطبيق: {order['app_name']}\n"
                        f"📦 الكمية: {order['quantity']}\n"
                        f"🎯 المستهدف: {order['target_id']}\n"
                        f"⭐ نقاط مكتسبة: +{points}\n\n"
                        f"⏳ جاري تنفيذ طلبك عبر النظام..."
                    )
                    await bot.send_message(order['user_id'], message_text)
                except Exception as e:
                    logger.error(f"❌ فشل إرسال رسالة للمستخدم: {e}")
                
                builder = InlineKeyboardBuilder()
                builder.row(
                    types.InlineKeyboardButton(text="✅ تم التنفيذ", callback_data=f"compl_order_{order_id}"),
                    types.InlineKeyboardButton(text="❌ تعذر التنفيذ", callback_data=f"fail_order_{order_id}"),
                    width=2
                )
                
                new_text = callback.message.text + "\n\n🔄 **جاري التنفيذ...**"
                await callback.message.edit_text(new_text, reply_markup=builder.as_markup())
                
                await callback.answer("✅ تمت الموافقة على الطلب")
            else:
                await callback.answer("❌ الطلب غير موجود", show_alert=True)
                
    except Exception as e:
        logger.error(f"❌ خطأ في موافقة الطلب: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reje_order_"))
async def reject_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """رفض طلب تطبيق من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT user_id, total_amount_syp FROM orders WHERE id = $1", order_id)
            
            if order:
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", order['total_amount_syp'], order['user_id'])
                await conn.execute("UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
                
                try:
                    await bot.send_message(
                        order['user_id'],
                        f"❌ **تم رفض طلبك #{order_id}**\n\n"
                        f"💰 **تم إعادة:** {order['total_amount_syp']:,.0f} ل.س لرصيدك\n\n"
                        f"🔸 **الأسباب المحتملة:**\n"
                        "• مشكلة في معلومات الحساب المستهدف\n"
                        "• الخدمة غير متوفرة حالياً\n"
                        "• مشكلة فنية في النظام\n\n"
                        f"📞 **للمساعدة تواصل مع الدعم.**",
                        parse_mode="Markdown"
                    )
                except:
                    pass
                
                await callback.message.edit_text(
                    callback.message.text + "\n\n❌ **تم رفض الطلب وإعادة الرصيد**",
                    reply_markup=None
                )
            else:
                await callback.answer("الطلب غير موجود", show_alert=True)
                
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الطلب: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("compl_order_"))
async def complete_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """تأكيد تنفيذ الطلب من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.id = $1
            ''', order_id)
            
            if not order:
                await callback.answer("❌ الطلب غير موجود", show_alert=True)
                return
            
            from database import get_points_per_order
            points = await get_points_per_order(db_pool)
            
            await conn.execute("UPDATE orders SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
            
            await conn.execute(
                "UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2",
                points, order['user_id']
            )
            
            await conn.execute("UPDATE orders SET points_earned = $1 WHERE id = $2", points, order_id)
            
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ''', order['user_id'], points, 'order_completed', f'نقاط من طلب مكتمل #{order_id}')
            
            from database import update_user_vip
            vip_info = await update_user_vip(db_pool, order['user_id'])
            
            total_spent = await conn.fetchval('''
                SELECT COALESCE(SUM(total_amount_syp), 0) 
                FROM orders 
                WHERE user_id = $1 AND status = 'completed'
            ''', order['user_id'])
            
            if vip_info:
                vip_discount = vip_info.get('discount', 0)
                vip_level = vip_info.get('level', 0)
            else:
                vip_discount = 0
                vip_level = 0
                
            vip_icons = ["⚪", "🔵", "🟣", "🟡"]
            vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "⚪"
            
            user_points = await conn.fetchval("SELECT total_points FROM users WHERE user_id = $1", order['user_id']) or 0
            
            try:
                await bot.send_message(
                    order['user_id'],
                    f"✅ **تم تنفيذ طلبك #{order_id} بنجاح!**\n\n"
                    f"📱 التطبيق: {order['app_name']}\n"
                    f"⭐ نقاط مكتسبة: +{points}\n"
                    f"💰 رصيد النقاط الجديد: {user_points}\n"
                    f"👑 مستواك: {vip_icon} VIP {vip_level} (خصم {vip_discount}%)\n\n"
                    f"شكراً لاستخدامك خدماتنا"
                )
            except Exception as e:
                logger.error(f"❌ فشل إرسال رسالة للمستخدم: {e}")
            
            await callback.message.edit_text(
                callback.message.text.replace("🔄 **جاري التنفيذ...**", "") + "\n\n✅ **تم التنفيذ بنجاح**",
                reply_markup=None
            )
            
            await callback.answer("✅ تم تأكيد التنفيذ")
                
    except Exception as e:
        logger.error(f"❌ خطأ في تأكيد التنفيذ: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("fail_order_"))
async def fail_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """تعذر تنفيذ الطلب من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT user_id, total_amount_syp FROM orders WHERE id = $1", order_id)
            
            if order:
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", order['total_amount_syp'], order['user_id'])
                await conn.execute("UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
                
                try:
                    await bot.send_message(
                        order['user_id'],
                        f"❌ **تعذر تنفيذ طلبك #{order_id}**\n\n"
                        f"💰 تم إعادة {order['total_amount_syp']:,.0f} ل.س لرصيدك\n"
                        f"⭐ لم تتم إضافة نقاط لهذا الطلب\n\n"
                        f"نعتذر عن الإزعاج، يرجى المحاولة لاحقاً"
                    )
                except Exception as e:
                    logger.error(f"❌ فشل إرسال رسالة للمستخدم: {e}")
                
                await callback.message.edit_text(
                    callback.message.text.replace("🔄 **جاري التنفيذ...**", "") + "\n\n❌ **تعذر التنفيذ وتم إعادة الرصيد**",
                    reply_markup=None
                )
                
                await callback.answer("❌ تم تحديث حالة الطلب")
            else:
                await callback.answer("❌ الطلب غير موجود", show_alert=True)
                
    except Exception as e:
        logger.error(f"❌ خطأ في تعذر التنفيذ: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# ============= رفع مستوى VIP =============

@router.callback_query(F.data.startswith("upgrade_vip_"))
async def upgrade_vip_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء رفع مستوى VIP لمستخدم"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user=user_id)
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT username, first_name, vip_level, discount_percent, total_spent FROM users WHERE user_id = $1",
            user_id
        )
    
    if not user:
        return await callback.answer("المستخدم غير موجود", show_alert=True)
    
    username = user['username'] or user['first_name'] or str(user_id)
    current_vip = user['vip_level']
    current_discount = user['discount_percent']
    total_spent = user['total_spent']
    
    text = (
        f"👑 **رفع مستوى VIP للمستخدم**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"📊 المستوى الحالي: VIP {current_vip} (خصم {current_discount}%)\n"
        f"💰 إجمالي المشتريات: {total_spent:,.0f} ل.س\n\n"
        f"اختر المستوى الجديد:"
    )
    
    builder = InlineKeyboardBuilder()
    levels = [
        ("⚪ VIP 0 (0%)", 0, 0), ("🔵 VIP 1 (1%)", 1, 1), ("🟣 VIP 2 (2%)", 2, 2),
        ("🟡 VIP 3 (3%)", 3, 3),
    ]
    
    for btn_text, level, discount in levels:
        if level != current_vip:
            builder.row(types.InlineKeyboardButton(text=btn_text, callback_data=f"set_vip_{user_id}_{level}_{discount}"))
    
    builder.row(types.InlineKeyboardButton(text="🎯 خصم مخصص", callback_data=f"custom_discount_{user_id}"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"user_info_cancel"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("set_vip_"))
async def set_vip_level(callback: types.CallbackQuery, db_pool):
    """تحديد مستوى VIP للمستخدم - يدوي"""
    parts = callback.data.split("_")
    user_id = int(parts[2])
    level = int(parts[3])
    discount = int(parts[4])
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            UPDATE users 
            SET vip_level = $1, discount_percent = $2, manual_vip = TRUE
            WHERE user_id = $3
        ''', level, discount, user_id)
        
        user = await conn.fetchrow("SELECT username, first_name FROM users WHERE user_id = $1", user_id)
    
    username = user['username'] or user['first_name'] or str(user_id)
    
    await callback.message.edit_text(
        f"✅ **تم رفع المستوى يدوياً!**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"👑 المستوى الجديد: VIP {level}\n"
        f"💰 نسبة الخصم: {discount}%\n\n"
        f"⚠️ هذا المستوى يدوي ولن يتغير تلقائياً."
    )
    
    try:
        vip_icons = ["⚪", "🔵", "🟣", "🟡"]
        icon = vip_icons[level] if level < len(vip_icons) else "⭐"
        await callback.bot.send_message(
            user_id,
            f"🎉 **تم ترقية مستواك في البوت يدوياً!**\n\n"
            f"{icon} مستواك الجديد: VIP {level}\n"
            f"💰 نسبة الخصم: {discount}%\n\n"
            f"✨ هذا المستوى خاص ولن يتغير تلقائياً."
        )
    except:
        pass

@router.callback_query(F.data.startswith("custom_discount_"))
async def custom_discount_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إعطاء خصم مخصص"""
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user=user_id)
    
    await callback.message.edit_text(
        f"🎯 **إعطاء خصم مخصص**\n\n"
        f"أدخل نسبة الخصم المطلوبة (0-100):\n"
        f"مثال: `15` تعني 15% خصم\n\n"
        f"❌ للإلغاء أرسل /cancel"
    )
    await state.set_state(AdminStates.waiting_vip_discount)

@router.message(AdminStates.waiting_vip_discount)
async def set_custom_discount(message: types.Message, state: FSMContext, db_pool):
    """تحديد خصم مخصص لمستخدم"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "/رجوع", "🔙 رجوع للقائمة"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    try:
        discount = float(message.text.strip())
        if discount < 0 or discount > 100:
            return await message.answer("❌ نسبة الخصم يجب أن تكون بين 0 و 100:", reply_markup=get_cancel_keyboard())
        
        data = await state.get_data()
        user_id = data['target_user']
        
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET discount_percent = $1, manual_vip = TRUE 
                WHERE user_id = $2
            ''', discount, user_id)
            
            user = await conn.fetchrow("SELECT username, first_name, vip_level FROM users WHERE user_id = $1", user_id)
        
        username = user['username'] or user['first_name'] or str(user_id)
        vip_level = user['vip_level']
        
        await message.answer(
            f"✅ **تم تحديث الخصم بنجاح**\n\n"
            f"👤 المستخدم: @{username}\n"
            f"🆔 الآيدي: `{user_id}`\n"
            f"👑 مستوى VIP: {vip_level}\n"
            f"💰 نسبة الخصم الجديدة: {discount}%"
        )
        
        try:
            await message.bot.send_message(
                user_id,
                f"🎁 **تم تعديل نسبة الخصم في حسابك!**\n\n"
                f"💰 نسبة الخصم الجديدة: {discount}%\n"
                f"👑 مستواك الحالي: VIP {vip_level}\n\n"
                f"شكراً لاستخدامك خدماتنا!"
            )
        except:
            pass
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ يرجى إدخال رقم صحيح:", reply_markup=get_cancel_keyboard())

@router.callback_query(F.data.startswith("downgrade_vip_"))
async def downgrade_vip_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء خفض مستوى VIP لمستخدم"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user=user_id)
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT username, first_name, vip_level, discount_percent, manual_vip FROM users WHERE user_id = $1",
            user_id
        )
    
    if not user:
        return await callback.answer("المستخدم غير موجود", show_alert=True)
    
    username = user['username'] or user['first_name'] or str(user_id)
    current_vip = user['vip_level']
    current_discount = user['discount_percent']
    manual_status = " (يدوي)" if user['manual_vip'] else ""
    
    text = (
        f"⚠️ **خفض مستوى VIP للمستخدم**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"📊 المستوى الحالي: VIP {current_vip}{manual_status} (خصم {current_discount}%)\n\n"
        f"اختر المستوى الجديد:"
    )
    
    builder = InlineKeyboardBuilder()
    for level in range(0, current_vip):
        if level == 0:
            discount = 0; btn_text = f"⚪ VIP 0 (0%)"
        elif level == 1:
            discount = 1; btn_text = f"🔵 VIP 1 (1%)"
        elif level == 2:
            discount = 2; btn_text = f"🟣 VIP 2 (2%)"
        elif level == 3:
            discount = 3; btn_text = f"🟡 VIP 3 (3%)"
            continue
        
        builder.row(types.InlineKeyboardButton(text=btn_text, callback_data=f"downgrade_to_{user_id}_{level}_{discount}"))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"user_info_cancel"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("downgrade_to_"))
async def downgrade_vip_ask_reason(callback: types.CallbackQuery, state: FSMContext):
    """طلب سبب خفض المستوى"""
    parts = callback.data.split("_")
    user_id = int(parts[2])
    new_level = int(parts[3])
    new_discount = int(parts[4])
    
    await state.update_data(target_user=user_id, new_level=new_level, new_discount=new_discount)
    
    await callback.message.edit_text(
        f"⚠️ **خفض مستوى VIP**\n\n"
        f"المستوى الجديد: VIP {new_level} (خصم {new_discount}%)\n\n"
        f"📝 **أدخل سبب خفض المستوى** (سيتم إرساله للمستخدم):\n"
        f"مثال: عدم الالتزام بشروط الاستخدام\n\n"
        f"أو أرسل /skip لتخطي إرسال سبب"
    )
    await state.set_state(AdminStates.waiting_vip_downgrade_reason)

@router.message(AdminStates.waiting_vip_downgrade_reason)
async def downgrade_vip_execute(message: types.Message, state: FSMContext, db_pool, bot: Bot):
    """تنفيذ خفض مستوى VIP مع إرسال تحذير"""
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    user_id = data['target_user']
    new_level = data['new_level']
    new_discount = data['new_discount']
    
    reason = None
    if message.text and message.text != "/skip":
        reason = message.text.strip()
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            UPDATE users 
            SET vip_level = $1, discount_percent = $2, manual_vip = TRUE
            WHERE user_id = $3
        ''', new_level, new_discount, user_id)
        
        user = await conn.fetchrow("SELECT username, first_name FROM users WHERE user_id = $1", user_id)
    
    username = user['username'] or user['first_name'] or str(user_id)
    
    admin_text = (
        f"✅ **تم خفض مستوى VIP بنجاح**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"👑 المستوى الجديد: VIP {new_level}\n"
        f"💰 نسبة الخصم: {new_discount}%\n"
    )
    
    if reason:
        admin_text += f"📝 السبب: {reason}\n"
    
    admin_text += f"\n⚠️ تم إرسال تحذير للمستخدم."
    
    await message.answer(admin_text)
    
    try:
        user_message = (
            f"⚠️ **تم تعديل مستواك في البوت**\n\n"
            f"👑 مستواك الجديد: VIP {new_level}\n"
            f"💰 نسبة الخصم: {new_discount}%\n\n"
        )
        
        if reason:
            user_message += f"📝 **السبب:** {reason}\n\n"
        
        user_message += (
            f"🔸 هذا التعديل نهائي ولن يتغير تلقائياً.\n"
            f"📞 للاستفسار، تواصل مع الدعم."
        )
        
        await bot.send_message(user_id, user_message)
    except Exception as e:
        await message.answer(f"❌ فشل إرسال إشعار للمستخدم: {e}")
    
    await state.clear()

@router.callback_query(F.data == "user_info_cancel")
async def user_info_cancel(callback: types.CallbackQuery):
    """إلغاء والعودة لمعلومات المستخدم"""
    await callback.message.edit_text("✅ تم الإلغاء")

@router.message(F.text.in_(["🔙 رجوع للقائمة", "/رجوع", "/cancel"]))
async def admin_back_handler(message: types.Message, state: FSMContext, db_pool):
    """الرجوع من أي عملية إدارية"""
    current_state = await state.get_state()
    
    if current_state is not None:
        await state.clear()
    
    from database import is_admin_user
    is_admin_flag = await is_admin_user(db_pool, message.from_user.id)
    
    if is_admin_flag:
        await message.answer(
            "👋 تم الإلغاء. استخدم /admin للعودة للوحة التحكم",
            reply_markup=get_main_menu_keyboard(is_admin_flag)
        )
    else:
        await message.answer(
            "✅ تم الإلغاء",
            reply_markup=get_back_keyboard()
        )
