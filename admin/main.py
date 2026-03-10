# admin/main.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import time
from typing import List, Tuple
from config import ADMIN_ID, MODERATORS
from handlers.keyboards import get_main_menu_keyboard, get_cancel_keyboard
from utils import is_admin, safe_edit_message, get_formatted_damascus_time
from cache import cached, clear_cache  # ✅ استيراد الكاش

logger = logging.getLogger(__name__)
router = Router(name="admin_main")

# ✅ ثوابت للأداء
ADMIN_BUTTONS_PER_ROW = 3
CACHE_TTL_BOT_STATUS = 30  # 30 ثانية

# ✅ قائمة أزرار لوحة التحكم (ثابتة)
ADMIN_BUTTONS: List[Tuple[str, str]] = [
    ("📈 سعر الصرف", "edit_rate"),
    ("📊 الإحصائيات", "bot_stats"),
    ("📢 رسالة للكل", "broadcast"),
    ("👤 معلومات مستخدم", "user_info"),
    ("⭐ إدارة النقاط", "manage_points"),
    ("📊 تقارير ونسخ", "reports_menu"),
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
    ("🏠 القائمة الرئيسية", "back_to_main"),
]

# ✅ كاش لحالة البوت
@cached(ttl=CACHE_TTL_BOT_STATUS, key_prefix="bot_status")
async def get_cached_bot_status(db_pool) -> Tuple[bool, str]:
    """جلب حالة البوت مع كاش 30 ثانية"""
    from database import get_bot_status
    status = await get_bot_status(db_pool)
    return status, "🟢 يعمل" if status else "🔴 متوقف"

# معالج الإلغاء العام
@router.message(F.text.in_(["❌ إلغاء", "/cancel", "/الغاء", "/رجوع"]))
async def global_cancel_handler(message: types.Message, state: FSMContext, db_pool):
    """معالج الإلغاء الموحد"""
    current_state = await state.get_state()
    if current_state is not None:
        logger.info(f"🔄 إلغاء الحالة {current_state} للمستخدم {message.from_user.id}")
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
    """عرض لوحة تحكم المشرفين"""
    if not is_admin(message.from_user.id):
        logger.warning(f"⚠️ محاولة وصول غير مصرح بها من {message.from_user.id}")
        return

    start_time = time.time()
    
    # ✅ استخدام الكاش لحالة البوت
    bot_status, status_text = await get_cached_bot_status(db_pool)
    
    # ✅ إنشاء الكيبورد
    builder = InlineKeyboardBuilder()
    for text, callback in ADMIN_BUTTONS:
        builder.add(types.InlineKeyboardButton(text=text, callback_data=callback))
    builder.adjust(ADMIN_BUTTONS_PER_ROW)
    
    elapsed_time = time.time() - start_time
    logger.info(f"✅ عرض لوحة التحكم للمشرف {message.from_user.id} في {elapsed_time:.3f} ثانية")
    
    await message.answer(
        f"🛠 **لوحة تحكم الإدارة**\n\n"
        f"حالة البوت: {status_text}\n"
        f"👤 المشرف: @{message.from_user.username or 'مشرف'}\n"
        f"🕐 {get_formatted_damascus_time()}\n\n"
        f"🔸 **اختر الإجراء المطلوب:**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# العودة للوحة التحكم
@router.callback_query(F.data == "back_to_admin")
@router.callback_query(F.data == "back_to_admin_panel")
async def back_to_admin_panel(callback: types.CallbackQuery, db_pool):
    """العودة للوحة التحكم الرئيسية"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    start_time = time.time()
    
    # ✅ استخدام الكاش لحالة البوت
    bot_status, status_text = await get_cached_bot_status(db_pool)
    
    # ✅ إنشاء الكيبورد
    builder = InlineKeyboardBuilder()
    for text, callback_data in ADMIN_BUTTONS:
        builder.add(types.InlineKeyboardButton(text=text, callback_data=callback_data))
    builder.adjust(ADMIN_BUTTONS_PER_ROW)
    
    elapsed_time = time.time() - start_time
    
    # ✅ تعديل النص والكيبورد بطلب واحد
    await safe_edit_message(
        callback.message,
        f"🛠 **لوحة تحكم الإدارة**\n\n"
        f"حالة البوت: {status_text}\n"
        f"👤 المشرف: @{callback.from_user.username or 'مشرف'}\n"
        f"🕐 {get_formatted_damascus_time()}\n\n"
        f"🔸 **اختر الإجراء المطلوب:**",
        reply_markup=builder.as_markup()
    )
    
    logger.info(f"✅ عودة للوحة التحكم للمشرف {callback.from_user.id} في {elapsed_time:.3f} ثانية")

# تحديث لوحة التحكم يدوياً (إضافة زر اختياري)
@router.callback_query(F.data == "refresh_admin_panel")
async def refresh_admin_panel(callback: types.CallbackQuery, db_pool):
    """تحديث لوحة التحكم يدوياً"""
    # ✅ إطفاء الزر فوراً
    await callback.answer("🔄 جاري التحديث...")
    
    # ✅ مسح كاش حالة البوت
    clear_cache("bot_status")
    
    # ✅ العودة للوحة التحكم
    await back_to_admin_panel(callback, db_pool)

# إحصائيات سريعة للمشرفين
@router.callback_query(F.data == "admin_quick_stats")
async def admin_quick_stats(callback: types.CallbackQuery, db_pool):
    """عرض إحصائيات سريعة للمشرفين"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    from database import get_bot_stats
    stats = await get_bot_stats(db_pool)
    
    if not stats:
        await callback.answer("❌ خطأ في جلب الإحصائيات", show_alert=True)
        return
    
    text = (
        f"📊 **إحصائيات سريعة**\n\n"
        f"👥 المستخدمين: {stats['users'].get('total_users', 0)}\n"
        f"💰 إجمالي الأرصدة: {stats['users'].get('total_balance', 0):,.0f} ل.س\n"
        f"⭐ إجمالي النقاط: {stats['users'].get('total_points', 0)}\n"
        f"📦 طلبات اليوم: {stats['orders'].get('today_orders', 0)}\n"
        f"💳 إيداعات اليوم: {stats['deposits'].get('today_deposits', 0)}\n"
        f"🕐 {get_formatted_damascus_time()}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 تحديث", callback_data="admin_quick_stats"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

# إضافة زر المساعدة السريعة
@router.callback_query(F.data == "admin_help")
async def admin_help(callback: types.CallbackQuery):
    """عرض مساعدة سريعة للمشرفين"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    help_text = (
        "📚 **مساعدة سريعة للمشرفين**\n\n"
        "• **إدارة المنتجات**: إضافة وتعديل وحذف المنتجات\n"
        "• **إدارة الأقسام**: تنظيم الأقسام وترتيبها\n"
        "• **إدارة الخيارات**: إضافة خيارات للألعاب والاشتراكات\n"
        "• **إدارة المستخدمين**: بحث، تعديل رصيد، حظر\n"
        "• **إدارة النقاط**: تعديل إعدادات النقاط والموافقة على الاسترداد\n"
        "• **التقارير**: تقارير Excel وتقارير الأرباح\n"
        "• **الرسائل**: إرسال رسائل جماعية أو خاصة\n\n"
        "للمساعدة الإضافية، تواصل مع المطور @developer"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await safe_edit_message(callback.message, help_text, reply_markup=builder.as_markup())

# إدارة الجلسات النشطة (اختياري)
@router.callback_query(F.data == "admin_sessions")
async def admin_sessions(callback: types.CallbackQuery, db_pool):
    """عرض الجلسات النشطة للمشرفين"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # يمكن إضافة منطق لعرض الجلسات النشطة هنا
    await callback.message.answer("🚧 هذه الميزة قيد التطوير")

# معالج للأوامر غير المعروفة في وضع المشرف
@router.message(F.text.startswith("/admin"))
async def unknown_admin_command(message: types.Message):
    """معالج للأوامر غير المعروفة"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "❌ أمر غير معروف\n"
        "استخدم /admin للعودة للوحة التحكم"
    )

# إضافة زر لتغيير لغة الواجهة (اختياري)
@router.callback_query(F.data == "admin_change_language")
async def admin_change_language(callback: types.CallbackQuery):
    """تغيير لغة واجهة المشرف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🇸🇦 العربية", callback_data="set_lang_ar"),
        types.InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")
    )
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await safe_edit_message(
        callback.message,
        "🌐 **اختر اللغة المفضلة**\n\nChoose your preferred language:",
        reply_markup=builder.as_markup()
    )
