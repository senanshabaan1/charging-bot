# handlers/keyboards.py
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ============= دوال الكيبورد الإنلاين فقط (Inline Keyboard) =============

def get_main_menu_keyboard(is_admin_user: bool = False):
    """القائمة الرئيسية - إنلاين (تظهر تحت الرسالة)"""
    builder = InlineKeyboardBuilder()
    
    # الأزرار الرئيسية - 2 في كل صف
    builder.row(
        types.InlineKeyboardButton(text="🛒 خدمات الشحن", callback_data="services"),
        types.InlineKeyboardButton(text="💰 شحن المحفظة", callback_data="deposit"),
        width=2
    )
    
    builder.row(
        types.InlineKeyboardButton(text="👤 حسابي", callback_data="profile"),
        types.InlineKeyboardButton(text="❓ مساعدة", callback_data="help"),
        width=2
    )
    
    if is_admin_user:
        builder.row(
            types.InlineKeyboardButton(text="⚙️ لوحة التحكم", callback_data="admin_panel"),
            width=1
        )
    
    return builder.as_markup()

def get_categories_keyboard(categories):
    """عرض الأقسام - إنلاين (2 في كل صف)"""
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
    """عرض التطبيقات في قسم معين - إنلاين (كل تطبيق بصف)"""
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
            
            min_units = int(app.get('min_units', 1) or 1)
            
            if min_units > 1:
                button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س (أقل كمية {min_units})"
            else:
                button_text = f"{icon} {app['name']}\n{price_syp:,.0f} ل.س"
            
            if vip_discount > 0:
                button_text += f" 🔹 خصم {vip_discount}%"
        else:
            icon = "🔒"
            callback_data = f"disabled_app_{app['id']}"
            button_text = f"{icon} {app['name']}\n(متوقف مؤقتاً)"
        
        builder.row(types.InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        ))
    
    # أزرار التنقل - صف واحد
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع للأقسام", callback_data="back_to_categories"),
        types.InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="back_to_main"),
        width=2
    )
    
    return builder.as_markup()

def get_options_keyboard(options, app_name, current_rate, vip_discount=0, app_type='game'):
    """عرض خيارات التطبيق (فئات) - إنلاين (كل خيار بصف)"""
    builder = InlineKeyboardBuilder()
    
    for opt in options:
        is_active = opt['is_active']
        
        if is_active:
            icon = "🎮" if app_type == 'game' else "📅" if app_type == 'subscription' else "📱"
            callback_data = f"var_{opt['id']}"
            
            opt_price = float(opt['price_usd']) if opt['price_usd'] else 0
            discounted_price_usd = opt_price * (1 - vip_discount/100)
            price_syp = discounted_price_usd * current_rate
            quantity = int(opt.get('quantity', 1) or 1)
            
            if quantity > 1:
                button_text = f"{icon} {opt['name']}\n{price_syp:,.0f} ل.س ({quantity} وحدة)"
            else:
                button_text = f"{icon} {opt['name']}\n{price_syp:,.0f} ل.س"
            
            if vip_discount > 0:
                button_text += f" 🔹 خصم {vip_discount}%"
        else:
            icon = "🔒"
            callback_data = f"disabled_option_{opt['id']}"
            button_text = f"{icon} {opt['name']}\n(متوقف مؤقتاً)"
        
        builder.row(types.InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        ))
    
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
        types.InlineKeyboardButton(text="✅ تأكيد ودفع", callback_data=callback_yes),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data=callback_no),
        width=2
    )
    return builder.as_markup()

def get_yes_no_keyboard(yes_data: str = "yes", no_data: str = "no"):
    """أزرار نعم/لا"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم", callback_data=yes_data),
        types.InlineKeyboardButton(text="❌ لا", callback_data=no_data),
        width=2
    )
    return builder.as_markup()

def get_points_keyboard():
    """كيبورد إنلاين خاص بنظام النقاط"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📋 سجل النقاط", callback_data="points_history"),
        types.InlineKeyboardButton(text="🎁 استرداد نقاط", callback_data="redeem_points"),
        width=2
    )
    builder.row(
        types.InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="referral_link"),
        width=1
    )
    return builder.as_markup()

def get_deposit_keyboard():
    """كيبورد إنلاين لشحن المحفظة"""
    builder = InlineKeyboardBuilder()
    
    # مبالغ مقترحة للشحن
    amounts = [1000, 2500, 5000, 10000, 25000, 50000]
    
    # عرض المبالغ 2 في كل صف
    for i in range(0, len(amounts), 2):
        row = []
        for amount in amounts[i:i+2]:
            row.append(types.InlineKeyboardButton(
                text=f"{amount:,.0f} ل.س",
                callback_data=f"deposit_{amount}"
            ))
        builder.row(*row)
    
    builder.row(
        types.InlineKeyboardButton(text="💰 مبلغ آخر", callback_data="deposit_custom"),
        width=1
    )
    
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع للقائمة الرئيسية", callback_data="back_to_main"),
        width=1
    )
    
    return builder.as_markup()

def get_profile_keyboard():
    """كيبورد إنلاين للحساب الشخصي"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="💰 رصيدي", callback_data="balance"),
        types.InlineKeyboardButton(text="⭐ نقاطي", callback_data="my_points"),
        width=2
    )
    builder.row(
        types.InlineKeyboardButton(text="📋 طلباتي", callback_data="my_orders"),
        types.InlineKeyboardButton(text="🎁 كوبوناتي", callback_data="my_coupons"),
        width=2
    )
    builder.row(
        types.InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="referral_link"),
        width=1
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع للقائمة الرئيسية", callback_data="back_to_main"),
        width=1
    )
    return builder.as_markup()

def get_admin_main_keyboard():
    """لوحة تحكم الإدارة - إنلاين (3 أزرار في كل صف)"""
    builder = InlineKeyboardBuilder()
    
    # أزرار الإدارة - 3 في كل صف
    admin_buttons = [
        ("📈 سعر الصرف", "edit_rate"),
        ("📊 الإحصائيات", "bot_stats"),
        ("📢 رسالة للكل", "broadcast"),
        ("👤 معلومات مستخدم", "user_info"),
        ("⭐ إدارة النقاط", "manage_points"),
        ("💳 الأكثر إيداعاً", "top_deposits"),
        ("🛒 الأكثر طلبات", "top_orders"),
        ("🔗 الأكثر إحالة", "top_referrals"),
        ("⭐ الأكثر نقاط", "top_points"),
        ("👥 إحصائيات VIP", "vip_stats"),
        ("📊 تقارير ونسخ", "reports_menu"),
        ("➕ إضافة منتج", "add_product"),
        ("✏️ تعديل منتج", "edit_product"),
        ("🗑️ حذف منتج", "delete_product"),
        ("📱 عرض المنتجات", "list_products"),
        ("📞 أرقام سيرياتل", "edit_syriatel"),
        ("🔄 تشغيل/إيقاف", "toggle_bot"),
        ("⚠️ تصفير البوت", "reset_bot"),
        ("👑 إدارة المشرفين", "manage_admins"),
        ("✏️ رسالة الصيانة", "edit_maintenance"),
        ("✉️ رسالة لمستخدم", "send_custom_message"),
        ("🔄 تفعيل/إيقاف التطبيقات", "manage_apps_status"),
        ("🎮 إدارة خيارات الألعاب", "manage_options"),
        ("📁 إدارة الأقسام", "manage_categories"),
        ("➕ إضافة قسم", "add_category"),
    ]
    
    for text, callback in admin_buttons:
        builder.add(types.InlineKeyboardButton(text=text, callback_data=callback))
    
    # توزيع 3 أزرار في كل صف
    builder.adjust(3)
    
    return builder.as_markup()
