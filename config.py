# config.py
import os
import sys
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from pathlib import Path

# ============= تحميل متغيرات البيئة =============

# تحديد مسار ملف .env (يبحث في المجلد الحالي والمجلدات الأصلية)
env_path = Path('.') / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"📁 تم تحميل ملف .env من {env_path.absolute()}")
else:
    # البحث في المجلدات الأصلية
    for parent in Path('.').absolute().parents:
        env_path = parent / '.env'
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            print(f"📁 تم تحميل ملف .env من {env_path.absolute()}")
            break
    else:
        print("⚠️ لم يتم العثور على ملف .env، سيتم استخدام متغيرات البيئة فقط")

# ============= دوال مساعدة =============

def get_env_int(key: str, default: int = 0) -> int:
    """الحصول على متغير بيئة كرقم صحيح"""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        print(f"⚠️ تحذير: {key} غير صالح (القيمة: {value})، سيتم استخدام {default}")
        return default

def get_env_float(key: str, default: float = 0.0) -> float:
    """الحصول على متغير بيئة كرقم عشري"""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value.strip())
    except ValueError:
        print(f"⚠️ تحذير: {key} غير صالح (القيمة: {value})، سيتم استخدام {default}")
        return default

def get_env_bool(key: str, default: bool = False) -> bool:
    """الحصول على متغير بيئة كقيمة منطقية"""
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in ('true', '1', 'yes', 'on', 'y')

def get_env_list(key: str, default: Optional[List[str]] = None, separator: str = ',') -> List[str]:
    """الحصول على متغير بيئة كقائمة"""
    value = os.getenv(key)
    if not value:
        return default or []
    return [x.strip() for x in value.split(separator) if x.strip()]

def get_env_list_int(key: str, default: Optional[List[int]] = None, separator: str = ',') -> List[int]:
    """الحصول على متغير بيئة كقائمة أرقام"""
    str_list = get_env_list(key, separator=separator)
    if not str_list:
        return default or []
    
    int_list = []
    for item in str_list:
        try:
            int_list.append(int(item))
        except ValueError:
            print(f"⚠️ تحذير: {key} تحتوي على قيمة غير صالحة: {item}")
    
    return int_list

# ============= الإعدادات الأساسية =============

# توكن البوت (إلزامي)
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN غير موجود في متغيرات البيئة!")

# معرف المالك (إلزامي)
ADMIN_ID = get_env_int("ADMIN_ID", 0)
if ADMIN_ID == 0:
    print("⚠️ تحذير: ADMIN_ID غير محدد، بعض وظائف الإدارة لن تعمل")

# المشرفون الإضافيون
MODERATORS = get_env_list_int("MODERATORS", [])

# إضافة ADMIN_ID إلى MODERATORS إذا لم يكن موجوداً
if ADMIN_ID and ADMIN_ID not in MODERATORS:
    MODERATORS.append(ADMIN_ID)

# ============= إعدادات قاعدة البيانات =============

# رابط قاعدة البيانات (الأولوية القصوى)
DATABASE_URL = os.getenv("DATABASE_URL")

# إعدادات قاعدة البيانات المحلية
DB_CONFIG: Dict[str, Any] = {}

if DATABASE_URL:
    # استخدام الرابط المباشر (مناسب لـ Supabase, Render, إلخ)
    DB_CONFIG = {
        "dsn": DATABASE_URL,
        "min_size": get_env_int("DB_POOL_MIN_SIZE", 1),
        "max_size": get_env_int("DB_POOL_MAX_SIZE", 10),
        "command_timeout": get_env_int("DB_COMMAND_TIMEOUT", 60),
    }
    print(f"✅ استخدام قاعدة بيانات عبر الرابط: {DATABASE_URL[:30]}...")
else:
    # إعدادات الاتصال المحلية
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": get_env_int("DB_PORT", 5432),
        "database": os.getenv("DB_NAME", "charging_bot"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
        "min_size": get_env_int("DB_POOL_MIN_SIZE", 1),
        "max_size": get_env_int("DB_POOL_MAX_SIZE", 5),  # أقل للخطة المجانية
        "command_timeout": get_env_int("DB_COMMAND_TIMEOUT", 60),
    }
    print(f"✅ استخدام قاعدة بيانات محلية: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")

# ============= أرقام الدفع =============

SYRIATEL_NUMS = get_env_list("SYRIATEL_NUMS", [])
SHAM_CASH_NUM = os.getenv("SHAM_CASH_NUM", "")
SHAM_CASH_NUM_USD = os.getenv("SHAM_CASH_NUM_USD", "")
USDT_BEP20_WALLET = os.getenv("USDT_BEP20_WALLET", "")

# ============= مجموعات الإدارة =============

DEPOSIT_GROUP = get_env_int("DEPOSIT_GROUP", 0)
ORDERS_GROUP = get_env_int("ORDERS_GROUP", 0)

# ============= إعدادات إضافية =============

# وضع التطوير
DEBUG = get_env_bool("DEBUG", False)

# إعدادات الويب (للـ webhook)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_PORT = get_env_int("PORT", 8000)  # Render يستخدم PORT
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", os.getenv("WEBHOOK_HOST", ""))

WEB_USERNAME = os.getenv("WEB_USERNAME", "admin")
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "admin")

# ============= إعدادات البوت =============

# سعر الصرف الافتراضي (سيتم تحديثه من قاعدة البيانات لاحقاً)
DEFAULT_USD_TO_SYP = get_env_float("DEFAULT_USD_TO_SYP", 118)
USD_TO_SYP = DEFAULT_USD_TO_SYP

# حالة البوت الافتراضية
BOT_STATUS = True

# ============= إعدادات الكاش =============

CACHE_CONFIG = {
    "default_ttl": get_env_int("CACHE_DEFAULT_TTL", 60),
    "max_size": get_env_int("CACHE_MAX_SIZE", 1000),
    "cleanup_interval": get_env_int("CACHE_CLEANUP_INTERVAL", 300),
}

# ============= إعدادات التسجيل =============

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
LOG_FILE = os.getenv("LOG_FILE", "")

# ============= دوال تحميل الإعدادات الديناميكية =============

async def load_exchange_rate(pool) -> bool:
    """تحميل سعر الصرف من قاعدة البيانات"""
    from database import get_exchange_rate
    global USD_TO_SYP
    try:
        db_rate = await get_exchange_rate(pool)
        if db_rate:
            USD_TO_SYP = db_rate
            print(f"💵 تم تحميل سعر الصرف من قاعدة البيانات: {USD_TO_SYP} ل.س")
        return True
    except Exception as e:
        print(f"❌ خطأ في تحميل سعر الصرف: {e}")
        return False

async def load_bot_settings(pool) -> bool:
    """تحميل جميع إعدادات البوت من قاعدة البيانات"""
    from database import get_bot_status, get_maintenance_message
    global BOT_STATUS
    try:
        BOT_STATUS = await get_bot_status(pool)
        print(f"🤖 حالة البوت: {'يعمل' if BOT_STATUS else 'متوقف'}")
        return True
    except Exception as e:
        print(f"❌ خطأ في تحميل حالة البوت: {e}")
        return False

# ============= التحقق من صحة الإعدادات =============

def validate_config() -> List[str]:
    """التحقق من صحة الإعدادات الأساسية"""
    errors = []
    warnings = []
    
    # تحقق من التوكن
    if not TOKEN:
        errors.append("❌ BOT_TOKEN غير موجود")
    elif len(TOKEN) < 40:
        warnings.append("⚠️ BOT_TOKEN قد يكون غير صالح (قصير جداً)")
    
    # تحقق من ADMIN_ID
    if ADMIN_ID == 0:
        warnings.append("⚠️ ADMIN_ID غير محدد (اختياري)")
    
    # تحقق من مجموعات الإدارة
    if DEPOSIT_GROUP == 0:
        warnings.append("⚠️ DEPOSIT_GROUP غير محدد (اختياري)")
    if ORDERS_GROUP == 0:
        warnings.append("⚠️ ORDERS_GROUP غير محدد (اختياري)")
    
    # تحقق من أرقام الدفع
    if not SYRIATEL_NUMS:
        warnings.append("⚠️ SYRIATEL_NUMS غير محددة (اختياري)")
    if not SHAM_CASH_NUM:
        warnings.append("⚠️ SHAM_CASH_NUM غير محددة (اختياري)")
    if not USDT_BEP20_WALLET:
        warnings.append("⚠️ USDT_BEP20_WALLET غير محددة (اختياري)")
    
    # تحقق من إعدادات قاعدة البيانات
    if DATABASE_URL:
        if not DATABASE_URL.startswith(('postgresql://', 'postgres://')):
            errors.append("❌ DATABASE_URL غير صالح (يجب أن يبدأ بـ postgresql://)")
    else:
        if not DB_CONFIG.get('password'):
            warnings.append("⚠️ DB_PASSWORD غير محددة (قد تحتاجها للاتصال المحلي)")
    
    return errors, warnings

# ============= طباعة ملخص الإعدادات =============

def print_config_summary():
    """طباعة ملخص الإعدادات عند التشغيل"""
    print("\n" + "="*50)
    print("🚀 ملخص إعدادات البوت")
    print("="*50)
    
    print(f"🤖 BOT_TOKEN: {'✅ موجود' if TOKEN else '❌ مفقود'}")
    print(f"👑 ADMIN_ID: {ADMIN_ID if ADMIN_ID else '⚠️ غير محدد'}")
    print(f"👥 MODERATORS: {len(MODERATORS)} مشرف")
    
    print("\n📦 قاعدة البيانات:")
    if DATABASE_URL:
        print(f"   ✅ رابط خارجي")
    else:
        print(f"   📍 محلية: {DB_CONFIG.get('host')}:{DB_CONFIG.get('port')}")
    
    print(f"\n💰 طرق الدفع:")
    print(f"   📞 سيرياتل: {len(SYRIATEL_NUMS)} رقم")
    print(f"   💳 شام كاش: {'✅' if SHAM_CASH_NUM else '❌'}")
    print(f"   💎 USDT: {'✅' if USDT_BEP20_WALLET else '❌'}")
    
    print(f"\n👥 مجموعات الإدارة:")
    print(f"   💰 DEPOSIT_GROUP: {DEPOSIT_GROUP if DEPOSIT_GROUP else '⚠️'}")
    print(f"   📦 ORDERS_GROUP: {ORDERS_GROUP if ORDERS_GROUP else '⚠️'}")
    
    print(f"\n⚙️ إعدادات إضافية:")
    print(f"   🔧 DEBUG: {DEBUG}")
    print(f"   📝 LOG_LEVEL: {LOG_LEVEL}")
    print(f"   💵 DEFAULT_USD_TO_SYP: {DEFAULT_USD_TO_SYP}")
    
    print("="*50 + "\n")

# التحقق من الإعدادات
errors, warnings = validate_config()

if errors:
    print("\n❌ أخطاء في الإعدادات:")
    for error in errors:
        print(f"   {error}")
    print("\n⚠️ يرجى تصحيح الأخطاء قبل تشغيل البوت")
    sys.exit(1)

if warnings:
    print("\n⚠️ تحذيرات:")
    for warning in warnings:
        print(f"   {warning}")

# طباعة الملخص
print_config_summary()

# ============= تصدير المتغيرات =============

__all__ = [
    'TOKEN',
    'ADMIN_ID',
    'MODERATORS',
    'DATABASE_URL',
    'DB_CONFIG',
    'SYRIATEL_NUMS',
    'SHAM_CASH_NUM',
    'SHAM_CASH_NUM_USD',
    'USDT_BEP20_WALLET',
    'DEPOSIT_GROUP',
    'ORDERS_GROUP',
    'WEBHOOK_URL',
    'WEBHOOK_PATH',
    'WEBHOOK_PORT',
    'WEBHOOK_HOST',
    'WEB_USERNAME',
    'WEB_PASSWORD',
    'DEBUG',
    'USD_TO_SYP',
    'DEFAULT_USD_TO_SYP',
    'BOT_STATUS',
    'CACHE_CONFIG',
    'LOG_LEVEL',
    'LOG_FORMAT',
    'LOG_FILE',
    'load_exchange_rate',
    'load_bot_settings'
]
