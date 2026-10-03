# handlers/keyboards.py
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ============= دوال الكيبورد الإنلاين (Inline Keyboard) =============

def get_main_menu_keyboard(is_admin_user: bool = False, currency: str = "USD"):
    """القائمة الرئيسية للمستخدمين - مطابقة للتصميم الجديد"""
    builder = InlineKeyboardBuilder()
    
    # تحديد نص زر العملة
    currency_text = "العملة : دولار ($)" if currency == "USD" else "العملة : ليرة (ل.س)"
    
    # الصف الأول (العملة)
    builder.row(
        types.InlineKeyboardButton(text=currency_text, callback_data="change_currency")
    )
    
    # الصف الثاني (المنتجات والشحن)
    builder.row(
        types.InlineKeyboardButton(text="منتجات المتجر 🛒", callback_data="show_categories"),
        types.InlineKeyboardButton(text="شحن رصيدي 💳", callback_data="show_deposit_methods")
    )
    
    # الصف الثالث (الطلبات والحساب)
    builder.row(
        types.InlineKeyboardButton(text="طلباتي 📦", callback_data="my_orders"),
        types.InlineKeyboardButton(text="حسابي 👤", callback_data="show_profile")
    )
    
    # الصف الرابع (نظام الخصومات)
    builder.row(
        types.InlineKeyboardButton(text="نظام الخصومات 💎", callback_data="vip_system")
    )
    
    # الصف الخامس (التعليمات والدعم)
    builder.row(
        types.InlineKeyboardButton(text="التعليمات ℹ️", callback_data="show_help"),
        types.InlineKeyboardButton(text="الدعم 🎧", url="https://t.me/Charger444") # استبدل بمعرف الدعم
    )
    
    # زر لوحة التحكم للمشرفين فقط
    if is_admin_user:
        builder.row(
            types.InlineKeyboardButton(text="🛠 لوحة تحكم الإدارة", callback_data="back_to_admin")
        )
    
    return builder.as_markup()

def get_currency_keyboard(current_currency: str = "USD"):
    """كيبورد اختيار العملة (مطابق لصورة 10)"""
    builder = InlineKeyboardBuilder()
    
    usd_text = "دولار ($) — العملة الأساسية ✅" if current_currency == "USD" else "دولار ($) — العملة الأساسية"
    syp_text = "ليرة (ل.س) ✅" if current_currency == "SYP" else "ليرة (ل.س)"
    
    builder.row(types.InlineKeyboardButton(text=usd_text, callback_data="set_curr_USD"))
    builder.row(types.InlineKeyboardButton(text=syp_text, callback_data="set_curr_SYP"))
    
    builder.row(types.InlineKeyboardButton(text="القائمة الرئيسية 🏠", callback_data="back_to_main"))
    return builder.as_markup()

def get_back_to_main_keyboard():
    """زر رجوع للقائمة الرئيسية فقط"""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="القائمة الرئيسية 🏠", callback_data="back_to_main"))
    return builder.as_markup()

def get_back_inline_keyboard(callback_data: str = "back_to_main", text: str = "رجوع ⬅️"):
    """زر رجوع عام مع إمكانية تحديد الوجهة"""
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text=text, callback_data=callback_data))
    builder.row(types.InlineKeyboardButton(text="القائمة الرئيسية 🏠", callback_data="back_to_main"))
    return builder.as_markup()

def get_confirmation_keyboard(callback_yes: str = "confirm", callback_no: str = "cancel"):
    """أزرار تأكيد وإلغاء"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="تأكيد ✅", callback_data=callback_yes),
        types.InlineKeyboardButton(text="إلغاء ❌", callback_data=callback_no)
    )
    return builder.as_markup()

def get_pagination_keyboard(current_page: int, total_pages: int, prefix: str):
    """كيبورد الصفحات (مطابق لصورة 104)"""
    builder = InlineKeyboardBuilder()
    buttons = []
    
    if current_page > 1:
        buttons.append(types.InlineKeyboardButton(text="◀️", callback_data=f"{prefix}_page_{current_page - 1}"))
    
    buttons.append(types.InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="ignore_pagination"))
    
    if current_page < total_pages:
        buttons.append(types.InlineKeyboardButton(text="▶️", callback_data=f"{prefix}_page_{current_page + 1}"))
    
    builder.row(*buttons)
    return builder
