# run_bot_webhook.py
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from config import TOKEN, ADMIN_ID
from database import init_db, get_pool
from handlers import start, deposit, services, admin

logging.basicConfig(level=logging.INFO)

async def on_startup(bot: Bot, base_url: str):
    """تشغيل عند بدء التشغيل - تعيين webhook"""
    await bot.set_webhook(f"{base_url}/webhook")
    logging.info(f"✅ تم تعيين webhook: {base_url}/webhook")

async def on_shutdown(bot: Bot):
    """تشغيل عند الإيقاف - حذف webhook"""
    await bot.delete_webhook()
    logging.info("✅ تم حذف webhook")

async def main():
    logging.info("🚀 بدأ تشغيل البوت...")
    
    # تهيئة قاعدة البيانات
    await init_db()
    
    # إنشاء مجمع الاتصالات
    db_pool = await get_pool()
    
    # تحميل سعر الصرف
    try:
        from config import load_exchange_rate
        await load_exchange_rate(db_pool)
    except Exception as e:
        logging.error(f"❌ خطأ في تحميل سعر الصرف: {e}")
    
    # إنشاء البوت
    bot = Bot(token=TOKEN)
    
    # إنشاء Dispatcher
    dp = Dispatcher()
    
    # تسجيل الهاندلرز
    dp.include_routers(
        admin.router,
        start.router,
        deposit.router,
        services.router
    )
    
    # إعدادات webhook
    PORT = int(os.environ.get('PORT', 8000))
    BASE_URL = os.environ.get('RENDER_EXTERNAL_URL', f'http://localhost:{PORT}')
    
    # إنشاء تطبيق aiohttp
    app = web.Application()
    
    # إضافة مسار webhook
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    
    # إضافة مسار للتحقق من الصحة
    async def health(request):
        return web.Response(text="OK")
    app.router.add_get('/health', health)
    
    logging.info(f"✅ البوت جاهز للاستخدام على {BASE_URL}")
    
    # تشغيل الخادم
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    
    # تعيين webhook عند بدء التشغيل
    await on_startup(bot, BASE_URL)
    
    try:
        await site.start()
        logging.info(f"✅ الخادم يعمل على المنفذ {PORT}")
        await asyncio.Event().wait()
    finally:
        await on_shutdown(bot)
        await runner.cleanup()
        await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())