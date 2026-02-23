# handlers/keyboards.py
from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# ============= دوال الكيبورد العادية (Reply Keyboard) =============

def get_main_menu_keyboard(is_admin_user=False):
    """القائمة الرئيسية للمستخدمين"""
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
    """زر إلغاء موحد للمشرفين"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="❌ إلغاء"))
    return builder.as_markup(resize_keyboard=True)

def get_back_keyboard():
    """زر رجوع للقائمة الرئيسية (للمستخدمين العاديين)"""
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

def get_back_inline_keyboard(callback_data="back_to_main"):
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
        callback_data="back_to_admin_panel"
    ))
    return builder.as_markup()

def get_confirmation_keyboard(callback_yes="confirm", callback_no="cancel"):
    """أزرار تأكيد وإلغاء"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ تأكيد", callback_data=callback_yes),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data=callback_no)
    )
    return builder.as_markup()

def get_yes_no_keyboard(yes_data="yes", no_data="no"):
    """أزرار نعم/لا"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم", callback_data=yes_data),
        types.InlineKeyboardButton(text="❌ لا", callback_data=no_data)
    )
    return builder.as_markup()

# ============= دوال مساعدة =============

async def send_message_with_back_keyboard(bot, chat_id, text, parse_mode=None):
    """إرسال رسالة مع كيبورد رجوع"""
    await bot.send_message(
        chat_id,
        text,
        reply_markup=get_back_keyboard(),
        parse_mode=parse_mode
    )

async def send_message_with_cancel_keyboard(bot, chat_id, text, parse_mode=None):
    """إرسال رسالة مع كيبورد إلغاء (للمشرفين)"""
    await bot.send_message(
        chat_id,
        text,
        reply_markup=get_cancel_keyboard(),
        parse_mode=parse_mode
    )
