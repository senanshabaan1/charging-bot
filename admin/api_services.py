# admin/api_services.py - نسخة محدثة بالكامل
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import json
from typing import Optional, Dict, Any

from database.users import is_admin_user
from handlers.keyboards import get_back_inline_keyboard, get_confirmation_keyboard
from database.core import get_exchange_rate
from api.client import get_api_client, set_api_token, close_api_client
from cache import clear_cache

logger = logging.getLogger(__name__)
router = Router(name="api_services")


class APIServiceStates(StatesGroup):
    waiting_service_id = State()
    waiting_api_url = State()
    waiting_api_token = State()
    waiting_search_keyword = State()
    waiting_profit_percent = State()
    confirm = State()


# ============= القائمة الرئيسية =============
@router.callback_query(F.data == "api_services_menu")
async def api_services_menu(callback: types.CallbackQuery, db_pool):
    """القائمة الرئيسية لإدارة خدمات Mousa Card API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    api = get_api_client()
    balance = await api.get_balance()
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📋 عرض جميع الخدمات", callback_data="list_api_services"),
        types.InlineKeyboardButton(text="🔄 مزامنة الخدمات", callback_data="sync_services_from_api")
    )
    builder.row(
        types.InlineKeyboardButton(text="💰 عرض الرصيد", callback_data="show_api_balance"),
        types.InlineKeyboardButton(text="🔧 اختبار الاتصال", callback_data="test_api_connection")
    )
    builder.row(
        types.InlineKeyboardButton(text="📊 إعدادات الربح", callback_data="api_profit_settings"),
        types.InlineKeyboardButton(text="🔑 تحديث التوكن", callback_data="update_api_token")
    )
    builder.row(
        types.InlineKeyboardButton(text="📁 استيراد تصنيفات", callback_data="import_categories"),
        types.InlineKeyboardButton(text="🗑️ مسح كاش API", callback_data="clear_api_cache")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="back_to_admin")
    )
    
    balance_text = f"💰 الرصيد: ${balance:,.2f}" if balance else "💰 الرصيد: غير متوفر"
    
    await callback.message.edit_text(
        f"🔌 **إدارة API - Mousa Card**\n\n"
        f"{balance_text}\n"
        f"🌐 **Base URL:** `{api.base_url}`\n\n"
        f"🔹 **الميزات:**\n"
        f"• 📋 عرض جميع الخدمات من Mousa Card\n"
        f"• 🔄 مزامنة تلقائية للخدمات والأسعار\n"
        f"• 📊 إدارة نسب الربح لكل خدمة\n"
        f"• 🔑 تحديث توكن API\n\n"
        f"اختر الإجراء المطلوب:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= عرض الخدمات =============
@router.callback_query(F.data == "list_api_services")
async def list_api_services(callback: types.CallbackQuery, db_pool):
    """عرض جميع الخدمات من API مع أزرار للتحكم"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await callback.message.edit_text("⏳ جاري جلب الخدمات من Mousa Card...")
    
    api = get_api_client()
    products = await api.get_products()
    
    if not products:
        await callback.message.edit_text(
            "❌ **فشل جلب الخدمات**\n\n"
            "تأكد من:\n"
            "• صحة توكن API\n"
            "• الاتصال بالإنترنت\n"
            "• الموقع متاح",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )
        return
    
    # تجميع الخدمات حسب الفئة
    categories = {}
    for p in products:
        cat_name = p.get('category_name', 'عام')
        if cat_name not in categories:
            categories[cat_name] = []
        categories[cat_name].append(p)
    
    # بناء النص
    text = f"📋 **خدمات Mousa Card**\n\n"
    text += f"📦 إجمالي الخدمات: {len(products)}\n"
    text += "━" * 20 + "\n\n"
    
    for cat_name, cat_products in categories.items():
        text += f"📁 **{cat_name}** ({len(cat_products)}):\n"
        for p in cat_products[:5]:  # عرض أول 5 فقط
            text += f"   • `{p['id']}` - {p['name']} - ${p['price']:.3f}\n"
        if len(cat_products) > 5:
            text += f"   ... و{len(cat_products) - 5} خدمات أخرى\n"
        text += "\n"
    
    # أزرار للتنقل
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔍 بحث في الخدمات", callback_data="search_api_services"),
        types.InlineKeyboardButton(text="🔄 تحديث القائمة", callback_data="list_api_services")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="api_services_menu")
    )
    
    # إذا كان النص طويلاً، نرسل كملف
    if len(text) > 4000:
        from io import BytesIO
        file = BytesIO()
        file.write(text.encode('utf-8'))
        file.seek(0)
        
        await callback.message.answer_document(
            types.BufferedInputFile(file=file.getvalue(), filename="mousa_services.txt"),
            caption="📋 قائمة خدمات Mousa Card"
        )
        await callback.message.answer(
            "🔹 اختر إجراء:",
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


# ============= البحث في الخدمات =============
@router.callback_query(F.data == "search_api_services")
async def search_api_services_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء البحث في الخدمات"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state(APIServiceStates.waiting_search_keyword)
    
    await callback.message.edit_text(
        "🔍 **البحث في خدمات Mousa Card**\n\n"
        "أدخل الكلمة المفتاحية للبحث (مثال: UC, PUBG, Instagram):\n\n"
        "🔹 سيبحث في:\n"
        "• اسم الخدمة\n"
        "• معرف الخدمة\n\n"
        "❌ للإلغاء أرسل /cancel",
        reply_markup=get_back_inline_keyboard("api_services_menu"),
        parse_mode="Markdown"
    )


@router.message(APIServiceStates.waiting_search_keyword)
async def search_api_services_result(message: types.Message, state: FSMContext, db_pool):
    """عرض نتائج البحث"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    keyword = message.text.strip().lower()
    
    if len(keyword) < 2:
        await message.answer(
            "⚠️ الكلمة المفتاحية يجب أن تكون حرفين على الأقل.\nيرجى إعادة المحاولة:"
        )
        return
    
    await message.answer(f"⏳ جاري البحث عن '{keyword}'...")
    
    api = get_api_client()
    products = await api.get_products()
    
    # فلترة النتائج
    results = []
    for p in products:
        if keyword in p['name'].lower() or keyword in str(p['id']):
            results.append(p)
    
    if not results:
        await message.answer(
            f"❌ لم يتم العثور على خدمات تحتوي على '{keyword}'\n\n"
            f"🔹 حاول استخدام كلمات مختلفة.",
            reply_markup=get_back_inline_keyboard("api_services_menu")
        )
        await state.clear()
        return
    
    builder = InlineKeyboardBuilder()
    
    for product in results[:20]:
        builder.row(types.InlineKeyboardButton(
            text=f"📦 {product['name']} (ID: {product['id']}) - ${product['price']:.3f}",
            callback_data=f"view_product_detail_{product['id']}"
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
        f"🔹 اضغط على أي خدمة لعرض تفاصيلها:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.clear()


# ============= عرض تفاصيل الخدمة =============
@router.callback_query(F.data.startswith("view_product_detail_"))
async def view_product_detail(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض تفاصيل خدمة معينة من API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    service_id = int(callback.data.split("_")[3])
    await callback.answer()
    
    await callback.message.edit_text("⏳ جاري جلب تفاصيل الخدمة...")
    
    api = get_api_client()
    product = await api.get_product_details(service_id)
    
    if not product:
        await callback.message.edit_text(
            f"❌ لم يتم العثور على خدمة بالمعرف {service_id}",
            reply_markup=get_back_inline_keyboard("api_services_menu")
        )
        return
    
    # جلب إعدادات الربح الحالية من قاعدة البيانات
    async with db_pool.acquire() as conn:
        db_product = await conn.fetchrow(
            "SELECT id, profit_percentage, api_service_id FROM applications WHERE api_service_id = $1",
            str(service_id)
        )
        current_profit = db_product['profit_percentage'] if db_product else 10
    
    exchange_rate = await get_exchange_rate(db_pool)
    selling_price = product['price'] * (1 + current_profit / 100)
    selling_price_syp = selling_price * exchange_rate
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text=f"📊 تعديل نسبة الربح (حالياً {current_profit}%)",
            callback_data=f"edit_service_profit_{service_id}"
        ),
        types.InlineKeyboardButton(
            text="➕ ربط الخدمة بتطبيق",
            callback_data=f"link_service_to_app_{service_id}"
        )
    )
    builder.row(
        types.InlineKeyboardButton(text="🔄 تحديث السعر", callback_data=f"refresh_service_price_{service_id}"),
        types.InlineKeyboardButton(text="📝 معاينة الوصف", callback_data=f"preview_description_{service_id}")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع للقائمة", callback_data="api_services_menu")
    )
    
    await callback.message.edit_text(
        f"📦 **تفاصيل الخدمة #{service_id}**\n\n"
        f"🔹 **الاسم:** {product['name']}\n"
        f"💰 **سعر المورد:** ${product['price']:.4f}\n"
        f"📊 **نسبة الربح الحالية:** {current_profit}%\n"
        f"💰 **سعر البيع:** ${selling_price:.4f} ≈ {selling_price_syp:,.0f} ل.س\n"
        f"📦 **الحد الأدنى:** {product['min_quantity']}\n"
        f"📈 **الحد الأقصى:** {product['max_quantity']}\n"
        f"✅ **متوفرة:** {'نعم' if product['available'] else 'لا'}\n\n"
        f"🔹 **لربط هذه الخدمة بتطبيق في البوت:**\n"
        f"اضغط على 'ربط الخدمة بتطبيق'",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= تعديل نسبة الربح لخدمة API =============
@router.callback_query(F.data.startswith("edit_service_profit_"))
async def edit_service_profit_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل نسبة الربح لخدمة API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    service_id = int(callback.data.split("_")[3])
    await state.update_data(api_service_id=service_id)
    await state.set_state(APIServiceStates.waiting_profit_percent)
    
    await callback.message.edit_text(
        f"📊 **تعديل نسبة الربح للخدمة #{service_id}**\n\n"
        f"أدخل نسبة الربح المطلوبة (0-100):\n"
        f"مثال: `15` يعني سعر البيع = سعر المورد + 15%\n\n"
        f"❌ للإلغاء أرسل /cancel",
        parse_mode="Markdown"
    )


@router.message(APIServiceStates.waiting_profit_percent)
async def edit_service_profit_save(message: types.Message, state: FSMContext, db_pool):
    """حفظ نسبة الربح الجديدة لخدمة API"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    try:
        profit = int(message.text.strip())
        if profit < 0 or profit > 100:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ **خطأ:** الرجاء إدخال نسبة صحيحة بين 0 و 100.\n"
            "مثال: 15",
            parse_mode="Markdown"
        )
        return
    
    data = await state.get_data()
    service_id = data.get('api_service_id')
    
    async with db_pool.acquire() as conn:
        # تحديث نسبة الربح في قاعدة البيانات
        await conn.execute('''
            UPDATE applications 
            SET profit_percentage = $1, updated_at = CURRENT_TIMESTAMP
            WHERE api_service_id = $2
        ''', profit, str(service_id))
        
        # جلب المنتج المحدث
        app = await conn.fetchrow(
            "SELECT id, name FROM applications WHERE api_service_id = $1",
            str(service_id)
        )
    
    api = get_api_client()
    product = await api.get_product_details(service_id)
    
    exchange_rate = await get_exchange_rate(db_pool)
    selling_price = product['price'] * (1 + profit / 100) if product else 0
    selling_price_syp = selling_price * exchange_rate
    
    await message.answer(
        f"✅ **تم تحديث نسبة الربح بنجاح!**\n\n"
        f"📦 **الخدمة:** {product['name'] if product else service_id}\n"
        f"📊 **نسبة الربح الجديدة:** {profit}%\n"
        f"💰 **سعر البيع الجديد:** ${selling_price:.4f} ≈ {selling_price_syp:,.0f} ل.س\n\n"
        f"🔹 سيتم تطبيق هذا السعر على جميع الطلبات الجديدة.",
        reply_markup=get_back_inline_keyboard("api_services_menu"),
        parse_mode="Markdown"
    )
    
    # مسح الكاش
    clear_cache("mousa_products")
    await state.clear()


# ============= تحديث السعر من API =============
@router.callback_query(F.data.startswith("refresh_service_price_"))
async def refresh_service_price(callback: types.CallbackQuery, db_pool):
    """تحديث سعر الخدمة من API وإعادة حساب سعر البيع"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    service_id = int(callback.data.split("_")[3])
    await callback.answer("🔄 جاري تحديث السعر...")
    
    api = get_api_client()
    product = await api.get_product_details(service_id)
    
    if not product:
        await callback.answer("❌ فشل جلب السعر من API", show_alert=True)
        return
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow(
            "SELECT profit_percentage FROM applications WHERE api_service_id = $1",
            str(service_id)
        )
        profit = app['profit_percentage'] if app else 10
    
    exchange_rate = await get_exchange_rate(db_pool)
    selling_price = product['price'] * (1 + profit / 100)
    selling_price_syp = selling_price * exchange_rate
    
    # تحديث السعر في قاعدة البيانات
    async with db_pool.acquire() as conn:
        await conn.execute('''
            UPDATE applications 
            SET unit_price_usd = $1, updated_at = CURRENT_TIMESTAMP
            WHERE api_service_id = $2
        ''', selling_price, str(service_id))
    
    await callback.message.edit_text(
        f"✅ **تم تحديث سعر الخدمة #{service_id}**\n\n"
        f"💰 **سعر المورد الجديد:** ${product['price']:.4f}\n"
        f"💰 **سعر البيع الجديد:** ${selling_price:.4f} ≈ {selling_price_syp:,.0f} ل.س\n"
        f"📊 **نسبة الربح:** {profit}%",
        reply_markup=get_back_inline_keyboard(f"view_product_detail_{service_id}"),
        parse_mode="Markdown"
    )


# ============= ربط الخدمة بتطبيق =============
@router.callback_query(F.data.startswith("link_service_to_app_"))
async def link_service_to_app_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """ربط خدمة API بتطبيق موجود في البوت"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    service_id = int(callback.data.split("_")[4])
    
    async with db_pool.acquire() as conn:
        apps = await conn.fetch('''
            SELECT id, name, api_service_id 
            FROM applications 
            ORDER BY name
        ''')
    
    if not apps:
        await callback.message.edit_text(
            "⚠️ لا توجد تطبيقات في النظام. قم بإضافة تطبيق أولاً.",
            reply_markup=get_back_inline_keyboard("api_services_menu")
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    for app in apps:
        status = "✅" if app['api_service_id'] else "❌"
        builder.row(types.InlineKeyboardButton(
            text=f"{status} {app['name']}",
            callback_data=f"confirm_link_api_app_{app['id']}_{service_id}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data=f"view_product_detail_{service_id}"
    ))
    
    await callback.message.edit_text(
        f"🔢 **API Service ID:** `{service_id}`\n\n"
        f"🔽 **اختر التطبيق لربطه بهذه الخدمة:**\n\n"
        f"✅ = مرتبط مسبقاً\n"
        f"❌ = غير مرتبط",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("confirm_link_api_app_"))
async def confirm_link_api_app(callback: types.CallbackQuery, db_pool):
    """تأكيد ربط التطبيق بخدمة API"""
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
            str(service_id), app_id
        )
    
    await callback.answer(f"✅ تم ربط {app['name']} بالخدمة {service_id}")
    
    await callback.message.edit_text(
        f"✅ **تم الربط بنجاح!**\n\n"
        f"📱 **التطبيق:** {app['name']}\n"
        f"🔢 **API Service ID:** {service_id}\n\n"
        f"📌 الآن عند الموافقة على طلبات هذا التطبيق، سيتم إرسالها تلقائياً إلى Mousa Card API.",
        reply_markup=get_back_inline_keyboard("api_services_menu"),
        parse_mode="Markdown"
    )


# ============= عرض الرصيد =============
@router.callback_query(F.data == "show_api_balance")
async def show_api_balance(callback: types.CallbackQuery, db_pool):
    """عرض الرصيد المتاح في Mousa Card"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await callback.message.edit_text("⏳ جاري جلب الرصيد...")
    
    api = get_api_client()
    balance = await api.get_balance()
    profile = await api.get_profile()
    
    if balance is not None:
        text = f"💰 **رصيد Mousa Card الحالي:**\n\n"
        text += f"💵 **{balance:,.3f} $**\n\n"
        
        if profile and profile.get('email'):
            text += f"📧 **البريد الإلكتروني:** {profile['email']}\n"
        
        text += f"\n📌 **ملاحظة:** هذا هو الرصيد المتاح لتنفيذ الطلبات التلقائية."
        
        await callback.message.edit_text(
            text,
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            "❌ **فشل جلب الرصيد**\n\n"
            "تأكد من:\n"
            "• صحة توكن API\n"
            "• الاتصال بالإنترنت\n"
            "• الموقع متاح",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )


# ============= اختبار الاتصال =============
@router.callback_query(F.data == "test_api_connection")
async def test_api_connection(callback: types.CallbackQuery, db_pool):
    """اختبار الاتصال بـ Mousa Card API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await callback.message.edit_text("⏳ جاري اختبار الاتصال بـ Mousa Card API...")
    
    api = get_api_client()
    products = await api.get_products()
    
    if products:
        balance = await api.get_balance()
        
        text = f"✅ **الاتصال بـ Mousa Card API يعمل بنجاح!**\n\n"
        text += f"🌐 **Base URL:** {api.base_url}\n"
        text += f"📦 **عدد المنتجات المتاحة:** {len(products)}\n"
        
        if balance:
            text += f"💰 **الرصيد المتاح:** ${balance:,.3f}\n\n"
        
        text += "🔹 **نماذج من المنتجات:**\n"
        for i, product in enumerate(products[:5]):
            text += f"   • `{product['id']}` - {product['name']} - ${product['price']:.3f}\n"
        
        await callback.message.edit_text(
            text,
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            f"❌ **فشل الاتصال بـ Mousa Card API**\n\n"
            f"🌐 **Base URL:** {api.base_url}\n\n"
            f"🔍 **أسباب محتملة:**\n"
            f"• توكن API غير صالح\n"
            f"• مشكلة في الاتصال بالإنترنت\n"
            f"• الموقع غير متاح",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )


# ============= مزامنة الخدمات =============
@router.callback_query(F.data == "sync_services_from_api")
async def sync_services_from_api(callback: types.CallbackQuery, db_pool):
    """مزامنة الخدمات من Mousa Card API إلى قاعدة البيانات"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await callback.message.edit_text("⏳ جاري مزامنة الخدمات من Mousa Card...\n(قد يستغرق هذا دقيقة)")
    
    api = get_api_client()
    
    # جلب نسبة الربح الافتراضية من الإعدادات
    async with db_pool.acquire() as conn:
        default_profit = await conn.fetchval(
            "SELECT value::int FROM bot_settings WHERE key = 'api_default_profit'"
        ) or 10
    
    synced_count = await api.sync_services_to_db(db_pool, default_profit)
    
    # مسح الكاش
    clear_cache("mousa_products")
    clear_cache("products_list")
    
    if synced_count > 0:
        await callback.message.edit_text(
            f"✅ **تمت المزامنة بنجاح!**\n\n"
            f"📦 تمت مزامنة {synced_count} خدمة من Mousa Card\n"
            f"📊 نسبة الربح الافتراضية: {default_profit}%\n\n"
            f"🔹 يمكنك الآن عرض الخدمات من القائمة الرئيسية.",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            "⚠️ **لم تتم إضافة خدمات جديدة**\n\n"
            "قد تكون جميع الخدمات موجودة مسبقاً، أو هناك مشكلة في الاتصال.",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )


# ============= إعدادات الربح =============
@router.callback_query(F.data == "api_profit_settings")
async def api_profit_settings(callback: types.CallbackQuery, db_pool):
    """إعدادات نسبة الربح الافتراضية لـ API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        default_profit = await conn.fetchval(
            "SELECT value::int FROM bot_settings WHERE key = 'api_default_profit'"
        ) or 10
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="📊 تغيير النسبة الافتراضية",
        callback_data="change_default_profit"
    ))
    builder.row(types.InlineKeyboardButton(
        text="📋 عرض الخدمات مع نسب الربح",
        callback_data="list_services_with_profit"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="api_services_menu"
    ))
    
    await callback.message.edit_text(
        f"📊 **إعدادات الربح - Mousa Card API**\n\n"
        f"🔹 **نسبة الربح الافتراضية:** {default_profit}%\n\n"
        f"📌 **كيف يعمل؟**\n"
        f"• سعر المورد من API: سعر الخدمة الأصلي\n"
        f"• سعر البيع = سعر المورد × (1 + نسبة الربح/100)\n"
        f"• يمكنك تعديل نسبة الربح لكل خدمة على حدة\n\n"
        f"اختر الإجراء المطلوب:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "change_default_profit")
async def change_default_profit_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تغيير نسبة الربح الافتراضية"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state("waiting_default_profit")
    
    await callback.message.edit_text(
        "📊 **تغيير نسبة الربح الافتراضية**\n\n"
        "أدخل نسبة الربح الجديدة (0-100):\n"
        "مثال: `15` يعني 15% ربح على جميع الخدمات الجديدة\n\n"
        "❌ للإلغاء أرسل /cancel",
        parse_mode="Markdown"
    )


@router.message(lambda m: m.text and m.text.isdigit() and 0 <= int(m.text) <= 100)
async def change_default_profit_save(message: types.Message, state: FSMContext, db_pool):
    """حفظ نسبة الربح الافتراضية الجديدة"""
    from database.users import is_admin_user
    
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    # التحقق من أن المستخدم في الحالة الصحيحة
    current_state = await state.get_state()
    if current_state != "waiting_default_profit":
        return
    
    profit = int(message.text)
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO bot_settings (key, value, description)
            VALUES ('api_default_profit', $1, 'نسبة الربح الافتراضية لخدمات API')
            ON CONFLICT (key) DO UPDATE SET value = $1
        ''', str(profit))
    
    await message.answer(
        f"✅ **تم تحديث نسبة الربح الافتراضية إلى {profit}%**\n\n"
        f"🔹 سيتم تطبيق هذه النسبة على الخدمات الجديدة عند المزامنة.",
        reply_markup=get_back_inline_keyboard("api_profit_settings"),
        parse_mode="Markdown"
    )
    await state.clear()


# ============= تحديث التوكن =============
@router.callback_query(F.data == "update_api_token")
async def update_api_token_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تحديث توكن API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state(APIServiceStates.waiting_api_token)
    
    await callback.message.edit_text(
        "🔑 **تحديث توكن API**\n\n"
        "أدخل توكن API الجديد من موقع Mousa Card:\n\n"
        "💡 يمكنك الحصول على التوكن من:\n"
        "https://mousa-card.com/api-docs\n\n"
        "❌ للإلغاء أرسل /cancel",
        parse_mode="Markdown"
    )


@router.message(APIServiceStates.waiting_api_token)
async def update_api_token_save(message: types.Message, state: FSMContext, db_pool):
    """حفظ توكن API الجديد"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    token = message.text.strip()
    
    if len(token) < 10:
        await message.answer(
            "❌ التوكن قصير جداً. يرجى التحقق من التوكن وإعادة المحاولة:"
        )
        return
    
    # تحديث التوكن في العميل
    set_api_token(token)
    
    # حفظ في قاعدة البيانات
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO bot_settings (key, value, description)
            VALUES ('api_token', $1, 'توكن API Mousa Card')
            ON CONFLICT (key) DO UPDATE SET value = $1
        ''', token)
    
    # اختبار التوكن الجديد
    api = get_api_client()
    products = await api.get_products()
    
    if products:
        await message.answer(
            f"✅ **تم تحديث توكن API بنجاح!**\n\n"
            f"🔹 تم العثور على {len(products)} خدمة متاحة.\n"
            f"🔹 يمكنك الآن مزامنة الخدمات.",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"⚠️ **تم تحديث التوكن لكن فشل الاتصال**\n\n"
            f"تأكد من صحة التوكن وحاول مرة أخرى.",
            reply_markup=get_back_inline_keyboard("api_services_menu"),
            parse_mode="Markdown"
        )
    
    await state.clear()


# ============= استيراد التصنيفات =============
@router.callback_query(F.data == "import_categories")
async def import_categories(callback: types.CallbackQuery, db_pool):
    """استيراد التصنيفات من Mousa Card"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await callback.message.edit_text("⏳ جاري استيراد التصنيفات من Mousa Card...")
    
    api = get_api_client()
    content = await api.get_categories_content(0)
    
    categories = content.get('categories', [])
    products = content.get('products', [])
    
    if not categories and not products:
        await callback.message.edit_text(
            "❌ فشل استيراد التصنيفات",
            reply_markup=get_back_inline_keyboard("api_services_menu")
        )
        return
    
    text = f"📁 **تصنيفات Mousa Card**\n\n"
    
    if categories:
        text += "**التصنيفات الرئيسية:**\n"
        for cat in categories[:15]:
            text += f"• {cat['name']} (ID: {cat['id']})\n"
    
    if products:
        text += f"\n**منتجات مميزة:**\n"
        for p in products[:10]:
            text += f"• {p['name']} - ${p['price']:.3f}\n"
    
    text += f"\n📊 إجمالي التصنيفات: {len(categories)}"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("api_services_menu"),
        parse_mode="Markdown"
    )


# ============= مسح كاش API =============
@router.callback_query(F.data == "clear_api_cache")
async def clear_api_cache(callback: types.CallbackQuery, db_pool):
    """مسح كاش API"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    clear_cache("mousa_products")
    clear_cache("mousa_categories")
    
    await callback.answer("✅ تم مسح كاش API", show_alert=True)
    
    await callback.message.edit_text(
        "✅ **تم مسح كاش API بنجاح!**\n\n"
        "🔹 في المرة القادمة سيتم جلب البيانات الجديدة من Mousa Card.",
        reply_markup=get_back_inline_keyboard("api_services_menu"),
        parse_mode="Markdown"
    )


# ============= معالج البحث المتقدم =============
@router.callback_query(F.data.startswith("search_more_"))
async def search_more(callback: types.CallbackQuery):
    """عرض المزيد من نتائج البحث"""
    keyword = callback.data.replace("search_more_", "")
    
    api = get_api_client()
    products = await api.get_products()
    
    results = [p for p in products if keyword in p['name'].lower() or keyword in str(p['id'])]
    
    if not results:
        await callback.answer("لا توجد نتائج إضافية")
        return
    
    builder = InlineKeyboardBuilder()
    
    for product in results[20:40]:
        builder.row(types.InlineKeyboardButton(
            text=f"📦 {product['name']} (ID: {product['id']}) - ${product['price']:.3f}",
            callback_data=f"view_product_detail_{product['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للبحث",
        callback_data="search_api_services"
    ))
    
    await callback.message.edit_text(
        f"🔍 **نتائج البحث عن '{keyword}' (الصفحة 2):**\n\n"
        f"عرض {min(40, len(results))} من {len(results)} نتيجة",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
