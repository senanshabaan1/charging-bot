# admin/api_services.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import json
from typing import Optional, Dict, Any

from utils.api_client import api_client
from database.users import is_admin_user
from handlers.keyboards import get_back_inline_keyboard
from database.core import get_exchange_rate

logger = logging.getLogger(__name__)
router = Router()

# ============= إدارة الحالات =============
class APIServiceStates(StatesGroup):
    waiting_service_id = State()
    waiting_api_url = State()
    waiting_api_token = State()
    waiting_search_keyword = State()
    confirm = State()


# ============= القائمة الرئيسية =============
@router.callback_query(F.data == "api_services_menu")
async def api_services_menu(callback: types.CallbackQuery, db_pool):
    """القائمة الرئيسية لإدارة خدمات API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📋 عرض جميع الخدمات", callback_data="list_api_services"),
        types.InlineKeyboardButton(text="➕ إضافة service_id", callback_data="add_api_service")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔍 بحث في الخدمات", callback_data="search_api_services"),
        types.InlineKeyboardButton(text="📊 تصنيف الخدمات", callback_data="categorize_services")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔧 اختبار API", callback_data="test_api_connection"),
        types.InlineKeyboardButton(text="💰 عرض الرصيد", callback_data="show_api_balance")
    )
    builder.row(
        types.InlineKeyboardButton(text="⚙️ إعدادات API", callback_data="api_settings"),
        types.InlineKeyboardButton(text="🔄 مزامنة الخدمات", callback_data="sync_services_from_api")
    )
    builder.row(
        types.InlineKeyboardButton(text="🗑️ مسح كاش الخدمات", callback_data="clear_products_cache"),
        types.InlineKeyboardButton(text="🔄 تحديث تلقائي", callback_data="auto_sync_settings")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin")
    )
    
    products = await api_client.get_products()
    total_services = len(products) if products else 0
    
    await callback.message.edit_text(
        "🔌 **إدارة خدمات API - Mousa Card**\n\n"
        f"📊 **إحصائيات:**\n"
        f"• عدد الخدمات المتاحة: {total_services}\n"
        f"• رابط API: `{api_client.base_url}`\n\n"
        "🔹 **الميزات المتاحة:**\n"
        "• 🔍 بحث متقدم في الخدمات\n"
        "• 📊 تصنيف الخدمات حسب الفئات\n"
        "• 🔄 تحديث تلقائي للخدمات\n"
        "• 💾 كاش للخدمات لسرعة الاستجابة\n\n"
        "اختر الإجراء المطلوب:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= عرض الخدمات المرتبطة =============
@router.callback_query(F.data == "list_api_services")
async def list_api_services(callback: types.CallbackQuery, db_pool):
    """عرض قائمة التطبيقات المرتبطة بخدمات API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        apps = await conn.fetch('''
            SELECT id, name, api_service_id, is_active 
            FROM applications 
            WHERE api_service_id IS NOT NULL AND api_service_id != ''
            ORDER BY name
        ''')
        
        apps_without_api = await conn.fetch('''
            SELECT id, name, api_service_id, is_active 
            FROM applications 
            WHERE api_service_id IS NULL OR api_service_id = ''
            ORDER BY name
            LIMIT 10
        ''')
    
    if not apps:
        await callback.message.edit_text(
            "⚠️ **لا توجد تطبيقات مرتبطة بخدمات API**\n\n"
            "لإضافة service_id لأحد التطبيقات:\n"
            "1. اختر '➕ إضافة service_id' من القائمة\n"
            "2. اختر التطبيق\n"
            "3. أدخل service_id من موقع Mousa Card",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    for app in apps:
        status = "✅" if app['is_active'] else "🔒"
        builder.row(types.InlineKeyboardButton(
            text=f"{status} {app['name']} (ID: {app['api_service_id']})",
            callback_data=f"edit_api_service_{app['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data="api_services_menu"
    ))
    
    text = f"📋 **التطبيقات المرتبطة بـ API**\n\n"
    text += f"عدد التطبيقات المرتبطة: {len(apps)}\n\n"
    
    if apps_without_api:
        text += f"⚠️ تطبيقات بدون service_id: {len(apps_without_api)}\n"
    
    text += "\n🔹 اضغط على أي تطبيق لتعديل service_id الخاص به"
    
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= البحث في الخدمات =============
@router.callback_query(F.data == "search_api_services")
async def search_api_services_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء البحث في الخدمات"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state(APIServiceStates.waiting_search_keyword)
    
    await callback.message.edit_text(
        "🔍 **البحث في خدمات API**\n\n"
        "أدخل الكلمة المفتاحية للبحث (مثال: instagram, تيك توك, telegram)\n\n"
        "🔹 سيبحث في:\n"
        "• اسم الخدمة\n"
        "• وصف الخ service\n"
        "• الفئة\n\n"
        "❌ للإلغاء أرسل /cancel",
        reply_markup=get_back_inline_keyboard("api_services_menu"),
        parse_mode="Markdown"
    )


@router.message(APIServiceStates.waiting_search_keyword)
async def search_api_services_result(message: types.Message, state: FSMContext, db_pool):
    """عرض نتائج البحث"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    keyword = message.text.strip()
    
    if len(keyword) < 2:
        await message.answer(
            "⚠️ الكلمة المفتاحية يجب أن تكون حرفين على الأقل.\nيرجى إعادة المحاولة:"
        )
        return
    
    await message.answer(f"⏳ جاري البحث عن '{keyword}'...")
    
    results = await api_client.search_products(keyword)
    
    if not results:
        await message.answer(
            f"❌ لم يتم العثور على خدمات تحتوي على '{keyword}'\n\n"
            f"🔹 حاول استخدام كلمات مختلفة أو أقل تخصصاً.",
            reply_markup=get_back_inline_keyboard("api_services_menu")
        )
        await state.clear()
        return
    
    builder = InlineKeyboardBuilder()
    
    for product in results[:20]:
        product_id = product.get('id', product.get('service_id'))
        product_name = product.get('name', 'غير معروف')
        price = product.get('price', 0)
        
        builder.row(types.InlineKeyboardButton(
            text=f"📦 {product_name} (ID: {product_id}) - ${price}",
            callback_data=f"view_product_detail_{product_id}"
        ))
    
    if len(results) > 20:
        builder.row(types.InlineKeyboardButton(
            text=f"📊 عرض المزيد ({len(results) - 20} خدمة أخرى)",
            callback_data=f"search_more_{keyword}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للقائمة",
        callback_data="api_services_menu"
    ))
    
    await message.answer(
        f"🔍 **نتائج البحث عن '{keyword}':**\n\n"
        f"✅ تم العثور على {len(results)} خدمة\n\n"
        f"🔹 اضغط على أي خدمة لعرض تفاصيلها وربطها بتطبيقك:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.clear()


# ============= عرض تفاصيل الخدمة =============
@router.callback_query(F.data.startswith("view_product_detail_"))
async def view_product_detail(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض تفاصيل خدمة معينة"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    service_id = int(callback.data.split("_")[3])
    
    await callback.answer()
    await callback.message.edit_text("⏳ جاري جلب تفاصيل الخدمة...")
    
    product = await api_client.get_product_details(service_id)
    
    if not product:
        await callback.message.edit_text(
            f"❌ لم يتم العثور على خدمة بالمعرف {service_id}",
            reply_markup=get_back_inline_keyboard("api_services_menu")
        )
        return
    
    name = product.get('name', 'غير معروف')
    product_id = product.get('id', product.get('service_id'))
    price = product.get('price', 0)
    min_qty = product.get('min', 1)
    max_qty = product.get('max', 99999)
    description = product.get('description', 'لا يوجد وصف')
    category = product.get('category', 'غير مصنف')
    
    price_syp = price * 118
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="➕ ربط هذا الخدمة بتطبيق", callback_data=f"link_to_app_{product_id}"),
        types.InlineKeyboardButton(text="📝 معاينة الوصف", callback_data=f"preview_description_{product_id}")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع للبحث", callback_data="back_to_search"),
        types.InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="api_services_menu")
    )
    
    await callback.message.edit_text(
        f"📦 **تفاصيل الخدمة**\n\n"
        f"🔹 **الاسم:** {name}\n"
        f"🔢 **service_id:** `{product_id}`\n"
        f"📂 **الفئة:** {category}\n"
        f"💰 **السعر:** ${price} ≈ {price_syp:,.0f} ل.س\n"
        f"📊 **الحد الأدنى:** {min_qty}\n"
        f"📈 **الحد الأقصى:** {max_qty}\n"
        f"📝 **الوصف:** {description[:300]}{'...' if len(description) > 300 else ''}\n\n"
        f"🔹 **لربط هذه الخدمة بتطبيق في البوت:**\n"
        f"اضغط على 'ربط هذا الخدمة بتطبيق'",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("preview_description_"))
async def preview_description(callback: types.CallbackQuery, db_pool):
    """معاينة وصف الخدمة كما سيظهر للمستخدم"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    service_id = int(callback.data.split("_")[2])
    
    description = await api_client.get_product_description(service_id)
    
    if description:
        await callback.message.answer(
            f"📝 **معاينة وصف الخدمة (service_id: {service_id}):**\n\n"
            f"{description}\n\n"
            f"✅ هذا النص سيظهر للمستخدم عند اختيار هذا التطبيق.",
            parse_mode="Markdown"
        )
        await callback.answer()
    else:
        await callback.answer("لا يوجد وصف لهذه الخدمة", show_alert=True)


@router.callback_query(F.data.startswith("link_to_app_"))
async def link_service_to_app_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء ربط الخدمة بتطبيق"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    service_id = int(callback.data.split("_")[3])
    
    async with db_pool.acquire() as conn:
        apps = await conn.fetch('''
            SELECT id, name, api_service_id 
            FROM applications 
            ORDER BY name
        ''')
    
    if not apps:
        await callback.message.edit_text(
            "⚠️ لا توجد تطبيقات في النظام. قم بإضافة تطبيقات أولاً.",
            reply_markup=get_back_inline_keyboard("api_services_menu")
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    for app in apps:
        status = "✅" if app['api_service_id'] else "❌"
        builder.row(types.InlineKeyboardButton(
            text=f"{status} {app['name']}",
            callback_data=f"confirm_link_app_{app['id']}_{service_id}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data=f"view_product_detail_{service_id}"
    ))
    
    await callback.message.edit_text(
        f"🔢 **service_id:** `{service_id}`\n\n"
        f"🔽 **اختر التطبيق الذي تريد ربطه بهذه الخدمة:**\n\n"
        f"✅ = مرتبط مسبقاً\n"
        f"❌ = غير مرتبط",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("confirm_link_app_"))
async def confirm_link_app(callback: types.CallbackQuery, db_pool):
    """تأكيد ربط التطبيق بالخدمة"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    parts = callback.data.split("_")
    app_id = int(parts[4])
    service_id = int(parts[5])
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow(
            "SELECT name FROM applications WHERE id = $1",
            app_id
        )
        
        await conn.execute(
            "UPDATE applications SET api_service_id = $1 WHERE id = $2",
            service_id, app_id
        )
    
    await callback.answer(f"✅ تم ربط {app['name']} بالخدمة {service_id}")
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="📋 عرض الخدمات المرتبطة",
        callback_data="list_api_services"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 القائمة الرئيسية",
        callback_data="api_services_menu"
    ))
    
    await callback.message.edit_text(
        f"✅ **تم الربط بنجاح!**\n\n"
        f"📱 **التطبيق:** {app['name']}\n"
        f"🔢 **service_id:** {service_id}\n\n"
        f"الآن عند الموافقة على طلبات هذا التطبيق، سيتم إرسالها تلقائياً إلى API.\n"
        f"كما سيظهر وصف الخدمة للمستخدمين تلقائياً.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= إضافة/تعديل service_id يدوياً =============
@router.callback_query(F.data.startswith("add_api_service"))
async def start_add_api_service(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء عملية إضافة service_id لتطبيق"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        apps = await conn.fetch('''
            SELECT id, name, api_service_id 
            FROM applications 
            ORDER BY name
        ''')
    
    if not apps:
        await callback.message.edit_text(
            "⚠️ لا توجد تطبيقات في النظام. قم بإضافة تطبيقات أولاً.",
            reply_markup=get_back_inline_keyboard("api_services_menu")
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    for app in apps:
        status = "✅" if app['api_service_id'] else "❌"
        builder.row(types.InlineKeyboardButton(
            text=f"{status} {app['name']}",
            callback_data=f"select_app_for_api_{app['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data="api_services_menu"
    ))
    
    await callback.message.edit_text(
        "🔽 **اختر التطبيق الذي تريد ربطه بخدمة API:**\n\n"
        "✅ = مرتبط مسبقاً\n"
        "❌ = غير مرتبط\n\n"
        "بعد اختيار التطبيق، ستدخل service_id الخاص به من موقع Mousa Card",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("select_app_for_api_"))
async def select_app_for_api(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """اختيار التطبيق وإدخال service_id"""
    app_id = int(callback.data.split("_")[4])
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow(
            "SELECT id, name, api_service_id FROM applications WHERE id = $1",
            app_id
        )
    
    if not app:
        await callback.answer("التطبيق غير موجود", show_alert=True)
        return
    
    await state.update_data(app_id=app_id, app_name=app['name'])
    await state.set_state(APIServiceStates.waiting_service_id)
    
    current_id = f" (الحالي: {app['api_service_id']})" if app['api_service_id'] else ""
    
    await callback.message.edit_text(
        f"📱 **التطبيق:** {app['name']}{current_id}\n\n"
        f"🔢 **أدخل service_id من موقع Mousa Card:**\n\n"
        f"📌 مثال: في الرابط `newOrder/364/params` الرقم 364 هو service_id\n\n"
        f"⚠️ **ملاحظة:** هذا الرقم يجب أن يكون صحيحاً حتى يعمل الإرسال التلقائي\n\n"
        f"❌ للإلغاء أرسل /cancel",
        reply_markup=get_back_inline_keyboard("add_api_service"),
        parse_mode="Markdown"
    )


@router.message(APIServiceStates.waiting_service_id)
async def save_api_service_id(message: types.Message, state: FSMContext, db_pool):
    """حفظ service_id للتطبيق"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    service_id = message.text.strip()
    
    if not service_id.isdigit():
        await message.answer(
            "❌ **خطأ:** service_id يجب أن يكون رقماً صحيحاً!\n"
            "مثال: 364\n\n"
            "يرجى إعادة المحاولة:",
            parse_mode="Markdown"
        )
        return
    
    data = await state.get_data()
    app_id = data.get('app_id')
    app_name = data.get('app_name')
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE applications SET api_service_id = $1 WHERE id = $2",
            int(service_id), app_id
        )
    
    await state.clear()
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="📋 عرض الخدمات", 
        callback_data="list_api_services"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 القائمة الرئيسية", 
        callback_data="api_services_menu"
    ))
    
    await message.answer(
        f"✅ **تم ربط التطبيق بنجاح!**\n\n"
        f"📱 **التطبيق:** {app_name}\n"
        f"🔢 **service_id:** {service_id}\n\n"
        f"📌 الآن عند الموافقة على طلبات هذا التطبيق، سيتم إرسالها تلقائياً إلى API.\n"
        f"📝 كما سيظهر وصف الخدمة للمستخدمين.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("edit_api_service_"))
async def edit_api_service(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """تعديل service_id لتطبيق موجود"""
    app_id = int(callback.data.split("_")[3])
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow(
            "SELECT id, name, api_service_id FROM applications WHERE id = $1",
            app_id
        )
    
    if not app:
        await callback.answer("التطبيق غير موجود", show_alert=True)
        return
    
    await state.update_data(app_id=app_id, app_name=app['name'])
    await state.set_state(APIServiceStates.waiting_service_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🗑️ حذف service_id", 
        callback_data=f"delete_api_service_{app_id}"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data="list_api_services"
    ))
    
    await callback.message.edit_text(
        f"📱 **التطبيق:** {app['name']}\n"
        f"🔢 **service_id الحالي:** `{app['api_service_id']}`\n\n"
        f"✏️ **أدخل service_id الجديد:**\n\n"
        f"أو اضغط 'حذف' لإزالة الربط.\n\n"
        f"❌ للإلغاء أرسل /cancel",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("delete_api_service_"))
async def delete_api_service(callback: types.CallbackQuery, db_pool):
    """حذف service_id من التطبيق"""
    app_id = int(callback.data.split("_")[3])
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow(
            "SELECT name FROM applications WHERE id = $1",
            app_id
        )
        
        await conn.execute(
            "UPDATE applications SET api_service_id = NULL WHERE id = $1",
            app_id
        )
    
    await callback.answer("✅ تم حذف service_id")
    
    await callback.message.edit_text(
        f"✅ **تم حذف service_id من التطبيق:** {app['name']}\n\n"
        f"لن يتم إرسال طلبات هذا التطبيق تلقائياً إلى API.",
        reply_markup=get_back_inline_keyboard("list_api_services")
    )


# ============= تصنيف الخدمات =============
@router.callback_query(F.data == "categorize_services")
async def categorize_services(callback: types.CallbackQuery, db_pool):
    """عرض الخدمات مصنفة حسب الفئات"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await callback.message.edit_text("⏳ جاري تصنيف الخدمات...")
    
    categories = await api_client.get_service_categories()
    
    if not categories:
        await callback.message.edit_text(
            "❌ فشل جلب تصنيف الخدمات",
            reply_markup=get_back_inline_keyboard("api_services_menu")
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    for category, products in categories.items():
        count = len(products)
        builder.row(types.InlineKeyboardButton(
            text=f"📁 {category} ({count})",
            callback_data=f"show_category_{category}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="api_services_menu"
    ))
    
    await callback.message.edit_text(
        f"📂 **تصنيف الخدمات حسب الفئات**\n\n"
        f"إجمالي الخدمات: {sum(len(p) for p in categories.values())}\n"
        f"عدد الفئات: {len(categories)}\n\n"
        f"🔹 اختر فئة لعرض خدماتها:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("show_category_"))
async def show_category_products(callback: types.CallbackQuery, db_pool):
    """عرض خدمات فئة معينة"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    category = callback.data.replace("show_category_", "")
    
    categories = await api_client.get_service_categories()
    products = categories.get(category, [])
    
    if not products:
        await callback.answer("لا توجد خدمات في هذه الفئة")
        return
    
    builder = InlineKeyboardBuilder()
    
    for product in products[:15]:
        product_id = product.get('id', product.get('service_id'))
        product_name = product.get('name', 'غير معروف')
        price = product.get('price', 0)
        
        builder.row(types.InlineKeyboardButton(
            text=f"📦 {product_name} (ID: {product_id}) - ${price}",
            callback_data=f"view_product_detail_{product_id}"
        ))
    
    if len(products) > 15:
        builder.row(types.InlineKeyboardButton(
            text=f"📊 عرض المزيد ({len(products) - 15} خدمة)",
            callback_data=f"show_more_category_{category}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للتصنيف",
        callback_data="categorize_services"
    ))
    
    await callback.message.edit_text(
        f"📂 **فئة: {category}**\n\n"
        f"عدد الخدمات: {len(products)}\n\n"
        f"🔹 اضغط على أي خدمة لعرض تفاصيلها:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= اختبار API وعرض الرصيد =============
@router.callback_query(F.data == "test_api_connection")
async def test_api_connection(callback: types.CallbackQuery, db_pool):
    """اختبار الاتصال بـ API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await callback.message.edit_text("⏳ جاري اختبار الاتصال بـ API...")
    
    async with db_pool.acquire() as conn:
        api_url = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = 'api_base_url'"
        )
    
    if api_url:
        api_client.base_url = api_url.rstrip('/')
    
    products = await api_client.get_products(force_refresh=True)
    
    if products:
        text = f"✅ **الاتصال بـ API يعمل بنجاح!**\n\n"
        text += f"🌐 **رابط API:** {api_client.base_url}\n"
        text += f"📦 **عدد المنتجات المتاحة:** {len(products)}\n\n"
        
        text += "🔹 **نماذج من المنتجات:**\n"
        for i, product in enumerate(products[:5]):
            product_name = product.get('name', 'غير معروف')
            product_id = product.get('id', product.get('service_id', 'N/A'))
            text += f"   • {product_name} (ID: {product_id})\n"
        
        if len(products) > 5:
            text += f"   ... و {len(products) - 5} منتج آخر\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            f"❌ **فشل الاتصال بـ API**\n\n"
            f"🌐 **رابط API:** {api_client.base_url}\n\n"
            f"🔍 **أسباب محتملة:**\n"
            f"• رابط API غير صحيح\n"
            f"• التوكن غير صالح\n"
            f"• مشكلة في الاتصال بالإنترنت\n\n"
            f"يمكنك تغيير رابط API من إعدادات API العامة",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )


@router.callback_query(F.data == "show_api_balance")
async def show_api_balance(callback: types.CallbackQuery, db_pool):
    """عرض الرصيد المتاح في API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await callback.message.edit_text("⏳ جاري جلب الرصيد...")
    
    balance = await api_client.get_balance()
    
    if balance is not None:
        await callback.message.edit_text(
            f"💰 **رصيد API الحالي:**\n\n"
            f"💵 **{balance:,.2f} $**\n\n"
            f"📊 يمكنك استخدام هذا الرصيد لتنفيذ الطلبات التلقائية.",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            "❌ **فشل جلب الرصيد**\n\n"
            "تأكد من:\n"
            "• صحة رابط API\n"
            "• صحة التوكن\n"
            "• الاتصال بالإنترنت",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )


# ============= إعدادات API =============
@router.callback_query(F.data == "api_settings")
async def api_settings(callback: types.CallbackQuery, db_pool):
    """إعدادات API العامة"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        api_url = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = 'api_base_url'"
        ) or "https://mousa-card.com"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔗 تغيير رابط API", 
        callback_data="change_api_url"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔄 إعادة تعيين الإعدادات", 
        callback_data="reset_api_settings"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data="api_services_menu"
    ))
    
    await callback.message.edit_text(
        f"⚙️ **إعدادات API العامة**\n\n"
        f"🌐 **رابط API:** `{api_url}`\n"
        f"🔑 **التوكن:** `{api_client.token[:20]}...`\n\n"
        f"📌 **ملاحظة:** التوكن مخزن في الكود، يمكنك تغييره مباشرة من ملف api_client.py",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "change_api_url")
async def change_api_url_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تغيير رابط API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state(APIServiceStates.waiting_api_url)
    
    await callback.message.edit_text(
        "🔗 **تغيير رابط API**\n\n"
        "أدخل رابط API الجديد (مثال: https://mousa-card.com)\n\n"
        "⚠️ **ملاحظة:** لا تضيف / في النهاية\n\n"
        "❌ للإلغاء أرسل /cancel",
        reply_markup=get_back_inline_keyboard("api_settings"),
        parse_mode="Markdown"
    )


@router.message(APIServiceStates.waiting_api_url)
async def save_api_url(message: types.Message, state: FSMContext, db_pool):
    """حفظ رابط API الجديد"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    new_url = message.text.strip().rstrip('/')
    
    if not new_url.startswith(('http://', 'https://')):
        await message.answer(
            "❌ **خطأ:** الرابط يجب أن يبدأ بـ http:// أو https://\n"
            "يرجى إعادة المحاولة:",
            parse_mode="Markdown"
        )
        return
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE bot_settings SET value = $1 WHERE key = 'api_base_url'",
            new_url
        )
    
    api_client.base_url = new_url
    api_client.clear_cache()
    
    await state.clear()
    
    await message.answer(
        f"✅ **تم تحديث رابط API بنجاح!**\n\n"
        f"🌐 **الرابط الجديد:** {new_url}\n\n"
        f"🔍 يرجى اختبار الاتصال للتأكد من صحة الرابط.",
        reply_markup=get_back_inline_keyboard("api_settings"),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "reset_api_settings")
async def reset_api_settings(callback: types.CallbackQuery, db_pool):
    """إعادة تعيين إعدادات API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE bot_settings SET value = 'https://mousa-card.com' WHERE key = 'api_base_url'"
        )
    
    api_client.base_url = "https://mousa-card.com"
    api_client.clear_cache()
    
    await callback.message.edit_text(
        "✅ **تم إعادة تعيين إعدادات API**\n\n"
        f"🌐 **الرابط:** https://mousa-card.com\n\n"
        "يمكنك الآن اختبار الاتصال من القائمة.",
        reply_markup=get_back_inline_keyboard("api_settings"),
        parse_mode="Markdown"
    )


# ============= مزامنة الخدمات =============
@router.callback_query(F.data == "sync_services_from_api")
async def sync_services_from_api(callback: types.CallbackQuery, db_pool):
    """مزامنة قائمة الخدمات من API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await callback.message.edit_text("⏳ جاري جلب قائمة الخدمات من API...")
    
    products = await api_client.get_products(force_refresh=True)
    
    if not products:
        await callback.message.edit_text(
            "❌ **فشل جلب الخدمات من API**\n\n"
            "تأكد من صحة الاتصال بالـ API أولاً.",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    for product in products[:20]:
        product_id = product.get('id', product.get('service_id', 'N/A'))
        product_name = product.get('name', 'غير معروف')
        builder.row(types.InlineKeyboardButton(
            text=f"📦 {product_name} (ID: {product_id})",
            callback_data=f"view_product_detail_{product_id}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="api_services_menu"
    ))
    
    await callback.message.edit_text(
        f"📋 **الخدمات المتاحة في API**\n\n"
        f"عدد الخدمات: {len(products)}\n\n"
        "🔹 اضغط على أي خدمة لعرض تفاصيلها وربطها بتطبيقك",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= مسح الكاش =============
@router.callback_query(F.data == "clear_products_cache")
async def clear_products_cache(callback: types.CallbackQuery, db_pool):
    """مسح كاش الخدمات"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    api_client.clear_cache()
    
    await callback.answer("🗑️ تم مسح الكاش", show_alert=True)
    
    await callback.message.edit_text(
        "✅ **تم مسح كاش الخدمات بنجاح!**\n\n"
        "في المرة القادمة التي تطلب فيها الخدمات، سيتم جلبها من API مباشرة.",
        reply_markup=get_back_inline_keyboard("api_services_menu"),
        parse_mode="Markdown"
    )


# ============= إعدادات التحديث التلقائي =============
@router.callback_query(F.data == "auto_sync_settings")
async def auto_sync_settings(callback: types.CallbackQuery, db_pool):
    """إعدادات التحديث التلقائي للخدمات"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        auto_sync = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = 'auto_sync_services'"
        ) or "disabled"
        sync_interval = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = 'sync_interval'"
        ) or "60"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="✅ تفعيل" if auto_sync == "disabled" else "❌ تعطيل",
            callback_data="toggle_auto_sync"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text=f"⏰ تغيير الفترة (حالياً: كل {sync_interval} دقيقة)",
            callback_data="change_sync_interval"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🔄 مزامنة الآن",
            callback_data="sync_services_from_api"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🔙 رجوع",
            callback_data="api_services_menu"
        )
    )
    
    status = "🟢 **مفعل**" if auto_sync != "disabled" else "🔴 **معطل**"
    
    await callback.message.edit_text(
        f"⚙️ **إعدادات التحديث التلقائي**\n\n"
        f"حالة التحديث: {status}\n"
        f"الفترة: كل {sync_interval} دقيقة\n\n"
        f"🔹 عند التفعيل، سيتم تحديث قائمة الخدمات تلقائياً\n"
        f"🔹 هذا يضمن أن الخدمات الجديدة تظهر في البحث والتصنيف\n\n"
        f"اختر الإجراء المطلوب:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "toggle_auto_sync")
async def toggle_auto_sync(callback: types.CallbackQuery, db_pool):
    """تبديل التحديث التلقائي"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        current = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = 'auto_sync_services'"
        ) or "disabled"
        
        new_value = "enabled" if current == "disabled" else "disabled"
        
        await conn.execute(
            "INSERT INTO bot_settings (key, value, description) VALUES ('auto_sync_services', $1, 'تفعيل/تعطيل التحديث التلقائي للخدمات') ON CONFLICT (key) DO UPDATE SET value = $1",
            new_value
        )
    
    await callback.answer(f"{'✅ تم التفعيل' if new_value == 'enabled' else '❌ تم التعطيل'}")
    await auto_sync_settings(callback, db_pool)


# ============= معالجات إضافية =============
@router.callback_query(F.data.startswith("search_more_"))
async def search_more(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض المزيد من نتائج البحث"""
    keyword = callback.data.replace("search_more_", "")
    
    results = await api_client.search_products(keyword)
    
    if not results:
        await callback.answer("لا توجد نتائج إضافية")
        return
    
    builder = InlineKeyboardBuilder()
    
    for product in results[20:40]:
        product_id = product.get('id', product.get('service_id'))
        product_name = product.get('name', 'غير معروف')
        price = product.get('price', 0)
        
        builder.row(types.InlineKeyboardButton(
            text=f"📦 {product_name} (ID: {product_id}) - ${price}",
            callback_data=f"view_product_detail_{product_id}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للبحث",
        callback_data="back_to_search"
    ))
    
    await callback.message.edit_text(
        f"🔍 **نتائج البحث عن '{keyword}' (الصفحة 2):**\n\n"
        f"عرض {min(40, len(results))} من {len(results)} نتيجة",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "back_to_search")
async def back_to_search(callback: types.CallbackQuery, state: FSMContext):
    """العودة لشاشة البحث"""
    await callback.answer()
    await state.set_state(APIServiceStates.waiting_search_keyword)
    
    await callback.message.edit_text(
        "🔍 **البحث في خدمات API**\n\n"
        "أدخل الكلمة المفتاحية للبحث (مثال: instagram, تيك توك, telegram)\n\n"
        "❌ للإلغاء أرسل /cancel",
        reply_markup=get_back_inline_keyboard("api_services_menu"),
        parse_mode="Markdown"
    )
