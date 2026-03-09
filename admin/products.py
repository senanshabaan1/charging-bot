# admin/products.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from utils import is_admin, format_amount, is_valid_positive_number
from handlers.keyboards import get_cancel_keyboard

logger = logging.getLogger(__name__)
router = Router(name="admin_products")

class ProductStates(StatesGroup):
    waiting_product_category = State()
    waiting_product_name = State()
    waiting_product_price = State()
    waiting_product_min = State()
    waiting_product_profit = State()
    waiting_product_id = State()

# إضافة منتج
@router.callback_query(F.data == "add_product")
async def add_product_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
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
        "📱 **إضافة منتج جديد**\n\nاختر القسم أولاً:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(ProductStates.waiting_product_category)

@router.callback_query(F.data.startswith("sel_cat_"))
async def select_category_for_product(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[2])
    await state.update_data(category_id=cat_id)
    await callback.message.edit_text("📝 **أدخل اسم المنتج:**")
    await state.set_state(ProductStates.waiting_product_name)

@router.message(ProductStates.waiting_product_name)
async def get_product_name(message: types.Message, state: FSMContext):
    await state.update_data(product_name=message.text)
    await message.answer(
        "💰 **أدخل سعر الوحدة بالدولار:**\nمثال: 0.001\n\nأو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ProductStates.waiting_product_price)

@router.message(ProductStates.waiting_product_price)
async def get_product_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(product_price=price)
        await message.answer(
            "📦 **أدخل الحد الأدنى للكمية:**\nمثال: 100\n\nأو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(ProductStates.waiting_product_min)
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح:", reply_markup=get_cancel_keyboard())

@router.message(ProductStates.waiting_product_min)
async def get_product_min(message: types.Message, state: FSMContext):
    try:
        min_units = int(message.text)
        if min_units <= 0:
            return await message.answer("⚠️ الحد الأدنى يجب أن يكون أكبر من 0:", reply_markup=get_cancel_keyboard())
        
        await state.update_data(product_min=min_units)
        await message.answer(
            "📈 **أدخل نسبة الربح (%):**\nمثال: 10\n\nأو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(ProductStates.waiting_product_profit)
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح:", reply_markup=get_cancel_keyboard())

@router.message(ProductStates.waiting_product_profit)
async def get_product_profit(message: types.Message, state: FSMContext, db_pool):
    try:
        profit = float(message.text)
        data = await state.get_data()
        
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, category_id, type)
                VALUES ($1, $2, $3, $4, $5, 'service')
            ''', data['product_name'], data['product_price'], data['product_min'], profit, data['category_id'])
        
        await message.answer(f"✅ **تم إضافة المنتج بنجاح!**\n\n📱 الاسم: {data['product_name']}\n💰 السعر: ${data['product_price']}\n📦 الحد الأدنى: {data['product_min']}\n📈 الربح: {profit}%")
        await state.clear()
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح:", reply_markup=get_cancel_keyboard())

# تعديل منتج
@router.callback_query(F.data == "edit_product")
async def edit_product_list(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.id, a.name, c.display_name 
            FROM applications a LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    if not products:
        return await callback.answer("❌ لا توجد منتجات", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(types.InlineKeyboardButton(
            text=f"{p['name']} ({p['display_name']})",
            callback_data=f"edit_prod_{p['id']}"
        ))
    
    await callback.message.edit_text("✏️ **اختر المنتج للتعديل:**", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("edit_prod_"))
async def edit_product_form(callback: types.CallbackQuery, state: FSMContext, db_pool):
    prod_id = int(callback.data.split("_")[2])
    
    async with db_pool.acquire() as conn:
        product = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", prod_id)
    
    if not product:
        return await callback.answer("❌ المنتج غير موجود", show_alert=True)
    
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
    await state.set_state(ProductStates.waiting_product_id)

@router.message(ProductStates.waiting_product_id)
async def update_product(message: types.Message, state: FSMContext, db_pool):
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
        
        await message.answer("✅ **تم تحديث المنتج بنجاح!**")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# حذف منتج
@router.callback_query(F.data == "delete_product")
async def delete_product_list(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.id, a.name, c.display_name 
            FROM applications a LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    if not products:
        return await callback.answer("❌ لا توجد منتجات", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(types.InlineKeyboardButton(
            text=f"🗑️ {p['name']} ({p['display_name']})",
            callback_data=f"del_prod_{p['id']}"
        ))
    
    await callback.message.edit_text("🗑️ **اختر المنتج للحذف:**", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("del_prod_"))
async def confirm_delete_product(callback: types.CallbackQuery, db_pool):
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
    prod_id = int(callback.data.split("_")[2])
    
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM applications WHERE id = $1", prod_id)
    
    await callback.message.edit_text("✅ **تم حذف المنتج بنجاح!**")

# عرض المنتجات
@router.callback_query(F.data == "list_products")
async def list_products(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.*, c.display_name 
            FROM applications a LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    if not products:
        return await callback.answer("❌ لا توجد منتجات", show_alert=True)
    
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

@router.callback_query(F.data == "cancel_del")
async def cancel_action(callback: types.CallbackQuery):
    await callback.message.edit_text("✅ تم الإلغاء.")