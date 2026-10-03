# handlers/services.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import math
import json
import logging

# ✅ التصحيح الجذري هنا: استدعاء الدوال من المسارات الصحيحة
from utils import is_admin, format_amount, get_formatted_damascus_time
from handlers.time_utils import get_damascus_time_now, format_damascus_time
from handlers.keyboards import get_main_menu_keyboard
from database.users import is_admin_user
from database.core import get_exchange_rate
from database.vip import get_user_vip
from database.points import get_points_per_order
from database.products import get_product_option
from config import ORDERS_GROUP

logger = logging.getLogger(__name__)
router = Router()

class OrderStates(StatesGroup):
    qty = State()
    target_id = State()
    confirm = State()

# ============= عرض الأقسام =============
@router.callback_query(F.data == "show_categories")
async def show_categories_callback(callback: types.CallbackQuery, db_pool):
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    
    if not categories:
        return await callback.message.edit_text("⚠️ لا توجد أقسام متاحة حالياً.")
    
    builder = InlineKeyboardBuilder()
    buttons = []
    
    for cat in categories:
        icon = cat.get('icon', '📁')
        name = cat.get('display_name', 'قسم')
        buttons.append(types.InlineKeyboardButton(
            text=f"{name} {icon}", 
            callback_data=f"cat_{cat['id']}_1"
        ))
    
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            builder.row(buttons[i+1], buttons[i])
        else:
            builder.row(buttons[i])
            
    builder.row(types.InlineKeyboardButton(text="القائمة الرئيسية 🏠", callback_data="back_to_main"))
    
    await callback.message.edit_text(
        "**منتجات المتجر 🛒**\n"
        "━━━━━━━━━━━━━━━\n\n"
        "اختر القسم 👇:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# ============= عرض التطبيقات مع الصفحات =============
@router.callback_query(F.data.startswith("cat_"))
async def show_apps_by_category(callback: types.CallbackQuery, db_pool):
    await callback.answer()
    
    parts = callback.data.split("_")
    cat_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1
    ITEMS_PER_PAGE = 10
    
    async with db_pool.acquire() as conn:
        apps = await conn.fetch(
            "SELECT * FROM applications WHERE category_id = $1 ORDER BY is_active DESC, name",
            cat_id
        )
        category = await conn.fetchrow("SELECT display_name, icon FROM categories WHERE id = $1", cat_id)
    
    if not apps:
        return await callback.answer("لا توجد تطبيقات في هذا القسم حالياً", show_alert=True)
    
    total_pages = math.ceil(len(apps) / ITEMS_PER_PAGE)
    current_apps = apps[(page-1)*ITEMS_PER_PAGE : page*ITEMS_PER_PAGE]
    
    builder = InlineKeyboardBuilder()
    buttons = []
    
    for app in current_apps:
        if not app['is_active']:
            buttons.append(types.InlineKeyboardButton(text=f"🔒 {app['name']}", callback_data=f"disabled_app"))
        else:
            buttons.append(types.InlineKeyboardButton(text=f"{app['name']}", callback_data=f"buy_{app['id']}"))
            
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            builder.row(buttons[i], buttons[i + 1])
        else:
            builder.row(buttons[i])
            
    nav_buttons = []
    if total_pages > 1:
        if page < total_pages:
            nav_buttons.append(types.InlineKeyboardButton(text="▶️", callback_data=f"cat_{cat_id}_{page+1}"))
        nav_buttons.append(types.InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore"))
        if page > 1:
            nav_buttons.append(types.InlineKeyboardButton(text="◀️", callback_data=f"cat_{cat_id}_{page-1}"))
        builder.row(*nav_buttons)
        
    builder.row(types.InlineKeyboardButton(text="رجوع ⬅️", callback_data="show_categories"))
    builder.row(types.InlineKeyboardButton(text="القائمة الرئيسية 🏠", callback_data="back_to_main"))
    
    cat_name = category['display_name'] if category else 'التطبيقات'
    cat_icon = category['icon'] if category else '📦'
    
    await callback.message.edit_text(
        f"**{cat_name} {cat_icon}**\n"
        "━━━━━━━━━━━━━━━\n\n"
        "اختر 👇:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# ============= اختيار التطبيق =============
@router.callback_query(F.data.startswith("buy_"))
async def start_order(callback: types.CallbackQuery, state: FSMContext, db_pool):
    await callback.answer()
    app_id = int(callback.data.split("_")[1])
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)
        category = await conn.fetchrow("SELECT display_name FROM categories WHERE id = $1", app['category_id'])
        options = await conn.fetch("SELECT * FROM product_options WHERE product_id = $1 AND is_active = TRUE ORDER BY price_usd", app_id)
    
    current_rate = await get_exchange_rate(db_pool)
    user_vip = await get_user_vip(db_pool, callback.from_user.id)
    discount = user_vip.get('discount_percent', 0)
    
    app_dict = dict(app)
    app_dict['unit_price_usd'] = float(app_dict['unit_price_usd'] or 0)
    app_dict['profit_percentage'] = float(app_dict.get('profit_percentage', 0))
    app_dict['min_units'] = int(app_dict.get('min_units', 1))
    app_dict['cat_name'] = category['display_name'] if category else 'تطبيقات'
    
    await state.update_data(app=app_dict, current_rate=current_rate, discount=discount)
    
    if options:
        builder = InlineKeyboardBuilder()
        for opt in options:
            builder.row(types.InlineKeyboardButton(text=opt['name'], callback_data=f"var_{opt['id']}"))
        builder.row(types.InlineKeyboardButton(text="رجوع ⬅️", callback_data=f"cat_{app['category_id']}_1"))
        builder.row(types.InlineKeyboardButton(text="القائمة الرئيسية 🏠", callback_data="back_to_main"))
        
        await callback.message.edit_text(
            f"**خيارات: {app['name']} 🛍️**\n"
            "━━━━━━━━━━━━━━━\n\n"
            "اختر الباقة المناسبة 👇:",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
    else:
        unit_price = app_dict['unit_price_usd'] * (1 + (app_dict['profit_percentage'] / 100))
        discounted_price = unit_price * (1 - discount/100)
        
        async with db_pool.acquire() as conn:
            balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", callback.from_user.id) or 0
        balance_usd = balance / current_rate if current_rate > 0 else 0
        
        example_qty = app_dict['min_units']
        example_price = example_qty * discounted_price
        
        text = (
            f"**تفاصيل المنتج 🛍️**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ **المنتج:** {app['name']}\n"
            f"📦 **القسم:** {app_dict['cat_name']}\n"
            f"📦 **نوع المنتج:** عداد\n"
            f"💵 **سعر الوحدة:** {discounted_price:.8f} $\n"
            f"🔢 **الكمية المسموحة:** من {app_dict['min_units']:,} إلى 500,000,000\n"
            f"🧮 **مثال:** {example_qty:,} وحدة = {example_price:.4f} $\n"
            f"✅ **الحالة:** متوفر\n"
            f"📝 **المطلوب منك:** ادخل ايدي المستخدم\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"💼 **رصيدك الحالي:** {balance_usd:.2f} $\n"
        )
        
        await state.update_data(final_unit_price_usd=discounted_price, is_variant=False)
        await state.set_state(OrderStates.qty)
        
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="رجوع ⬅️", callback_data=f"cat_{app['category_id']}_1"), types.InlineKeyboardButton(text="القائمة الرئيسية 🏠", callback_data="back_to_main"))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await callback.message.answer("📝 **أرسل الكمية المطلوبة الآن (أرقام فقط):**", parse_mode="Markdown")

# ============= تفاصيل المنتج الثابت =============
@router.callback_query(F.data.startswith("var_"))
async def show_variant_details(callback: types.CallbackQuery, state: FSMContext, db_pool):
    await callback.answer()
    variant_id = int(callback.data.split("_")[1])
    
    option = await get_product_option(db_pool, variant_id)
    data = await state.get_data()
    app = data['app']
    discount = data['discount']
    current_rate = data['current_rate']
    
    opt_price = float(option['price_usd'])
    price_with_profit = opt_price * (1 + (app['profit_percentage'] / 100))
    discounted_price = price_with_profit * (1 - discount/100)
    total_syp = discounted_price * current_rate
    
    async with db_pool.acquire() as conn:
        balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", callback.from_user.id) or 0
    balance_usd = balance / current_rate if current_rate > 0 else 0
    
    await state.update_data(variant=dict(option), final_price_usd=discounted_price, total_syp=total_syp, is_variant=True)
    
    text = (
        f"**تفاصيل المنتج 🛍**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ **المنتج:** {option['name']}\n"
        f"📦 **القسم:** {app['cat_name']}\n"
        f"📦 **نوع المنتج:** ثابت\n"
        f"💵 **السعر:** {discounted_price:.4f} $\n"
        f"✅ **الحالة:** متوفر\n"
        f"📝 **المطلوب منك:** Player ID\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 **رصيدك الحالي:** {balance_usd:.2f} $\n"
        f"🛡️ يتم التحقق من اسم اللاعب تلقائياً (إن وجد)\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="طلب المنتج 🛒", callback_data="confirm_variant_order"))
    builder.row(types.InlineKeyboardButton(text="رجوع ⬅️", callback_data=f"buy_{app['id']}"), types.InlineKeyboardButton(text="القائمة الرئيسية 🏠", callback_data="back_to_main"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# ============= معالجة الكمية للعداد =============
@router.message(OrderStates.qty)
async def process_counter_qty(message: types.Message, state: FSMContext, db_pool):
    if not message.text.isdigit():
        return await message.answer("⚠ يرجى إدخال أرقام فقط للكمية.")
        
    qty = int(message.text)
    data = await state.get_data()
    app = data['app']
    
    if qty < app['min_units']:
        return await message.answer(f"⚠️ أقل كمية مسموح بها هي {app['min_units']}.")
        
    total_usd = qty * data['final_unit_price_usd']
    total_syp = total_usd * data['current_rate']
    
    await state.update_data(qty=qty, total_syp=total_syp, total_usd=total_usd)
    await state.set_state(OrderStates.target_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="إلغاء ❌", callback_data="back_to_main"))
    await message.answer(
        f"✅ تم تأكيد الكمية: **{qty:,}**\n"
        f"💰 الإجمالي: **{total_usd:.4f} $**\n\n"
        "📝 **الرجاء إرسال الـ ID الخاص بك الآن:**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# ============= طلب الآيدي للمنتج الثابت =============
@router.callback_query(F.data == "confirm_variant_order")
async def ask_for_id_variant(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(OrderStates.target_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="إلغاء ❌", callback_data="back_to_main"))
    
    await callback.message.edit_text(
        "📝 **الرجاء إرسال الـ Player ID الخاص بك الآن:**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# ============= إرسال الطلب وحفظه =============
@router.message(OrderStates.target_id)
async def process_target_id_and_checkout(message: types.Message, state: FSMContext, db_pool):
    target_id = message.text.strip()
    data = await state.get_data()
    total_syp = data['total_syp']
    
    async with db_pool.acquire() as conn:
        balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", message.from_user.id) or 0
        
        if balance < total_syp:
            await state.clear()
            return await message.answer("❌ رصيدك غير كافي لإتمام هذه العملية.\nيرجى شحن رصيدك والمحاولة لاحقاً.")
            
        await conn.execute("UPDATE users SET balance = balance - $1, total_orders = total_orders + 1 WHERE user_id = $2", total_syp, message.from_user.id)
        points = await get_points_per_order(db_pool)
        
        if data['is_variant']:
            variant = data['variant']
            await conn.execute('''
                INSERT INTO orders (user_id, username, app_id, app_name, variant_id, variant_name, quantity, unit_price_usd, total_amount_syp, target_id, status, points_earned)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'pending', $11)
            ''', message.from_user.id, message.from_user.username, data['app']['id'], data['app']['name'], variant['id'], variant['name'], int(variant.get('quantity', 1)), data['final_price_usd'], total_syp, target_id, points)
        else:
            await conn.execute('''
                INSERT INTO orders (user_id, username, app_id, app_name, quantity, unit_price_usd, total_amount_syp, target_id, status, points_earned)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', $9)
            ''', message.from_user.id, message.from_user.username, data['app']['id'], data['app']['name'], data['qty'], data['final_unit_price_usd'], total_syp, target_id, points)

    await state.clear()
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="طلباتي 📦", callback_data="my_orders"))
    builder.row(types.InlineKeyboardButton(text="القائمة الرئيسية 🏠", callback_data="back_to_main"))
    
    await message.answer(
        "✅ **تم استلام طلبك بنجاح وجاري المعالجة!**\n"
        "سيتم خصم المبلغ من رصيدك فور اكتمال الطلب.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: types.CallbackQuery):
    await callback.answer()
    
@router.callback_query(F.data == "disabled_app")
async def disabled_app_callback(callback: types.CallbackQuery):
    await callback.answer("🔒 هذا التطبيق متوقف حالياً للصيانة", show_alert=True)

# ============= توجيه الطلبات للمزود الذكي =============
async def send_order_to_api(order_id: int, db_pool, bot: Bot) -> bool:
    from api.client import get_api_client
    
    async with db_pool.acquire() as conn:
        order = await conn.fetchrow('''
            SELECT o.*, a.api_service_id, p.base_url, p.api_token, p.name as provider_name
            FROM orders o
            JOIN applications a ON o.app_id = a.id
            LEFT JOIN api_providers p ON a.provider_id = p.id
            WHERE o.id = $1 AND o.status = 'processing'
        ''', order_id)
        
        if not order:
            logger.warning(f"⚠️ الطلب {order_id} غير موجود أو ليس في حالة processing")
            return False
        
        if not order['api_service_id'] or not order['base_url']:
            logger.warning(f"⚠️ التطبيق {order['app_name']} غير مرتبط بمزود API صالح")
            return False
        
        extra_params = {}
        app_name = order['app_name'].lower()
        if any(x in app_name for x in ['pubg', 'free fire', 'clash']):
            extra_params['playerId'] = order['target_id']
        else:
            extra_params['playerId'] = order['target_id']
        
        api = get_api_client(order['base_url'], order['api_token'])
        
        result = await api.create_order(
            product_id=int(order['api_service_id']),
            quantity=order['quantity'],
            player_id=order['target_id'] if 'player' in str(extra_params) else None,
            extra_params=extra_params if extra_params else None
        )
        
        if result['success']:
            await conn.execute('''
                UPDATE orders 
                SET status = 'completed', api_response = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
            ''', json.dumps(result.get('raw', {})), order_id)
            
            await bot.send_message(
                order['user_id'],
                f"✅ **تم تنفيذ طلبك #{order_id} بنجاح!**\n\n"
                f"📱 **المنتج:** {order['app_name']}\n"
                f"🎯 **الحساب:** {order['target_id']}\n"
                f"📋 **رقم العملية ({order['provider_name']}):** {result.get('order_id')}\n\n"
                f"شكراً لاستخدامك خدماتنا!",
                parse_mode="Markdown"
            )
            return True
        else:
            await conn.execute('''
                UPDATE orders 
                SET status = 'failed', admin_notes = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
            ''', f"فشل الإرسال للمزود: {result.get('error')}", order_id)
            
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                order['total_amount_syp'], order['user_id']
            )
            
            await bot.send_message(
                order['user_id'],
                f"❌ **عذراً، تعذر تنفيذ طلبك #{order_id}**\n\n"
                f"🔸 **السبب:** مزود الخدمة يواجه ضغطاً حالياً.\n"
                f"💰 **تم إعادة المبلغ إلى رصيدك.**\n",
                parse_mode="Markdown"
            )
            return False
