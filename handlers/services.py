# handlers/services.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove
import config
from config import ORDERS_GROUP
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from datetime import datetime
from handlers.time_utils import get_damascus_time_now
from handlers.keyboards import (
    get_main_menu_keyboard,
    get_categories_keyboard,
    get_apps_keyboard,
    get_options_keyboard,
    get_back_inline_keyboard,
    get_confirmation_keyboard,
    get_deposit_keyboard,
    get_profile_keyboard
)
from database import is_admin_user, get_exchange_rate, get_user_vip, get_points_per_order, get_product_options, get_product_option

logger = logging.getLogger(__name__)
router = Router()

class OrderStates(StatesGroup):
    qty = State()
    target_id = State()
    confirm = State()
    choosing_variant = State()
    deposit_amount = State()
    deposit_custom = State()

def get_damascus_time():
    """الحصول على الوقت الحالي بتوقيت دمشق"""
    return get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')

async def send_order_to_group(bot: Bot, order_data: dict):
    """إرسال طلب التطبيق للمجموعة مع أزرار - بتوقيت دمشق"""
    try:
        caption = (
            "🆕 **طلب تطبيق جديد**\n\n"
            f"👤 **المستخدم:** @{order_data['username']}\n"
            f"🆔 **الآيدي:** `{order_data['user_id']}`\n"
            f"📱 **التطبيق:** {order_data['app_name']}\n"
        )
        
        if 'variant_name' in order_data:
            caption += f"📦 **الفئة:** {order_data['variant_name']}\n"
        else:
            caption += f"📦 **الكمية:** {order_data['quantity']}\n"
        
        caption += (
            f"💰 **المبلغ:** {order_data['total_syp']:,.0f} ل.س\n"
            f"🎯 **المستهدف:** `{order_data['target_id']}`\n"
            f"⏰ **الوقت:** {get_damascus_time()}\n\n"
            "🔹 **الإجراءات:**"
        )
        
        # أزرار للموافقة/الرفض
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(
                text="✅ موافقة", 
                callback_data=f"appr_order_{order_data['order_id']}"
            ),
            types.InlineKeyboardButton(
                text="❌ رفض", 
                callback_data=f"reje_order_{order_data['order_id']}"
            ),
            width=2
        )
        
        msg = await bot.send_message(
            chat_id=ORDERS_GROUP,
            text=caption,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        
        logger.info(f"✅ تم إرسال الطلب #{order_data['order_id']} للمجموعة")
        return msg.message_id
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال الطلب للمجموعة: {e}")
        return None

# ============= معالج بدء المحادثة =============

@router.message(F.text == "/start")
async def cmd_start(message: types.Message, db_pool):
    """بداية المحادثة - عرض القائمة الرئيسية إنلاين"""
    is_admin = await is_admin_user(db_pool, message.from_user.id)
    
    await message.answer(
        "👋 **أهلاً بك في البوت!**\n\n"
        "اختر من القائمة أدناه:",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown"
    )

# ============= معالج الرجوع الموحد (للكيبورد الإنلاين) =============

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, db_pool):
    """العودة للقائمة الرئيسية"""
    is_admin = await is_admin_user(db_pool, callback.from_user.id)
    
    await callback.message.edit_text(
        "👋 **القائمة الرئيسية**\n\nاختر من القائمة أدناه:",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "services")
async def show_categories(callback: types.CallbackQuery, db_pool):
    """عرض الأقسام"""
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    
    if not categories:
        await callback.answer("⚠️ لا توجد أقسام متاحة حالياً", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🌟 **اختر القسم:**\n\n"
        "🔸 اختر الفئة التي تريدها:", 
        reply_markup=get_categories_keyboard(categories),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "deposit")
async def show_deposit_options(callback: types.CallbackQuery):
    """عرض خيارات الشحن"""
    await callback.message.edit_text(
        "💰 **شحن المحفظة**\n\n"
        "اختر المبلغ الذي تريد شحنه:\n"
        "أو اختر 'مبلغ آخر' لإدخال مبلغ مخصص",
        reply_markup=get_deposit_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery, db_pool):
    """عرض الحساب الشخصي"""
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT balance, total_points, vip_level FROM users WHERE user_id = $1",
            callback.from_user.id
        )
        
        if not user:
            user = {'balance': 0, 'total_points': 0, 'vip_level': 0}
    
    vip_icons = ["⚪", "🔵", "🟣", "🟡"]
    vip_icon = vip_icons[user['vip_level']] if user['vip_level'] < len(vip_icons) else "⚪"
    
    await callback.message.edit_text(
        f"👤 **حسابي الشخصي**\n\n"
        f"💰 الرصيد: {user['balance']:,.0f} ل.س\n"
        f"⭐ النقاط: {user['total_points']}\n"
        f"👑 مستواك: {vip_icon} VIP {user['vip_level']}\n\n"
        f"اختر من القائمة:",
        reply_markup=get_profile_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "help")
async def show_help(callback: types.CallbackQuery):
    """عرض المساعدة"""
    help_text = (
        "❓ **مساعدة**\n\n"
        "🛒 **خدمات الشحن**: لشراء التطبيقات والألعاب\n"
        "💰 **شحن المحفظة**: لزيادة رصيدك\n"
        "👤 **حسابي**: لعرض رصيدك ونقاطك\n\n"
        "📞 **للتواصل مع الدعم**: @support"
    )
    
    await callback.message.edit_text(
        help_text,
        reply_markup=get_back_inline_keyboard("back_to_main"),
        parse_mode="Markdown"
    )

# ============= معالجات التطبيقات المعطلة =============

@router.callback_query(F.data.startswith("disabled_app_"))
async def handle_disabled_app(callback: types.CallbackQuery):
    """معالج للتطبيقات المعطلة"""
    await callback.answer(
        "❌ هذا التطبيق متوقف حالياً، يرجى المحاولة لاحقاً",
        show_alert=True
    )

@router.callback_query(F.data.startswith("disabled_option_"))
async def handle_disabled_option(callback: types.CallbackQuery):
    """معالج للخيارات المعطلة"""
    await callback.answer(
        "🔒 هذا الخيار متوقف حالياً، يرجى المحاولة لاحقاً أو اختيار خيار آخر",
        show_alert=True
    )

# ============= عرض التطبيقات في قسم =============

@router.callback_query(F.data.startswith("cat_"))
async def show_apps_by_category(callback: types.CallbackQuery, db_pool):
    """عرض التطبيقات في قسم معين"""
    cat_id = int(callback.data.split("_")[1])
    
    async with db_pool.acquire() as conn:
        apps = await conn.fetch(
            "SELECT * FROM applications WHERE category_id = $1 ORDER BY is_active DESC, name",
            cat_id
        )
        category = await conn.fetchrow(
            "SELECT display_name FROM categories WHERE id = $1",
            cat_id
        )
        current_rate = await get_exchange_rate(db_pool)
        user_vip = await get_user_vip(db_pool, callback.from_user.id)
        discount = user_vip.get('discount_percent', 0)
        vip_level = user_vip.get('vip_level', 0)
        vip_icon = user_vip.get('icon', '⚪')
        vip_name = user_vip.get('name', 'عادي')
    
    if not apps:
        await callback.answer("لا توجد تطبيقات في هذا القسم حالياً", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"📱 **{category['display_name']}**\n\n"
        f"👤 مستواك: {vip_icon} {vip_name} (خصم {discount}%)\n"
        f"💰 **سعر الصرف:** {current_rate:,.0f} ل.س = 1$\n"
        f"🔒 التطبيقات المقفلة متوقفة مؤقتاً\n\n"
        "🔸 اختر التطبيق:", 
        reply_markup=get_apps_keyboard(apps, category['display_name'], current_rate, discount),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: types.CallbackQuery, db_pool):
    """العودة إلى الأقسام"""
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    
    await callback.message.edit_text(
        "🌟 **اختر القسم:**\n\n"
        "🔸 اختر الفئة التي تريدها:", 
        reply_markup=get_categories_keyboard(categories),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "back_to_apps")
async def back_to_apps(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """العودة من الخيارات إلى التطبيقات"""
    data = await state.get_data()
    if data and 'app' in data:
        cat_id = data['app']['category_id']
        
        # إعادة عرض التطبيقات
        fake_callback = types.CallbackQuery(
            id='0',
            from_user=callback.from_user,
            message=callback.message,
            data=f"cat_{cat_id}",
            bot=callback.bot
        )
        await show_apps_by_category(fake_callback, db_pool)
    else:
        await back_to_categories(callback, db_pool)
    
    await state.clear()

# ============= بدء الطلب =============

@router.callback_query(F.data.startswith("buy_"))
async def start_order(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء طلب شراء مع تطبيق الخصم"""
    parts = callback.data.split("_")
    app_id = int(parts[1])
    app_type = parts[2] if len(parts) > 2 else 'service'
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)
        
        if not app:
            await callback.answer("عذراً، هذا التطبيق غير متوفر حالياً.", show_alert=True)
            return
        
        if not app['is_active']:
            await callback.answer(
                "❌ هذا التطبيق متوقف حالياً، يرجى المحاولة لاحقاً",
                show_alert=True
            )
            return

        current_rate = await get_exchange_rate(db_pool)
        user_vip = await get_user_vip(db_pool, callback.from_user.id)
        discount = user_vip.get('discount_percent', 0)
        vip_level = user_vip.get('vip_level', 0)
    
    app_dict = dict(app)
    app_dict['unit_price_usd'] = float(app_dict['unit_price_usd']) if app_dict['unit_price_usd'] is not None else 0.0
    app_dict['profit_percentage'] = float(app_dict.get('profit_percentage', 0) or 0)
    app_dict['min_units'] = int(app_dict.get('min_units', 1) or 1)
    
    await state.update_data({
        'app': app_dict,
        'app_type': app_type,
        'current_rate': current_rate,
        'discount': discount,
        'vip_level': vip_level
    })
    
    async with db_pool.acquire() as conn:
        options = await conn.fetch(
            "SELECT * FROM product_options WHERE product_id = $1 ORDER BY is_active DESC, sort_order, price_usd",
            app_id
        )
    
    if options and len(options) > 0:
        active_count = sum(1 for opt in options if opt['is_active'])
        disabled_count = len(options) - active_count
        
        status_message = ""
        if disabled_count > 0:
            status_message = f"\n🔒 هناك {disabled_count} خيارات متوقفة مؤقتاً"
        
        type_name = "لعبة" if app_type == 'game' else "اشتراك" if app_type == 'subscription' else "خدمة"
        
        await callback.message.edit_text(
            f"**{app_dict['name']}**\n\n"
            f"📱 **النوع:** {type_name}\n"
            f"👑 **مستواك:** VIP {vip_level} (خصم {discount}%)\n"
            f"💰 **سعر الصرف:** {current_rate:,.0f} ل.س = 1$\n"
            f"{status_message}\n\n"
            "🔸 **اختر الخيار المناسب:**",
            reply_markup=get_options_keyboard(options, app_dict['name'], current_rate, discount, app_type),
            parse_mode="Markdown"
        )
        await state.set_state(OrderStates.choosing_variant)
    
    else:
        profit_percentage = app_dict['profit_percentage']
        final_unit_price_usd = app_dict['unit_price_usd'] * (1 + (profit_percentage / 100))
        discounted_unit_price_usd = final_unit_price_usd * (1 - discount/100)
        price_per_unit_syp = discounted_unit_price_usd * current_rate
        
        await state.update_data({
            'final_unit_price_usd': final_unit_price_usd,
            'discounted_unit_price_usd': discounted_unit_price_usd,
            'profit_percentage': profit_percentage
        })
        
        await state.set_state(OrderStates.qty)
        
        await callback.message.answer(
            f"🏷 **الخدمة:** {app_dict['name']}\n"
            f"📦 **أقل كمية:** {app_dict['min_units']}\n"
            f"💰 **سعر الوحدة:** {price_per_unit_syp:,.0f} ل.س\n\n"
            f"**الرجاء إدخال الكمية المطلوبة:**",
            reply_markup=None,  # لا يوجد كيبورد سفلي
            parse_mode="Markdown"
        )

# ============= استلام الكمية (نصياً) =============

@router.message(OrderStates.qty)
async def get_qty(message: types.Message, state: FSMContext, db_pool):
    """استقبال الكمية"""
    logger.info(f"📩 استقبال كمية من {message.from_user.id}: {message.text}")
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        is_admin = await is_admin_user(db_pool, message.from_user.id)
        await message.answer(
            "✅ تم إلغاء الطلب",
            reply_markup=get_main_menu_keyboard(is_admin),
            parse_mode="Markdown"
        )
        return

    if not message.text.isdigit():
        await message.answer(
            "⚠️ يرجى إدخال رقم صحيح (كمية)."
        )
        return

    qty = int(message.text)
    
    data = await state.get_data()
    if not data or 'app' not in data:
        await message.answer("❌ انتهت صلاحية الطلب، يرجى البدء من جديد")
        await state.clear()
        return
    
    app = data['app']
    current_rate = data.get('current_rate', 118)
    discount = data.get('discount', 0)
    vip_level = data.get('vip_level', 0)
    min_units = app.get('min_units', 1) or 1
    
    if qty < min_units:
        await message.answer(
            f"⚠️ أقل كمية مسموح بها هي {min_units}."
        )
        return
    
    final_unit_price_usd = data.get('final_unit_price_usd', 0)
    
    original_total_usd = final_unit_price_usd * qty
    original_total_syp = original_total_usd * current_rate
    
    discounted_unit_price_usd = final_unit_price_usd * (1 - discount/100)
    total_usd = qty * discounted_unit_price_usd
    total_syp = total_usd * current_rate
    
    await state.update_data(
        qty=qty,
        total_usd=total_usd,
        total_syp=total_syp,
        original_total_syp=original_total_syp
    )
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT balance FROM users WHERE user_id = $1",
            message.from_user.id
        )
        
        if not user or user['balance'] < total_syp:
            remaining = total_syp - user['balance'] if user else total_syp
            await message.answer(
                f"⚠️ **رصيدك غير كافي**\n\n"
                f"💰 الرصيد الحالي: {user['balance'] if user else 0:,.0f} ل.س\n"
                f"💳 المبلغ المطلوب: {total_syp:,.0f} ل.س\n"
                f"🔸 المبلغ المتبقي: {remaining:,.0f} ل.س\n\n"
                f"قم بشحن رصيدك من خلال قسم الإيداع",
                parse_mode="Markdown"
            )
            return
    
    app_name = app['name'].lower()
    instructions = "🎯 **الرجاء إرسال الحساب المستهدف:**"
    
    if 'pubg' in app_name:
        instructions = "🎮 **الرجاء إرسال ID اللاعب (PUBG):**"
    elif 'free fire' in app_name:
        instructions = "🔥 **الرجاء إرسال ID اللاعب (Free Fire):**"
    elif 'clash' in app_name:
        instructions = "⚔️ **الرجاء إرسال إيميل Supercell ID:**"
    elif 'instagram' in app_name:
        instructions = "📸 **الرجاء إرسال اسم المستخدم على Instagram:**"
    elif 'tiktok' in app_name:
        instructions = "🎵 **الرجاء إرسال اسم المستخدم على TikTok:**"
    elif 'netflix' in app_name:
        instructions = "🎬 **الرجاء إرسال البريد الإلكتروني للحساب:**"
    
    await message.answer(
        f"✅ **تم قبول الكمية**\n\n"
        f"💰 **المبلغ الإجمالي:** {total_syp:,.0f} ل.س\n\n"
        f"{instructions}",
        parse_mode="Markdown"
    )
    
    await state.set_state(OrderStates.target_id)

# ============= اختيار الفئة =============

@router.callback_query(F.data.startswith("var_"))
async def choose_variant(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """اختيار خيار"""
    variant_id = int(callback.data.split("_")[1])
    
    option = await get_product_option(db_pool, variant_id)
    
    if not option:
        await callback.answer("هذا الخيار غير متوفر", show_alert=True)
        return
    
    data = await state.get_data()
    if not data or 'app' not in data:
        await callback.answer("انتهت صلاحية الطلب، يرجى المحاولة مرة أخرى", show_alert=True)
        await state.clear()
        return
    
    app = data['app']
    current_rate = data['current_rate']
    discount = data['discount']
    vip_level = data['vip_level']
    app_type = data.get('app_type', 'service')
    
    app_profit = float(app.get('profit_percentage', 0) or 0)
    opt_price = float(option['price_usd']) if option['price_usd'] is not None else 0.0
    
    price_with_profit = opt_price * (1 + (app_profit / 100))
    discounted_price_usd = price_with_profit * (1 - discount/100)
    total_syp = discounted_price_usd * current_rate
    
    quantity = int(option.get('quantity', 1) or 1)
    
    await state.update_data({
        'variant': dict(option),
        'final_price_usd': discounted_price_usd,
        'total_syp': total_syp,
        'qty': quantity
    })
    
    details = f"**{app['name']}**\n\n"
    details += f"📦 **الخيار:** {option['name']}\n"
    details += f"🔢 **الكمية:** {quantity}\n"
    
    if option.get('description'):
        details += f"📝 **الوصف:**\n{option['description']}\n\n"
    
    details += f"💰 **السعر:** {total_syp:,.0f} ل.س\n\n"
    
    # تعليمات مناسبة
    app_name = app['name'].lower()
    if 'pubg' in app_name or 'free fire' in app_name:
        instructions = "🎮 **يرجى إرسال ID اللاعب الخاص بك:**"
    elif 'clash' in app_name:
        instructions = "📧 **يرجى إرسال إيميل Supercell ID الخاص بك:**"
    elif 'instagram' in app_name or 'tiktok' in app_name:
        instructions = "📸 **يرجى إرسال اسم المستخدم:**"
    else:
        instructions = "🎯 **يرجى إرسال الحساب المستهدف:**"
    
    await callback.message.answer(
        f"{details}{instructions}",
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.target_id)

# ============= استلام الهدف والتأكيد =============

@router.message(OrderStates.target_id)
async def confirm_order(message: types.Message, state: FSMContext, db_pool):
    """استقبال ID الهدف وتأكيد الطلب"""
    logger.info(f"📩 استقبال target_id من {message.from_user.id}: {message.text}")
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        is_admin = await is_admin_user(db_pool, message.from_user.id)
        await message.answer(
            "✅ تم إلغاء الطلب",
            reply_markup=get_main_menu_keyboard(is_admin),
            parse_mode="Markdown"
        )
        return
    
    target_id = message.text.strip()
    if not target_id:
        await message.answer("⚠️ يرجى إدخال ID الحساب.")
        return
    
    data = await state.get_data()
    if not data or 'app' not in data:
        await message.answer("❌ انتهت صلاحية الطلب، يرجى البدء من جديد")
        await state.clear()
        return
    
    total_syp = data.get('total_syp', 0)
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT balance FROM users WHERE user_id = $1",
            message.from_user.id
        )
        
        if not user or user['balance'] < total_syp:
            await state.clear()
            await message.answer("❌ رصيدك غير كافي. تم إلغاء الطلب.")
            return
    
    await state.update_data(target_id=target_id)
    
    msg = (
        f"📋 **تفاصيل الطلب:**\n\n"
        f"🔹 **التطبيق:** {data['app']['name']}\n"
    )
    
    if 'variant' in data:
        msg += f"🔹 **الفئة:** {data['variant']['name']}\n"
    else:
        msg += f"🔹 **الكمية:** {data['qty']}\n"
    
    msg += (
        f"🔹 **المستهدف:** `{target_id}`\n"
        f"💰 **المبلغ:** {total_syp:,.0f} ل.س\n\n"
        f"💳 **سيتم خصم المبلغ من رصيدك.**\n"
        f"⏳ **بعد التأكيد، انتظر موافقة الإدارة.**"
    )
    
    await message.answer(
        msg,
        reply_markup=get_confirmation_keyboard("execute_buy", "cancel_order"),
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.confirm)

# ============= تنفيذ الطلب =============

@router.callback_query(F.data == "execute_buy")
async def execute_order(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    """تنفيذ الطلب"""
    data = await state.get_data()
    
    if not data:
        await callback.answer("انتهت صلاحية الطلب", show_alert=True)
        await state.clear()
        return
    
    points = await get_points_per_order(db_pool)
    total_syp = float(data['total_syp'])
    
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            current_balance = await conn.fetchval(
                "SELECT balance FROM users WHERE user_id = $1",
                callback.from_user.id
            )
            
            if current_balance < total_syp:
                await callback.answer("❌ رصيد غير كافي", show_alert=True)
                await state.clear()
                return
            
            await conn.execute(
                "UPDATE users SET balance = balance - $1, total_orders = total_orders + 1 WHERE user_id = $2",
                total_syp, callback.from_user.id
            )
            
            if 'variant' in data:
                variant = data['variant']
                order_id = await conn.fetchval('''
                    INSERT INTO orders 
                    (user_id, username, app_id, app_name, variant_id, variant_name, 
                     quantity, unit_price_usd, total_amount_syp, target_id, status, points_earned)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'pending', $11)
                    RETURNING id
                ''',
                callback.from_user.id,
                callback.from_user.username,
                data['app']['id'],
                data['app']['name'],
                variant['id'],
                variant['name'],
                int(variant.get('quantity', 1) or 1),
                float(data.get('final_price_usd', 0)),
                total_syp,
                data['target_id'],
                points
                )
                
                order_data = {
                    'order_id': order_id,
                    'user_id': callback.from_user.id,
                    'username': callback.from_user.username or 'غير معروف',
                    'app_name': data['app']['name'],
                    'variant_name': variant['name'],
                    'quantity': int(variant.get('quantity', 1) or 1),
                    'total_syp': total_syp,
                    'target_id': data['target_id'],
                }
            else:
                order_id = await conn.fetchval('''
                    INSERT INTO orders 
                    (user_id, username, app_id, app_name, quantity, unit_price_usd, 
                     total_amount_syp, target_id, status, points_earned)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', $9)
                    RETURNING id
                ''',
                callback.from_user.id,
                callback.from_user.username,
                data['app']['id'],
                data['app']['name'],
                data['qty'],
                data.get('discounted_unit_price_usd', 0),
                total_syp,
                data['target_id'],
                points
                )
                
                order_data = {
                    'order_id': order_id,
                    'user_id': callback.from_user.id,
                    'username': callback.from_user.username or 'غير معروف',
                    'app_name': data['app']['name'],
                    'quantity': data['qty'],
                    'total_syp': total_syp,
                    'target_id': data['target_id'],
                }
            
            group_msg_id = await send_order_to_group(bot, order_data)
            
            if group_msg_id:
                await conn.execute(
                    "UPDATE orders SET group_message_id = $1 WHERE id = $2",
                    group_msg_id, order_id
                )
    
    await callback.message.edit_text(
        f"✅ **تم إرسال طلبك بنجاح!**\n\n"
        f"⏳ **جاري مراجعة طلبك...**\n"
        f"⭐ **نقاط مضافة:** +{points}\n\n"
        f"🔸 **رقم طلبك:** #{order_id}",
        parse_mode="Markdown"
    )
    
    is_admin = await is_admin_user(db_pool, callback.from_user.id)
    await callback.message.answer(
        "👋 يمكنك العودة للقائمة الرئيسية:",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown"
    )
    
    await state.clear()

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """إلغاء الطلب"""
    await state.clear()
    is_admin = await is_admin_user(db_pool, callback.from_user.id)
    
    await callback.message.edit_text("❌ **تم إلغاء الطلب.**")
    await callback.message.answer(
        "👋 القائمة الرئيسية:",
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="Markdown"
    )
