# admin/options.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from utils import is_admin, format_amount, is_valid_positive_number, get_formatted_damascus_time
from handlers.keyboards import get_cancel_keyboard
from database import get_product_option, get_exchange_rate

logger = logging.getLogger(__name__)
router = Router(name="admin_options")

class OptionStates(StatesGroup):
    waiting_option_name = State()
    waiting_option_quantity = State()
    waiting_option_supplier_price = State()
    waiting_option_profit = State()
    waiting_option_description = State()
    waiting_edit_option_field = State()
    waiting_edit_option_value = State()
    waiting_new_game_name = State()
    waiting_new_game_type = State()

# قائمة إدارة الخيارات الرئيسية
@router.callback_query(F.data == "manage_options")
async def manage_options_start(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    
    if not categories:
        await callback.message.edit_text(
            "⚠️ لا توجد أقسام حالياً.\n\nقم بإضافة قسم أولاً من لوحة التحكم.",
            reply_markup=InlineKeyboardBuilder().row(
                types.InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="back_to_admin")
            ).as_markup()
        )
        return
    
    text = "📁 **إدارة خيارات المنتجات**\n\nاختر القسم لعرض التطبيقات التابعة له:\n\n"
    builder = InlineKeyboardBuilder()
    
    for cat in categories:
        async with db_pool.acquire() as conn:
            apps_count = await conn.fetchval("SELECT COUNT(*) FROM applications WHERE category_id = $1", cat['id'])
        
        builder.row(types.InlineKeyboardButton(
            text=f"{cat['icon']} {cat['display_name']} ({apps_count} تطبيق)",
            callback_data=f"manage_opts_cat_{cat['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(text="➕ إضافة تطبيق جديد", callback_data="add_new_game"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="back_to_admin"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("manage_opts_cat_"))
async def manage_options_category(callback: types.CallbackQuery, db_pool):
    cat_id = int(callback.data.split("_")[3])
    
    async with db_pool.acquire() as conn:
        category = await conn.fetchrow("SELECT * FROM categories WHERE id = $1", cat_id)
        products = await conn.fetch('''
            SELECT a.id, a.name, a.type, a.is_active,
                   (SELECT COUNT(*) FROM product_options WHERE product_id = a.id) as options_count
            FROM applications a
            WHERE a.category_id = $1
            ORDER BY a.is_active DESC, a.name
        ''', cat_id)
    
    if not products:
        await callback.message.edit_text(
            f"{category['icon']} **{category['display_name']}**\n\n"
            f"⚠️ لا توجد تطبيقات في هذا القسم.\n\n"
            f"يمكنك إضافة تطبيق جديد باستخدام الزر أدناه.",
            reply_markup=InlineKeyboardBuilder().row(
                types.InlineKeyboardButton(text="➕ إضافة تطبيق جديد", callback_data="add_new_game"),
                types.InlineKeyboardButton(text="🔙 رجوع للأقسام", callback_data="manage_options")
            ).as_markup()
        )
        return
    
    text = f"{category['icon']} **{category['display_name']}**\n"
    text += f"📊 عدد التطبيقات: {len(products)}\n➖➖➖➖➖➖\n\n"
    
    builder = InlineKeyboardBuilder()
    for product in products:
        if not product['is_active']:
            icon = "🔒"
            status = " (متوقف)"
        elif product['type'] == 'game':
            icon = "🎮"
            status = ""
        elif product['type'] == 'subscription':
            icon = "📅"
            status = ""
        else:
            icon = "📱"
            status = ""
        
        options_info = f" [{product['options_count']} خيار]" if product['options_count'] > 0 else ""
        button_text = f"{icon} {product['name']}{status}{options_info}"
        builder.row(types.InlineKeyboardButton(text=button_text, callback_data=f"prod_options_{product['id']}"))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للأقسام", callback_data="manage_options"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("prod_options_"))
async def show_product_options(callback: types.CallbackQuery, db_pool):
    product_id = int(callback.data.split("_")[2])
    
    async with db_pool.acquire() as conn:
        product = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", product_id)
        options = await conn.fetch(
            "SELECT * FROM product_options WHERE product_id = $1 ORDER BY is_active DESC, sort_order, price_usd",
            product_id
        )
    
    type_icon = "🎮" if product['type'] == 'game' else "📅" if product['type'] == 'subscription' else "📱"
    
    text = f"{type_icon} **{product['name']}**\n"
    text += f"📝 **النوع:** {product['type']}\n"
    if product.get('description'):
        text += f"📄 {product['description']}\n"
    text += "➖➖➖➖➖➖\n\n"
    
    if not options:
        text += "⚠️ لا توجد خيارات لهذا المنتج."
    else:
        text += f"**الخيارات الحالية ({len(options)}):**\n\n"
        for i, opt in enumerate(options, 1):
            status_icon = "✅" if opt['is_active'] else "🔒"
            status_text = "" if opt['is_active'] else " (متوقف)"
            
            text += f"**{i}. {status_icon} {opt['name']}{status_text}**\n"
            text += f"   🆔 `{opt['id']}`\n"
            text += f"   📦 الكمية: {opt['quantity']}\n"
            text += f"   💰 سعر المورد: ${float(opt['price_usd']):.3f}\n"
            if opt.get('description'):
                text += f"   📝 {opt['description']}\n"
            text += "   ➖➖➖➖\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة خيار جديد", callback_data=f"add_option_{product_id}"))
    
    for opt in options:
        builder.row(
            types.InlineKeyboardButton(text=f"✏️ تعديل {opt['name']}", callback_data=f"edit_option_{opt['id']}"),
            types.InlineKeyboardButton(
                text=f"{'🔒 تعطيل' if opt['is_active'] else '✅ تفعيل'} {opt['name']}", 
                callback_data=f"toggle_option_{opt['id']}_{'1' if opt['is_active'] else '0'}"
            ),
            types.InlineKeyboardButton(text=f"🗑️ حذف {opt['name']}", callback_data=f"delete_option_{opt['id']}")
        )
    
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع للقسم", callback_data=f"manage_opts_cat_{product['category_id']}"),
        types.InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="manage_options")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# إضافة خيار جديد
@router.callback_query(F.data.startswith("add_option_"))
async def add_option_start(callback: types.CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    
    await callback.message.edit_text(
        "➕ **إضافة خيار جديد - الخطوة 1/5**\n\n"
        "📝 **أدخل اسم الخيار:**\n"
        "مثال: `60 UC`\nمثال: `570 ماسة`\n\n"
        "❌ اضغط على زر الإلغاء للرجوع",
        reply_markup=None
    )
    
    await callback.message.answer("أدخل اسم الخيار:", reply_markup=get_cancel_keyboard())
    await state.set_state(OptionStates.waiting_option_name)

@router.message(OptionStates.waiting_option_name)
async def add_option_step_name(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❌ الاسم قصير جداً. أدخل اسم مناسب:", reply_markup=get_cancel_keyboard())
        return
    
    await state.update_data(option_name=name)
    await message.answer(
        "➕ **إضافة خيار جديد - الخطوة 2/5**\n\n"
        f"📦 **أدخل الكمية:** (رقم فقط)\n"
        f"مثال: `60` لـ 60 UC\n"
        f"الاسم: **{name}**\n\n"
        f"❌ اضغط على زر الإلغاء للرجوع",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OptionStates.waiting_option_quantity)

@router.message(OptionStates.waiting_option_quantity)
async def add_option_step_quantity(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            return await message.answer("❌ الكمية يجب أن تكون أكبر من 0:", reply_markup=get_cancel_keyboard())
        
        await state.update_data(option_quantity=quantity)
        data = await state.get_data()
        option_name = data.get('option_name', '')
        
        await message.answer(
            "➕ **إضافة خيار جديد - الخطوة 3/5**\n\n"
            "💰 **أدخل سعر المورد (بالدولار):**\n"
            f"مثال: `0.99` لـ {quantity} وحدة\n"
            f"الاسم: **{option_name}**\n"
            f"الكمية: **{quantity}**\n\n"
            f"❌ اضغط على زر الإلغاء للرجوع",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(OptionStates.waiting_option_supplier_price)
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح للكمية:", reply_markup=get_cancel_keyboard())

@router.message(OptionStates.waiting_option_supplier_price)
async def add_option_step_supplier_price(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    try:
        supplier_price = float(message.text.strip())
    except ValueError:
        return await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح للسعر:", reply_markup=get_cancel_keyboard())
    
    if supplier_price <= 0:
        return await message.answer("❌ السعر يجب أن يكون أكبر من 0:", reply_markup=get_cancel_keyboard())
    
    await state.update_data(supplier_price=supplier_price)
    data = await state.get_data()
    product_id = data['product_id']
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow("SELECT profit_percentage FROM applications WHERE id = $1", product_id)
        default_profit = float(app['profit_percentage'] or 10) if app else 10
    
    option_name = data.get('option_name', '')
    quantity = data.get('option_quantity', 0)
    
    await message.answer(
        "➕ **إضافة خيار جديد - الخطوة 4/5**\n\n"
        "📈 **أدخل نسبة الربح (%):**\n"
        f"النسبة الافتراضية: **{default_profit}%**\n"
        f"الاسم: **{option_name}**\n"
        f"الكمية: **{quantity}**\n"
        f"سعر المورد: **${supplier_price:.3f}**\n\n"
        f"❌ اضغط على زر الإلغاء للرجوع",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OptionStates.waiting_option_profit)

@router.message(OptionStates.waiting_option_profit)
async def add_option_step_profit(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    try:
        profit_percent = float(message.text.strip())
        if profit_percent < 0:
            return await message.answer("❌ نسبة الربح لا يمكن أن تكون سالبة:", reply_markup=get_cancel_keyboard())
        
        await state.update_data(profit_percent=profit_percent)
        data = await state.get_data()
        
        await message.answer(
            "➕ **إضافة خيار جديد - الخطوة 5/5**\n\n"
            "📝 **أدخل وصف الخيار:**\n"
            "أدخل الوصف (أو أرسل `-` لتخطي):\n\n"
            f"الاسم: **{data['option_name']}**\n"
            f"الكمية: **{data['option_quantity']}**\n"
            f"سعر المورد: **${data['supplier_price']:.3f}**\n"
            f"نسبة الربح: **{profit_percent}%**\n\n"
            f"❌ اضغط على زر الإلغاء للرجوع",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(OptionStates.waiting_option_description)
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح لنسبة الربح:", reply_markup=get_cancel_keyboard())

@router.message(OptionStates.waiting_option_description)
async def add_option_step_description(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    description = None
    if message.text and message.text != "-":
        description = message.text.strip()
    
    data = await state.get_data()
    product_id = data['product_id']
    option_name = data['option_name']
    quantity = data['option_quantity']
    supplier_price = data['supplier_price']
    profit_percent = data['profit_percent']
    
    exchange_rate = await get_exchange_rate(db_pool)
    final_price_usd = supplier_price * (1 + profit_percent / 100)
    final_price_syp = final_price_usd * exchange_rate
    
    async with db_pool.acquire() as conn:
        product = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", product_id)
        
        option_id = await conn.fetchval('''
            INSERT INTO product_options 
            (product_id, name, quantity, price_usd, description, sort_order, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, TRUE)
            RETURNING id
        ''', product_id, option_name, quantity, supplier_price, description, 0)
        
        options = await conn.fetch(
            "SELECT * FROM product_options WHERE product_id = $1 AND is_active = TRUE ORDER BY sort_order, price_usd",
            product_id
        )
    
    confirm_text = (
        f"✅ **تم إضافة الخيار بنجاح!**\n\n"
        f"📦 **الخيار:** {option_name}\n"
        f"🔢 **الكمية:** {quantity}\n\n"
        f"💰 **تفاصيل السعر:**\n"
        f"• سعر المورد: **${supplier_price:.3f}**\n"
        f"• نسبة الربح: **{profit_percent}%**\n"
        f"• سعر البيع: **${final_price_usd:.3f}**\n"
        f"• سعر البيع (ل.س): **{final_price_syp:,.0f} ل.س**\n\n"
    )
    
    if description:
        confirm_text += f"📝 **الوصف:**\n{description}\n\n"
    
    await message.answer(confirm_text, reply_markup=None)
    await state.clear()
    
    # عرض الخيارات المحدثة
    type_icon = "🎮" if product['type'] == 'game' else "📅" if product['type'] == 'subscription' else "📱"
    type_name = "لعبة" if product['type'] == 'game' else "اشتراك" if product['type'] == 'subscription' else "خدمة"
    
    text = f"{type_icon} **{product['name']}**\n"
    text += f"📝 **النوع:** {type_name}\n"
    if product.get('description'):
        text += f"📄 {product['description']}\n"
    text += "➖➖➖➖➖➖\n\n"
    
    if not options:
        text += "⚠️ لا توجد خيارات لهذا المنتج."
    else:
        text += f"**الخيارات الحالية ({len(options)}):**\n\n"
        for i, opt in enumerate(options, 1):
            text += f"**{i}. {opt['name']}**\n"
            text += f"   🆔 `{opt['id']}`\n"
            text += f"   📦 الكمية: {opt['quantity']}\n"
            text += f"   💰 سعر المورد: ${float(opt['price_usd']):.3f}\n"
            if opt.get('description'):
                text += f"   📝 {opt['description']}\n"
            text += "   ➖➖➖➖\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة خيار جديد", callback_data=f"add_option_{product_id}"))
    
    for opt in options:
        builder.row(
            types.InlineKeyboardButton(text=f"✏️ تعديل {opt['name']}", callback_data=f"edit_option_{opt['id']}"),
            types.InlineKeyboardButton(text=f"🗑️ حذف {opt['name']}", callback_data=f"delete_option_{opt['id']}")
        )
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للقائمة", callback_data="manage_options"))
    await message.answer(text, reply_markup=builder.as_markup())

# تعديل خيار
@router.callback_query(F.data.startswith("edit_option_"))
async def edit_option_menu(callback: types.CallbackQuery, state: FSMContext, db_pool):
    try:
        parts = callback.data.split("_")
        option_id = int(parts[2])
        
        option = await get_product_option(db_pool, option_id)
        if not option:
            return await callback.answer("❌ الخيار غير موجود", show_alert=True)
        
        await state.update_data(option_id=option_id, product_id=option['product_id'])
        
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📝 تعديل الاسم", callback_data=f"edit_fld_name_{option_id}"))
        builder.row(types.InlineKeyboardButton(text="🔢 تعديل الكمية", callback_data=f"edit_fld_quantity_{option_id}"))
        builder.row(types.InlineKeyboardButton(text="💰 تعديل سعر المورد", callback_data=f"edit_fld_price_{option_id}"))
        builder.row(types.InlineKeyboardButton(text="📈 تعديل نسبة الربح", callback_data=f"edit_fld_profit_{option_id}"))
        builder.row(types.InlineKeyboardButton(text="📝 تعديل الوصف", callback_data=f"edit_fld_desc_{option_id}"))
        
        status_text = "🔒 تعطيل" if option['is_active'] else "✅ تفعيل"
        builder.row(types.InlineKeyboardButton(
            text=f"{status_text} الخيار", 
            callback_data=f"toggle_option_{option_id}_{'1' if option['is_active'] else '0'}"
        ))
        
        builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"prod_options_{option['product_id']}"))
        
        status_icon = "✅" if option['is_active'] else "🔒"
        status_text = "نشط" if option['is_active'] else "معطل"
        
        text = (
            f"✏️ **تعديل الخيار**\n\n"
            f"**البيانات الحالية:**\n"
            f"• الاسم: {option['name']}\n"
            f"• الكمية: {option['quantity']}\n"
            f"• سعر المورد: ${option['price_usd']:.3f}\n"
            f"• الحالة: {status_icon} {status_text}\n"
        )
        
        if option.get('description'):
            text += f"• الوصف: {option['description']}\n"
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"❌ خطأ في edit_option_menu: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("edit_fld_"))
async def edit_field_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split("_")
        if len(parts) != 4:
            return await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
        
        field_type = parts[2]
        option_id = int(parts[3])
        
        field_names = {'name': 'الاسم', 'quantity': 'الكمية', 'price': 'سعر المورد', 'profit': 'نسبة الربح', 'desc': 'الوصف'}
        field_name = field_names.get(field_type, field_type)
        
        await state.update_data(edit_field=field_type, option_id=option_id)
        
        instructions = {
            'name': "أدخل الاسم الجديد:",
            'quantity': "أدخل الكمية الجديدة (رقم فقط):",
            'price': "أدخل سعر المورد الجديد (بالدولار):",
            'profit': "أدخل نسبة الربح الجديدة (%):",
            'desc': "أدخل الوصف الجديد (أو - لحذف الوصف):"
        }
        
        await callback.message.answer(
            f"✏️ **تعديل {field_name}**\n\n"
            f"{instructions.get(field_type, 'أدخل القيمة الجديدة:')}\n\n"
            f"📝 أرسل القيمة الجديدة الآن\n"
            f"❌ أو أرسل /cancel للإلغاء"
        )
        
        await state.set_state(OptionStates.waiting_edit_option_value)
        await callback.answer("📝 جاري انتظار الإدخال...")
    except Exception as e:
        logger.error(f"❌ خطأ في edit_field_start: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.message(OptionStates.waiting_edit_option_value)
async def save_edited_value(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    data = await state.get_data()
    option_id = data.get('option_id')
    field = data.get('edit_field')
    
    if not option_id or not field:
        await message.answer("❌ بيانات غير صالحة. الرجاء البدء من جديد.")
        await state.clear()
        return
    
    value = message.text.strip()
    
    try:
        update_value = None
        field_name = ""
        db_column = ""
        
        if field == 'name':
            if len(value) < 2:
                await message.answer("❌ الاسم قصير جداً. أدخل اسم أطول:", reply_markup=get_cancel_keyboard())
                return
            update_value = value
            field_name = "الاسم"
            db_column = "name"
        elif field == 'quantity':
            try:
                quantity = int(value)
                if quantity <= 0:
                    await message.answer("❌ الكمية يجب أن تكون أكبر من 0:", reply_markup=get_cancel_keyboard())
                    return
                update_value = quantity
                field_name = "الكمية"
                db_column = "quantity"
            except ValueError:
                await message.answer("❌ يرجى إدخال رقم صحيح للكمية:", reply_markup=get_cancel_keyboard())
                return
        elif field == 'price':
            try:
                price = float(value)
                if price <= 0:
                    await message.answer("❌ السعر يجب أن يكون أكبر من 0:", reply_markup=get_cancel_keyboard())
                    return
                update_value = price
                field_name = "سعر المورد"
                db_column = "price_usd"
            except ValueError:
                await message.answer("❌ يرجى إدخال رقم صحيح للسعر:", reply_markup=get_cancel_keyboard())
                return
        elif field == 'profit':
            try:
                profit = float(value)
                if profit < 0:
                    await message.answer("❌ نسبة الربح لا يمكن أن تكون سالبة:", reply_markup=get_cancel_keyboard())
                    return
                update_value = profit
                field_name = "نسبة الربح"
                db_column = "profit_percentage"
            except ValueError:
                await message.answer("❌ يرجى إدخال رقم صحيح لنسبة الربح:", reply_markup=get_cancel_keyboard())
                return
        elif field == 'desc':
            update_value = None if value == '-' else value
            field_name = "الوصف"
            db_column = "description"
        else:
            await message.answer("❌ حقل غير معروف")
            await state.clear()
            return
        
        async with db_pool.acquire() as conn:
            if field == 'profit':
                option = await conn.fetchrow("SELECT product_id FROM product_options WHERE id = $1", option_id)
                if option:
                    await conn.execute(f"UPDATE applications SET {db_column} = $1 WHERE id = $2", update_value, option['product_id'])
                    product = await conn.fetchrow("SELECT name FROM applications WHERE id = $1", option['product_id'])
                    product_name = product['name'] if product else "المنتج"
                    await message.answer(f"✅ تم تحديث {field_name} للمنتج **{product_name}** بنجاح!")
                else:
                    await message.answer("❌ لم يتم العثور على الخيار")
                    await state.clear()
                    return
            else:
                query = f'UPDATE product_options SET "{db_column}" = $1 WHERE id = $2'
                await conn.execute(query, update_value, option_id)
                
                updated_option = await conn.fetchrow(
                    "SELECT po.*, a.name as product_name FROM product_options po JOIN applications a ON po.product_id = a.id WHERE po.id = $1",
                    option_id
                )
                
                if updated_option:
                    await message.answer(
                        f"✅ **تم التحديث بنجاح!**\n\n"
                        f"📦 المنتج: **{updated_option['product_name']}**\n"
                        f"🔧 الخيار: **{updated_option['name']}**\n"
                        f"📝 الحقل المعدل: **{field_name}**\n"
                        f"📊 القيمة الجديدة: **{update_value}**"
                    )
                else:
                    await message.answer(f"✅ تم تحديث {field_name} بنجاح!")
        
        await state.clear()
        
        if 'updated_option' in locals() and updated_option:
            product_id = updated_option['product_id']
        else:
            async with db_pool.acquire() as conn:
                opt = await conn.fetchrow("SELECT product_id FROM product_options WHERE id = $1", option_id)
                product_id = opt['product_id'] if opt else None
        
        if product_id:
            builder = InlineKeyboardBuilder()
            builder.row(types.InlineKeyboardButton(text="🔙 العودة لقائمة الخيارات", callback_data=f"prod_options_{product_id}"))
            await message.answer("🔍 اختر ما تريد فعله الآن:", reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ التعديل: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# حذف خيار
@router.callback_query(F.data.startswith("delete_option_"))
async def delete_option_confirm(callback: types.CallbackQuery, db_pool):
    option_id = int(callback.data.split("_")[2])
    option = await get_product_option(db_pool, option_id)
    
    if not option:
        return await callback.answer("❌ الخيار غير موجود", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم، احذف", callback_data=f"confirm_delete_option_{option_id}"),
        types.InlineKeyboardButton(text="❌ لا", callback_data=f"prod_options_{option['product_id']}")
    )
    
    await callback.message.edit_text(
        f"⚠️ **تأكيد حذف الخيار**\n\n"
        f"هل أنت متأكد من حذف هذا الخيار؟\n\n"
        f"📦 **الاسم:** {option['name']}\n"
        f"🔢 **الكمية:** {option['quantity']}\n"
        f"💰 **السعر:** ${option['price_usd']:.2f}",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("confirm_delete_option_"))
async def delete_option_execute(callback: types.CallbackQuery, db_pool):
    option_id = int(callback.data.split("_")[3])
    option = await get_product_option(db_pool, option_id)
    
    if not option:
        return await callback.answer("❌ الخيار غير موجود", show_alert=True)
    
    product_id = option['product_id']
    
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE product_options SET is_active = FALSE WHERE id = $1", option_id)
    
    await callback.answer("✅ تم حذف الخيار بنجاح")
    
    # العودة لقائمة الخيارات
    fake_callback = types.CallbackQuery(
        id='0', from_user=callback.from_user, message=callback.message,
        data=f"prod_options_{product_id}", bot=callback.bot
    )
    await show_product_options(fake_callback, db_pool)

# تشغيل/إيقاف الخيارات
@router.callback_query(F.data.startswith("toggle_option_"))
async def toggle_option_status(callback: types.CallbackQuery, db_pool):
    try:
        parts = callback.data.split("_")
        option_id = int(parts[2])
        current_status = bool(int(parts[3]))
        new_status = not current_status
        
        async with db_pool.acquire() as conn:
            option = await conn.fetchrow(
                "SELECT po.*, a.name as product_name FROM product_options po JOIN applications a ON po.product_id = a.id WHERE po.id = $1",
                option_id
            )
            if not option:
                return await callback.answer("❌ الخيار غير موجود", show_alert=True)
            
            await conn.execute("UPDATE product_options SET is_active = $1 WHERE id = $2", new_status, option_id)
        
        status_text = "✅ مفعل" if new_status else "🔒 معطل"
        await callback.answer(f"تم تغيير حالة الخيار '{option['name']}' إلى {status_text}")
        
        new_callback = types.CallbackQuery(
            id=callback.id, from_user=callback.from_user,
            chat_instance=callback.chat_instance, message=callback.message,
            data=f"prod_options_{option['product_id']}", bot=callback.bot
        )
        await show_product_options(new_callback, db_pool)
    except Exception as e:
        logger.error(f"❌ خطأ في toggle_option_status: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# إضافة لعبة أو اشتراك جديد
@router.callback_query(F.data == "add_new_game")
async def add_new_game_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT id, display_name FROM categories ORDER BY sort_order")
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(types.InlineKeyboardButton(text=cat['display_name'], callback_data=f"new_game_cat_{cat['id']}"))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_options"))
    await callback.message.edit_text("➕ **إضافة لعبة أو اشتراك جديد**\n\nاختر القسم أولاً:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("new_game_cat_"))
async def new_game_get_name(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[3])
    await state.update_data(category_id=cat_id)
    
    await callback.message.edit_text(
        "📝 **أدخل اسم اللعبة أو الاشتراك:**\n\n"
        "مثال: `PUBG Mobile`\nمثال: `Netflix Premium`\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    await state.set_state(OptionStates.waiting_new_game_name)

@router.message(OptionStates.waiting_new_game_name)
async def new_game_get_type(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    name = message.text.strip()
    await state.update_data(game_name=name)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🎮 لعبة", callback_data="new_game_type_game"),
        types.InlineKeyboardButton(text="📅 اشتراك", callback_data="new_game_type_subscription")
    )
    
    await message.answer(f"📱 **الاسم:** {name}\n\nاختر النوع:", reply_markup=builder.as_markup())
    await state.set_state(OptionStates.waiting_new_game_type)

@router.callback_query(F.data.startswith("new_game_type_"))
async def new_game_save(callback: types.CallbackQuery, state: FSMContext, db_pool):
    game_type = callback.data.replace("new_game_type_", "")
    data = await state.get_data()
    name = data['game_name']
    category_id = data['category_id']
    
    try:
        async with db_pool.acquire() as conn:
            existing = await conn.fetchval("SELECT id FROM applications WHERE name = $1", name)
            if existing:
                await callback.message.edit_text(f"❌ **فشل الإضافة**\n\nتطبيق باسم **{name}** موجود مسبقاً.\nالرجاء استخدام اسم مختلف.")
                await state.clear()
                return
            
            game_id = await conn.fetchval('''
                INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, category_id, type, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                RETURNING id
            ''', name, 0.01, 1, 10, category_id, game_type)
        
        await callback.message.edit_text(
            f"✅ **تم إضافة {name} بنجاح!**\n\n"
            f"📱 النوع: {'🎮 لعبة' if game_type == 'game' else '📅 اشتراك'}\n"
            f"🆔 المعرف: {game_id}\n\n"
            f"🔹 الآن يمكنك إضافة خيارات لهذا التطبيق."
        )
        await state.clear()
    except Exception as e:
        await callback.message.edit_text(f"❌ **حدث خطأ:** {str(e)}\n\nيرجى المحاولة مرة أخرى.")
        await state.clear()