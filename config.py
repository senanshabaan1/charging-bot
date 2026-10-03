import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "ضع_توكن_البوت_هنا_اذا_لم_تستخدم_متغيرات_البيئة")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789")) # ضع آيدي حسابك هنا
DATABASE_URL = os.getenv("DATABASE_URL") # رابط قاعدة بيانات PostgreSQL

# إعدادات الويب هوك لـ Render
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 8000))