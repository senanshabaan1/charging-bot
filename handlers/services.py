import math
import json
import html
import logging
from datetime import datetime

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from config import ORDERS_GROUP, USD_TO_SYP
from handlers.time_utils import get_damascus_time_now, format_damascus_time, DAMASCUS_TZ
from handlers.keyboards import get_main_menu_keyboard
from database.users import is_admin_user
from database.core import get_exchange_rate
from database.vip import get_user_vip
from database.points import get_points_per_order
from database.products import get_product_options, get_product_option
from utils import get_formatted_damascus_time, format_amount, is_valid_positive_number
from api.client import get_api_client

logger = logging.getLogger(__name__)
router = Router()

ITEMS_PER_PAGE = 10  # عدد العناصر في كل صفحة

class OrderStates(StatesGroup):
    qty = State()
    target_id = State()
    confirm = State()
    choosing_variant = State()

async def get_cached_categories(db_pool):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM categories ORDER BY sort_order")

# ============= معالج الرجوع الموحد =============
@router.message(F.text.in_(["🔙 رجوع للقائمة", "/cancel", "/رجوع", "🏠 القائمة الرئيسية", "❌ إلغاء"]))
async def global_back_handler(message: types.Message, state: FSMContext, db_pool):
    await state.clear()
    is_admin = await is_admin_user(db_pool, message.from_user.id)
    await message.answer("👋 أهلاً بك في القائمة الرئيسية", reply_markup=get_main_menu_keyboard(is_admin))

# ============= عرض الأقسام (بنظام الصفحات) =============
@router.callback_query(F.data == "show_categories")
@router.callback_query(F.data.startswith("cats_page_"))
async def show_categories_callback(callback: types.CallbackQuery, db_pool):
    await callback.answer()
    
    page = int(callback.data.split("_")[2]) if callback.data.startswith("cats_page_") else 1
    categories = await get_cached_categories(db_pool)
    
    if not categories:
        return await callback.message.edit_text("⚠️ لا توجد أقسام متاحة حالياً.")
    
    total_pages = math.ceil(len(categories) / ITEMS_PER_PAGE)
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    cats_to_show = categories[start_idx:end_idx]
    
    builder = InlineKeyboardBuilder()
    for cat in cats_to_show:
        icon = cat.get('icon', '📁')
        builder.row(types.InlineKeyboardButton(text=f"{icon} {cat['display_name']}", callback_data=f"cat_{cat['id']}_page_1"))
    
    # أزرار التنقل بين الصفحات
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️ السابق", callback_data=f"cats_page_{page-1}"))
    if total_pages > 1:
        nav_buttons.append(types.InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton(text="التالي ▶️", callback_data=f"cats_page_{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
        
    builder.row(types.InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="back_to_main"))
    
    await callback.message.edit_text("🌟 <b>أقسام الخدمات المتوفرة:</b>\n\n🔸 اختر القسم المطلوب:", reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery, state: FSMContext, db_pool):
    await callback.answer()
    await state.clear()
    is_admin = await is_admin_user(db_pool, callback.from_user.id)
    await callback.message.edit_text("👋 مرحباً بك في القائمة الرئيسية. اختر ما تريد:", reply_markup=get_main_menu_keyboard(is_admin))

@router.callback_query(F.data.startswith("disabled_app_"))
async def handle_disabled_app(callback: types.CallbackQuery):
    await callback.answer("🔒 هذه الخدمة متوقفة للصيانة حالياً.", show_alert=True)

# ============= عرض الخدمات داخل القسم (بنظام الصفحات) =============
@router.callback_query(F.data.startswith("cat_"))
async def show_apps_by_category(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split("_")
    cat_id = int(parts[1])
    page = int(parts[3]) if len(parts) > 3 else 1
    
    async with db_pool.acquire() as conn:
        apps = await conn.fetch("SELECT * FROM applications WHERE category_id = $1 ORDER BY is_active DESC, name", cat_id)
        category = await conn.fetchrow("SELECT display_name, icon FROM categories WHERE id = $1", cat_id)
        current_rate = await get_exchange_rate(db_pool)
        user_vip = await get_user_vip(db_pool, callback.from_user.id)
        discount = user_vip.get('discount_percent', 0)
        vip_icon = user_vip.get('icon', '⚪')
        vip_name = user_vip.get('name', 'عادي')
    
    if not apps:
        return await callback.answer("لا توجد خدمات في هذا القسم حالياً", show_alert=True)
    
    total_pages = math.ceil(len(apps) / ITEMS_PER_PAGE)
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    apps_to_show = apps[start_idx:end_idx]
    
    builder = InlineKeyboardBuilder()
    
    for app in apps_to_show:
        if not app['is_active']:
            builder.row(types.InlineKeyboardButton(text=f"🔒 {app['name']} (متوقف)", callback_data=f"disabled_app_{app['id']}"))
        else:
            icon = "🎮" if app['type'] == 'game' else "📅" if app['type'] == 'subscription' else "🛒"
            builder.row(types.InlineKeyboardButton(text=f"{icon} {app['name']}", callback_data=f"buy_{app['id']}_{app['type']}"))
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️", callback_data=f"cat_{cat_id}_page_{page-1}"))
    if total_pages > 1:
        nav_buttons.append(types.InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton(text="▶️", callback_data=f"cat_{cat_id}_page_{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
        
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للأقسام", callback_data="show_categories"))
    
    cat_icon = category['icon'] if category else '📁'
    cat_name = category['display_name'] if category else 'القسم'
    
    await callback.message.edit_text(
        f"{cat_icon} <b>{cat_name}</b>\n\n"
        f"👤 مستواك: {vip_icon} {vip_name} (خصم {discount}%)\n\n"
        f"🔸 <b>اختر الخدمة المطلوبة:</b>", 
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# ============= بدء طلب الخدمة =============
@router.callback_query(F.data.startswith("buy_"))
async def start_order(callback: types.CallbackQuery, state: FSMContext, db_pool):
    parts = callback.data.split("_")
    app_id = int(parts[1])
    app_type = parts[2] if len(parts) > 2 else 'service'
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)
        if not app or not app['is_active']:
            return await callback.answer("هذه الخدمة غير متوفرة حالياً 🔒", show_alert=True)
        
        current_rate = await get_exchange_rate(db_pool)
        user_vip = await get_user_vip(db_pool, callback.from_user.id)
        discount = user_vip.get('discount_percent', 0)
        vip_level = user_vip.get('vip_level', 0)
        options = await conn.fetch("SELECT * FROM product_options WHERE product_id = $1 ORDER BY is_active DESC, sort_order, price_usd", app_id)
    
    app_dict = dict(app)
    app_dict['unit_price_usd'] = float(app_dict['unit_price_usd'] or 0.0)
    app_dict['profit_percentage'] = float(app_dict.get('profit_percentage', 0) or 0)
    app_dict['min_units'] = int(app_dict.get('min_units', 1) or 1)
    
    await state.update_data({'app': app_dict, 'app_type': app_type, 'current_rate': current_rate, 'discount': discount, 'vip_level': vip_level})
    
    # إذا كان للخدمة خيارات (Variants)
    if options:
        builder = InlineKeyboardBuilder()
        for opt in options:
            opt_price = float(opt['price_usd'] or 0.0)
            if opt['is_active']:
                price_with_profit = opt_price * (1 + (app_dict['profit_percentage'] / 100))
                discounted_usd = price_with_profit * (1 - discount/100)
                price_syp = discounted_usd
                
                btn_text = f"💎 {opt['name']} | {price_syp:,.0f} ل.س"
                if discount > 0:
                    btn_text += f" (خصم {discount}%)"
                builder.row(types.InlineKeyboardButton(text=btn_text, callback_data=f"var_{opt['id']}"))
            else:
                builder.row(types.InlineKeyboardButton(text=f"🔒 {opt['name']} (متوقف)", callback_data=f"disabled_option_{opt['id']}"))
        
        builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"cat_{app_dict['category_id']}_page_1"))
        await callback.message.edit_text(
            f"🛒 <b>الخدمة:</b> {app_dict['name']}\n\n"
            f"🔸 <b>اختر الباقة المناسبة:</b>",
            reply_markup=builder.as_markup(), parse_mode="HTML"
        )
        await state.set_state(OrderStates.choosing_variant)
    
    # إذا كانت خدمة بكمية مفتوحة
    else:
        profit_percentage = app_dict['profit_percentage']
        final_usd = app_dict['unit_price_usd'] * (1 + (profit_percentage / 100))
        discounted_usd = final_usd * (1 - discount/100)
        price_syp = discounted_usd * current_rate
        
        await state.update_data({'final_unit_price_usd': final_usd})
        
        min_units = app_dict['min_units']
        
        # أزرار الكمية السريعة الذكية
        builder = InlineKeyboardBuilder()
        if min_units < 10:
            builder.row(
                types.InlineKeyboardButton(text="1", callback_data="quickqty_1"),
                types.InlineKeyboardButton(text="2", callback_data="quickqty_2"),
                types.InlineKeyboardButton(text="5", callback_data="quickqty_5"),
                types.InlineKeyboardButton(text="10", callback_data="quickqty_10")
            )
        else:
            builder.row(
                types.InlineKeyboardButton(text=f"{min_units}", callback_data=f"quickqty_{min_units}"),
                types.InlineKeyboardButton(text=f"{min_units*2}", callback_data=f"quickqty_{min_units*2}"),
                types.InlineKeyboardButton(text=f"{min_units*5}", callback_data=f"quickqty_{min_units*5}")
            )
        builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"cat_{app_dict['category_id']}_page_1"))
        
        price_text = f"💰 سعر الوحدة: {price_syp:,.0f} ل.س"
        if discount > 0:
            original = final_usd * current_rate
            price_text = f"💰 سعر الوحدة: <s>{original:,.0f} ل.س</s> <b>{price_syp:,.0f} ل.س</b>\n🎁 خصمك: {discount}%"
            
        await callback.message.edit_text(
            f"🛒 <b>الخدمة:</b> {app_dict['name']}\n\n"
            f"{price_text}\n"
            f"📦 الحد الأدنى: {min_units}\n\n"
            f"🔸 <b>اختر الكمية أو اكتبها كرسالة:</b>",
            reply_markup=builder.as_markup(), parse_mode="HTML"
        )
        await state.set_state(OrderStates.qty)

@router.callback_query(F.data.startswith("disabled_option_"))
async def handle_disabled_option(callback: types.CallbackQuery):
    await callback.answer("🔒 هذا الخيار متوقف حالياً، يرجى اختيار باقة أخرى.", show_alert=True)

# ============= معالجة اختيار باقة (Variant) =============
@router.callback_query(F.data.startswith("var_"))
async def choose_variant(callback: types.CallbackQuery, state: FSMContext, db_pool):
    variant_id = int(callback.data.split("_")[1])
    option = await get_product_option(db_pool, variant_id)
    
    if not option:
        return await callback.answer("هذا الخيار غير متوفر", show_alert=True)
    
    data = await state.get_data()
    app = data['app']
    current_rate, discount, vip_level = data['current_rate'], data['discount'], data['vip_level']
    
    app_profit = float(app.get('profit_percentage', 0) or 0) / 100
    opt_price = float(option['price_usd'] or 0.0)
    
    price_with_profit = opt_price * (1 + app_profit)
    discounted_usd = price_with_profit * (1 - discount/100)
    total_syp = discounted_usd * current_rate
    original_syp = price_with_profit
    
    await state.update_data({
        'variant': dict(option),
        'final_price_usd': discounted_usd,
        'total_syp': total_syp,
        'original_total_syp': original_syp,
        'qty': int(option.get('quantity', 1) or 1)
    })
    
    await ask_for_target_id(callback.message, state, app['name'], option['name'], total_syp, original_syp, discount, is_edit=True)

# ============= معالجة الكمية السريعة واليدوية =============
@router.callback_query(F.data.startswith("quickqty_"))
async def quick_qty(callback: types.CallbackQuery, state: FSMContext, db_pool):
    qty = int(callback.data.split("_")[1])
    await process_quantity(callback.message, state, qty, db_pool, is_edit=True)

@router.message(OrderStates.qty)
async def manual_qty(message: types.Message, state: FSMContext, db_pool):
    if message.text in ["🔙 رجوع للقائمة", "/cancel", "❌ إلغاء"]:
        await global_back_handler(message, state, db_pool)
        return
    if not message.text.isdigit():
        return await message.answer("⚠️ يرجى إدخال رقم صحيح (الكمية).")
    await process_quantity(message, state, int(message.text), db_pool, is_edit=False)

async def process_quantity(message_obj: types.Message, state: FSMContext, qty: int, db_pool, is_edit=False):
    data = await state.get_data()
    app = data['app']
    current_rate, discount = data['current_rate'], data['discount']
    min_units = app.get('min_units', 1) or 1
    
    if qty < min_units:
        msg = f"⚠️ أقل كمية مسموح بها هي {min_units}."
        if is_edit: await message_obj.edit_text(msg)
        else: await message_obj.answer(msg)
        return
        
    final_unit_usd = data['final_unit_price_usd']
    original_syp = final_unit_usd * qty * current_rate
    discounted_usd = final_unit_usd * (1 - discount/100)
    total_syp = qty * discounted_usd * current_rate
    
    await state.update_data(qty=qty, total_usd=qty*discounted_usd, total_syp=total_syp, original_total_syp=original_syp)
    
    await ask_for_target_id(message_obj, state, app['name'], f"كمية: {qty}", total_syp, original_syp, discount, is_edit)

async def ask_for_target_id(message_obj: types.Message, state: FSMContext, app_name: str, pkg_name: str, total_syp: float, original_syp: float, discount: float, is_edit: bool):
    """توليد رسالة طلب الآيدي والتأكيد"""
    app_name_lower = app_name.lower()
    instructions = "🆔 <b>الرجاء إرسال الـ ID الخاص بالحساب:</b>"
    
    if any(x in app_name_lower for x in ['pubg', 'ببجي']):
        instructions = "🎯 <b>الرجاء إرسال 🆔 اللاعب (أرقام فقط):</b>"
    elif 'free fire' in app_name_lower or 'فري فاير' in app_name_lower:
        instructions = "🔥 <b>الرجاء إرسال 🆔 اللاعب (Free Fire):</b>"
    elif 'telegram' in app_name_lower or 'تيليجرام' in app_name_lower:
        instructions = "🪪 <b>الرجاء إرسال معرف التيليجرام (@username):</b>"
    elif 'tiktok' in app_name_lower or 'instagram' in app_name_lower:
        instructions = "📸 <b>الرجاء إرسال اسم المستخدم (الرابط أو اليوزر):</b>"

    price_text = f"💰 <b>الإجمالي:</b> {total_syp:,.0f} ل.س"
    if discount > 0:
        saved = original_syp - total_syp
        price_text = f"💰 <b>الإجمالي:</b> <s>{original_syp:,.0f}</s> <b>{total_syp:,.0f} ل.س</b>\n🎁 وفرت {saved:,.0f} ل.س بفضل الـ VIP!"

    text = (
        f"✅ <b>ممتاز، خطوة أخيرة!</b>\n\n"
        f"🛒 <b>الخدمة:</b> {app_name}\n"
        f"📦 <b>الباقة:</b> {pkg_name}\n"
        f"{price_text}\n\n"
        f"{instructions}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="❌ إلغاء الطلب", callback_data="cancel_order"))
    
    if is_edit:
        await message_obj.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await message_obj.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        
    await state.set_state(OrderStates.target_id)

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext, db_pool):
    await state.clear()
    is_admin = await is_admin_user(db_pool, callback.from_user.id)
    await callback.message.edit_text("❌ <b>تم إلغاء الطلب.</b>", parse_mode="HTML")
    await callback.message.answer("👋 عدنا للقائمة الرئيسية", reply_markup=get_main_menu_keyboard(is_admin))

# ============= استلام الـ ID والتأكيد النهائي =============
@router.message(OrderStates.target_id)
async def confirm_order(message: types.Message, state: FSMContext, db_pool):
    if message.text in ["🔙 رجوع للقائمة", "/cancel", "❌ إلغاء"]:
        return await global_back_handler(message, state, db_pool)
    
    target_id = html.escape(message.text.strip())
    data = await state.get_data()
    total_syp = data.get('total_syp', 0)
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", message.from_user.id)
        if not user or user['balance'] < total_syp:
            await state.clear()
            await message.answer(f"❌ <b>رصيدك غير كافي لإتمام العملية!</b>\nالمطلوب: {total_syp:,.0f} ل.س\nرصيدك: {user['balance'] if user else 0:,.0f} ل.س", parse_mode="HTML")
            return
            
    await state.update_data(target_id=target_id)
    
    pkg_name = data['variant']['name'] if 'variant' in data else f"كمية: {data['qty']}"
    
    text = (
        f"⚠️ <b>يرجى مراجعة تفاصيل طلبك وتأكيدها:</b>\n\n"
        f"📱 <b>الخدمة:</b> {data['app']['name']}\n"
        f"📦 <b>الباقة:</b> {pkg_name}\n"
        f"🎯 <b>الـ ID / المستهدف:</b> <code>{target_id}</code>\n"
        f"💳 <b>سيتم خصم:</b> {total_syp:,.0f} ل.س من رصيدك\n\n"
        f"<i>تأكد من صحة الـ ID قبل الدفع، لا يمكن التراجع بعد التنفيذ!</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="✅ تأكيد ودفع", callback_data="execute_buy"))
    builder.row(types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_order"))
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(OrderStates.confirm)

# ============= التنفيذ (الآلي / اليدوي) =============
@router.callback_query(F.data == "execute_buy")
async def execute_order(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    data = await state.get_data()
    if not data:
        return await callback.answer("انتهت صلاحية الجلسة", show_alert=True)
        
    points = await get_points_per_order(db_pool)
    total_syp = float(data['total_syp'])
    app_data = data['app']
    
    is_api_linked = bool(app_data.get('api_service_id'))
    initial_status = 'processing' if is_api_linked else 'pending'
    
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            current_bal = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", callback.from_user.id)
            if current_bal < total_syp:
                await callback.answer("❌ رصيد غير كافي", show_alert=True)
                await state.clear()
                return
                
            await conn.execute("UPDATE users SET balance = balance - $1, total_orders = total_orders + 1 WHERE user_id = $2", total_syp, callback.from_user.id)
            
            if 'variant' in data:
                variant = data['variant']
                order_id = await conn.fetchval('''
                    INSERT INTO orders (user_id, username, app_id, app_name, variant_id, variant_name, quantity, duration_days, unit_price_usd, total_amount_syp, target_id, status, points_earned)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13) RETURNING id
                ''', callback.from_user.id, callback.from_user.username, app_data['id'], app_data['name'], variant['id'], variant['name'], int(variant.get('quantity', 1) or 1), 0, float(data.get('final_price_usd', 0)), total_syp, data['target_id'], initial_status, points)
                order_dict = {'order_id': order_id, 'user_id': callback.from_user.id, 'username': callback.from_user.username, 'app_name': app_data['name'], 'variant_name': variant['name'], 'total_syp': total_syp, 'target_id': data['target_id']}
            else:
                order_id = await conn.fetchval('''
                    INSERT INTO orders (user_id, username, app_id, app_name, quantity, unit_price_usd, total_amount_syp, target_id, status, points_earned)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id
                ''', callback.from_user.id, callback.from_user.username, app_data['id'], app_data['name'], data['qty'], float(data.get('discounted_unit_price_usd', 0)), total_syp, data['target_id'], initial_status, points)
                order_dict = {'order_id': order_id, 'user_id': callback.from_user.id, 'username': callback.from_user.username, 'app_name': app_data['name'], 'quantity': data['qty'], 'total_syp': total_syp, 'target_id': data['target_id']}

    if is_api_linked:
        await callback.message.edit_text("⚡ <b>جاري التنفيذ التلقائي عبر الـ API...</b>\nالرجاء الانتظار ثوانٍ معدودة ⏱️", parse_mode="HTML")
        await send_order_to_mousa_api(order_id, db_pool, bot)
    else:
        from handlers.services import send_order_to_group # Re-using original func just for logging
        group_msg_id = await send_order_to_group(bot, order_dict)
        if group_msg_id:
            async with db_pool.acquire() as conn:
                await conn.execute("UPDATE orders SET group_message_id = $1 WHERE id = $2", group_msg_id, order_id)
        await callback.message.edit_text(f"✅ <b>تم إرسال طلبك بنجاح!</b>\n\n⏳ <b>جاري مراجعة طلبك من قبل الإدارة...</b>\n🔸 <b>رقم طلبك:</b> #{order_id}", parse_mode="HTML")
    
    is_admin = await is_admin_user(db_pool, callback.from_user.id)
    await callback.message.answer("👋 عدنا للقائمة الرئيسية", reply_markup=get_main_menu_keyboard(is_admin))
    await state.clear()

async def send_order_to_group(bot: Bot, order_data: dict):
    try:
        caption = f"🆕 <b>طلب خدمة يدوية</b>\n\n👤 <b>العميل:</b> @{order_data['username']}\n📱 <b>الخدمة:</b> {order_data['app_name']}\n📦 <b>الباقة:</b> {order_data.get('variant_name', order_data.get('quantity'))}\n💰 <b>المبلغ:</b> {order_data['total_syp']:,.0f} ل.س\n🎯 <b>المستهدف:</b> <code>{order_data['target_id']}</code>\n\n🔹 <b>القرار:</b>"
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="✅ موافقة وتأكيد", callback_data=f"appr_order_{order_data['order_id']}"), types.InlineKeyboardButton(text="❌ رفض", callback_data=f"reje_order_{order_data['order_id']}"))
        msg = await bot.send_message(chat_id=ORDERS_GROUP, text=caption, reply_markup=builder.as_markup(), parse_mode="HTML")
        return msg.message_id
    except: return None

async def send_order_to_mousa_api(order_id: int, db_pool, bot: Bot) -> bool:
    api = get_api_client()
    async with db_pool.acquire() as conn:
        order = await conn.fetchrow("SELECT o.*, a.api_service_id FROM orders o JOIN applications a ON o.app_id = a.id WHERE o.id = $1", order_id)
        if not order or not order['api_service_id']: return False
        
        result = await api.create_order(
            product_id=int(order['api_service_id']),
            quantity=order['quantity'],
            player_id=order['target_id'],
            extra_params={'playerId': order['target_id']}
        )
        
        if result['success']:
            await conn.execute("UPDATE orders SET status = 'completed', api_response = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2", json.dumps(result.get('raw', {})), order_id)
            await conn.execute("UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2", order['points_earned'], order['user_id'])
            
            await bot.send_message(
                order['user_id'],
                f"🎉 <b>تم تنفيذ طلبك آلياً في ثوانٍ!</b>\n\n📱 الخدمة: {order['app_name']}\n🎯 المستهدف: <code>{order['target_id']}</code>\n⭐ نقاط مكتسبة: +{order['points_earned']}\n📋 رقم الطلب: #{result.get('order_id')}",
                parse_mode="HTML"
            )
            return True
        else:
            await conn.execute("UPDATE orders SET status = 'failed', admin_notes = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2", f"فشل API: {result.get('error')}", order_id)
            await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", order['total_amount_syp'], order['user_id'])
            
            await bot.send_message(
                order['user_id'],
                f"❌ <b>عذراً، فشل تنفيذ الطلب آلياً</b>\nالسبب: {result.get('error', 'خدمة غير متاحة من المصدر')}\n💰 تمت استعادة {order['total_amount_syp']:,.0f} ل.س إلى رصيدك.",
                parse_mode="HTML"
            )
            return False
