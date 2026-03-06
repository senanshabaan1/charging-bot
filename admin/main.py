# admin/main.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from config import ADMIN_ID, MODERATORS
from handlers.keyboards import get_main_menu_keyboard, get_cancel_keyboard
from utils import is_admin, safe_edit_message, get_formatted_damascus_time

logger = logging.getLogger(__name__)
router = Router(name="admin_main")

# ✅ تم نقل is_admin إلى utils.py



# معالج الإلغاء العام
@router.message(F.text.in_(["❌ إلغاء", "/cancel", "/الغاء", "/رجوع"]))
async def global_cancel_handler(message: types.Message, state: FSMContext, db_pool):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    
    from database import is_admin_user
    is_admin_user_flag = await is_admin_user(db_pool, message.from_user.id)
    
    await message.answer(
        "✅ تم إلغاء العملية",
        reply_markup=get_main_menu_keyboard(is_admin_user_flag)
    )

# لوحة التحكم الرئيسية
@router.message(Command("admin"))
async def admin_panel(message: types.Message, db_pool):
    if not is_admin(message.from_user.id):
        return

    from database import get_bot_status
    bot_status = await get_bot_status(db_pool)
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"

    buttons_data = [
        ("📈 سعر الصرف", "edit_rate"),
        ("📊 الإحصائيات", "bot_stats"),
        ("📢 رسالة للكل", "broadcast"),
        ("👤 معلومات مستخدم", "user_info"),
        ("⭐ إدارة النقاط", "manage_points"),
        ("💳 الأكثر إيداعاً", "top_deposits"),
        ("🛒 الأكثر طلبات", "top_orders"),
        ("🔗 الأكثر إحالة", "top_referrals"),
        ("⭐ الأكثر نقاط", "top_points"),
        ("👥 إحصائيات VIP", "vip_stats"),
        ("📊 تقارير ونسخ", "reports_menu"),
        ("➕ إضافة منتج", "add_product"),
        ("✏️ تعديل منتج", "edit_product"),
        ("🗑️ حذف منتج", "delete_product"),
        ("📱 عرض المنتجات", "list_products"),
        ("📞 أرقام سيرياتل", "edit_syriatel"),
        ("🔄 تشغيل/إيقاف", "toggle_bot"),
        ("⚠️ تصفير البوت", "reset_bot"),
        ("👑 إدارة المشرفين", "manage_admins"),
        ("✏️ رسالة الصيانة", "edit_maintenance"),
        ("✉️ رسالة لمستخدم", "send_custom_message"),
        ("🔄 تفعيل/إيقاف التطبيقات", "manage_apps_status"),
        ("🎮 إدارة خيارات الألعاب", "manage_options"),
        ("📁 إدارة الأقسام", "manage_categories"),
        ("➕ إضافة قسم", "add_category"),
    ]
    
    builder = InlineKeyboardBuilder()
    for text, callback in buttons_data:
        builder.add(types.InlineKeyboardButton(text=text, callback_data=callback))
    builder.adjust(3)
    
    await message.answer(
        f"🛠 **لوحة تحكم الإدارة**\n\n"
        f"حالة البوت: {status_text}\n\n"
        f"🔸 **اختر الإجراء المطلوب:**",
        reply_markup=builder.as_markup(),
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

    builder = InlineKeyboardBuilder()
    
    # نفس الأزرار
    builder.add(
        types.InlineKeyboardButton(text="📈 سعر الصرف", callback_data="edit_rate"),
        types.InlineKeyboardButton(text="📊 الإحصائيات", callback_data="bot_stats"),
        types.InlineKeyboardButton(text="📢 رسالة للكل", callback_data="broadcast"),
        types.InlineKeyboardButton(text="👤 معلومات مستخدم", callback_data="user_info"),
        types.InlineKeyboardButton(text="⭐ إدارة النقاط", callback_data="manage_points"),
        types.InlineKeyboardButton(text="💳 الأكثر إيداعاً", callback_data="top_deposits"),
        types.InlineKeyboardButton(text="🛒 الأكثر طلبات", callback_data="top_orders"),
        types.InlineKeyboardButton(text="🔗 الأكثر إحالة", callback_data="top_referrals"),
        types.InlineKeyboardButton(text="⭐ الأكثر نقاط", callback_data="top_points"),
        types.InlineKeyboardButton(text="👥 إحصائيات VIP", callback_data="vip_stats"),
        types.InlineKeyboardButton(text="📊 تقارير ونسخ", callback_data="reports_menu"),
        types.InlineKeyboardButton(text="➕ إضافة منتج", callback_data="add_product"),
        types.InlineKeyboardButton(text="✏️ تعديل منتج", callback_data="edit_product"),
        types.InlineKeyboardButton(text="🗑️ حذف منتج", callback_data="delete_product"),
        types.InlineKeyboardButton(text="📱 عرض المنتجات", callback_data="list_products"),
        types.InlineKeyboardButton(text="📞 أرقام سيرياتل", callback_data="edit_syriatel"),
        types.InlineKeyboardButton(text="🔄 تشغيل/إيقاف", callback_data="toggle_bot"),
        types.InlineKeyboardButton(text="⚠️ تصفير البوت", callback_data="reset_bot"),
        types.InlineKeyboardButton(text="👑 إدارة المشرفين", callback_data="manage_admins"),
        types.InlineKeyboardButton(text="✏️ رسالة الصيانة", callback_data="edit_maintenance"),
        types.InlineKeyboardButton(text="✉️ رسالة لمستخدم", callback_data="send_custom_message"),
        types.InlineKeyboardButton(text="🔄 تفعيل/إيقاف التطبيقات", callback_data="manage_apps_status"),
        types.InlineKeyboardButton(text="🎮 إدارة خيارات الألعاب", callback_data="manage_options"),
        types.InlineKeyboardButton(text="📁 إدارة الأقسام", callback_data="manage_categories"),
        types.InlineKeyboardButton(text="➕ إضافة قسم", callback_data="add_category"),
    )
    
    # توزيع 3 أزرار في كل صف
    builder.adjust(3)
    
    await callback.message.edit_text(
        f"🛠 **لوحة تحكم الإدارة**\n\n"
        f"حالة البوت: {status_text}\n\n"
        f"🔸 **اختر الإجراء المطلوب:**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )