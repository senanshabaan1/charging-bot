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
    """إنشاء زر رجوع مع خيارات إضافية للخروج"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔙 رجوع للقائمة"))
    builder.row(types.KeyboardButton(text="🏠 القائمة الرئيسية"))
    builder.row(types.KeyboardButton(text="/cancel"))
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
        # التحقق من وجود التطبيق
        app = await conn.fetchrow("SELECT * FROM applications WHERE id = $1 AND is_active = TRUE", app_id)
        
        if not app:
            await callback.answer("عذراً، هذا التطبيق غير متوفر حالياً.", show_alert=True)
            return
        
        # جلب سعر الصرف الحالي ومستوى VIP
        from database import get_exchange_rate, get_user_vip
        current_rate = await get_exchange_rate(db_pool)
        user_vip = await get_user_vip(db_pool, callback.from_user.id)
        discount = user_vip.get('discount_percent', 0)
        vip_level = user_vip.get('vip_level', 0)
    
    # ✅ تحويل جميع القيم من Decimal إلى float
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
    
    # معالجة مختلفة حسب نوع التطبيق
    if app_type == 'service':
        # خدمة عادية - نطلب الكمية
        profit_percentage = app_dict['profit_percentage']
        final_unit_price_usd = app_dict['unit_price_usd'] * (1 + (profit_percentage / 100))
        
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
            f"🏷 **الخدمة:** {app_dict['name']}\n"
            f"📦 **أقل كمية:** {app_dict['min_units']}\n"
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
        for opt in variants:
            # ✅ تحويل Decimal إلى float
            opt_dict = dict(opt)
            opt_price = float(opt_dict['price_usd']) if opt_dict['price_usd'] is not None else 0.0
            
            price_with_profit = opt_price * (1 + (app_dict['profit_percentage'] / 100))
            discounted_price_usd = price_with_profit * (1 - discount/100)
            price_syp = discounted_price_usd * current_rate
            
            if app_type == 'game':
                button_text = f"📦 {opt_dict['name']}\n{price_syp:,.0f} ل.س"
            else:  # subscription
                button_text = f"⏱️ {opt_dict['name']}\n{price_syp:,.0f} ل.س"
            
            if discount > 0:
                button_text += f" (خصم {discount}%)"
            
            builder.row(types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"var_{opt_dict['id']}"
            ))
        
        builder.row(types.InlineKeyboardButton(
            text="🔙 رجوع",
            callback_data=f"cat_{app_dict['category_id']}"
        ))
        
        await callback.message.edit_text(
            f"**{app_dict['name']}**\n\n"
            f"👑 **مستواك:** VIP {vip_level} (خصم {discount}%)\n"
            f"💰 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n\n"
            "🔸 **اختر الفئة المناسبة:**",
            reply_markup=builder.as_markup()
        )
        await state.set_state(OrderStates.choosing_variant)
@router.message(OrderStates.qty)
async def get_qty(message: types.Message, state: FSMContext, db_pool):
    """استقبال الكمية مع تطبيق الخصم"""
    logger.info(f"📩 استقبال كمية من {message.from_user.id}: {message.text}")
    
    # التحقق من الإلغاء أولاً
    if message.text in ["🔙 رجوع للقائمة", "/cancel", "/رجوع", "🏠 القائمة الرئيسية"]:
        await state.clear()
        from handlers.start import get_main_menu_keyboard
        from database import is_admin_user
        is_admin = await is_admin_user(db_pool, message.from_user.id)
        await message.answer(
            "✅ تم إلغاء الطلب",
            reply_markup=get_main_menu_keyboard(is_admin)
        )
        return

    # التحقق من أن الإدخال رقم
    if not message.text.isdigit():
        await message.answer(
            "⚠️ يرجى إدخال رقم صحيح (كمية).",
            reply_markup=get_back_keyboard()
        )
        return

    qty = int(message.text)
    
    # التحقق من وجود البيانات في state
    data = await state.get_data()
    if not data or 'app' not in data:
        await message.answer("❌ انتهت صلاحية الطلب، يرجى البدء من جديد")
        await state.clear()
        return
    
    app = data['app']
    current_rate = data.get('current_rate', 115)
    discount = data.get('discount', 0)
    vip_level = data.get('vip_level', 0)
    min_units = app.get('min_units', 1) or 1
    
    # التحقق من الحد الأدنى
    if qty < min_units:
        await message.answer(
            f"⚠️ أقل كمية مسموح بها هي {min_units}.",
            reply_markup=get_back_keyboard()
        )
        return
    
    # حساب السعر
    final_unit_price_usd = data.get('final_unit_price_usd', 0)
    discounted_unit_price_usd = final_unit_price_usd * (1 - discount/100) if final_unit_price_usd > 0 else 0
    total_usd = qty * discounted_unit_price_usd
    total_syp = total_usd * current_rate
    
    # حفظ البيانات الجديدة
    await state.update_data(
        qty=qty,
        total_usd=total_usd,
        total_syp=total_syp
    )
    
    # التحقق من الرصيد
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT balance FROM users WHERE user_id = $1",
            message.from_user.id
        )
        
        if not user:
            await message.answer(
                "❌ حسابك غير موجود في النظام.",
                reply_markup=get_back_keyboard()
            )
            await state.clear()
            return
        
        if user['balance'] < total_syp:
            # حساب المبلغ المتبقي
            remaining = total_syp - user['balance']
            await message.answer(
                f"⚠️ **رصيدك غير كافي**\n\n"
                f"💰 الرصيد الحالي: {user['balance']:,.0f} ل.س\n"
                f"💳 المبلغ المطلوب: {total_syp:,.0f} ل.س\n"
                f"🔸 المبلغ المتبقي: {remaining:,.0f} ل.س\n\n"
                f"قم بشحن رصيدك من خلال قسم الإيداع",
                reply_markup=get_back_keyboard()
            )
            return
    
    # رسالة مع تفاصيل الخصم
    if discount > 0:
        original_total = (final_unit_price_usd * qty * current_rate)
        saved_amount = original_total - total_syp
        price_message = (
            f"💰 **المبلغ الإجمالي:** {total_syp:,.0f} ل.س\n"
            f"🎁 **وفرت:** {saved_amount:,.0f} ل.س (خصم VIP {vip_level}: {discount}%)"
        )
    else:
        price_message = f"💰 **المبلغ الإجمالي:** {total_syp:,.0f} ل.س"
    
    # رسالة تعليمات حسب نوع الخدمة
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
        f"{price_message}\n\n"
        f"{instructions}",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    
    # تغيير الحالة إلى target_id
    await state.set_state(OrderStates.target_id)
    logger.info(f"✅ تم تغيير الحالة إلى target_id للمستخدم {message.from_user.id}")

@router.message(OrderStates.choosing_variant)
async def handle_choosing_variant(message: types.Message, state: FSMContext):
    """معالج إذا كان المستخدم في حالة اختيار الفئة وأرسل رسالة نصية"""
    await message.answer(
        "⚠️ الرجاء اختيار الفئة من الأزرار أعلاه",
        reply_markup=get_back_keyboard()
    )
@router.message(OrderStates.confirm)
async def handle_confirm_state(message: types.Message, state: FSMContext):
    """معالج إذا كان المستخدم في حالة التأكيد وأرسل رسالة نصية"""
    await message.answer(
        "⚠️ الرجاء استخدام الأزرار لتأكيد الطلب أو إلغائه",
        reply_markup=get_back_keyboard()
    )

@router.callback_query(F.data.startswith("var_"))
async def choose_variant(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """اختيار فئة فرعية (للألعاب والاشتراكات) مع عرض الوصف"""
    variant_id = int(callback.data.split("_")[1])
    
    from database import get_product_option
    option = await get_product_option(db_pool, variant_id)
    
    if not option:
        return await callback.answer("هذه الفئة غير متوفرة", show_alert=True)
    
    data = await state.get_data()
    app = data['app']
    current_rate = data['current_rate']
    discount = data['discount']
    vip_level = data['vip_level']
    
    # ✅ تحويل القيم إلى float
    app_profit = float(app.get('profit_percentage', 0) or 0)
    opt_price = float(option['price_usd']) if option['price_usd'] is not None else 0.0
    
    price_with_profit = opt_price * (1 + (app_profit / 100))
    discounted_price_usd = price_with_profit * (1 - discount/100)
    total_syp = discounted_price_usd * current_rate
    
    # السعر الأصلي للعرض
    original_price_usd = price_with_profit
    original_total_syp = original_price_usd * current_rate
    
    # ✅ تحويل الكمية إلى int
    quantity = int(option.get('quantity', 1) or 1)
    
    await state.update_data({
        'variant': dict(option),
        'final_price_usd': discounted_price_usd,
        'total_syp': total_syp,
        'original_total_syp': original_total_syp,
        'qty': quantity
    })
    
    # بناء رسالة التفاصيل
    details = f"📋 **{app['name']}**\n\n"
    details += f"📦 **الخيار:** {option['name']}\n"
    details += f"🔢 **الكمية:** {quantity}\n"
    
    # إضافة الوصف إذا وجد
    if option.get('description'):
        details += f"📝 **الوصف:**\n{option['description']}\n\n"
    
    if discount > 0:
        details += f"💰 **السعر:** {total_syp:,.0f} ل.س (بدلاً من {original_total_syp:,.0f} ل.س)\n"
        details += f"🎁 **خصم VIP {vip_level}:** {discount}% (وفرت {original_total_syp - total_syp:,.0f} ل.س)\n\n"
    else:
        details += f"💰 **السعر:** {total_syp:,.0f} ل.س\n\n"
    
    # رسالة تعليمات حسب نوع اللعبة
    app_name = app['name'].lower()
    if 'pubg' in app_name or 'free fire' in app_name:
        instructions = "🎮 **يرجى إرسال ID اللاعب الخاص بك:**"
    elif 'clash' in app_name:
        instructions = "📧 **يرجى إرسال إيميل Supercell ID الخاص بك:**"
    else:
        instructions = "🎯 **يرجى إرسال الحساب المستهدف:**"
    
    await callback.message.answer(
        f"{details}{instructions}",
        reply_markup=get_back_keyboard()
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
    
    if not data:
        await callback.answer("انتهت صلاحية الطلب، يرجى المحاولة مرة أخرى", show_alert=True)
        await state.clear()
        return
    
    from database import get_points_per_order
    
    # جلب عدد النقاط من الإعدادات
    points = await get_points_per_order(db_pool)
    discount = data.get('discount', 0)
    vip_level = data.get('vip_level', 0)
    
    # ✅ تحويل القيم إلى float للتأكد
    total_syp = float(data['total_syp'])
    
    async with db_pool.acquire() as conn:
        # بدء transaction لضمان تكامل البيانات
        async with conn.transaction():
            # التحقق من الرصيد أولاً
            current_balance = await conn.fetchval(
                "SELECT balance FROM users WHERE user_id = $1",
                callback.from_user.id
            )
            
            if current_balance < total_syp:
                await callback.answer("❌ رصيد غير كافي", show_alert=True)
                await state.clear()
                return
            
            # خصم الرصيد
            await conn.execute(
                "UPDATE users SET balance = balance - $1, total_orders = total_orders + 1 WHERE user_id = $2",
                total_syp, callback.from_user.id
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
                float(data.get('final_price_usd', data.get('discounted_unit_price_usd', 0))),
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
            
            # إرسال الطلب للمجموعة
            group_msg_id = await send_order_to_group(bot, order_data)
            
            if group_msg_id:
                await conn.execute(
                    "UPDATE orders SET group_message_id = $1 WHERE id = $2",
                    group_msg_id, order_id
                )
    
    # رسالة التأكيد مع تفاصيل الخصم
    if discount > 0:
        saved_amount = data.get('original_total_syp', total_syp) - total_syp
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
async def back_to_main(callback: types.CallbackQuery):
    """العودة للقائمة الرئيسية"""
    from handlers.start import get_main_menu_keyboard
    from database import is_admin_user
    
    is_admin = await is_admin_user(None, callback.from_user.id)  # 👈 تحتاج تمرير pool هنا
    
    await callback.message.delete()
    await callback.message.answer(
        "👋 أهلاً بك في القائمة الرئيسية",
        reply_markup=get_main_menu_keyboard(is_admin)
    )
@router.message(F.text.in_(["🔙 رجوع للقائمة", "/رجوع", "/cancel", "🏠 القائمة الرئيسية"]))
async def global_back_handler(message: types.Message, state: FSMContext, db_pool):
    """معالج الرجوع من أي مكان"""
    current_state = await state.get_state()
    
    if current_state is not None:
        await state.clear()
    
    if message.text == "🏠 القائمة الرئيسية":
        from handlers.start import get_main_menu_keyboard
        from database import is_admin_user
        
        is_admin = await is_admin_user(db_pool, message.from_user.id)
        
        await message.answer(
            "👋 أهلاً بك في القائمة الرئيسية",
            reply_markup=get_main_menu_keyboard(is_admin)
        )
    else:
        await message.answer(
            "✅ تم إلغاء العملية",
            reply_markup=get_back_keyboard()
        )
