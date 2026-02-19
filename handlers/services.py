# handlers/services.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import config
from config import ORDERS_GROUP, USD_TO_SYP
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = Router()

class OrderStates(StatesGroup):
    qty = State()
    target_id = State()
    confirm = State()
    choosing_variant = State()

def get_back_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔙 رجوع للقائمة"))
    return builder.as_markup(resize_keyboard=True)

async def send_order_to_group(bot: Bot, order_data: dict):
    """إرسال طلب التطبيق للمجموعة مع أزرار"""
    try:
        caption = (
            "🆕 **طلب تطبيق جديد**\n\n"
            f"👤 **المستخدم:** @{order_data['username']}\n"
            f"🆔 **الآيدي:** `{order_data['user_id']}`\n"
            f"📱 **التطبيق:** {order_data['app_name']}\n"
            f"📦 **الكمية:** {order_data['quantity']}\n"
            f"💰 **المبلغ:** {order_data['total_syp']:,.0f} ل.س\n"
            f"🎯 **المستهدف:** `{order_data['target_id']}`\n"
            f"⏰ **الوقت:** {order_data['time']}\n\n"
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

async def update_order_message(bot: Bot, message_id: int, order_data: dict, status: str):
    """تحديث رسالة الطلب في المجموعة بعد المعالجة"""
    try:
        status_text = {
            "processing": "🔄 **جاري التنفيذ...**",
            "completed": "✅ **تم التنفيذ بنجاح**",
            "failed": "❌ **تعذر التنفيذ**"
        }
        
        caption = (
            f"{status_text.get(status, '📋 تحديث الطلب')}\n\n"
            f"👤 **المستخدم:** @{order_data['username']}\n"
            f"🆔 **الآيدي:** `{order_data['user_id']}`\n"
            f"📱 **التطبيق:** {order_data['app_name']}\n"
            f"📦 **الكمية:** {order_data['quantity']}\n"
            f"💰 **المبلغ:** {order_data['total_syp']:,.0f} ل.س\n"
            f"🎯 **المستهدف:** `{order_data['target_id']}`\n"
            f"⏰ **الوقت:** {order_data['time']}"
        )
        
        # أزرار جديدة بناءً على الحالة
        builder = InlineKeyboardBuilder()
        if status == "processing":
            builder.row(
                types.InlineKeyboardButton(
                    text="✅ تم التنفيذ", 
                    callback_data=f"compl_order_{order_data['order_id']}"
                ),
                types.InlineKeyboardButton(
                    text="❌ تعذر التنفيذ", 
                    callback_data=f"fail_order_{order_data['order_id']}"
                ),
                width=2
            )
        
        await bot.edit_message_text(
            chat_id=ORDERS_GROUP,
            message_id=message_id,
            text=caption,
            reply_markup=builder.as_markup() if status == "processing" else None,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"خطأ في تحديث رسالة المجموعة: {e}")

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

# في دالة show_apps_by_category
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
    
    if not apps:
        await callback.answer("لا توجد تطبيقات في هذا القسم حالياً", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    
    buttons = []
    for app in apps:
        # تعيين الأيقونة حسب نوع التطبيق
        if app['type'] == 'game':
            icon = "🎮"
        elif app['type'] == 'subscription':
            icon = "📅"
        else:  # service
            icon = "📱"
        
        # حساب السعر مع الخصم
        profit_percentage = app.get('profit_percentage', 0)
        final_price_usd = app['unit_price_usd'] * (1 + (profit_percentage / 100))
        
        # تطبيق الخصم
        discounted_price_usd = final_price_usd * (1 - discount/100)
        price_syp = discounted_price_usd * current_rate
        
        # عرض السعر مع إشارة الخصم
        if discount > 0:
            original_price = final_price_usd * current_rate
            button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س (خصم {discount}%)"
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
    vip_text = vip_icons[user_vip['vip_level']] if user_vip['vip_level'] <= 5 else "VIP 0 🟢"
    
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
    """بدء طلب شراء"""
    parts = callback.data.split("_")
    app_id = int(parts[1])
    app_type = parts[2] if len(parts) > 2 else 'service'
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)
        
        # جلب سعر الصرف الحالي
        from database import get_exchange_rate
        current_rate = await get_exchange_rate(db_pool)
    
    if not app:
        return await callback.answer("عذراً، هذه الخدمة لم تعد متوفرة.", show_alert=True)
    
    await state.update_data({
        'app': dict(app),
        'app_type': app_type,
        'current_rate': current_rate
    })
    
    # معالجة مختلفة حسب نوع التطبيق
    if app_type == 'service':
        # خدمة عادية - نطلب الكمية
        profit_percentage = app.get('profit_percentage', 0)
        final_unit_price_usd = app['unit_price_usd'] * (1 + (profit_percentage / 100))
        price_per_unit_syp = final_unit_price_usd * current_rate
        
        await state.update_data({
            'final_unit_price_usd': final_unit_price_usd,
            'profit_percentage': profit_percentage
        })
        
        await state.set_state(OrderStates.qty)
        
        await callback.message.answer(
            f"🏷 **الخدمة:** {app['name']}\n"
            f"📦 **أقل كمية:** {app['min_units']}\n"
            f"💰 **سعر الوحدة:** {price_per_unit_syp:,.0f} ل.س\n\n"
            f"**الرجاء إدخال الكمية المطلوبة:**",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
    
    elif app_type == 'game' or app_type == 'subscription':
        # لعبة أو اشتراك - نعرض الفئات
        from database import get_app_variants
        variants = await get_app_variants(db_pool, app_id)
        
        if not variants:
            return await callback.answer("لا توجد فئات متاحة لهذا التطبيق حالياً", show_alert=True)
        
        builder = InlineKeyboardBuilder()
        for v in variants:
            price_with_profit = v['price_usd'] * (1 + (app['profit_percentage'] / 100))
            price_syp = price_with_profit * current_rate
            
            if app_type == 'game':
                button_text = f"📦 {v['quantity']} وحدة\n{price_syp:,.0f} ل.س"
            else:  # subscription
                button_text = f"⏱️ {v['duration_days']} يوم\n{price_syp:,.0f} ل.س"
            
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
            f"💰 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n\n"
            "🔸 **اختر الفئة المناسبة:**",
            reply_markup=builder.as_markup()
        )
        await state.set_state(OrderStates.choosing_variant)

@router.message(OrderStates.qty)
async def get_qty(message: types.Message, state: FSMContext, db_pool):
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
    
    if qty < app['min_units']:
        return await message.answer(
            f"⚠️ أقل كمية مسموح بها هي {app['min_units']}.",
            reply_markup=get_back_keyboard()
        )
    
    total_usd = qty * data['final_unit_price_usd']
    total_syp = total_usd * current_rate
    
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
    
    await state.update_data(qty=qty, total_usd=total_usd, total_syp=total_syp)
    
    await message.answer(
        f"✅ **الكمية مقبولة**\n\n"
        f"💰 **المبلغ الإجمالي:** {total_syp:,.0f} ل.س\n\n"
        f"**الرجاء إرسال (ID الحساب) المراد شحنه:**",
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
    
    msg = (
        f"📋 **تفاصيل الطلب:**\n\n"
        f"🔹 **التطبيق:** {data['app']['name']}\n"
        f"🔹 **الكمية:** {data['qty']}\n"
        f"🔹 **المستهدف:** `{target_id}`\n"
        f"🔹 **السعر الإجمالي:** {data['total_syp']:,.0f} ل.س\n\n"
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
    """تنفيذ الطلب (لجميع الأنواع)"""
    data = await state.get_data()
    
    from datetime import datetime
    from database import get_points_per_order
    
    # جلب عدد النقاط من الإعدادات
    points = await get_points_per_order(db_pool)
    logger.info(f"📊 نقاط الطلب: {points}")
    
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
                variant.get('quantity', 0),
                variant.get('duration_days', 0),
                data['final_price_usd'],
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
                    'quantity': variant.get('quantity', 0),
                    'duration_days': variant.get('duration_days', 0),
                    'total_syp': data['total_syp'],
                    'target_id': data['target_id'],
                    'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                data['final_unit_price_usd'],
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
                    'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            
            # إرسال الطلب للمجموعة
            group_msg_id = await send_order_to_group(bot, order_data)
            
            if group_msg_id:
                await conn.execute(
                    "UPDATE orders SET group_message_id = $1 WHERE id = $2",
                    group_msg_id, order_id
                )
            
    
    # إرسال رسالة التأكيد للمستخدم
    await callback.message.edit_text(
        f"✅ **تم إرسال طلبك بنجاح!**\n\n"
        f"⏳ **جاري مراجعة طلبك من قبل الإدارة...**\n"
        f"📋 **سيتم التنفيذ خلال 24 ساعة.**\n"
        f"⭐ **نقاط مضافة:** +{points}\n\n"
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
