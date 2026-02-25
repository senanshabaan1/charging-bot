# handlers/keyboards.py
from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# ============= دوال الكيبورد العادية (Reply Keyboard) =============

def get_main_menu_keyboard(is_admin_user: bool = False):
    """القائمة الرئيسية للمستخدمين مع أزرار تفعيلية دائمة"""
    builder = ReplyKeyboardBuilder()
    
    # الصف الأول: الخدمات الرئيسية
    builder.row(types.KeyboardButton(text="📱 خدمات الشحن"))
    
    # الصف الثاني: المحفظة والحساب
    builder.row(
        types.KeyboardButton(text="💰 شحن المحفظة"), 
        types.KeyboardButton(text="👤 حسابي")
    )
    
    # الصف الثالث: أزرار تفعيلية دائمة
    builder.row(
        types.KeyboardButton(text="📢 القناة"),
        types.KeyboardButton(text="📞 الدعم")
    )
    
    # الصف الرابع: موقع الويب (اختياري)
    builder.row(types.KeyboardButton(text="🌐 الموقع الإلكتروني"))
    
    # لوحة التحكم للمشرفين
    if is_admin_user:
        builder.row(types.KeyboardButton(text="🛠 لوحة التحكم"))
    
    # زر المساعدة في النهاية
    builder.row(types.KeyboardButton(text="❓ مساعدة"))
    
    return builder.as_markup(resize_keyboard=True)

def get_back_keyboard():
    """زر رجوع + أزرار تفعيلية"""
    builder = ReplyKeyboardBuilder()
    
    # الصف الأول: رجوع
    builder.row(types.KeyboardButton(text="🔙 رجوع للقائمة"))
    
    # الصف الثاني: أزرار تفعيلية
    builder.row(
        types.KeyboardButton(text="📢 القناة"),
        types.KeyboardButton(text="📞 الدعم")
    )
    
    return builder.as_markup(resize_keyboard=True)

def get_cancel_keyboard():
    """زر إلغاء + أزرار تفعيلية"""
    builder = ReplyKeyboardBuilder()
    
    # الصف الأول: إلغاء
    builder.row(types.KeyboardButton(text="❌ إلغاء"))
    
    # الصف الثاني: أزرار تفعيلية
    builder.row(
        types.KeyboardButton(text="📢 القناة"),
        types.KeyboardButton(text="📞 الدعم")
    )
    
    return builder.as_markup(resize_keyboard=True)

def get_deposit_keyboard():
    """كيبورد خاص بالإيداع مع أزرار تفعيلية"""
    builder = ReplyKeyboardBuilder()
    
    # طرق الدفع
    builder.row(
        types.KeyboardButton(text="💳 سيرياتل كاش"),
        types.KeyboardButton(text="💳 بطاقة مصرفية")
    )
    
    # أزرار تفعيلية
    builder.row(
        types.KeyboardButton(text="📢 القناة"),
        types.KeyboardButton(text="📞 الدعم")
    )
    
    # رجوع
    builder.row(types.KeyboardButton(text="🔙 رجوع للقائمة"))
    
    return builder.as_markup(resize_keyboard=True)

def get_main_menu_only_keyboard():
    """العودة للقائمة الرئيسية فقط + أزرار تفعيلية"""
    builder = ReplyKeyboardBuilder()
    
    builder.row(types.KeyboardButton(text="🏠 القائمة الرئيسية"))
    builder.row(
        types.KeyboardButton(text="📢 القناة"),
        types.KeyboardButton(text="📞 الدعم")
    )
    
    return builder.as_markup(resize_keyboard=True)

def get_back_and_cancel_keyboard():
    """أزرار رجوع وإلغاء معاً + أزرار تفعيلية"""
    builder = ReplyKeyboardBuilder()
    
    builder.row(
        types.KeyboardButton(text="🔙 رجوع للقائمة"),
        types.KeyboardButton(text="❌ إلغاء")
    )
    builder.row(
        types.KeyboardButton(text="📢 القناة"),
        types.KeyboardButton(text="📞 الدعم")
    )
    
    return builder.as_markup(resize_keyboard=True)

# ============= دوال الكيبورد الإنلاين (Inline Keyboard) =============

def get_back_inline_keyboard(callback_data: str = "back_to_main"):
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

def get_profile_keyboard():
    """كيبورد إنلاين للملف الشخصي"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📋 سجل النقاط", callback_data="points_history"),
        types.InlineKeyboardButton(text="🎁 استرداد نقاط", callback_data="redeem_points")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="referral_link"),
        types.InlineKeyboardButton(text="📊 إحصائياتي", callback_data="my_stats")
    )
    builder.row(
        types.InlineKeyboardButton(text="📋 آخر 5 طلبات", callback_data="recent_orders")
    )
    return builder.as_markup()

# ============= أزرار تفعيلية إنلاين (اختياري) =============

def get_action_buttons_inline():
    """أزرار تفعيلية بشكل إنلاين (تظهر تحت أي رسالة)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📢 القناة", url="https://t.me/LINKcharger22"),
        types.InlineKeyboardButton(text="📞 الدعم", url="https://t.me/support")
    )
    builder.row(
        types.InlineKeyboardButton(text="🌐 الموقع", url="https://charging-bot-worker.onrender.com")
    )
    return builder.as_markup()

# ============= دوال مساعدة =============

async def send_message_with_back_keyboard(bot, chat_id: int, text: str, parse_mode: str = None):
    """إرسال رسالة مع كيبورد رجوع + أزرار تفعيلية"""
    await bot.send_message(
        chat_id,
        text,
        reply_markup=get_back_keyboard(),
        parse_mode=parse_mode
    )

async def send_message_with_cancel_keyboard(bot, chat_id: int, text: str, parse_mode: str = None):
    """إرسال رسالة مع كيبورد إلغاء + أزرار تفعيلية"""
    await bot.send_message(
        chat_id,
        text,
        reply_markup=get_cancel_keyboard(),
        parse_mode=parse_mode
    )

async def send_message_with_main_menu_keyboard(bot, chat_id: int, text: str, is_admin: bool = False, parse_mode: str = None):
    """إرسال رسالة مع القائمة الرئيسية + أزرار تفعيلية"""
    await bot.send_message(
        chat_id,
        text,
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode=parse_mode
    )
