# utils.py
import re
import logging
from config import ADMIN_ID, MODERATORS
from handlers.time_utils import get_damascus_time_now

logger = logging.getLogger(__name__)

# ============= دوال المشرفين =============
def is_admin(user_id):
    """التحقق من صلاحيات المشرف"""
    return user_id == ADMIN_ID or user_id in MODERATORS

# ============= دوال التوقيت =============
def get_formatted_damascus_time():
    """الحصول على الوقت الحالي بتوقيت دمشق منسق"""
    return get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')

def format_datetime(dt, format_str='%Y-%m-%d %H:%M:%S'):
    """تنسيق أي تاريخ حسب الصيغة المطلوبة"""
    if dt is None:
        return "غير معروف"
    if hasattr(dt, 'strftime'):
        return dt.strftime(format_str)
    return str(dt)

# ============= دوال تنسيق العملة =============
def format_syp(amount):
    """تنسيق المبلغ بالليرة السورية"""
    return f"{amount:,.0f} ل.س"

def format_usd(amount):
    """تنسيق المبلغ بالدولار"""
    return f"${amount:,.2f}"

def format_amount(amount, currency='syp', decimals=0):
    """تنسيق المبلغ حسب العملة"""
    if currency == 'usd':
        return f"${amount:,.2f}"
    elif currency == 'usd_raw':
        return f"${amount:,.{decimals}f}"
    return f"{amount:,.0f} ل.س"

# ============= دوال معالجة الرسائل =============
async def safe_edit_message(message, text, reply_markup=None):
    """تعديل الرسالة بأمان مع معالجة الأخطاء"""
    try:
        if message.photo:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text=text, reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.error(f"خطأ في تعديل الرسالة: {e}")
        return False

def format_message_text(text):
    """تحويل النص من Markdown إلى HTML"""
    if not text:
        return text
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    text = re.sub(r'__(.*?)__', r'<u>\1</u>', text)
    return text

# ============= دوال FSM المساعدة =============
async def get_state_data_field(state, field):
    """جلب حقل معين من FSM state"""
    data = await state.get_data()
    return data.get(field, '')

async def clear_state_and_return(state, message, text, keyboard=None):
    """مسح الحالة وإرسال رسالة"""
    await state.clear()
    await message.answer(text, reply_markup=keyboard)

# ============= دوال التحقق من الصحة =============
def is_valid_number(text, allow_float=True):
    """التحقق من صحة الرقم"""
    if allow_float:
        try:
            float(text.replace(',', ''))
            return True
        except ValueError:
            return False
    else:
        return text.replace(',', '').isdigit()

def is_valid_positive_number(text, allow_float=True):
    """التحقق من أن الرقم موجب"""
    if not is_valid_number(text, allow_float):
        return False
    value = float(text.replace(',', '')) if allow_float else int(text.replace(',', ''))
    return value > 0

def parse_number(text, allow_float=True):
    """تحويل النص إلى رقم"""
    clean_text = text.replace(',', '').replace(' ', '')
    return float(clean_text) if allow_float else int(clean_text)

# ============= دوال إنشاء الكيبورد =============
def create_inline_keyboard(buttons_data, row_width=2):
    """إنشاء كيبورد إنلاين من مصفوفة أزرار"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram import types
    
    builder = InlineKeyboardBuilder()
    for text, callback in buttons_data:
        builder.add(types.InlineKeyboardButton(text=text, callback_data=callback))
    builder.adjust(row_width)
    return builder.as_markup()

# ============= دوال معالجة الأخطاء =============
def log_error(error, context=""):
    """تسجيل الأخطاء بشكل موحد"""
    logger.error(f"❌ {context}: {error}")
    import traceback
    traceback.print_exc()

# ============= دوال إحصائيات سريعة =============
def calculate_percentage(part, whole):
    """حساب النسبة المئوية"""
    if whole == 0:
        return 0
    return (part / whole) * 100

def format_percentage(value, decimals=1):
    """تنسيق النسبة المئوية"""
    return f"{value:.{decimals}f}%"