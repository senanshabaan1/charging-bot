# handlers/keyboards.py
from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# ============= دوال الكيبورد العادية (Reply Keyboard) =============

def get_main_menu_keyboard(is_admin_user: bool = False):
    """القائمة الرئيسية للمستخدمين مع زر المشرفين إذا كانوا مشرفين"""
    builder = ReplyKeyboardBuilder()
    
    builder.row(types.KeyboardButton(text="📱 خدمات الشحن"))
    builder.row(
        types.KeyboardButton(text="💰 شحن المحفظة"), 
        types.KeyboardButton(text="👤 حسابي")
    )
    
    if is_admin_user:
        builder.row(types.KeyboardButton(text="🛠 لوحة التحكم"))
    
    builder.row(types.KeyboardButton(text="❓ مساعدة"))
    
    return builder.as_markup(resize_keyboard=True)

def get_cancel_keyboard():
    """زر إلغاء موحد للمشرفين والمستخدمين"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="❌ إلغاء"))
    return builder.as_markup(resize_keyboard=True)

def get_back_keyboard():
    """زر رجوع للقائمة السابقة"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔙 رجوع للقائمة"))
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
        types.KeyboardButton(text="🔙 رجوع للقائمة"),
        types.KeyboardButton(text="❌ إلغاء")
    )
    return builder.as_markup(resize_keyboard=True)

def get_deposit_keyboard():
    """كيبورد خاص بالإيداع"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="💳 سيرياتل كاش"),
        types.KeyboardButton(text="💳 بطاقة مصرفية")
    )
    builder.row(types.KeyboardButton(text="🔙 رجوع للقائمة"))
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
        types.InlineKeyboardButton(text="📋 آخر 5 طلبات", callback_data="recent_orders"),
        types.InlineKeyboardButton(text="🏆 المتصدرين", callback_data="leaderboard_menu")
    )
    return builder.as_markup()

def get_vip_keyboard():
    """كيبورد إنلاين خاص بنظام VIP"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="👑 مستوى VIP الحالي", callback_data="vip_current"),
        types.InlineKeyboardButton(text="📊 تقدم VIP", callback_data="vip_progress")
    )
    builder.row(
        types.InlineKeyboardButton(text="🏆 المتصدرين", callback_data="leaderboard_menu")
    )
    return builder.as_markup()

def get_leaderboard_keyboard():
    """كيبورد إنلاين لقوائم المتصدرين"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="💰 الأكثر إيداعاً", callback_data="top_deposits_simple"),
        types.InlineKeyboardButton(text="🛒 الأكثر طلبات", callback_data="top_orders_simple")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔗 الأكثر إحالة", callback_data="top_referrals_simple"),
        types.InlineKeyboardButton(text="⭐ الأكثر نقاط", callback_data="top_points_simple")
    )
    builder.row(
        types.InlineKeyboardButton(text="👑 الأكثر إنفاق (VIP)", callback_data="top_spenders")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_profile")
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
