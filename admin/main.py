# admin/main.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import time
from typing import List, Tuple
from config import ADMIN_ID, MODERATORS
from handlers.keyboards import get_main_menu_keyboard
from utils import is_admin, safe_edit_message, get_formatted_damascus_time
from cache import cached, clear_cache

logger = logging.getLogger(__name__)
router = Router(name="admin_main")

# ✅ ثوابت للأداء
ADMIN_BUTTONS_PER_ROW = 3
CACHE_TTL_BOT_STATUS = 30

# ✅ قائمة أزرار لوحة التحكم
ADMIN_BUTTONS: List[Tuple[str, str]] = [
    ("📈 سعر الصرف", "edit_rate"),
    ("💰 إدارة أسعار الصرف", "exchange_rates_menu"),
    ("📊 الإحصائيات", "bot_stats"),
    ("📢 رسالة للكل", "broadcast"),
    ("👤 معلومات مستخدم", "user_info"),
    ("⭐ إدارة النقاط", "manage_points"),
    ("📊 تقارير ونسخ", "reports_menu"),
    ("🔌 إدارة خدمات API", "api_services_menu"),
    ("🎁 العروض والمكافآت", "offers_menu"),
    ("📊 إدارة نسب ربح الخيارات", "manage_option_profits"),
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
    
    bot_status, status_text = await get_cached_bot_status(db_pool)
    
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
    await callback.answer()
    
    start_time = time.time()
    
    bot_status, status_text = await get_cached_bot_status(db_pool)
    
    builder = InlineKeyboardBuilder()
    for text, callback_data in ADMIN_BUTTONS:
        builder.add(types.InlineKeyboardButton(text=text, callback_data=callback_data))
    builder.adjust(ADMIN_BUTTONS_PER_ROW)
    
    elapsed_time = time.time() - start_time
    
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


# ============= معالجات الأزرار =============

@router.callback_query(F.data == "exchange_rates_menu")
async def handle_exchange_rates_menu(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """توجيه إلى قائمة أسعار الصرف"""
    await callback.answer()
    from admin.settings import exchange_rates_menu
    await exchange_rates_menu(callback, state, db_pool)


@router.callback_query(F.data == "api_services_menu")
async def handle_api_services_menu(callback: types.CallbackQuery, db_pool):
    """توجيه إلى قائمة إدارة API"""
    await callback.answer()
    from admin.api_services import api_services_menu
    await api_services_menu(callback, db_pool)


@router.callback_query(F.data == "offers_menu")
async def handle_offers_menu(callback: types.CallbackQuery, db_pool):
    """توجيه إلى قائمة العروض والمكافآت"""
    await callback.answer()
    from admin.offers import offers_menu
    await offers_menu(callback, db_pool)


@router.callback_query(F.data == "manage_option_profits")
async def handle_manage_option_profits(callback: types.CallbackQuery, db_pool):
    """توجيه إلى إدارة نسب ربح الخيارات"""
    await callback.answer()
    from admin.option_profits import manage_option_profits_start
    await manage_option_profits_start(callback, db_pool)


# ✅ إضافة معالجات للأزرار التي كانت لا تعمل

@router.callback_query(F.data == "toggle_bot")
async def handle_toggle_bot(callback: types.CallbackQuery, db_pool):
    """توجيه إلى تشغيل/إيقاف البوت"""
    await callback.answer()
    from admin.settings import toggle_bot
    await toggle_bot(callback, db_pool)


@router.callback_query(F.data == "edit_maintenance")
async def handle_edit_maintenance(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """توجيه إلى تعديل رسالة الصيانة"""
    await callback.answer()
    from admin.settings import edit_maintenance_start
    await edit_maintenance_start(callback, state, db_pool)


@router.callback_query(F.data == "edit_rate")
async def handle_edit_rate(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """توجيه إلى تعديل سعر الصرف"""
    await callback.answer()
    from admin.settings import start_edit_rate
    await start_edit_rate(callback, state, db_pool)


@router.callback_query(F.data == "edit_syriatel")
async def handle_edit_syriatel(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """توجيه إلى تعديل أرقام سيرياتل"""
    await callback.answer()
    from admin.settings import edit_syriatel_start
    await edit_syriatel_start(callback, state, db_pool)


# admin/main.py - السطر 210 تقريباً

@router.callback_query(F.data == "reset_bot")
async def handle_reset_bot(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """توجيه إلى تصفير البوت"""
    await callback.answer()
    from admin.reset import reset_bot_start
    await reset_bot_start(callback, state)  # ✅ فقط callback و state


@router.callback_query(F.data == "bot_stats")
async def handle_bot_stats(callback: types.CallbackQuery, db_pool):
    """توجيه إلى إحصائيات البوت"""
    await callback.answer()
    from admin.stats import bot_stats
    await bot_stats(callback, db_pool)


@router.callback_query(F.data == "manage_points")
async def handle_manage_points(callback: types.CallbackQuery, db_pool):
    """توجيه إلى إدارة النقاط"""
    await callback.answer()
    from admin.points import manage_points
    await manage_points(callback, db_pool)


@router.callback_query(F.data == "manage_admins")
async def handle_manage_admins(callback: types.CallbackQuery, db_pool):
    """توجيه إلى إدارة المشرفين"""
    await callback.answer()
    from admin.admins import manage_admins_menu
    await manage_admins_menu(callback, db_pool)


@router.callback_query(F.data == "edit_product")
async def handle_edit_product(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """توجيه إلى تعديل منتج"""
    await callback.answer()
    from admin.products import edit_product_list
    await edit_product_list(callback, db_pool)


@router.callback_query(F.data == "delete_product")
async def handle_delete_product(callback: types.CallbackQuery, db_pool):
    """توجيه إلى حذف منتج"""
    await callback.answer()
    from admin.products import delete_product_list
    await delete_product_list(callback, db_pool)


@router.callback_query(F.data == "list_products")
async def handle_list_products(callback: types.CallbackQuery, db_pool):
    """توجيه إلى عرض المنتجات"""
    await callback.answer()
    from admin.products import list_products
    await list_products(callback, db_pool)


@router.callback_query(F.data == "manage_categories")
async def handle_manage_categories(callback: types.CallbackQuery, db_pool):
    """توجيه إلى إدارة الأقسام"""
    await callback.answer()
    from admin.categories import manage_categories_menu
    await manage_categories_menu(callback, db_pool)


@router.callback_query(F.data == "manage_options")
async def handle_manage_options(callback: types.CallbackQuery, db_pool):
    """توجيه إلى إدارة خيارات الألعاب"""
    await callback.answer()
    from admin.options import manage_options_menu
    await manage_options_menu(callback, db_pool)


@router.callback_query(F.data == "manage_apps_status")
async def handle_manage_apps_status(callback: types.CallbackQuery, db_pool):
    """توجيه إلى تفعيل/إيقاف التطبيقات"""
    await callback.answer()
    from admin.products import manage_apps_status_menu
    await manage_apps_status_menu(callback, db_pool)


@router.callback_query(F.data == "broadcast")
async def handle_broadcast(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """توجيه إلى رسالة للكل"""
    await callback.answer()
    from admin.broadcast import broadcast_start
    await broadcast_start(callback, state, db_pool)


@router.callback_query(F.data == "user_info")
async def handle_user_info(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """توجيه إلى معلومات مستخدم"""
    await callback.answer()
    from admin.users import user_info_start
    await user_info_start(callback, state, db_pool)


@router.callback_query(F.data == "send_custom_message")
async def handle_send_custom_message(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """توجيه إلى رسالة لمستخدم"""
    await callback.answer()
    from admin.users import send_custom_message_start
    await send_custom_message_start(callback, state, db_pool)


# معالج للأوامر غير المعروفة
@router.message(F.text.startswith("/admin"))
async def unknown_admin_command(message: types.Message):
    """معالج للأوامر غير المعروفة"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "❌ أمر غير معروف\n"
        "استخدم /admin للعودة للوحة التحكم"
    )
