# config.py
import os
from dotenv import load_dotenv

# تحميل المتغيرات من ملف .env (للتشغيل المحلي فقط)
load_dotenv()  # ✅ بسيطة وبتشتغل دايماً

# التوكن والإعدادات الأساسية
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN غير موجود في متغيرات البيئة!")

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0
    print("⚠️ تحذير: ADMIN_ID غير صالح، سيتم استخدام 0")

MODERATORS = []
moderators_str = os.getenv("MODERATORS", "")
if moderators_str:
    try:
        MODERATORS = [int(x.strip()) for x in moderators_str.split(",") if x.strip()]
    except ValueError:
        print("⚠️ تحذير: MODERATORS تحتوي على قيم غير صالحة")

# ====== قسم قاعدة البيانات - آمن ومبسط ======
# الأولوية لـ DATABASE_URL من متغيرات البيئة
DATABASE_URL = os.getenv("DATABASE_URL")

print(f"🔍 DATABASE_URL found: {'Yes' if DATABASE_URL else 'No'}")

if DATABASE_URL:
    # ✅ استخدام الرابط مباشرة - الأفضل والأكثر أماناً
    DB_CONFIG = {
        "dsn": DATABASE_URL  # الرابط كامل مع كلمة المرور
    }
    print(f"✅ Using Supabase database via DATABASE_URL")
else:
    # للإستخدام المحلي فقط (تطوير)
    print("⚠️ No DATABASE_URL found, using local config")
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "charging_bot"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "")
    }
# =======================================

# أرقام الدفع
SYRIATEL_NUMS = [x.strip() for x in os.getenv("SYRIATEL_NUMS", "").split(",") if x.strip()]
SHAM_CASH_NUM = os.getenv("SHAM_CASH_NUM", "")
SHAM_CASH_NUM_USD = os.getenv("SHAM_CASH_NUM_USD", "")
USDT_BEP20_WALLET = os.getenv("USDT_BEP20_WALLET", "")

# مجموعات الإدارة
try:
    DEPOSIT_GROUP = int(os.getenv("DEPOSIT_GROUP", "0"))
except ValueError:
    DEPOSIT_GROUP = 0
    print("⚠️ تحذير: DEPOSIT_GROUP غير صالح")

try:
    ORDERS_GROUP = int(os.getenv("ORDERS_GROUP", "0"))
except ValueError:
    ORDERS_GROUP = 0
    print("⚠️ تحذير: ORDERS_GROUP غير صالح")

# إعدادات الويب
WEB_USERNAME = os.getenv("WEB_USERNAME", "admin")
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "admin")

# سعر الصرف الافتراضي
try:
    USD_TO_SYP = int(os.getenv("DEFAULT_USD_TO_SYP", "118"))
except ValueError:
    USD_TO_SYP = 118
    print("⚠️ تحذير: DEFAULT_USD_TO_SYP غير صالح، استخدام 118")

BOT_STATUS = True

# دالة لتحميل سعر الصرف من قاعدة البيانات
async def load_exchange_rate(pool):
    """تحميل سعر الصرف من قاعدة البيانات"""
    from database import get_exchange_rate
    global USD_TO_SYP
    try:
        USD_TO_SYP = await get_exchange_rate(pool)
        print(f"💵 تم تحميل سعر الصرف: {USD_TO_SYP} ل.س")
        return True
    except Exception as e:
        print(f"❌ خطأ في تحميل سعر الصرف: {e}")
        return False

# دالة للتحقق من صحة الإعدادات
def validate_config():
    """التحقق من صحة الإعدادات الأساسية"""
    errors = []
    
    if not TOKEN:
        errors.append("❌ BOT_TOKEN غير موجود")
    
    if ADMIN_ID == 0:
        errors.append("⚠️ ADMIN_ID غير محدد (اختياري)")
    
    if DEPOSIT_GROUP == 0:
        errors.append("⚠️ DEPOSIT_GROUP غير محدد (اختياري)")
    
    if ORDERS_GROUP == 0:
        errors.append("⚠️ ORDERS_GROUP غير محدد (اختياري)")
    
    return errors

# طباعة التحقق عند التشغيل
config_errors = validate_config()
if config_errors:
    for error in config_errors:
        print(error)
else:
    print("✅ جميع الإعدادات الأساسية صحيحة")
