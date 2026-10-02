from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from utils import is_admin, safe_edit_message, get_formatted_damascus_time
from cache import cached, clear_cache

logger = logging.getLogger(__name__)
router = Router(name="admin_main")

# ============= عرض اللوحة الرئيسية =============
@router.message(Command("admin"))
@router.message(F.text == "🛠 لوحة التحكم")
async def admin_panel(message: types.Message, db_pool):
    """عرض لوحة تحكم المشرفين"""
    if not is_admin(message.from_user.id):
        return
    await show_admin_dashboard(message, db_pool, is_edit=False)

@router.callback_query(F.data == "back_to_admin")
async def back_to_admin_panel(callback: types.CallbackQuery, db_pool):
    """العودة للوحة التحكم الرئيسية"""
    await callback.answer()
    await show_admin_dashboard(callback.message, db_pool, is_edit=True)

async def show_admin_dashboard(message: types.Message, db_pool, is_edit=False):
    """بناء لوحة القيادة المباشرة"""
    # جلب الإحصائيات الحية
    async with db_pool.acquire() as conn:
        bot_status = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'bot_status'")
        exchange_rate = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'usd_to_syp'")
        api_profit = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'api_default_profit'")
        pending_orders = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'pending' OR status = 'processing'")
        pending_deposits = await conn.fetchval("SELECT COUNT(*) FROM deposit_requests WHERE status = 'pending'")
        
    status_text = "🟢 يعمل" if bot_status == 'running' else "🔴 متوقف"
    rate = float(exchange_rate) if exchange_rate else 15000
    profit = int(api_profit) if api_profit else 10
    
    text = (
        f"👑 <b>لوحة القيادة | Dashboard</b> 👑\n\n"
        f"📊 <b>نظرة عامة على النظام:</b>\n"
        f"🤖 <b>حالة البوت:</b> {status_text}\n"
        f"💵 <b>سعر الصرف:</b> {rate:,.0f} ل.س\n"
        f"📈 <b>ربح الـ API التلقائي:</b> {profit}%\n"
        f"🛒 <b>طلبات قيد الانتظار:</b> {pending_orders}\n"
        f"💰 <b>إيداعات بانتظار التأكيد:</b> {pending_deposits}\n\n"
        f"🕐 <code>{get_formatted_damascus_time()}</code>\n\n"
        f"🔸 <b>اختر قسم الإدارة المطلوب:</b>"
    )
    
    builder = InlineKeyboardBuilder()
    # الصفوف مقسمة منطقياً
    builder.row(types.InlineKeyboardButton(text="⚙️ إعدادات النظام والمحافظ", callback_data="admin_settings_menu"))
    builder.row(types.InlineKeyboardButton(text="📦 إدارة الأقسام والمنتجات", callback_data="admin_products_menu"))
    builder.row(types.InlineKeyboardButton(text="👥 المستخدمين والإشعارات", callback_data="admin_users_menu"))
    builder.row(
        types.InlineKeyboardButton(text="📊 الإحصائيات", callback_data="bot_stats"),
        types.InlineKeyboardButton(text="🔌 ربط الـ API", callback_data="api_services_menu")
    )
    
    if is_edit:
        await safe_edit_message(message, text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# ============= القوائم الفرعية =============

@router.callback_query(F.data == "admin_settings_menu")
async def admin_settings_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="💵 تعديل سعر الصرف", callback_data="edit_rate"),
        types.InlineKeyboardButton(text="💳 محافظ وبنوك الدفع", callback_data="edit_wallets_menu")
    )
    builder.row(
        types.InlineKeyboardButton(text="🤖 تشغيل/إيقاف البوت", callback_data="toggle_bot"),
        types.InlineKeyboardButton(text="✏️ رسالة الصيانة", callback_data="edit_maintenance")
    )
    builder.row(
        types.InlineKeyboardButton(text="👑 إدارة المشرفين", callback_data="manage_admins"),
        types.InlineKeyboardButton(text="⚠️ تصفير البوت", callback_data="reset_bot")
    )
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للرئيسية", callback_data="back_to_admin"))
    await safe_edit_message(callback.message, "⚙️ <b>إعدادات النظام والمحافظ</b>\nاختر ما تريد تعديله:", reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "admin_products_menu")
async def admin_products_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📁 إدارة الأقسام", callback_data="manage_categories"),
        types.InlineKeyboardButton(text="📋 عرض المنتجات", callback_data="list_products")
    )
    builder.row(
        types.InlineKeyboardButton(text="➕ إضافة منتج", callback_data="add_product"),
        types.InlineKeyboardButton(text="✏️ تعديل منتج", callback_data="edit_product")
    )
    builder.row(
        types.InlineKeyboardButton(text="🗑️ حذف منتج", callback_data="delete_product"),
        types.InlineKeyboardButton(text="🎮 إدارة الخيارات", callback_data="manage_options")
    )
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للرئيسية", callback_data="back_to_admin"))
    await safe_edit_message(callback.message, "📦 <b>إدارة الأقسام والمنتجات</b>\nترتيب وتخصيص خدماتك:", reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "admin_users_menu")
async def admin_users_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔍 معلومات مستخدم", callback_data="user_info"),
        types.InlineKeyboardButton(text="📢 إرسال للكل", callback_data="broadcast")
    )
    builder.row(
        types.InlineKeyboardButton(text="✉️ رسالة لشخص", callback_data="send_custom_message"),
        types.InlineKeyboardButton(text="⭐ إدارة النقاط", callback_data="manage_points")
    )
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للرئيسية", callback_data="back_to_admin"))
    await safe_edit_message(callback.message, "👥 <b>المستخدمين والإشعارات</b>\nالتواصل وإدارة الحسابات:", reply_markup=builder.as_markup(), parse_mode="HTML")
