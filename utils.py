# utils.py
import re
import logging
import pytz
import traceback
from datetime import datetime
from typing import Union, Optional, List, Tuple, Any
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ADMIN_ID, MODERATORS
from handlers.time_utils import get_damascus_time_now, DAMASCUS_TZ, format_damascus_time

logger = logging.getLogger(__name__)

# ============= دوال المشرفين =============

def is_admin(user_id: int) -> bool:
    """
    التحقق من صلاحيات المشرف
    
    Args:
        user_id: آيدي المستخدم
    
    Returns:
        bool: True إذا كان المستخدم مشرفاً
    """
    return user_id == ADMIN_ID or user_id in MODERATORS


def is_owner(user_id: int) -> bool:
    """
    التحقق من أن المستخدم هو المالك
    
    Args:
        user_id: آيدي المستخدم
    
    Returns:
        bool: True إذا كان المستخدم هو المالك
    """
    return user_id == ADMIN_ID


def get_admin_ids() -> List[int]:
    """الحصول على قائمة بجميع آيديات المشرفين"""
    admin_ids = [ADMIN_ID]
    admin_ids.extend(MODERATORS)
    return list(set(admin_ids))  # إزالة التكرار


# ============= دوال التوقيت =============

def get_formatted_damascus_time() -> str:
    """
    الحصول على الوقت الحالي بتوقيت دمشق منسق
    
    Returns:
        str: الوقت الحالي بصيغة YYYY-MM-DD HH:MM:SS
    """
    return get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')


def format_datetime(
    dt: Optional[Union[datetime, str]], 
    format_str: str = '%Y-%m-%d %H:%M:%S'
) -> str:
    """
    تنسيق أي تاريخ حسب الصيغة المطلوبة - مع تحويل تلقائي لتوقيت دمشق
    
    Args:
        dt: التاريخ (datetime object أو string)
        format_str: صيغة التنسيق المطلوبة
    
    Returns:
        str: التاريخ المنسق
    """
    return format_damascus_time(dt, format_str)


def get_timestamp() -> int:
    """الحصول على الوقت الحالي بصيغة timestamp"""
    return int(datetime.now().timestamp())


# ============= دوال تنسيق العملة =============

def format_syp(amount: Union[int, float]) -> str:
    """
    تنسيق المبلغ بالليرة السورية
    
    Args:
        amount: المبلغ
    
    Returns:
        str: المبلغ المنسق (مثال: "1,500 ل.س")
    """
    return f"{amount:,.0f} ل.س"


def format_usd(amount: Union[int, float], decimals: int = 2) -> str:
    """
    تنسيق المبلغ بالدولار
    
    Args:
        amount: المبلغ
        decimals: عدد الخانات العشرية
    
    Returns:
        str: المبلغ المنسق (مثال: "$1,500.00")
    """
    return f"${amount:,.{decimals}f}"


def format_amount(
    amount: Union[int, float], 
    currency: str = 'syp', 
    decimals: int = 0
) -> str:
    """
    تنسيق المبلغ حسب العملة
    
    Args:
        amount: المبلغ
        currency: العملة ('syp', 'usd', 'usd_raw')
        decimals: عدد الخانات العشرية (لـ usd_raw فقط)
    
    Returns:
        str: المبلغ المنسق
    """
    if currency == 'usd':
        return format_usd(amount)
    elif currency == 'usd_raw':
        return f"${amount:,.{decimals}f}"
    return format_syp(amount)


def parse_amount(amount_str: str) -> Optional[float]:
    """
    تحويل نص إلى رقم (يدعم الفواصل والمسافات)
    
    Args:
        amount_str: النص المراد تحويله (مثال: "1,500.50")
    
    Returns:
        Optional[float]: الرقم أو None إذا فشل
    """
    try:
        # إزالة الفواصل والمسافات وعلامة $
        clean = amount_str.replace(',', '').replace(' ', '').replace('$', '').replace('ل.س', '')
        return float(clean)
    except (ValueError, TypeError):
        return None


# ============= دوال معالجة الرسائل =============

async def safe_edit_message(
    message: types.Message, 
    text: str, 
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = None
) -> bool:
    """
    تعديل الرسالة بأمان مع معالجة الأخطاء
    
    Args:
        message: الرسالة المراد تعديلها
        text: النص الجديد
        reply_markup: الكيبورد الجديد (اختياري)
        parse_mode: وضع التنسيق (Markdown, HTML)
    
    Returns:
        bool: True إذا نجح التعديل
    """
    try:
        if message.photo:
            await message.edit_caption(
                caption=text, 
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            await message.edit_text(
                text=text, 
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في تعديل الرسالة: {e}")
        return False


def format_message_text(text: str, from_markdown: bool = True) -> str:
    """
    تحويل النص بين صيغ Markdown و HTML
    
    Args:
        text: النص المراد تحويله
        from_markdown: True للتحويل من Markdown إلى HTML، False للعكس
    
    Returns:
        str: النص المحول
    """
    if not text:
        return text
    
    if from_markdown:
        # Markdown -> HTML
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
        text = re.sub(r'__(.*?)__', r'<u>\1</u>', text)
    else:
        # HTML -> Markdown
        text = re.sub(r'<b>(.*?)</b>', r'**\1**', text)
        text = re.sub(r'<i>(.*?)</i>', r'*\1*', text)
        text = re.sub(r'<code>(.*?)</code>', r'`\1`', text)
        text = re.sub(r'<u>(.*?)</u>', r'__\1__', text)
    
    return text


def escape_markdown(text: str) -> str:
    """
    تخطي الرموز الخاصة في Markdown
    
    Args:
        text: النص المراد تخطي رموزه
    
    Returns:
        str: النص مع تخطي الرموز
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


# ============= دوال FSM المساعدة =============

async def get_state_data_field(state, field: str, default: Any = '') -> Any:
    """
    جلب حقل معين من FSM state
    
    Args:
        state: FSMContext
        field: اسم الحقل
        default: القيمة الافتراضية إذا لم يوجد الحقل
    
    Returns:
        Any: قيمة الحقل
    """
    data = await state.get_data()
    return data.get(field, default)


async def clear_state_and_return(
    state, 
    message: types.Message, 
    text: str, 
    keyboard: Optional[types.ReplyKeyboardMarkup] = None
) -> None:
    """
    مسح الحالة وإرسال رسالة
    
    Args:
        state: FSMContext
        message: الرسالة
        text: النص المراد إرساله
        keyboard: الكيبورد (اختياري)
    """
    await state.clear()
    await message.answer(text, reply_markup=keyboard)


async def update_state_data(state, **kwargs) -> None:
    """
    تحديث بيانات الـ state
    
    Args:
        state: FSMContext
        **kwargs: البيانات المراد تحديثها
    """
    data = await state.get_data()
    data.update(kwargs)
    await state.set_data(data)


# ============= دوال التحقق من الصحة =============

def is_valid_number(text: str, allow_float: bool = True) -> bool:
    """
    التحقق من صحة الرقم
    
    Args:
        text: النص المراد التحقق منه
        allow_float: السماح بالأرقام العشرية
    
    Returns:
        bool: True إذا كان النص رقماً صحيحاً
    """
    if not text:
        return False
    
    clean_text = text.replace(',', '').replace(' ', '')
    
    if allow_float:
        try:
            float(clean_text)
            return True
        except ValueError:
            return False
    else:
        return clean_text.isdigit()


def is_valid_positive_number(text: str, allow_float: bool = True) -> bool:
    """
    التحقق من أن الرقم موجب
    
    Args:
        text: النص المراد التحقق منه
        allow_float: السماح بالأرقام العشرية
    
    Returns:
        bool: True إذا كان الرقماً موجباً
    """
    if not is_valid_number(text, allow_float):
        return False
    
    clean_text = text.replace(',', '').replace(' ', '')
    value = float(clean_text) if allow_float else int(clean_text)
    return value > 0


def parse_number(text: str, allow_float: bool = True) -> Union[float, int, None]:
    """
    تحويل النص إلى رقم
    
    Args:
        text: النص المراد تحويله
        allow_float: السماح بالأرقام العشرية
    
    Returns:
        Union[float, int, None]: الرقم أو None إذا فشل
    """
    if not text:
        return None
    
    clean_text = text.replace(',', '').replace(' ', '')
    
    try:
        if allow_float:
            return float(clean_text)
        else:
            return int(clean_text)
    except ValueError:
        return None


def validate_target_id(target_id: str, min_length: int = 1, max_length: int = 100) -> Tuple[bool, str]:
    """
    التحقق من صحة ID الهدف
    
    Args:
        target_id: النص المراد التحقق منه
        min_length: الحد الأدنى للطول
        max_length: الحد الأقصى للطول
    
    Returns:
        Tuple[bool, str]: (صحيح/خطأ, رسالة الخطأ)
    """
    if not target_id:
        return False, "❌ الحقل فارغ"
    
    if len(target_id) < min_length:
        return False, f"❌ الطول يجب أن يكون على الأقل {min_length} أحرف"
    
    if len(target_id) > max_length:
        return False, f"❌ الطول يجب أن لا يتجاوز {max_length} أحرف"
    
    # التحقق من عدم وجود رموز خطيرة
    dangerous_chars = ['<', '>', '"', "'", ';', '--']
    for char in dangerous_chars:
        if char in target_id:
            return False, f"❌ لا يمكن استخدام الرمز '{char}'"
    
    return True, "✅ صحيح"


# ============= دوال إنشاء الكيبورد =============

def create_inline_keyboard(
    buttons_data: List[Tuple[str, str]], 
    row_width: int = 2
) -> types.InlineKeyboardMarkup:
    """
    إنشاء كيبورد إنلاين من مصفوفة أزرار
    
    Args:
        buttons_data: قائمة من الأزرار، كل عنصر (نص الزر, callback_data)
        row_width: عدد الأزرار في كل صف
    
    Returns:
        types.InlineKeyboardMarkup: الكيبورد
    """
    builder = InlineKeyboardBuilder()
    
    for text, callback in buttons_data:
        builder.add(types.InlineKeyboardButton(text=text, callback_data=callback))
    
    builder.adjust(row_width)
    return builder.as_markup()


def create_url_keyboard(buttons_data: List[Tuple[str, str]]) -> types.InlineKeyboardMarkup:
    """
    إنشاء كيبورد إنلاين بروابط
    
    Args:
        buttons_data: قائمة من الأزرار، كل عنصر (نص الزر, الرابط)
    
    Returns:
        types.InlineKeyboardMarkup: الكيبورد
    """
    builder = InlineKeyboardBuilder()
    
    for text, url in buttons_data:
        builder.add(types.InlineKeyboardButton(text=text, url=url))
    
    return builder.as_markup()


def split_into_chunks(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    تقسيم قائمة إلى أجزاء
    
    Args:
        items: القائمة المراد تقسيمها
        chunk_size: حجم كل جزء
    
    Returns:
        List[List[Any]]: قائمة الأجزاء
    """
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


# ============= دوال معالجة الأخطاء =============

def log_error(error: Exception, context: str = "") -> None:
    """
    تسجيل الأخطاء بشكل موحد
    
    Args:
        error: الخطأ
        context: سياق الخطأ
    """
    logger.error(f"❌ {context}: {error}")
    traceback.print_exc()


def get_error_message(error: Exception) -> str:
    """
    الحصول على رسالة خطأ مناسبة للمستخدم
    
    Args:
        error: الخطأ
    
    Returns:
        str: رسالة الخطأ
    """
    error_str = str(error).lower()
    
    if "timeout" in error_str:
        return "⚠️ انتهت المهلة، يرجى المحاولة مرة أخرى"
    elif "connection" in error_str:
        return "⚠️ مشكلة في الاتصال، يرجى المحاولة لاحقاً"
    elif "database" in error_str:
        return "⚠️ مشكلة في قاعدة البيانات، يرجى المحاولة لاحقاً"
    else:
        return f"❌ حدث خطأ: {str(error)}"


# ============= دوال إحصائيات سريعة =============

def calculate_percentage(part: Union[int, float], whole: Union[int, float]) -> float:
    """
    حساب النسبة المئوية
    
    Args:
        part: الجزء
        whole: الكل
    
    Returns:
        float: النسبة المئوية
    """
    if whole == 0:
        return 0
    return (part / whole) * 100


def format_percentage(value: float, decimals: int = 1) -> str:
    """
    تنسيق النسبة المئوية
    
    Args:
        value: القيمة
        decimals: عدد الخانات العشرية
    
    Returns:
        str: النسبة المئوية المنسقة
    """
    return f"{value:.{decimals}f}%"


def calculate_discount(original: float, discounted: float) -> float:
    """
    حساب نسبة الخصم
    
    Args:
        original: السعر الأصلي
        discounted: السعر بعد الخصم
    
    Returns:
        float: نسبة الخصم
    """
    if original == 0:
        return 0
    return ((original - discounted) / original) * 100


# ============= دوال مساعدة متنوعة =============

def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    اقتطاع النص إذا كان طويلاً
    
    Args:
        text: النص
        max_length: الحد الأقصى للطول
        suffix: اللاحقة
    
    Returns:
        str: النص المقتطع
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def clean_html(text: str) -> str:
    """
    إزالة وسوم HTML من النص
    
    Args:
        text: النص
    
    Returns:
        str: النص بدون وسوم HTML
    """
    return re.sub(r'<[^>]+>', '', text)


def extract_numbers(text: str) -> List[int]:
    """
    استخراج الأرقام من النص
    
    Args:
        text: النص
    
    Returns:
        List[int]: قائمة الأرقام
    """
    return [int(num) for num in re.findall(r'\d+', text)]


# تصدير الدوال الرئيسية
__all__ = [
    'is_admin',
    'is_owner',
    'get_admin_ids',
    'get_formatted_damascus_time',
    'format_datetime',
    'get_timestamp',
    'format_syp',
    'format_usd',
    'format_amount',
    'parse_amount',
    'safe_edit_message',
    'format_message_text',
    'escape_markdown',
    'get_state_data_field',
    'clear_state_and_return',
    'update_state_data',
    'is_valid_number',
    'is_valid_positive_number',
    'parse_number',
    'validate_target_id',
    'create_inline_keyboard',
    'create_url_keyboard',
    'split_into_chunks',
    'log_error',
    'get_error_message',
    'calculate_percentage',
    'format_percentage',
    'calculate_discount',
    'truncate_text',
    'clean_html',
    'extract_numbers'
]
