# config.py
import os
from dotenv import load_dotenv

# تحميل المتغيرات من ملف .env
load_dotenv()

# التوكن والإعدادات الأساسية
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MODERATORS = [int(x) for x in os.getenv("MODERATORS", "").split(",") if x]

# قاعدة البيانات
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "charging_bot"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "")
}

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
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "5000"))

# سعر الصرف الافتراضي
USD_TO_SYP = int(os.getenv("DEFAULT_USD_TO_SYP", "118"))
BOT_STATUS = True  # حالة البوت (يعمل/متوقف)

# إعدادات API (اختياري)
EXTERNAL_API_URL = os.getenv("EXTERNAL_API_URL", "https://api.example.com/order")
EXTERNAL_API_KEY = os.getenv("EXTERNAL_API_KEY", "")

# أقسام التطبيقات
APP_CATEGORIES = {
    "games": "🎮 ألعاب",
    "services": "🛠 خدمات"
}

# دالة لتحميل سعر الصرف من قاعدة البيانات
async def load_exchange_rate(pool):
    """تحميل سعر الصرف من قاعدة البيانات"""
    from database import get_exchange_rate
    global USD_TO_SYP
    USD_TO_SYP = await get_exchange_rate(pool)
    print(f"💵 تم تحميل سعر الصرف: {USD_TO_SYP} ل.س")