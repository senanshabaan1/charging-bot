# admin/products.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import time
from typing import Optional, List, Dict, Any
from utils import is_admin, format_amount, is_valid_positive_number, safe_edit_message
from handlers.keyboards import get_confirmation_keyboard
from cache import cached, clear_cache  # ✅ استيراد الكاش

logger = logging.getLogger(__name__)
router = Router(name="admin_products")

class ProductStates(StatesGroup):
    waiting_product_category = State()
    waiting_product_name = State()
    waiting_product_price = State()
    waiting_product_min = State()
    waiting_product_profit = State()
    waiting_product_id = State()

# ✅ ثوابت للأداء
PRODUCT_TYPES = ['service', 'game', 'subscription']
PRODUCT_TYPE_ICONS = {
    'service': '📱',
    'game': '🎮',
    'subscription': '📅'
}

# ✅ كاش للأقسام
@cached(ttl=300, key_prefix="categories")
async def get_cached_categories(db_pool):
    """جلب الأقسام مع كاش 5 دقائق"""
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT id, display_name FROM categories ORDER BY sort_order")

# ✅ كاش لقائمة المنتجات
@cached(ttl=60, key_prefix="products_list")
async def get_cached_products(db_pool):
    """جلب قائمة المنتجات مع كاش دقيقة"""
    async with db_pool.acquire() as conn:
        return await conn.fetch('''
            SELECT a.id, a.name, c.display_name 
            FROM applications a 
            LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')

# ✅ كاش لتفاصيل المنتج
@cached(ttl=60, key_prefix="product_details")
async def get_cached_product_details(db_pool, product_id: int):
    """جلب تفاصيل المنتج مع كاش دقيقة"""
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM applications WHERE id = $1", product_id)

# ✅ كاش لعدد المنتجات في كل قسم
@cached(ttl=60, key_prefix="products_count")
async def get_cached_products_count(db_pool, category_id: Optional[int] = None):
    """جلب عدد المنتجات مع كاش دقيقة"""
    async with db_pool.acquire() as conn:
        if category_id:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM applications WHERE category_id = $1",
                category_id
            ) or 0
        else:
            return await conn.fetchval("SELECT COUNT(*) FROM applications") or 0

# إضافة منتج
@router.callback_query(F.data == "add_product")
async def add_product_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إضافة منتج جديد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    categories = await get_cached_categories(db_pool)
    
    if not categories:
        await callback.answer("❌ لا توجد أقسام. أضف قسماً أولاً.", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        products_count = await get_cached_products_count(db_pool, cat['id'])
        builder.row(types.InlineKeyboardButton(
            text=f"{cat['display_name']} ({products_count} منتج)",
            callback_data=f"sel_cat_{cat['id']}"
        ))
    
    await callback.message.answer(
        "📱 **إضافة منتج جديد**\n\n"
        "اختر القسم أولاً:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(ProductStates.waiting_product_category)

@router.callback_query(F.data.startswith("sel_cat_"))
async def select_category_for_product(callback: types.CallbackQuery, state: FSMContext):
    """اختيار القسم للمنتج"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    cat_id = int(callback.data.split("_")[2])
    await state.update_data(category_id=cat_id)
    
    await safe_edit_message(
        callback.message,
        "📝 **أدخل اسم المنتج:**\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    await state.set_state(ProductStates.waiting_product_name)

@router.message(ProductStates.waiting_product_name)
async def get_product_name(message: types.Message, state: FSMContext):
    """استلام اسم المنتج"""
    if not is_admin(message.from_user.id):
        return
    
    product_name = message.text.strip()
    if len(product_name) < 2:
        return await message.answer(
            "❌ اسم المنتج قصير جداً. أدخل اسم أطول:",
            reply_markup=get_cancel_keyboard()
        )
    
    await state.update_data(product_name=product_name)
    await message.answer(
        "💰 **أدخل سعر الوحدة بالدولار:**\n"
        "مثال: 0.001\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ProductStates.waiting_product_price)

@router.message(ProductStates.waiting_product_price)
async def get_product_price(message: types.Message, state: FSMContext):
    """استلام سعر المنتج"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        price = float(message.text.replace(',', ''))
        if price <= 0:
            return await message.answer(
                "⚠️ السعر يجب أن يكون أكبر من 0:",
                reply_markup=get_cancel_keyboard()
            )
        
        await state.update_data(product_price=price)
        await message.answer(
            "📦 **أدخل الحد الأدنى للكمية:**\n"
            "مثال: 100\n\n"
            "أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(ProductStates.waiting_product_min)
    except ValueError:
        await message.answer(
            "⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 0.001):",
            reply_markup=get_cancel_keyboard()
        )

@router.message(ProductStates.waiting_product_min)
async def get_product_min(message: types.Message, state: FSMContext):
    """استلام الحد الأدنى للكمية"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        min_units = int(message.text)
        if min_units <= 0:
            return await message.answer(
                "⚠️ الحد الأدنى يجب أن يكون أكبر من 0:",
                reply_markup=get_cancel_keyboard()
            )
        
        await state.update_data(product_min=min_units)
        
        # ✅ إضافة اختيار نوع المنتج
        builder = InlineKeyboardBuilder()
        for product_type in PRODUCT_TYPES:
            icon = PRODUCT_TYPE_ICONS.get(product_type, '📱')
            builder.row(types.InlineKeyboardButton(
                text=f"{icon} {product_type}",
                callback_data=f"set_type_{product_type}"
            ))
        
        await message.answer(
            "📱 **اختر نوع المنتج:**\n\n"
            "أو أرسل /skip للاستمرار بدون تحديد النوع",
            reply_markup=builder.as_markup()
        )
        # سنستخدم حالة مؤقتة أو نخزن في FSM
        await state.update_data(product_type='service')  # القيمة الافتراضية
        await message.answer(
            "📈 **أدخل نسبة الربح (%):**\n"
            "مثال: 10\n\n"
            "أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(ProductStates.waiting_product_profit)
        
    except ValueError:
        await message.answer(
            "⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 100):",
            reply_markup=get_cancel_keyboard()
        )

@router.message(ProductStates.waiting_product_profit)
async def get_product_profit(message: types.Message, state: FSMContext, db_pool):
    """استلام نسبة الربح وحفظ المنتج"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        profit = float(message.text)
        if profit < 0:
            return await message.answer(
                "⚠️ نسبة الربح لا يمكن أن تكون سالبة:",
                reply_markup=get_cancel_keyboard()
            )
        
        data = await state.get_data()
        start_time = time.time()
        
        async with db_pool.acquire() as conn:
            product_id = await conn.fetchval('''
                INSERT INTO applications 
                (name, unit_price_usd, min_units, profit_percentage, category_id, type, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                RETURNING id
            ''', 
            data['product_name'], 
            data['product_price'], 
            data['product_min'], 
            profit, 
            data['category_id'],
            data.get('product_type', 'service')
            )
        
        # ✅ مسح الكاش
        clear_cache("products_list")
        clear_cache(f"products_count:{data['category_id']}")
        clear_cache("products_count")
        
        elapsed_time = time.time() - start_time
        
        await message.answer(
            f"✅ **تم إضافة المنتج بنجاح!**\n\n"
            f"📱 الاسم: {data['product_name']}\n"
            f"💰 السعر: ${data['product_price']}\n"
            f"📦 الحد الأدنى: {data['product_min']}\n"
            f"📈 الربح: {profit}%\n"
            f"🆔 المعرف: {product_id}\n"
            f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
        )
        await state.clear()
        
    except ValueError:
        await message.answer(
            "⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 10):",
            reply_markup=get_cancel_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة المنتج: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

@router.callback_query(F.data.startswith("set_type_"))
async def set_product_type(callback: types.CallbackQuery, state: FSMContext):
    """تحديد نوع المنتج"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    product_type = callback.data.replace("set_type_", "")
    await state.update_data(product_type=product_type)
    
    await safe_edit_message(
        callback.message,
        f"✅ تم اختيار النوع: {PRODUCT_TYPE_ICONS.get(product_type, '📱')} {product_type}\n\n"
        "تابع إدخال البيانات..."
    )

# تعديل منتج
@router.callback_query(F.data == "edit_product")
async def edit_product_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المنتجات للتعديل"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    products = await get_cached_products(db_pool)
    
    if not products:
        return await callback.answer("❌ لا توجد منتجات", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(types.InlineKeyboardButton(
            text=f"✏️ {p['name']} ({p['display_name']})",
            callback_data=f"edit_prod_{p['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="add_product"))
    
    await safe_edit_message(
        callback.message,
        "✏️ **اختر المنتج للتعديل:**",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("edit_prod_"))
async def edit_product_form(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض نموذج تعديل المنتج"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    prod_id = int(callback.data.split("_")[2])
    
    # ✅ استخدام الكاش
    product = await get_cached_product_details(db_pool, prod_id)
    
    if not product:
        return await callback.answer("❌ المنتج غير موجود", show_alert=True)
    
    await state.update_data(product_id=prod_id)
    
    text = (
        f"✏️ **تعديل المنتج:** {product['name']}\n\n"
        f"**البيانات الحالية:**\n"
        f"• القسم: {product.get('category_id', 'غير محدد')}\n"
        f"• السعر: ${product['unit_price_usd']}\n"
        f"• الحد الأدنى: {product['min_units']}\n"
        f"• الربح: {product['profit_percentage']}%\n"
        f"• النوع: {product['type']}\n"
        f"• الحالة: {'✅ نشط' if product['is_active'] else '❌ غير نشط'}\n\n"
        f"📝 أرسل البيانات الجديدة بالصيغة:\n"
        f"`الاسم|السعر|الحد_الأدنى|الربح`\n\n"
        f"مثال: `اسم جديد|0.002|200|15`\n\n"
        f"أو أرسل /cancel للإلغاء"
    )
    
    await safe_edit_message(callback.message, text)
    await state.set_state(ProductStates.waiting_product_id)

@router.message(ProductStates.waiting_product_id)
async def update_product(message: types.Message, state: FSMContext, db_pool):
    """تحديث بيانات المنتج"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        parts = message.text.split('|')
        if len(parts) != 4:
            return await message.answer(
                "❌ صيغة غير صحيحة. استخدم: `الاسم|السعر|الحد_الأدنى|الربح`\n"
                "مثال: `اسم جديد|0.002|200|15`"
            )
        
        name, price, min_units, profit = [p.strip() for p in parts]
        data = await state.get_data()
        prod_id = data['product_id']
        
        # التحقق من صحة البيانات
        try:
            price_float = float(price)
            min_int = int(min_units)
            profit_float = float(profit)
            
            if price_float <= 0 or min_int <= 0 or profit_float < 0:
                return await message.answer("❌ القيم يجب أن تكون موجبة")
        except ValueError:
            return await message.answer("❌ القيم غير صحيحة. تأكد من الأرقام")
        
        start_time = time.time()
        
        async with db_pool.acquire() as conn:
            # جلب معلومات المنتج القديم لمسح الكاش
            old_product = await conn.fetchrow(
                "SELECT category_id FROM applications WHERE id = $1",
                prod_id
            )
            
            await conn.execute('''
                UPDATE applications 
                SET name = $1, unit_price_usd = $2, min_units = $3, profit_percentage = $4
                WHERE id = $5
            ''', name, price_float, min_int, profit_float, prod_id)
        
        # ✅ مسح الكاش
        clear_cache("products_list")
        clear_cache(f"product_details:{prod_id}")
        if old_product:
            clear_cache(f"products_count:{old_product['category_id']}")
        
        elapsed_time = time.time() - start_time
        
        await message.answer(
            f"✅ **تم تحديث المنتج بنجاح!**\n\n"
            f"📱 الاسم: {name}\n"
            f"💰 السعر: ${price_float}\n"
            f"📦 الحد الأدنى: {min_int}\n"
            f"📈 الربح: {profit_float}%\n"
            f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث المنتج: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# حذف منتج
@router.callback_query(F.data == "delete_product")
async def delete_product_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المنتجات للحذف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    products = await get_cached_products(db_pool)
    
    if not products:
        return await callback.answer("❌ لا توجد منتجات", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(types.InlineKeyboardButton(
            text=f"🗑️ {p['name']} ({p['display_name']})",
            callback_data=f"del_prod_{p['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="add_product"))
    
    await safe_edit_message(
        callback.message,
        "🗑️ **اختر المنتج للحذف:**",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("del_prod_"))
async def confirm_delete_product(callback: types.CallbackQuery, db_pool):
    """تأكيد حذف المنتج"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    prod_id = int(callback.data.split("_")[2])
    
    # ✅ استخدام الكاش
    product = await get_cached_product_details(db_pool, prod_id)
    
    if not product:
        return await callback.answer("❌ المنتج غير موجود", show_alert=True)
    
    # ✅ التحقق من وجود خيارات مرتبطة
    async with db_pool.acquire() as conn:
        options_count = await conn.fetchval(
            "SELECT COUNT(*) FROM product_options WHERE product_id = $1",
            prod_id
        ) or 0
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم، احذف", callback_data=f"conf_del_{prod_id}"),
        types.InlineKeyboardButton(text="❌ لا", callback_data="cancel_del")
    )
    
    warning = ""
    if options_count > 0:
        warning = f"\n\n⚠️ **تحذير:** هذا المنتج لديه {options_count} خيارات مرتبطة به وستُحذف أيضاً!"
    
    await safe_edit_message(
        callback.message,
        f"⚠️ **تأكيد حذف المنتج**\n\n"
        f"هل أنت متأكد من حذف المنتج **{product['name']}**؟"
        f"{warning}",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("conf_del_"))
async def execute_delete_product(callback: types.CallbackQuery, db_pool):
    """تنفيذ حذف المنتج"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    prod_id = int(callback.data.split("_")[2])
    
    start_time = time.time()
    
    async with db_pool.acquire() as conn:
        # جلب معلومات المنتج لمسح الكاش
        product = await conn.fetchrow(
            "SELECT name, category_id FROM applications WHERE id = $1",
            prod_id
        )
        
        if not product:
            return await callback.answer("❌ المنتج غير موجود", show_alert=True)
        
        # حذف الخيارات المرتبطة أولاً
        await conn.execute("DELETE FROM product_options WHERE product_id = $1", prod_id)
        
        # حذف المنتج
        await conn.execute("DELETE FROM applications WHERE id = $1", prod_id)
    
    # ✅ مسح الكاش
    clear_cache("products_list")
    clear_cache(f"product_details:{prod_id}")
    clear_cache(f"products_count:{product['category_id']}")
    clear_cache("products_count")
    clear_cache(f"product_options:{prod_id}")
    
    elapsed_time = time.time() - start_time
    
    await safe_edit_message(
        callback.message,
        f"✅ **تم حذف المنتج بنجاح!**\n\n"
        f"📱 المنتج: {product['name']}\n"
        f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
    )

# عرض المنتجات
# عرض المنتجات
@router.callback_query(F.data == "list_products")
async def list_products(callback: types.CallbackQuery, db_pool):
    """عرض جميع المنتجات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    start_time = time.time()
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.*, c.display_name,
                   (SELECT COUNT(*) FROM product_options WHERE product_id = a.id) as options_count
            FROM applications a 
            LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    if not products:
        # ✅ إذا ما في منتجات، عرض رسالة مع زر رجوع
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(
            text="🔙 رجوع للوحة التحكم", 
            callback_data="back_to_admin"
        ))
        
        await safe_edit_message(
            callback.message,
            "❌ لا توجد منتجات",
            reply_markup=builder.as_markup()
        )
        return
    
    # تجميع المنتجات حسب القسم
    products_by_category = {}
    for p in products:
        cat_name = p['display_name'] or 'بدون قسم'
        if cat_name not in products_by_category:
            products_by_category[cat_name] = []
        products_by_category[cat_name].append(p)
    
    text = "📱 **قائمة المنتجات**\n\n"
    total_count = len(products)
    text += f"إجمالي المنتجات: {total_count}\n"
    text += "=" * 30 + "\n\n"
    
    for category, cats in products_by_category.items():
        text += f"**{category}** ({len(cats)} منتج):\n"
        for p in cats:
            status = "✅" if p['is_active'] else "❌"
            options_info = f" ({p['options_count']} خيار)" if p['options_count'] > 0 else ""
            text += f"{status} **{p['name']}**{options_info}\n"
            text += f"   💰 ${p['unit_price_usd']} | 📦 {p['min_units']} | 📈 {p['profit_percentage']}%\n"
        text += "\n"
    
    elapsed_time = time.time() - start_time
    text += f"\n⚡ وقت التحميل: {elapsed_time:.2f} ثانية"
    
    # ✅ إضافة زر الرجوع للوحة التحكم
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للوحة التحكم", 
        callback_data="back_to_admin"
    ))
    
    # تقسيم النص إذا كان طويلاً
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for i, part in enumerate(parts):
            if i == 0:
                await safe_edit_message(callback.message, part, reply_markup=builder.as_markup() if i == len(parts)-1 else None)
            else:
                await callback.message.answer(part, reply_markup=builder.as_markup() if i == len(parts)-1 else None)
    else:
        await safe_edit_message(
            callback.message, 
            text, 
            reply_markup=builder.as_markup()
        )
@router.callback_query(F.data == "cancel_del")
async def cancel_action(callback: types.CallbackQuery):
    """إلغاء عملية الحذف"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await safe_edit_message(callback.message, "✅ تم الإلغاء.")

# تصدير المنتجات
@router.callback_query(F.data == "export_products")
async def export_products(callback: types.CallbackQuery, db_pool):
    """تصدير قائمة المنتجات كملف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer("📊 جاري إنشاء الملف...")
    
    try:
        async with db_pool.acquire() as conn:
            products = await conn.fetch('''
                SELECT a.*, c.display_name as category_name,
                       (SELECT COUNT(*) FROM product_options WHERE product_id = a.id) as options_count
                FROM applications a 
                LEFT JOIN categories c ON a.category_id = c.id
                ORDER BY c.sort_order, a.name
            ''')
        
        # إنشاء نص الملف
        report = "📊 **تقرير المنتجات**\n\n"
        report += f"تاريخ التقرير: {get_formatted_damascus_time()}\n"
        report += "=" * 50 + "\n\n"
        
        for p in products:
            report += f"**{p['name']}**\n"
            report += f"• القسم: {p['category_name'] or 'بدون قسم'}\n"
            report += f"• السعر: ${p['unit_price_usd']}\n"
            report += f"• الحد الأدنى: {p['min_units']}\n"
            report += f"• الربح: {p['profit_percentage']}%\n"
            report += f"• النوع: {p['type']}\n"
            report += f"• الحالة: {'نشط' if p['is_active'] else 'غير نشط'}\n"
            report += f"• عدد الخيارات: {p['options_count']}\n"
            report += "-" * 30 + "\n"
        
        # إرسال الملف
        from io import BytesIO
        file = BytesIO()
        file.write(report.encode('utf-8'))
        file.seek(0)
        
        filename = f"products_report_{get_formatted_damascus_time().replace(':', '-')}.txt"
        
        await callback.message.answer_document(
            types.BufferedInputFile(file=file.getvalue(), filename=filename),
            caption=f"✅ تقرير المنتجات - {len(products)} منتج"
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في تصدير المنتجات: {e}")
        await callback.answer("❌ فشل إنشاء التقرير", show_alert=True)
