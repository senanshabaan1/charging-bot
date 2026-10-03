# admin/api_services.py
from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.users import is_admin_user
from api.client import get_api_client
from cache import clear_cache

router = Router(name="api_services")

@router.callback_query(F.data == "api_services_menu")
async def api_services_menu(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المزودين (المواقع المرتبطة)"""
    if not await is_admin_user(db_pool, callback.from_user.id): return
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        providers = await conn.fetch("SELECT * FROM api_providers ORDER BY id")
    
    builder = InlineKeyboardBuilder()
    for p in providers:
        status = "🟢" if p['is_active'] else "🔴"
        builder.row(types.InlineKeyboardButton(text=f"{status} {p['name']}", callback_data=f"view_prov_{p['id']}"))
        
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="back_to_admin"))
    
    await callback.message.edit_text(
        "🔌 **إدارة مزودي الـ API (المواقع المرتبطة)**\n\n"
        "اختر المزود لإدارته أو مزامنة خدماته:", 
        reply_markup=builder.as_markup(), parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("view_prov_"))
async def view_provider(callback: types.CallbackQuery, db_pool):
    """عرض تفاصيل مزود محدد وفحص الرصيد"""
    prov_id = int(callback.data.split("_")[2])
    async with db_pool.acquire() as conn:
        p = await conn.fetchrow("SELECT * FROM api_providers WHERE id = $1", prov_id)
    
    if not p: return await callback.answer("المزود غير موجود", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري فحص الاتصال وجلب الرصيد من الموقع...")
    
    api = get_api_client(p['base_url'], p['api_token'])
    balance = await api.get_balance()
    bal_text = f"${balance:.3f}" if balance is not None else "❌ فشل الاتصال (تأكد من الرابط والتوكن)"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 مزامنة وجلب الخدمات", callback_data=f"sync_prov_{prov_id}"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للمزودين", callback_data="api_services_menu"))
    
    await callback.message.edit_text(
        f"🔌 **المزود:** {p['name']}\n"
        f"🌐 **الرابط:** `{p['base_url']}`\n"
        f"💰 **رصيدك في هذا الموقع:** {bal_text}\n\n"
        f"⚠️ **ملاحظة:** المزامنة ستجلب جميع الخدمات المتوفرة في هذا الموقع وتضيفها تلقائياً لقاعدة بيانات البوت.",
        reply_markup=builder.as_markup(), parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("sync_prov_"))
async def sync_prov(callback: types.CallbackQuery, db_pool):
    """مزامنة المنتجات من المزود المحدد"""
    prov_id = int(callback.data.split("_")[2])
    await callback.answer("⏳ جاري جلب الخدمات، قد يستغرق الأمر دقيقة...", show_alert=True)
    
    async with db_pool.acquire() as conn:
        p = await conn.fetchrow("SELECT * FROM api_providers WHERE id = $1", prov_id)
        default_profit = await conn.fetchval("SELECT value::int FROM bot_settings WHERE key = 'api_default_profit'") or 10
        
    api = get_api_client(p['base_url'], p['api_token'])
    count = await api.sync_services_to_db(db_pool, default_profit, prov_id)
    clear_cache()
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"view_prov_{prov_id}"))
    await callback.message.edit_text(
        f"✅ **اكتملت المزامنة بنجاح!**\n\n"
        f"📦 تم إضافة/تحديث **{count}** خدمة من موقع {p['name']} إلى قاعدة بيانات البوت.",
        reply_markup=builder.as_markup(), parse_mode="Markdown"
    )
