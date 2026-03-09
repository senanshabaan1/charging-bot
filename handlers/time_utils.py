# handlers/time_utils.py
from datetime import datetime, timedelta
import pytz
from typing import Union, Optional

# المنطقة الزمنية لدمشق
DAMASCUS_TZ = pytz.timezone('Asia/Damascus')
# تنسيقات التاريخ المختلفة
DEFAULT_FORMAT = '%Y-%m-%d %H:%M:%S'
DATE_FORMAT = '%Y-%m-%d'
TIME_FORMAT = '%H:%M:%S'
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
DATETIME_FORMAT_FULL = '%Y-%m-%d %H:%M:%S %Z'

def format_damascus_time(dt: Optional[Union[datetime, str]], format_str: str = DEFAULT_FORMAT) -> str:
    """
    تحويل أي وقت إلى توقيت دمشق وتنسيقه
    
    Args:
        dt: التاريخ والوقت (datetime object أو string)
        format_str: صيغة التنسيق المطلوبة
        
    Returns:
        str: التاريخ المنسق بتوقيت دمشق
    """
    if dt is None:
        return "غير معروف"
    
    # تحويل النص إلى datetime
    if isinstance(dt, str):
        try:
            # محاولة تحويل النص إلى datetime
            clean_dt = dt.replace('Z', '+00:00').replace('T', ' ')
            if '+' in clean_dt:
                dt = datetime.fromisoformat(clean_dt)
            else:
                # إذا كان بدون توقيت، نعتبره UTC
                dt = datetime.fromisoformat(clean_dt)
                dt = pytz.UTC.localize(dt)
        except (ValueError, TypeError):
            # إذا فشل التحويل، نعيد النص كما هو
            return dt
    
    # التأكد من أن dt هو datetime object
    if not isinstance(dt, datetime):
        return str(dt)
    
    # إضافة منطقة زمنية إذا لم تكن موجودة
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    # تحويل إلى توقيت دمشق
    damascus_dt = dt.astimezone(DAMASCUS_TZ)
    
    # تنسيق العرض
    try:
        return damascus_dt.strftime(format_str)
    except Exception:
        # إذا فشل التنسيق، نعيد الصيغة الافتراضية
        return damascus_dt.strftime(DEFAULT_FORMAT)

def get_damascus_time_now() -> datetime:
    """الحصول على الوقت الحالي بتوقيت دمشق"""
    return datetime.now(DAMASCUS_TZ)

def get_damascus_time_str(format_str: str = DEFAULT_FORMAT) -> str:
    """الحصول على الوقت الحالي بتوقيت دمشق كنص منسق"""
    return get_damascus_time_now().strftime(format_str)

def get_damascus_date_str() -> str:
    """الحصول على التاريخ الحالي بتوقيت دمشق (YYYY-MM-DD)"""
    return get_damascus_time_now().strftime(DATE_FORMAT)

def get_damascus_time_only_str() -> str:
    """الحصول على الوقت الحالي فقط (HH:MM:SS)"""
    return get_damascus_time_now().strftime(TIME_FORMAT)

def format_relative_time(dt: Union[datetime, str]) -> str:
    """
    تحويل الوقت إلى صيغة نسبية (منذ كم من الوقت)
    
    مثال: "منذ 5 دقائق", "منذ ساعتين", "الآن"
    """
    now = get_damascus_time_now()
    
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    damascus_dt = dt.astimezone(DAMASCUS_TZ)
    diff = now - damascus_dt
    
    seconds = diff.total_seconds()
    
    if seconds < 0:
        return "في المستقبل"
    if seconds < 10:
        return "الآن"
    if seconds < 60:
        return f"منذ {int(seconds)} ثانية"
    if seconds < 3600:
        minutes = int(seconds / 60)
        return f"منذ {minutes} دقيقة" + ("ق" if minutes == 1 else "ق")
    if seconds < 86400:
        hours = int(seconds / 3600)
        return f"منذ {hours} ساعة" + ("ة" if hours == 1 else "ات")
    if seconds < 604800:
        days = int(seconds / 86400)
        return f"منذ {days} يوم" + ("" if days == 1 else "ين" if days == 2 else "اً")
    
    # أكثر من أسبوع
    return damascus_dt.strftime(DATE_FORMAT)

def get_day_start(date: Optional[datetime] = None) -> datetime:
    """
    الحصول على بداية اليوم (00:00:00)
    
    Args:
        date: التاريخ المطلوب (إذا كان None يستخدم التاريخ الحالي)
    
    Returns:
        datetime: بداية اليوم بتوقيت دمشق
    """
    if date is None:
        date = get_damascus_time_now()
    elif date.tzinfo is None:
        date = DAMASCUS_TZ.localize(date)
    else:
        date = date.astimezone(DAMASCUS_TZ)
    
    return datetime(date.year, date.month, date.day, 0, 0, 0, tzinfo=DAMASCUS_TZ)

def get_day_end(date: Optional[datetime] = None) -> datetime:
    """
    الحصول على نهاية اليوم (23:59:59)
    
    Args:
        date: التاريخ المطلوب (إذا كان None يستخدم التاريخ الحالي)
    
    Returns:
        datetime: نهاية اليوم بتوقيت دمشق
    """
    day_start = get_day_start(date)
    return day_start + timedelta(days=1) - timedelta(microseconds=1)

def get_week_start(date: Optional[datetime] = None) -> datetime:
    """
    الحصول على بداية الأسبوع (الاثنين 00:00:00)
    
    Args:
        date: التاريخ المطلوب (إذا كان None يستخدم التاريخ الحالي)
    
    Returns:
        datetime: بداية الأسبوع بتوقيت دمشق
    """
    if date is None:
        date = get_damascus_time_now()
    elif date.tzinfo is None:
        date = DAMASCUS_TZ.localize(date)
    else:
        date = date.astimezone(DAMASCUS_TZ)
    
    # في Python، الاثنين هو 0 والأحد هو 6
    days_to_subtract = date.weekday()
    week_start = date - timedelta(days=days_to_subtract)
    return datetime(week_start.year, week_start.month, week_start.day, 0, 0, 0, tzinfo=DAMASCUS_TZ)

def get_month_start(date: Optional[datetime] = None) -> datetime:
    """
    الحصول على بداية الشهر
    
    Args:
        date: التاريخ المطلوب (إذا كان None يستخدم التاريخ الحالي)
    
    Returns:
        datetime: بداية الشهر بتوقيت دمشق
    """
    if date is None:
        date = get_damascus_time_now()
    elif date.tzinfo is None:
        date = DAMASCUS_TZ.localize(date)
    else:
        date = date.astimezone(DAMASCUS_TZ)
    
    return datetime(date.year, date.month, 1, 0, 0, 0, tzinfo=DAMASCUS_TZ)

def parse_damascus_time(date_str: str, format_str: str = DEFAULT_FORMAT) -> Optional[datetime]:
    """
    تحويل نص إلى datetime بتوقيت دمشق
    
    Args:
        date_str: النص المراد تحويله
        format_str: صيغة النص
    
    Returns:
        Optional[datetime]: التاريخ المحول أو None إذا فشل
    """
    try:
        dt = datetime.strptime(date_str, format_str)
        return DAMASCUS_TZ.localize(dt)
    except (ValueError, TypeError):
        return None

def is_same_day(dt1: Union[datetime, str], dt2: Union[datetime, str]) -> bool:
    """التحقق مما إذا كان التاريخان في نفس اليوم"""
    if isinstance(dt1, str):
        dt1 = parse_damascus_time(dt1) or get_damascus_time_now()
    if isinstance(dt2, str):
        dt2 = parse_damascus_time(dt2) or get_damascus_time_now()
    
    if dt1.tzinfo is None:
        dt1 = DAMASCUS_TZ.localize(dt1)
    if dt2.tzinfo is None:
        dt2 = DAMASCUS_TZ.localize(dt2)
    
    dt1_dam = dt1.astimezone(DAMASCUS_TZ)
    dt2_dam = dt2.astimezone(DAMASCUS_TZ)
    
    return (dt1_dam.year, dt1_dam.month, dt1_dam.day) == (dt2_dam.year, dt2_dam.month, dt2_dam.day)

def time_until_midnight() -> timedelta:
    """الوقت المتبقي حتى منتصف الليل"""
    now = get_damascus_time_now()
    midnight = get_day_end(now) + timedelta(microseconds=1)
    return midnight - now

def time_since_midnight() -> timedelta:
    """الوقت المنقضي منذ منتصف الليل"""
    now = get_damascus_time_now()
    midnight = get_day_start(now)
    return now - midnight

# تصدير الدوال الرئيسية للاستخدام السهل
__all__ = [
    'DAMASCUS_TZ',
    'DEFAULT_FORMAT',
    'DATE_FORMAT',
    'TIME_FORMAT',
    'DATETIME_FORMAT',
    'format_damascus_time',
    'get_damascus_time_now',
    'get_damascus_time_str',
    'get_damascus_date_str',
    'get_damascus_time_only_str',
    'format_relative_time',
    'get_day_start',
    'get_day_end',
    'get_week_start',
    'get_month_start',
    'parse_damascus_time',
    'is_same_day',
    'time_until_midnight',
    'time_since_midnight'
]