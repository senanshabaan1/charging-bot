# handlers/services.py - التعديلات النهائية

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import config
from config import ORDERS_GROUP, USD_TO_SYP
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from datetime import datetime
from handlers.time_utils import get_damascus_time_now, format_damascus_time, DAMASCUS_TZ
from handlers.keyboards import get_main_menu_keyboard, get_cancel_keyboard
from database.users import is_admin_user
from database.core import get_exchange_rate
from database.vip import get_user_vip
from database.points import get_points_per_order
from database.products import get_product_options, get_product_option
from utils import get_formatted_damascus_time, format_amount, is_valid_positive_number

logger = logging.getLogger(__name__)
router = Router()

class OrderStates(StatesGroup):
    qty = State()
    target_id = State()
    confirm = State()
    choosing_variant = State()

# دالة مساعدة للتخزين المؤقت
async def get_cached_categories(db_pool):
    """جلب الأقسام مع إمكانية التخزين المؤقت"""
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM categories ORDER BY sort_order")

# ============= معالج الكولباك للقائمة الرئيسية =============
@router.callback_query(F.data == "show_categories")
async def show_categories_callback(callback: types.CallbackQuery, db_pool):
    """عرض الأقسام من القائمة الإنلاين"""
    await callback.answer()
    
    categories = await get_cached_categories(db_pool)
    
    if not categories:
        await callback.message.edit_text(
            "⚠️ لا توجد أقسام متاحة حالياً."
        )
        return
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        icon = cat.get('icon', '📁')
        display_name = cat.get('display_name', 'قسم')
        builder.row(types.InlineKeyboardButton(
            text=f"{icon} {display_name}", 
            callback_data=f"cat_{cat['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data="back_to_main"
    ))
    
    await callback.message.edit_text(
        "🌟 **📁 الأقسام**:\n\n"
        "🔸اختر القسم المفضل:", 
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """العودة للقائمة الرئيسية"""
    await callback.answer()
    await state.clear()
    
    is_admin = await is_admin_user(db_pool, callback.from_user.id)
    
    await callback.message.edit_text(
        "👋 مرحباً بك في القائمة الرئيسية. يمكنك اختيار ما تريد من الأزرار أدناه:",
        reply_markup=get_main_menu_keyboard(is_admin)
    )

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
            f"⏰ **الوقت:** {get_formatted_damascus_time()}\n\n"
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

# ============= معالج الرجوع الموحد =============

@router.message(F.text.in_(["🔙 رجوع للقائمة", "/رجوع", "/cancel", "🏠 القائمة الرئيسية", "❌ إلغاء"]))
async def global_back_handler(message: types.Message, state: FSMContext, db_pool):
    """معالج الرجوع من أي مكان"""
    current_state = await state.get_state()
    
    if current_state is not None:
        logger.info(f"تم إلغاء الحالة {current_state} للمستخدم {message.from_user.id}")
        await state.clear()
    
    is_admin = await is_admin_user(db_pool, message.from_user.id)
    
    if message.text == "🏠 القائمة الرئيسية":
        await message.answer(
            "👋 أهلاً بك في القائمة الرئيسية",
            reply_markup=get_main_menu_keyboard(is_admin)
        )
    else:
        await message.answer(
            "✅ تم إلغاء العملية",
            reply_markup=get_main_menu_keyboard(is_admin)
        )

# ============= عرض الأقسام =============

@router.message(F.text == "📱 خدمات الشحن")
async def show_categories(message: types.Message, db_pool):
    """عرض الأقسام أولاً"""
    categories = await get_cached_categories(db_pool)
    
    if not categories:
        is_admin = await is_admin_user(db_pool, message.from_user.id)
        await message.answer(
            "⚠️ لا توجد أقسام متاحة حالياً.",
            reply_markup=get_main_menu_keyboard(is_admin)
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

@router.callback_query(F.data.startswith("disabled_app_"))
async def handle_disabled_app(callback: types.CallbackQuery):
    """معالج للتطبيقات المعطلة"""
    app_id = int(callback.data.split("_")[2])
    
    await callback.answer(
        "❌ هذا التطبيق متوقف حالياً، يرجى المحاولة لاحقاً",
        show_alert=True
    )

@router.callback_query(F.data.startswith("cat_"))
async def show_apps_by_category(callback: types.CallbackQuery, db_pool):
    """عرض التطبيقات في قسم معين - مع تمييز التطبيقات المعطلة"""
    cat_id = int(callback.data.split("_")[1])
    
    async with db_pool.acquire() as conn:
        # جلب جميع التطبيقات في القسم (سواء مفعلة أو معطلة)
        apps = await conn.fetch(
            "SELECT * FROM applications WHERE category_id = $1 ORDER BY is_active DESC, name",
            cat_id
        )
        category = await conn.fetchrow(
            "SELECT display_name FROM categories WHERE id = $1",
            cat_id
        )
        
        # جلب سعر الصرف الحالي
        current_rate = await get_exchange_rate(db_pool)
        
        # جلب مستوى VIP للمستخدم
        user_vip = await get_user_vip(db_pool, callback.from_user.id)
        discount = user_vip.get('discount_percent', 0)
        vip_level = user_vip.get('vip_level', 0)
        vip_icon = user_vip.get('icon', '⚪')
        vip_name = user_vip.get('name', 'عادي')
    
    if not apps:
        await callback.answer("لا توجد تطبيقات في هذا القسم حالياً", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    buttons = []
    
    for app in apps:
        is_active = app['is_active']
        
        # تحديد الأيقونة حسب حالة التطبيق ونوعه
        if not is_active:
            icon = "🔒"  # قفل للتطبيقات المعطلة
            callback_data = f"disabled_app_{app['id']}"
        else:
            # تعيين الأيقونة حسب نوع التطبيق للمفعلة
            if app['type'] == 'game':
                icon = "🎮"
            elif app['type'] == 'subscription':
                icon = "📅"
            else:
                icon = "📱"
            callback_data = f"buy_{app['id']}_{app['type']}"
        
        if is_active:
            # حساب السعر فقط للتطبيقات المفعلة
            unit_price = float(app['unit_price_usd']) if app['unit_price_usd'] is not None else 0.0
            profit_percentage = float(app.get('profit_percentage', 0) or 0)
            min_units = int(app.get('min_units', 1) or 1)
            
            final_price_usd = unit_price * (1 + (profit_percentage / 100))
            discounted_price_usd = final_price_usd * (1 - discount/100)
            price_syp = discounted_price_usd * current_rate
            
            # عرض السعر مع إشارة الخصم
            if discount > 0:
                if app['type'] == 'game' and min_units > 1:
                    button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س (أقل كمية {min_units}) (خصم {discount}%)"
                else:
                    button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س (خصم {discount}%)"
            else:
                if app['type'] == 'game' and min_units > 1:
                    button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س (أقل كمية {min_units})"
                else:
                    button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س"
        else:
            # للتطبيقات المعطلة - عرض رسالة التوقف فقط
            button_text = f"{icon} {app['name']} (متوقف)"
        
        buttons.append(types.InlineKeyboardButton(
            text=button_text, 
            callback_data=callback_data
        ))
    
    # ترتيب الأزرار (2 في كل صف)
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            builder.row(buttons[i], buttons[i + 1])
        else:
            builder.row(buttons[i])
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للأقسام", 
        callback_data="back_to_categories"
    ))
    
    # إظهار مستوى المستخدم بالأيقونة والاسم الصحيحين
    await callback.message.edit_text(
        f"📱 **{category['display_name']}**\n\n"
        f"👤 مستواك: {vip_icon} {vip_name} (خصم {discount}%)\n"
        f"💰 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n"
        f"🔒 التطبيقات المقفلة متوقفة حالياً\n\n"
        "🔸 اختر التطبيق المطلوب:", 
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: types.CallbackQuery, db_pool):
    """العودة إلى الأقسام"""
    categories = await get_cached_categories(db_pool)
    
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

# ============= بدء الطلب =============

# ============= بدء الطلب =============

@router.callback_query(F.data.startswith("buy_"))
async def start_order(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء طلب شراء مع تطبيق الخصم - عرض جميع الخيارات مع تمييز المعطل"""
    parts = callback.data.split("_")
    app_id = int(parts[1])
    app_type = parts[2] if len(parts) > 2 else 'service'
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)
        
        if not app:
            await callback.answer("عذراً، هذا التطبيق غير متوفر حالياً.", show_alert=True)
            return
        
        # التحقق من حالة تفعيل التطبيق نفسه
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
    
    # تحويل القيم إلى float
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
    
    # جلب جميع الخيارات (المفعلة والمعطلة) من product_options
    async with db_pool.acquire() as conn:
        options = await conn.fetch(
            "SELECT * FROM product_options WHERE product_id = $1 ORDER BY is_active DESC, sort_order, price_usd",
            app_id
        )
    
    # إذا كان هناك خيارات، اعرضها كلها مع تمييز المعطل
    if options and len(options) > 0:
        builder = InlineKeyboardBuilder()
        
        for opt in options:
            is_active = opt['is_active']
            opt_price = float(opt['price_usd']) if opt['price_usd'] is not None else 0.0
            
            # تحديد الأيقونة حسب الحالة
            if is_active:
                # أيقونة مناسبة حسب نوع التطبيق للمفعلة
                if app_type == 'game':
                    icon = "🎮"
                elif app_type == 'subscription':
                    icon = "📅"
                else:
                    icon = "📱"
                callback_data = f"var_{opt['id']}"
            else:
                icon = "🔒"  # قفل للخيارات المعطلة
                callback_data = f"disabled_option_{opt['id']}"
            
            # حساب السعر فقط للخيارات المفعلة
            if is_active:
                price_with_profit = opt_price * (1 + (app_dict['profit_percentage'] / 100))
                discounted_price_usd = price_with_profit * (1 - discount/100)
                price_syp = discounted_price_usd * current_rate
                
                if discount > 0:
                    button_text = f"{icon} {opt['name']}\n{price_syp:,.0f} ل.س (خصم {discount}%)"
                else:
                    button_text = f"{icon} {opt['name']}\n{price_syp:,.0f} ل.س"
            else:
                # للخيارات المعطلة - عرض رسالة التوقف فقط
                button_text = f"{icon} {opt['name']} (متوقف)"
            
            builder.row(types.InlineKeyboardButton(
                text=button_text,
                callback_data=callback_data
            ))
        
        # ✅ زر الرجوع الصحيح - يرجع للقسم وليس إلغاء
        builder.row(types.InlineKeyboardButton(
            text="🔙 رجوع للقسم",
            callback_data=f"cat_{app_dict['category_id']}"  # يرجع للقسم
        ))
        
        # رسالة مناسبة حسب نوع التطبيق
        type_name = "لعبة" if app_type == 'game' else "اشتراك" if app_type == 'subscription' else "خدمة"
        
        # حساب عدد الخيارات المتاحة
        active_count = sum(1 for opt in options if opt['is_active'])
        disabled_count = len(options) - active_count
        
        status_message = ""
        if disabled_count > 0:
            status_message = f"\n🔒 هناك {disabled_count} خيارات متوقفة مؤقتاً"
        
        await callback.message.edit_text(
            f"**{app_dict['name']}**\n\n"
            f"📱 **النوع:** {type_name}\n"
            f"👑 **مستواك:** VIP {vip_level} (خصم {discount}%)\n"
            f"💰 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n"
            f"{status_message}\n\n"
            "🔸 **اختر الخيار المناسب:**\n"
            "🔒 الخيارات المقفلة متوقفة مؤقتاً",
            reply_markup=builder.as_markup()
        )
        await state.set_state(OrderStates.choosing_variant)
    
    else:
        # إذا لم توجد خيارات، استخدم الطريقة القديمة (إدخال الكمية يدوياً)
        profit_percentage = app_dict['profit_percentage']
        final_unit_price_usd = app_dict['unit_price_usd'] * (1 + (profit_percentage / 100))
        discounted_unit_price_usd = final_unit_price_usd * (1 - discount/100)
        price_per_unit_syp = discounted_unit_price_usd * current_rate
        
        await state.update_data({
            'final_unit_price_usd': final_unit_price_usd,
            'discounted_unit_price_usd': discounted_unit_price_usd,
            'profit_percentage': profit_percentage
        })
        
        if discount > 0:
            original_price = final_unit_price_usd * current_rate
            price_text = f"💰 **سعر الوحدة:** {price_per_unit_syp:,.0f} ل.س (بدلاً من {original_price:,.0f} ل.س)\n"
            price_text += f"🎁 **خصم VIP {vip_level}:** {discount}%"
        else:
            price_text = f"💰 **سعر الوحدة:** {price_per_unit_syp:,.0f} ل.س"
        
        await state.set_state(OrderStates.qty)
        
        # ✅ زر الرجوع الصحيح - يرجع للقسم
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(
            text="🔙 رجوع للقسم",
            callback_data=f"cat_{app_dict['category_id']}"  # يرجع للقسم
        ))
        
        await callback.message.edit_text(
            f"🏷 **الخدمة:** {app_dict['name']}\n"
            f"📦 **أقل كمية:** {app_dict['min_units']}\n"
            f"{price_text}\n\n"
            f"**الرجاء إدخال الكمية المطلوبة:**",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith("disabled_option_"))
async def handle_disabled_option(callback: types.CallbackQuery):
    """معالج للخيارات المعطلة"""
    option_id = int(callback.data.split("_")[2])
    
    await callback.answer(
        "🔒 هذا الخيار متوقف حالياً، يرجى المحاولة لاحقاً أو اختيار خيار آخر",
        show_alert=True
    )

# ============= استلام الكمية =============

@router.message(OrderStates.qty)
async def get_qty(message: types.Message, state: FSMContext, db_pool):
    """استقبال الكمية مع تطبيق الخصم"""
    logger.info(f"📩 استقبال كمية من {message.from_user.id}: {message.text}")
    
    if message.text in ["🔙 رجوع للقائمة", "/cancel", "/رجوع", "🏠 القائمة الرئيسية", "❌ إلغاء"]:
        await state.clear()
        is_admin = await is_admin_user(db_pool, message.from_user.id)
        await message.answer(
            "✅ تم إلغاء الطلب",
            reply_markup=get_main_menu_keyboard(is_admin)
        )
        return

    if not message.text.isdigit():
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(
            text="🔙 رجوع",
            callback_data="cancel_order"
        ))
        await message.answer(
            "⚠️ يرجى إدخال رقم صحيح (كمية).",
            reply_markup=builder.as_markup()
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
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(
            text="🔙 رجوع",
            callback_data="cancel_order"
        ))
        await message.answer(
            f"⚠️ أقل كمية مسموح بها هي {min_units}.",
            reply_markup=builder.as_markup()
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
        
        if not user:
            is_admin = await is_admin_user(db_pool, message.from_user.id)
            await message.answer(
                "❌ حسابك غير موجود في النظام.",
                reply_markup=get_main_menu_keyboard(is_admin)
            )
            await state.clear()
            return
        
        if user['balance'] < total_syp:
            remaining = total_syp - user['balance']
            builder = InlineKeyboardBuilder()
            builder.row(types.InlineKeyboardButton(
                text="🔙 رجوع",
                callback_data="cancel_order"
            ))
            await message.answer(
                f"⚠️ **رصيدك غير كافي**\n\n"
                f"💰 الرصيد الحالي: {user['balance']:,.0f} ل.س\n"
                f"💳 المبلغ المطلوب: {total_syp:,.0f} ل.س\n"
                f"🔸 المبلغ المتبقي: {remaining:,.0f} ل.س\n\n"
                f"قم بشحن رصيدك من خلال قسم الإيداع",
                reply_markup=builder.as_markup()
            )
            return
    
    if discount > 0:
        saved_amount = original_total_syp - total_syp
        price_message = (
            f"💰 **المبلغ قبل الخصم:** {original_total_syp:,.0f} ل.س\n"
            f"💰 **المبلغ بعد الخصم:** {total_syp:,.0f} ل.س\n"
            f"🎁 **وفرت:** {saved_amount:,.0f} ل.س (خصم VIP {vip_level}: {discount}%)"
        )
    else:
        price_message = f"💰 **المبلغ الإجمالي:** {total_syp:,.0f} ل.س"
    
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
    
    # استخدام builder للرجوع
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="cancel_order"
    ))
    
    await message.answer(
        f"✅ **تم قبول الكمية**\n\n"
        f"{price_message}\n\n"
        f"{instructions}",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    await state.set_state(OrderStates.target_id)
    logger.info(f"✅ تم تغيير الحالة إلى target_id للمستخدم {message.from_user.id}")

@router.message(OrderStates.choosing_variant)
async def handle_choosing_variant(message: types.Message, state: FSMContext):
    """معالج إذا كان المستخدم في حالة اختيار الفئة وأرسل رسالة نصية"""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="cancel_order"
    ))
    
    await message.answer(
        "⚠️ الرجاء اختيار الفئة من الأزرار أعلاه",
        reply_markup=builder.as_markup()
    )

@router.message(OrderStates.confirm)
async def handle_confirm_state(message: types.Message, state: FSMContext):
    """معالج إذا كان المستخدم في حالة التأكيد وأرسل رسالة نصية"""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="cancel_order"
    ))
    
    await message.answer(
        "⚠️ الرجاء استخدام الأزرار لتأكيد الطلب أو إلغائه",
        reply_markup=builder.as_markup()
    )

# ============= اختيار الفئة =============

# ============= اختيار الفئة =============

@router.callback_query(F.data.startswith("var_"))
async def choose_variant(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """اختيار خيار (لجميع أنواع المنتجات) مع عرض الوصف"""
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
    app_id = app['id']  # معرف التطبيق
    
    app_profit = float(app.get('profit_percentage', 0) or 0)
    opt_price = float(option['price_usd']) if option['price_usd'] is not None else 0.0
    
    price_with_profit = opt_price * (1 + (app_profit / 100))
    discounted_price_usd = price_with_profit * (1 - discount/100)
    total_syp = discounted_price_usd * current_rate
    
    original_price_usd = price_with_profit
    original_total_syp = original_price_usd * current_rate
    
    quantity = int(option.get('quantity', 1) or 1)
    
    await state.update_data({
        'variant': dict(option),
        'final_price_usd': discounted_price_usd,
        'total_syp': total_syp,
        'original_total_syp': original_total_syp,
        'qty': quantity
    })
    
    # تحديد نوع المنتج للعرض
    type_icon = "🎮" if app_type == 'game' else "📅" if app_type == 'subscription' else "📱"
    
    details = f"{type_icon} **{app['name']}**\n\n"
    details += f"📦 **الخيار:** {option['name']}\n"
    details += f"🔢 **الكمية:** {quantity}\n"
    
    # إضافة الوصف هنا
    if option.get('description'):
        details += f"📝 **الوصف:**\n{option['description']}\n\n"
    
    if discount > 0:
        saved = original_total_syp - total_syp
        details += f"💰 **السعر:** {total_syp:,.0f} ل.س (بدلاً من {original_total_syp:,.0f} ل.س)\n"
        details += f"🎁 **خصم VIP {vip_level}:** {discount}% (وفرت {saved:,.0f} ل.س)\n\n"
    else:
        details += f"💰 **السعر:** {total_syp:,.0f} ل.س\n\n"
    
    # تعليمات مناسبة حسب نوع التطبيق
    app_name = app['name'].lower()
    if 'pubg' in app_name or 'free fire' in app_name:
        instructions = "🎮 **يرجى إرسال ID اللاعب الخاص بك:**"
    elif 'clash' in app_name:
        instructions = "📧 **يرجى إرسال إيميل Supercell ID الخاص بك:**"
    elif 'instagram' in app_name or 'tiktok' in app_name:
        instructions = "📸 **يرجى إرسال اسم المستخدم:**"
    else:
        instructions = "🎯 **يرجى إرسال الحساب المستهدف:**"
    
    # ✅ زر الرجوع للخيارات السابقة
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للخيارات",
        callback_data=f"back_to_options_{app_id}_{app_type}"  # يرجع للخيارات
    ))
    
    await callback.message.edit_text(
        f"{details}{instructions}",
        reply_markup=builder.as_markup()
    )
    await state.set_state(OrderStates.target_id)

@router.callback_query(F.data.startswith("back_to_options_"))
async def back_to_options(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """الرجوع إلى شاشة اختيار الخيارات"""
    await callback.answer()
    
    parts = callback.data.split("_")
    app_id = int(parts[3])
    app_type = parts[4]
    
    # إعادة عرض خيارات التطبيق
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)
        options = await conn.fetch(
            "SELECT * FROM product_options WHERE product_id = $1 ORDER BY is_active DESC, sort_order, price_usd",
            app_id
        )
        
        current_rate = await get_exchange_rate(db_pool)
        user_vip = await get_user_vip(db_pool, callback.from_user.id)
        discount = user_vip.get('discount_percent', 0)
        vip_level = user_vip.get('vip_level', 0)
    
    if not app:
        await callback.answer("التطبيق غير موجود", show_alert=True)
        return
    
    app_dict = dict(app)
    app_dict['unit_price_usd'] = float(app_dict['unit_price_usd']) if app_dict['unit_price_usd'] is not None else 0.0
    app_dict['profit_percentage'] = float(app_dict.get('profit_percentage', 0) or 0)
    
    # تحديث الـ state
    await state.update_data({
        'app': app_dict,
        'app_type': app_type,
        'current_rate': current_rate,
        'discount': discount,
        'vip_level': vip_level
    })
    
    # بناء كيبورد الخيارات
    builder = InlineKeyboardBuilder()
    
    for opt in options:
        is_active = opt['is_active']
        opt_price = float(opt['price_usd']) if opt['price_usd'] is not None else 0.0
        
        if is_active:
            if app_type == 'game':
                icon = "🎮"
            elif app_type == 'subscription':
                icon = "📅"
            else:
                icon = "📱"
            callback_data = f"var_{opt['id']}"
        else:
            icon = "🔒"
            callback_data = f"disabled_option_{opt['id']}"
        
        if is_active:
            price_with_profit = opt_price * (1 + (app_dict['profit_percentage'] / 100))
            discounted_price_usd = price_with_profit * (1 - discount/100)
            price_syp = discounted_price_usd * current_rate
            
            if discount > 0:
                button_text = f"{icon} {opt['name']}\n{price_syp:,.0f} ل.س (خصم {discount}%)"
            else:
                button_text = f"{icon} {opt['name']}\n{price_syp:,.0f} ل.س"
        else:
            button_text = f"{icon} {opt['name']} (متوقف)"
        
        builder.row(types.InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للقسم",
        callback_data=f"cat_{app_dict['category_id']}"
    ))
    
    type_name = "لعبة" if app_type == 'game' else "اشتراك" if app_type == 'subscription' else "خدمة"
    active_count = sum(1 for opt in options if opt['is_active'])
    disabled_count = len(options) - active_count
    status_message = f"\n🔒 هناك {disabled_count} خيارات متوقفة مؤقتاً" if disabled_count > 0 else ""
    
    await callback.message.edit_text(
        f"**{app_dict['name']}**\n\n"
        f"📱 **النوع:** {type_name}\n"
        f"👑 **مستواك:** VIP {vip_level} (خصم {discount}%)\n"
        f"💰 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n"
        f"{status_message}\n\n"
        "🔸 **اختر الخيار المناسب:**\n"
        "🔒 الخيارات المقفلة متوقفة مؤقتاً",
        reply_markup=builder.as_markup()
    )
    await state.set_state(OrderStates.choosing_variant)

# ============= استلام الهدف والتأكيد =============

@router.message(OrderStates.target_id)
async def confirm_order(message: types.Message, state: FSMContext, db_pool):
    """استقبال ID الهدف وتأكيد الطلب"""
    logger.info(f"📩 استقبال target_id من {message.from_user.id}: {message.text}")
    
    if message.text in ["🔙 رجوع للقائمة", "/cancel", "/رجوع", "🏠 القائمة الرئيسية", "❌ إلغاء"]:
        await state.clear()
        is_admin = await is_admin_user(db_pool, message.from_user.id)
        await message.answer(
            "✅ تم إلغاء الطلب",
            reply_markup=get_main_menu_keyboard(is_admin)
        )
        return
    
    target_id = message.text.strip()
    if not target_id:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(
            text="🔙 رجوع",
            callback_data="cancel_order"
        ))
        await message.answer(
            "⚠️ يرجى إدخال ID الحساب.",
            reply_markup=builder.as_markup()
        )
        return
    
    data = await state.get_data()
    if not data or 'app' not in data:
        await message.answer("❌ انتهت صلاحية الطلب، يرجى البدء من جديد")
        await state.clear()
        return
    
    discount = data.get('discount', 0)
    vip_level = data.get('vip_level', 0)
    total_syp = data.get('total_syp', 0)
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT balance FROM users WHERE user_id = $1",
            message.from_user.id
        )
        
        if not user or user['balance'] < total_syp:
            await state.clear()
            is_admin = await is_admin_user(db_pool, message.from_user.id)
            await message.answer(
                "❌ رصيدك غير كافي. تم إلغاء الطلب.",
                reply_markup=get_main_menu_keyboard(is_admin)
            )
            return
    
    await state.update_data(target_id=target_id)
    
    # حساب السعر الأصلي قبل الخصم
    if 'variant' in data:
        app = data['app']
        variant = data['variant']
        app_profit = float(app.get('profit_percentage', 0) or 0) / 100
        opt_price = float(variant.get('price_usd', 0))
        original_price_usd = opt_price * (1 + app_profit)
        original_total_syp = original_price_usd * data.get('current_rate', 118)
    else:
        final_unit_price_usd = data.get('final_unit_price_usd', 0)
        qty = data.get('qty', 1)
        original_total_syp = final_unit_price_usd * qty * data.get('current_rate', 118)
    
    await state.update_data(original_total_syp=original_total_syp)
    
    # أزرار إنلاين فقط - بدون كيبورد سفلي
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ تأكيد ودفع", callback_data="execute_buy"),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_order")
    )
    
    if discount > 0:
        saved_amount = original_total_syp - total_syp
        if saved_amount > 0:
            price_detail = (
                f"💰 **السعر قبل الخصم:** {original_total_syp:,.0f} ل.س\n"
                f"💰 **السعر بعد الخصم:** {total_syp:,.0f} ل.س\n"
                f"🎁 **وفرت:** {saved_amount:,.0f} ل.س (خصم VIP {vip_level}: {discount}%)"
            )
        else:
            price_detail = f"💰 **السعر الإجمالي:** {total_syp:,.0f} ل.س"
    else:
        price_detail = f"💰 **السعر الإجمالي:** {total_syp:,.0f} ل.س"
    
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
    
    # إرسال رسالة التأكيد بدون كيبورد سفلي
    await message.answer(
        msg,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.confirm)
    logger.info(f"✅ تم تغيير الحالة إلى confirm للمستخدم {message.from_user.id}")

# ============= تنفيذ الطلب =============

@router.callback_query(F.data == "execute_buy")
async def execute_order(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    """تنفيذ الطلب (لجميع الأنواع) مع تطبيق الخصم"""
    data = await state.get_data()
    
    if not data:
        await callback.answer("انتهت صلاحية الطلب، يرجى المحاولة مرة أخرى", show_alert=True)
        await state.clear()
        return
    
    points = await get_points_per_order(db_pool)
    discount = data.get('discount', 0)
    vip_level = data.get('vip_level', 0)
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
                # للتوافق مع الخدمات القديمة
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
    
    # إضافة أزرار إنلاين للعودة للقائمة الرئيسية
    is_admin = await is_admin_user(db_pool, callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🏠 القائمة الرئيسية",
        callback_data="back_to_main"
    ))
    
    await callback.message.answer(
        "👋 يمكنك العودة للقائمة الرئيسية من هنا:",
        reply_markup=builder.as_markup()
    )
    
    await state.clear()

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """إلغاء الطلب"""
    await state.clear()
    
    # إرسال رسالة إلغاء مع القائمة الرئيسية
    is_admin = await is_admin_user(db_pool, callback.from_user.id)
    await callback.message.edit_text("❌ **تم إلغاء الطلب.**")
    
    # إضافة أزرار إنلاين للعودة للقائمة الرئيسية
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🏠 القائمة الرئيسية",
        callback_data="back_to_main"
    ))
    
    await callback.message.answer(
        "👋 تم العودة للقائمة الرئيسية",
        reply_markup=builder.as_markup()
    )
