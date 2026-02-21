# handlers/services.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import config
from config import ORDERS_GROUP, USD_TO_SYP
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import logging
from datetime import datetime
import pytz

# ضبط المنطقة الزمنية لدمشق
DAMASCUS_TZ = pytz.timezone('Asia/Damascus')

logger = logging.getLogger(__name__)
router = Router()

class OrderStates(StatesGroup):
    qty = State()
    target_id = State()
    confirm = State()
    choosing_variant = State()

def get_back_keyboard():
    """إنشاء زر رجوع فقط"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔙 رجوع للقائمة"))
    builder.row(types.KeyboardButton(text="/رجوع"))
    return builder.as_markup(resize_keyboard=True)

def get_damascus_time():
    """الحصول على الوقت الحالي بتوقيت دمشق"""
    return datetime.now(DAMASCUS_TZ).strftime('%Y-%m-%d %H:%M:%S')

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
        
        return msg.message_id
    except Exception as e:
        logging.error(f"خطأ في إرسال الطلب للمجموعة: {e}")
        return None

@router.message(F.text == "📱 خدمات الشحن")
async def show_categories(message: types.Message, db_pool):
    """عرض الأقسام أولاً"""
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    
    if not categories:
        await message.answer(
            "⚠️ لا توجد أقسام متاحة حالياً.",
            reply_markup=get_back_keyboard()
        )
        return
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(types.InlineKeyboardButton(
            text=f"{cat['icon']} {cat['display_name']}", 
            callback_data=f"cat_{cat['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data="back_to_main"
    ))
    
    await message.answer(
        "🌟 **اختر القسم:**\n\n"
        "🔸 اختر الفئة التي تريدها:", 
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("cat_"))
async def show_apps_by_category(callback: types.CallbackQuery, db_pool):
    """عرض التطبيقات في قسم معين - مع تمييز نوع التطبيق"""
    cat_id = int(callback.data.split("_")[1])
    
    async with db_pool.acquire() as conn:
        apps = await conn.fetch(
            "SELECT * FROM applications WHERE category_id = $1 AND is_active = TRUE ORDER BY name",
            cat_id
        )
        category = await conn.fetchrow(
            "SELECT display_name FROM categories WHERE id = $1",
            cat_id
        )
        
        # جلب سعر الصرف الحالي
        from database import get_exchange_rate, get_user_vip
        current_rate = await get_exchange_rate(db_pool)
        
        # جلب مستوى VIP للمستخدم
        user_vip = await get_user_vip(db_pool, callback.from_user.id)
        discount = user_vip.get('discount_percent', 0)
        vip_level = user_vip.get('vip_level', 0)
    
    if not apps:
        await callback.answer("لا توجد تطبيقات في هذا القسم حالياً", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    
    buttons = []
    for app in apps:
        # ✅ تحويل Decimal إلى float
        unit_price = float(app['unit_price_usd']) if app['unit_price_usd'] is not None else 0.0
        profit_percentage = float(app.get('profit_percentage', 0) or 0)
        min_units = int(app.get('min_units', 1) or 1)
        
        # تعيين الأيقونة حسب نوع التطبيق
        if app['type'] == 'game':
            icon = "🎮"
        elif app['type'] == 'subscription':
            icon = "📅"
        else:  # service
            icon = "📱"
        
        # حساب السعر مع الخصم
        final_price_usd = unit_price * (1 + (profit_percentage / 100))
        
        # تطبيق الخصم
        discounted_price_usd = final_price_usd * (1 - discount/100)
        price_syp = discounted_price_usd * current_rate
        
        # عرض السعر مع إشارة الخصم
        if discount > 0:
            original_price = final_price_usd * current_rate
            if app['type'] == 'game' and min_units > 1:
                button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س (أقل كمية {min_units}) (خصم {discount}%)"
            else:
                button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س (خصم {discount}%)"
        else:
            if app['type'] == 'game' and min_units > 1:
                button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س (أقل كمية {min_units})"
            else:
                button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س"
        
        buttons.append(types.InlineKeyboardButton(
            text=button_text, 
            callback_data=f"buy_{app['id']}_{app['type']}"
        ))
    
    # ترتيب الأزرار
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            builder.row(buttons[i], buttons[i + 1])
        else:
            builder.row(buttons[i])
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للأقسام", 
        callback_data="back_to_categories"
    ))
    
    # إظهار مستوى المستخدم
    vip_icons = ["🟢 VIP 0", "🔵 VIP 1", "🟣 VIP 2", "🟡 VIP 3", "🔴 VIP 4", "💎 VIP 5"]
    vip_text = vip_icons[vip_level] if vip_level <= 5 else "VIP 0 🟢"
    
    await callback.message.edit_text(
        f"📱 **{category['display_name']}**\n\n"
        f"👤 مستواك: {vip_text} (خصم {discount}%)\n"
        f"💰 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n\n"
        "🔸 اختر التطبيق المطلوب:", 
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: types.CallbackQuery, db_pool):
    """العودة إلى الأقسام"""
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(types.InlineKeyboardButton(
            text=f"{cat['icon']} {cat['display_name']}", 
            callback_data=f"cat_{cat['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data="back_to_main"
    ))
    
    await callback.message.edit_text(
        "🌟 **اختر القسم:**\n\n"
        "🔸 اختر الفئة التي تريدها:", 
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("buy_"))
async def start_order(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء طلب شراء مع تطبيق الخصم"""
    parts = callback.data.split("_")
    app_id = int(parts[1])
    app_type = parts[2] if len(parts) > 2 else 'service'
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)
        
        # جلب سعر الصرف الحالي ومستوى VIP
        from database import get_exchange_rate, get_user_vip
        current_rate = await get_exchange_rate(db_pool)
        user_vip = await get_user_vip(db_pool, callback.from_user.id)
        discount = user_vip.get('discount_percent', 0)
        vip_level = user_vip.get('vip_level', 0)
    
    if not app:
        return await callback.answer("عذراً، هذه الخدمة لم تعد متوفرة.", show_alert=True)
    
    # ✅ تحويل Decimal إلى float
    unit_price = float(app['unit_price_usd']) if app['unit_price_usd'] is not None else 0.0
    profit_percentage = float(app.get('profit_percentage', 0) or 0)
    min_units = int(app.get('min_units', 1) or 1)
    
    await state.update_data({
        'app': dict(app),
        'app_type': app_type,
        'current_rate': current_rate,
        'discount': discount,
        'vip_level': vip_level,
        'unit_price': unit_price,
        'min_units': min_units
    })
    
    # معالجة مختلفة حسب نوع التطبيق
    if app_type == 'service':
        # خدمة عادية - نطلب الكمية
        final_unit_price_usd = unit_price * (1 + (profit_percentage / 100))
        
        # تطبيق الخصم
        discounted_unit_price_usd = final_unit_price_usd * (1 - discount/100)
        price_per_unit_syp = discounted_unit_price_usd * current_rate
        
        await state.update_data({
            'final_unit_price_usd': final_unit_price_usd,
            'discounted_unit_price_usd': discounted_unit_price_usd,
            'profit_percentage': profit_percentage
        })
        
        # رسالة مع إظهار الخصم إذا موجود
        if discount > 0:
            original_price = final_unit_price_usd * current_rate
            price_text = f"💰 **سعر الوحدة:** {price_per_unit_syp:,.0f} ل.س (بدلاً من {original_price:,.0f} ل.س)\n"
            price_text += f"🎁 **خصم VIP {vip_level}:** {discount}%"
        else:
            price_text = f"💰 **سعر الوحدة:** {price_per_unit_syp:,.0f} ل.س"
        
        await state.set_state(OrderStates.qty)
        
        await callback.message.answer(
            f"🏷 **الخدمة:** {app['name']}\n"
            f"📦 **أقل كمية:** {min_units}\n"
            f"{price_text}\n\n"
            f"**الرجاء إدخال الكمية المطلوبة:**",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif app_type == 'game' or app_type == 'subscription':
        # لعبة أو اشتراك - نعرض الفئات
        from database import get_product_options
        variants = await get_product_options(db_pool, app_id)
        
        if not variants:
            return await callback.answer("لا توجد فئات متاحة لهذا التطبيق حالياً", show_alert=True)
        
        builder = InlineKeyboardBuilder()
        for v in variants:
            # ✅ تحويل Decimal إلى float
            v_price = float(v['price_usd']) if v['price_usd'] is not None else 0.0
            price_with_profit = v_price * (1 + (profit_percentage / 100))
            discounted_price_usd = price_with_profit * (1 - discount/100)
            price_syp = discounted_price_usd * current_rate
            
            if app_type == 'game':
                qty_text = int(v.get('quantity', 1) or 1)
                button_text = f"📦 {qty_text} وحدة\n{price_syp:,.0f} ل.س"
            else:  # subscription
                days = int(v.get('duration_days', 30) or 30)
                button_text = f"⏱️ {days} يوم\n{price_syp:,.0f} ل.س"
            
            if discount > 0:
                button_text += f" (خصم {discount}%)"
            
            builder.row(types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"var_{v['id']}"
            ))
        
        builder.row(types.InlineKeyboardButton(
            text="🔙 رجوع",
            callback_data=f"cat_{app['category_id']}"
        ))
        
        await callback.message.edit_text(
            f"**{app['name']}**\n\n"
            f"👑 **مستواك:** VIP {vip_level} (خصم {discount}%)\n"
            f"💰 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n\n"
            "🔸 **اختر الفئة المناسبة:**",
            reply_markup=builder.as_markup()
        )
        await state.set_state(OrderStates.choosing_variant)

@router.callback_query(F.data.startswith("var_"))
async def choose_variant(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """اختيار فئة فرعية (للألعاب والاشتراكات)"""
    variant_id = int(callback.data.split("_")[1])
    
    from database import get_product_option
    variant = await get_product_option(db_pool, variant_id)
    
    if not variant:
        return await callback.answer("هذه الفئة غير متوفرة", show_alert=True)
    
    data = await state.get_data()
    app = data['app']
    current_rate = data['current_rate']
    discount = data['discount']
    vip_level = data['vip_level']
    profit_percentage = float(app.get('profit_percentage', 0) or 0)
    
    # ✅ تحويل Decimal إلى float
    v_price = float(variant['price_usd']) if variant['price_usd'] is not None else 0.0
    price_with_profit = v_price * (1 + (profit_percentage / 100))
    discounted_price_usd = price_with_profit * (1 - discount/100)
    total_syp = discounted_price_usd * current_rate
    
    # السعر الأصلي للعرض
    original_price_usd = price_with_profit
    original_total_syp = original_price_usd * current_rate
    
    await state.update_data({
        'variant': dict(variant),
        'final_price_usd': discounted_price_usd,
        'total_syp': total_syp,
        'original_total_syp': original_total_syp,
        'qty': int(variant.get('quantity', 1) or 1)
    })
    
    # رسالة تعليمات حسب نوع اللعبة
    app_name = app['name'].lower()
    if 'pubg' in app_name or 'free fire' in app_name:
        instructions = "🎮 **يرجى إرسال ID اللاعب الخاص بك:**\n"
    elif 'clash' in app_name:
        instructions = "📧 **يرجى إرسال إيميل Supercell ID الخاص بك:**\n"
    else:
        instructions = "🎯 **يرجى إرسال الحساب المستهدف:**\n"
    
    await callback.message.answer(
        f"📋 **تفاصيل الطلب**\n\n"
        f"📱 **التطبيق:** {app['name']}\n"
        f"📦 **الفئة:** {variant['name']}\n"
        f"💰 **السعر:** {total_syp:,.0f} ل.س\n\n"
        f"{instructions}",
        reply_markup=get_back_keyboard()
    )
    await state.set_state(OrderStates.target_id)

@router.message(OrderStates.qty)
async def get_qty(message: types.Message, state: FSMContext, db_pool):
    """استقبال الكمية مع تطبيق الخصم"""
    if message.text == "🔙 رجوع للقائمة":
        await state.clear()
        await message.answer("تم إلغاء الطلب.")
        return
    
    if not message.text.isdigit():
        return await message.answer(
            "⚠️ يرجى إدخال رقم صحيح (كمية).",
            reply_markup=get_back_keyboard()
        )
    
    qty = int(message.text)
    data = await state.get_data()
    app = data['app']
    current_rate = data.get('current_rate', 115)
    discount = data.get('discount', 0)
    vip_level = data.get('vip_level', 0)
    min_units = data.get('min_units', 1) or 1
    
    if qty < min_units:
        return await message.answer(
            f"⚠️ أقل كمية مسموح بها هي {min_units}.",
            reply_markup=get_back_keyboard()
        )
    
    # استخدام السعر بعد الخصم
    discounted_unit_price_usd = data.get('discounted_unit_price_usd', data.get('final_unit_price_usd'))
    total_usd = qty * discounted_unit_price_usd
    total_syp = total_usd * current_rate
    
    # السعر الأصلي للعرض
    original_unit_price_usd = data.get('final_unit_price_usd')
    original_total_usd = qty * original_unit_price_usd
    original_total_syp = original_total_usd * current_rate
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT balance FROM users WHERE user_id = $1",
            message.from_user.id
        )
        
        if not user:
            return await message.answer(
                "❌ حسابك غير موجود في النظام.",
                reply_markup=get_back_keyboard()
            )
        
        if user['balance'] < total_syp:
            return await message.answer(
                f"⚠️ رصيدك غير كافي.\n"
                f"💳 الرصيد الحالي: {user['balance']:,.0f} ل.س\n"
                f"💰 المطلوب: {total_syp:,.0f} ل.س\n"
                f"🔸 تحتاج: {total_syp - user['balance']:,.0f} ل.س",
                reply_markup=get_back_keyboard()
            )
    
    await state.update_data(
        qty=qty, 
        total_usd=total_usd, 
        total_syp=total_syp,
        original_total_syp=original_total_syp
    )
    
    # رسالة مع تفاصيل الخصم
    if discount > 0:
        saved_amount = original_total_syp - total_syp
        price_message = f"💰 **المبلغ الإجمالي:** {total_syp:,.0f} ل.س (بدلاً من {original_total_syp:,.0f} ل.س)\n"
        price_message += f"🎁 **وفرت:** {saved_amount:,.0f} ل.س (خصم VIP {vip_level}: {discount}%)"
    else:
        price_message = f"💰 **المبلغ الإجمالي:** {total_syp:,.0f} ل.س"
    
    # رسالة تعليمات حسب نوع اللعبة
    app_name = app['name'].lower()
    if 'pubg' in app_name or 'free fire' in app_name:
        instructions = "🎮 **الرجاء إرسال ID اللاعب الخاص بك:**\n"
    elif 'clash' in app_name:
        instructions = "📧 **الرجاء إرسال إيميل Supercell ID الخاص بك:**\n"
    else:
        instructions = "🎯 **الرجاء إرسال الحساب المستهدف:**\n"
    
    await message.answer(
        f"✅ **الكمية مقبولة**\n\n"
        f"{price_message}\n\n"
        f"{instructions}",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.target_id)

@router.message(OrderStates.target_id)
async def confirm_order(message: types.Message, state: FSMContext, db_pool):
    if message.text == "🔙 رجوع للقائمة":
        await state.clear()
        await message.answer("تم إلغاء الطلب.")
        return
    
    target_id = message.text.strip()
    if not target_id:
        return await message.answer(
            "⚠️ يرجى إدخال ID الحساب.",
            reply_markup=get_back_keyboard()
        )
    
    data = await state.get_data()
    discount = data.get('discount', 0)
    vip_level = data.get('vip_level', 0)
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT balance FROM users WHERE user_id = $1",
            message.from_user.id
        )
        
        if not user or user['balance'] < data['total_syp']:
            await state.clear()
            return await message.answer(
                "❌ رصيدك غير كافي. تم إلغاء الطلب.",
                reply_markup=get_back_keyboard()
            )
    
    await state.update_data(target_id=target_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="✅ تأكيد ودفع", callback_data="execute_buy"))
    builder.row(types.InlineKeyboardButton(text="🔙 إلغاء", callback_data="cancel_order"))
    
    # رسالة التأكيد مع تفاصيل الخصم
    if discount > 0:
        saved_amount = data.get('original_total_syp', data['total_syp']) - data['total_syp']
        price_detail = f"💰 **السعر الإجمالي:** {data['total_syp']:,.0f} ل.س (بدلاً من {data.get('original_total_syp', data['total_syp']):,.0f} ل.س)\n"
        price_detail += f"🎁 **خصم VIP {vip_level}:** {discount}% (وفرت {saved_amount:,.0f} ل.س)"
    else:
        price_detail = f"💰 **السعر الإجمالي:** {data['total_syp']:,.0f} ل.س"
    
    # إضافة تحذيرات حسب نوع الخدمة
    app_name = data['app']['name'].lower()
    warnings = ""
    if 'pubg' in app_name or 'free fire' in app_name:
        warnings = "\n⚠️ **تنبيه:** غير مسؤولين عن أي ID خاطئ. تأكد من صحة ID اللاعب قبل الإرسال.\n"
    elif 'clash' in app_name:
        warnings = "\n⚠️ **تنبيه:** تأكد من صحة إيميل Supercell ID الخاص بك.\n"
    
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
        f"{price_detail}\n"
        f"{warnings}\n"
        f"💳 **سيتم خصم المبلغ من رصيدك.**\n"
        f"⏳ **بعد التأكيد، انتظر موافقة الإدارة.**"
    )
    
    await message.answer(
        msg, 
        reply_markup=builder.as_markup(), 
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.confirm)

@router.callback_query(F.data == "execute_buy")
async def execute_order(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    """تنفيذ الطلب (لجميع الأنواع) مع تطبيق الخصم"""
    data = await state.get_data()
    
    from database import get_points_per_order
    
    # جلب عدد النقاط من الإعدادات
    points = await get_points_per_order(db_pool)
    discount = data.get('discount', 0)
    vip_level = data.get('vip_level', 0)
    logger.info(f"📊 نقاط الطلب: {points}, خصم VIP: {discount}%")
    
    async with db_pool.acquire() as conn:
        # بدء transaction لضمان تكامل البيانات
        async with conn.transaction():
            # خصم الرصيد
            await conn.execute(
                "UPDATE users SET balance = balance - $1, total_orders = total_orders + 1 WHERE user_id = $2",
                data['total_syp'], callback.from_user.id
            )
            
            if 'variant' in data:
                # طلب بفئة
                variant = data['variant']
                order_id = await conn.fetchval('''
                    INSERT INTO orders 
                    (user_id, username, app_id, app_name, variant_id, variant_name, 
                     quantity, duration_days, unit_price_usd, total_amount_syp, target_id, status, points_earned)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'pending', $12)
                    RETURNING id
                ''',
                callback.from_user.id,
                callback.from_user.username,
                data['app']['id'],
                data['app']['name'],
                variant['id'],
                variant['name'],
                int(variant.get('quantity', 1) or 1),
                int(variant.get('duration_days', 0) or 0),
                data['final_price_usd'] if 'final_price_usd' in data else data['discounted_unit_price_usd'],
                data['total_syp'],
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
                    'total_syp': data['total_syp'],
                    'target_id': data['target_id'],
                }
            else:
                # طلب عادي
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
                data['discounted_unit_price_usd'],
                data['total_syp'],
                data['target_id'],
                points
                )
                
                order_data = {
                    'order_id': order_id,
                    'user_id': callback.from_user.id,
                    'username': callback.from_user.username or 'غير معروف',
                    'app_name': data['app']['name'],
                    'quantity': data['qty'],
                    'total_syp': data['total_syp'],
                    'target_id': data['target_id'],
                }
            
            # إرسال الطلب للمجموعة
            group_msg_id = await send_order_to_group(bot, order_data)
            
            if group_msg_id:
                await conn.execute(
                    "UPDATE orders SET group_message_id = $1 WHERE id = $2",
                    group_msg_id, order_id
                )
    
    # رسالة التأكيد مع تفاصيل الخصم
    if discount > 0:
        saved_amount = data.get('original_total_syp', data['total_syp']) - data['total_syp']
        discount_text = f"\n🎁 **خصم VIP {vip_level}:** {discount}% (وفرت {saved_amount:,.0f} ل.س)"
    else:
        discount_text = ""
    
    await callback.message.edit_text(
        f"✅ **تم إرسال طلبك بنجاح!**\n\n"
        f"⏳ **جاري مراجعة طلبك من قبل الإدارة...**\n"
        f"📋 **سيتم التنفيذ خلال 24 ساعة.**\n"
        f"⭐ **نقاط مضافة:** +{points}"
        f"{discount_text}\n\n"
        f"🔸 **رقم طلبك:** #{order_id}",
        parse_mode="Markdown"
    )
    
    await state.clear()

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ **تم إلغاء الطلب.**")

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_services(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "تم العودة للقائمة الرئيسية.",
        reply_markup=get_back_keyboard()
    )
