# handlers/keyboards.py
from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
 
# ============= دوال الكيبورد الإنلاين (Inline Keyboard) =============

def get_main_menu_keyboard(is_admin_user: bool = False):
    """القائمة الرئيسية للمستخدمين - كيبورد إنلاين"""
    builder = InlineKeyboardBuilder()
    
    # الصف الأول
    builder.row(
        types.InlineKeyboardButton(text="📱 خدمات الشحن", callback_data="show_categories")
    )
    
    # الصف الثاني
    builder.row(
        types.InlineKeyboardButton(text="💰 شحن المحفظة", callback_data="show_deposit_methods"),
        types.InlineKeyboardButton(text="👤 حسابي", callback_data="show_profile")
    )
    
    # الصف الثالث (للمشرفين فقط)
    if is_admin_user:
        builder.row(
            types.InlineKeyboardButton(text="🛠 لوحة التحكم", callback_data="back_to_admin")
        )
    
    # الصف الرابع (مساعدة)
    builder.row(
        types.InlineKeyboardButton(text="❓ مساعدة", callback_data="show_help")
    )
    
    return builder.as_markup()

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

def get_admin_main_menu_keyboard():
    """كيبورد إنلاين للقائمة الرئيسية للمشرفين"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📊 إحصائيات", callback_data="bot_stats"),
        types.InlineKeyboardButton(text="📢 رسالة للكل", callback_data="broadcast")
    )
    builder.row(
        types.InlineKeyboardButton(text="👤 معلومات مستخدم", callback_data="user_info"),
        types.InlineKeyboardButton(text="💰 إدارة النقاط", callback_data="manage_points")
    )
    builder.row(
        types.InlineKeyboardButton(text="📁 إدارة الأقسام", callback_data="manage_categories"),
        types.InlineKeyboardButton(text="🎮 إدارة الخيارات", callback_data="manage_options")
    )
    return builder.as_markup()

def get_pagination_keyboard(current_page: int, total_pages: int, prefix: str = "page"):
    """كيبورد للتنقل بين الصفحات"""
    builder = InlineKeyboardBuilder()
    buttons = []
    
    if current_page > 1:
        buttons.append(types.InlineKeyboardButton(
            text="◀️ السابق", 
            callback_data=f"{prefix}_prev_{current_page}"
        ))
    
    buttons.append(types.InlineKeyboardButton(
        text=f"📄 {current_page}/{total_pages}", 
        callback_data="current_page"
    ))
    
    if current_page < total_pages:
        buttons.append(types.InlineKeyboardButton(
            text="التالي ▶️", 
            callback_data=f"{prefix}_next_{current_page}"
        ))
    
    builder.row(*buttons)
    return builder.as_markup()

def get_products_per_row_keyboard(buttons: list, row_width: int = 2):
    """كيبورد لعرض المنتجات مع عدد محدد في كل صف"""
    builder = InlineKeyboardBuilder()
    for i in range(0, len(buttons), row_width):
        row_buttons = buttons[i:i + row_width]
        builder.row(*row_buttons)
    return builder.as_markup()

def get_action_keyboard(actions: list):
    """كيبورد ديناميكي لإنشاء أزرار من قائمة"""
    builder = InlineKeyboardBuilder()
    for text, callback in actions:
        builder.row(types.InlineKeyboardButton(text=text, callback_data=callback))
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

async def edit_message_with_new_keyboard(message: types.Message, new_text: str = None, new_keyboard = None):
    """تعديل رسالة مع كيبورد جديد (طلب واحد)"""
    try:
        if new_text:
            await message.edit_text(
                text=new_text,
                reply_markup=new_keyboard
            )
        else:
            await message.edit_reply_markup(reply_markup=new_keyboard)
        return True
    except Exception as e:
        logging.getLogger(__name__).error(f"خطأ في تعديل الرسالة: {e}")
        return False
