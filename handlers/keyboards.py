# handlers/keyboards.py
from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# ============= دوال الكيبورد العادية (Reply Keyboard) =============
# هذي للقوائم الرئيسية - تظهر في أسفل الشاشة

def get_main_menu_keyboard(is_admin_user: bool = False):
    """القائمة الرئيسية - أزرار سفلية كبيرة"""
    builder = ReplyKeyboardBuilder()
    
    # الأزرار الأساسية - كل واحد بصف لحالو عشان يكون كبير
    builder.row(types.KeyboardButton(text="🛒 خدمات الشحن"))
    builder.row(types.KeyboardButton(text="💰 شحن المحفظة"))
    builder.row(types.KeyboardButton(text="👤 حسابي"))
    
    if is_admin_user:
        builder.row(types.KeyboardButton(text="⚙️ لوحة التحكم"))
    
    builder.row(types.KeyboardButton(text="❓ مساعدة"))
    
    return builder.as_markup(resize_keyboard=True)

def get_cancel_keyboard():
    """زر إلغاء موحد - يظهر أثناء العمليات"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="❌ إلغاء"))
    return builder.as_markup(resize_keyboard=True)

def get_back_keyboard():
    """زر رجوع للقائمة السابقة"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔙 رجوع"))
    return builder.as_markup(resize_keyboard=True)

def get_main_menu_only_keyboard():
    """العودة للقائمة الرئيسية فقط"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🏠 القائمة الرئيسية"))
    return builder.as_markup(resize_keyboard=True)

def get_back_and_cancel_keyboard():
    """أزرار رجوع وإلغاء معاً"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="🔙 رجوع"),
        types.KeyboardButton(text="❌ إلغاء")
    )
    return builder.as_markup(resize_keyboard=True)


# ============= دوال الكيبورد الإنلاين (Inline Keyboard) =============
# هذي تظهر تحت الرسالة - مناسبة للقوائم الفرعية والخيارات الكثيرة

def get_categories_keyboard(categories):
    """عرض الأقسام - إنلاين (2-3 أزرار في كل صف)"""
    builder = InlineKeyboardBuilder()
    
    # عرض الأقسام 2 في كل صف
    for i in range(0, len(categories), 2):
        row = []
        for cat in categories[i:i+2]:
            row.append(types.InlineKeyboardButton(
                text=f"{cat['icon']} {cat['display_name']}",
                callback_data=f"cat_{cat['id']}"
            ))
        builder.row(*row)
    
    # زر الرجوع للقائمة الرئيسية
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للقائمة الرئيسية",
        callback_data="back_to_main"
    ))
    
    return builder.as_markup()

def get_apps_keyboard(apps, category_name, current_rate, vip_discount=0):
    """عرض التطبيقات في قسم معين - إنلاين"""
    builder = InlineKeyboardBuilder()
    
    for app in apps:
        is_active = app['is_active']
        
        if is_active:
            icon = "🎮" if app['type'] == 'game' else "📅" if app['type'] == 'subscription' else "📱"
            callback_data = f"buy_{app['id']}_{app['type']}"
            
            # حساب السعر
            unit_price = float(app['unit_price_usd']) if app['unit_price_usd'] else 0
            profit = float(app.get('profit_percentage', 0) or 0)
            final_price_usd = unit_price * (1 + profit/100)
            discounted_price_usd = final_price_usd * (1 - vip_discount/100)
            price_syp = discounted_price_usd * current_rate
            
            button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س"
            if vip_discount > 0:
                button_text += f" (خصم {vip_discount}%)"
        else:
            icon = "🔒"
            callback_data = f"disabled_app_{app['id']}"
            button_text = f"{icon} {app['name']} (متوقف)"
        
        builder.row(types.InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        ))
    
    # أزرار التنقل
    nav_buttons = []
    nav_buttons.append(types.InlineKeyboardButton(
        text="🔙 رجوع للأقسام",
        callback_data="back_to_categories"
    ))
    nav_buttons.append(types.InlineKeyboardButton(
        text="🏠 القائمة الرئيسية",
        callback_data="back_to_main"
    ))
    
    builder.row(*nav_buttons)
    
    return builder.as_markup()

def get_options_keyboard(options, app_name, current_rate, vip_discount=0, app_type='game'):
    """عرض خيارات التطبيق (فئات) - إنلاين"""
    builder = InlineKeyboardBuilder()
    
    for opt in options:
        is_active = opt['is_active']
        
        if is_active:
            icon = "🎮" if app_type == 'game' else "📅" if app_type == 'subscription' else "📱"
            callback_data = f"var_{opt['id']}"
            
            opt_price = float(opt['price_usd']) if opt['price_usd'] else 0
            discounted_price_usd = opt_price * (1 - vip_discount/100)
            price_syp = discounted_price_usd * current_rate
            
            button_text = f"{icon} {opt['name']}\n{price_syp:,.0f} ل.س"
            if vip_discount > 0:
                button_text += f" (خصم {vip_discount}%)"
        else:
            icon = "🔒"
            callback_data = f"disabled_option_{opt['id']}"
            button_text = f"{icon} {opt['name']} (متوقف)"
        
        builder.row(types.InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        ))
    
    # عرض وصف الخيار إذا موجود - كنص منفصل
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للتطبيقات",
        callback_data="back_to_apps"
    ))
    
    return builder.as_markup()

def get_back_inline_keyboard(callback_data: str = "back"):
    """زر رجوع إنلاين واحد"""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data=callback_data
    ))
    return builder.as_markup()

def get_back_to_admin_inline_keyboard():
    """زر رجوع للوحة التحكم"""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للوحة التحكم", 
        callback_data="back_to_admin"
    ))
    return builder.as_markup()

def get_confirmation_keyboard(callback_yes: str = "confirm", callback_no: str = "cancel"):
    """أزرار تأكيد وإلغاء"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ تأكيد", callback_data=callback_yes),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data=callback_no)
    )
    return builder.as_markup()

def get_yes_no_keyboard(yes_data: str = "yes", no_data: str = "no"):
    """أزرار نعم/لا"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم", callback_data=yes_data),
        types.InlineKeyboardButton(text="❌ لا", callback_data=no_data)
    )
    return builder.as_markup()

def get_points_keyboard():
    """كيبورد إنلاين خاص بنظام النقاط"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📋 سجل النقاط", callback_data="points_history"),
        types.InlineKeyboardButton(text="🎁 استرداد نقاط", callback_data="redeem_points")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="referral_link")
    )
    return builder.as_markup()


# ============= دوال مساعدة =============

async def send_message_with_back_keyboard(bot, chat_id: int, text: str, parse_mode: str = None):
    """إرسال رسالة مع كيبورد رجوع"""
    await bot.send_message(
        chat_id,
        text,
        reply_markup=get_back_keyboard(),
        parse_mode=parse_mode
    )

async def send_message_with_cancel_keyboard(bot, chat_id: int, text: str, parse_mode: str = None):
    """إرسال رسالة مع كيبورد إلغاء"""
    await bot.send_message(
        chat_id,
        text,
        reply_markup=get_cancel_keyboard(),
        parse_mode=parse_mode
    )

async def send_message_with_main_menu_keyboard(bot, chat_id: int, text: str, is_admin: bool = False, parse_mode: str = None):
    """إرسال رسالة مع القائمة الرئيسية"""
    await bot.send_message(
        chat_id,
        text,
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode=parse_mode
    )
