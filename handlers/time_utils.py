# handlers/time_utils.py
from datetime import datetime
import pytz

DAMASCUS_TZ = pytz.timezone('Asia/Damascus')

def format_damascus_time(dt):
    """تحويل أي وقت إلى توقيت دمشق وتنسيقه"""
    if dt is None:
        return "غير معروف"
    
    # إذا كان النص، نحوله إلى datetime
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    
    # إذا كان بدون منطقة زمنية، نعتبره UTC
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    # تحويل إلى توقيت دمشق
    damascus_dt = dt.astimezone(DAMASCUS_TZ)
    
    # تنسيق العرض
    return damascus_dt.strftime('%Y-%m-%d %H:%M:%S')

def get_damascus_time_now():
    """الحصول على الوقت الحالي بتوقيت دمشق"""
    return datetime.now(DAMASCUS_TZ)