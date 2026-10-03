from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

def main_menu(is_admin: bool, currency: str):
    builder = InlineKeyboardBuilder()
    curr_text = "دولار ($)" if currency == 'USD' else "ليرة (ل.س)"
    
    builder.row(InlineKeyboardButton(text=f"العملة : {curr_text}", callback_data="change_currency"))
    builder.row(
        InlineKeyboardButton(text="منتجات المتجر 🛒", callback_data="shop"),
        InlineKeyboardButton(text="شحن رصيدي 💳", callback_data="deposit")
    )
    builder.row(InlineKeyboardButton(text="حسابي 👤", callback_data="profile"))
    
    if is_admin:
        builder.row(InlineKeyboardButton(text="🛠 لوحة التحكم", callback_data="admin_panel"))
        
    return builder.as_markup()

def currency_menu(current: str):
    builder = InlineKeyboardBuilder()
    usd = "دولار ($) ✅" if current == 'USD' else "دولار ($)"
    syp = "ليرة (ل.س) ✅" if current == 'SYP' else "ليرة (ل.س)"
    
    builder.row(InlineKeyboardButton(text=usd, callback_data="set_curr_USD"))
    builder.row(InlineKeyboardButton(text=syp, callback_data="set_curr_SYP"))
    builder.row(InlineKeyboardButton(text="الرئيسية 🏠", callback_data="main_menu"))
    return builder.as_markup()

def admin_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ إضافة موقع ربط (API)", callback_data="admin_add_provider"))
    builder.row(InlineKeyboardButton(text="➕ إضافة قسم", callback_data="admin_add_category"))
    builder.row(InlineKeyboardButton(text="➕ إضافة منتج", callback_data="admin_add_product"))
    builder.row(InlineKeyboardButton(text="💵 تعديل سعر الصرف", callback_data="admin_set_rate"))
    return builder.as_markup()