# config.py
import os
from dotenv import load_dotenv
import re
from urllib.parse import quote_plus

# تحميل المتغيرات من ملف .env (للتشغيل المحلي فقط)
if os.path.exists('.env'):
    load_dotenv()

# التوكن والإعدادات الأساسية
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MODERATORS = [int(x) for x in os.getenv("MODERATORS", "").split(",") if x]

# ====== قسم قاعدة البيانات المعدل لـ Supabase ======
# الأولوية لـ DATABASE_URL من متغيرات البيئة
DATABASE_URL = os.getenv("DATABASE_URL")

print(f"🔍 DATABASE_URL found: {'Yes' if DATABASE_URL else 'No'}")

if DATABASE_URL:
    # تحليل رابط PostgreSQL
    try:
        # نقبل الرابط ببداية postgresql:// أو postgres://
        match = re.match(r'postgres(?:ql)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', DATABASE_URL)
        if match:
            user, password, host, port, database = match.groups()
            DB_CONFIG = {
                "host": host,
                "port": int(port),
                "database": database,
                "user": user,
                "password": password
            }
            print(f"✅ Using Supabase database: {host}/{database}")
        else:
            # إذا ما انطابق النمط، استخدم الرابط مباشرة
            print("⚠️ DATABASE_URL format not recognized, using as dsn")
            DB_CONFIG = {
                "dsn": DATABASE_URL
            }
    except Exception as e:
        print(f"⚠️ Error parsing DATABASE_URL: {e}, using fallback config")
        # بيانات Supabase من متغيرات البيئة الفردية
        DB_CONFIG = {
            "host": os.getenv("DB_HOST", "aws-1-ap-northeast-1.pooler.supabase.com"),
            "port": int(os.getenv("DB_PORT", "6543")),
            "database": os.getenv("DB_NAME", "postgres"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "3xQx4Ve3!123")
        }
else:
    print("⚠️ No DATABASE_URL found, using local config")
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "aws-1-ap-northeast-1.pooler.supabase.com"),
        "port": int(os.getenv("DB_PORT", "6543")),
        "database": os.getenv("DB_NAME", "postgres"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "3xQx4Ve3!123")
    }
# =======================================

# أرقام الدفع
SYRIATEL_NUMS = os.getenv("SYRIATEL_NUMS", "").split(",")
SHAM_CASH_NUM = os.getenv("SHAM_CASH_NUM", "")
SHAM_CASH_NUM_USD = os.getenv("SHAM_CASH_NUM_USD", "")
USDT_BEP20_WALLET = os.getenv("USDT_BEP20_WALLET", "")

# مجموعات الإدارة
DEPOSIT_GROUP = int(os.getenv("DEPOSIT_GROUP", "0"))
ORDERS_GROUP = int(os.getenv("ORDERS_GROUP", "0"))

# إعدادات الويب
WEB_USERNAME = os.getenv("WEB_USERNAME", "admin")
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "admin")

# سعر الصرف الافتراضي
USD_TO_SYP = int(os.getenv("DEFAULT_USD_TO_SYP", "118"))
BOT_STATUS = True

# دالة لتحميل سعر الصرف من قاعدة البيانات
async def load_exchange_rate(pool):
    from database import get_exchange_rate
    global USD_TO_SYP
    USD_TO_SYP = await get_exchange_rate(pool)
    print(f"💵 تم تحميل سعر الصرف: {USD_TO_SYP} ل.س")
