import asyncio
import logging
import sys
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import BOT_TOKEN, WEBHOOK_PATH, WEBHOOK_URL, PORT
import database as db
from handlers import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot, db_pool):
    logger.info("🚀 جاري إعداد الويب هوك...")
    await bot.set_webhook(
        WEBHOOK_URL,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )
    logger.info(f"✅ تم ربط الويب هوك بالرابط: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot, db_pool):
    logger.info("🛑 جاري إيقاف البوت...")
    await bot.delete_webhook()
    await db_pool.close()
    await bot.session.close()

async def main():
    # تهيئة قاعدة البيانات
    db_pool = await db.init_db()
    if not db_pool:
        logger.error("❌ فشل الاتصال بقاعدة البيانات. تأكد من رابط DATABASE_URL.")
        sys.exit(1)

    # إعداد البوت والـ Dispatcher
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # تمرير الـ pool لكل الـ handlers
    dp["db_pool"] = db_pool
    dp.include_router(router)
    
    # إعداد تطبيق الويب لـ Render
    app = web.Application()
    
    # تسجيل معالج الويب هوك
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # دوال الإقلاع والإطفاء
    app.on_startup.append(lambda app: on_startup(bot, db_pool))
    app.on_cleanup.append(lambda app: on_shutdown(bot, db_pool))

    # إضافة صفحة فحص (Health Check) لكي يعلم Render أن السيرفر يعمل
    async def health_check(request):
        return web.json_response({"status": "ok", "bot": "running"})
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)

    # تشغيل الخادم
    logger.info(f"🌐 جاري تشغيل الخادم على المنفذ {PORT}...")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    # إبقاء السيرفر يعمل
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("تم إيقاف البوت يدوياً.")