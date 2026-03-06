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

# العودة للوحة التحكم
@router.callback_query(F.data.in_(["back_to_admin", "back_to_admin_panel"]))
async def back_to_admin_panel(callback: types.CallbackQuery, db_pool):
    await admin_panel(callback.message, db_pool)