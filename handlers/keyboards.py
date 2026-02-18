# في بداية start.py أو ملف keyboards.py جديد
from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

def get_main_menu_keyboard(is_admin_user=False):
    """إنشاء قائمة الأزرار الرئيسية"""
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

def get_back_keyboard():
    """إنشاء زر رجوع فقط"""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔙 رجوع للقائمة"))
    return builder.as_markup(resize_keyboard=True)