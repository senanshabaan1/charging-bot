# run_bot_webhook.py
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from config import TOKEN, ADMIN_ID
from database import init_db, get_pool, fix_points_history_table  # أضف fix_points_history_table هنا
from handlers import start, deposit, services, admin
import pytz
from datetime import datetime

logging.basicConfig(level=logging.INFO)

# ضبط المنطقة الزمنية لدمشق
DAMASCUS_TZ = pytz.timezone('Asia/Damascus')

async def on_startup(bot: Bot, base_url: str, db_pool):
    """تشغيل عند بدء التشغيل - تعيين webhook"""
    await bot.set_webhook(f"{base_url}/webhook")
    logging.info(f"✅ تم تعيين webhook: {base_url}/webhook")
    logging.info("✅ البوت جاهز لاستقبال التحديثات")

async def on_shutdown(bot: Bot):
    """تشغيل عند الإيقاف - حذف webhook"""
    await bot.delete_webhook()
    logging.info("✅ تم حذف webhook")

async def set_timezone_for_connection(conn):
    """ضبط المنطقة الزمنية لاتصال قاعدة البيانات"""
    try:
        await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
        current_time = await conn.fetchval("SELECT NOW()")
        logging.info(f"🕒 وقت قاعدة البيانات بعد الضبط: {current_time}")
    except Exception as e:
        logging.error(f"⚠️ خطأ في ضبط المنطقة الزمنية: {e}")

async def main():
    logging.info("🚀 بدأ تشغيل البوت...")
    
    # إنشاء مجمع الاتصالات أولاً
    db_pool = await get_pool()
    if not db_pool:
        logging.error("❌ فشل الاتصال بقاعدة البيانات")
        return
    
    # ضبط المنطقة الزمنية لكل اتصال جديد
    async with db_pool.acquire() as conn:
        await set_timezone_for_connection(conn)
    
    logging.info(f"🕒 الوقت الحالي في النظام: {datetime.now(DAMASCUS_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    
    # تهيئة قاعدة البيانات وإصلاحها
    await init_db()
    await fix_points_history_table(db_pool)
    logging.info("✅ تم تهيئة قاعدة البيانات")
    
    # تحميل سعر الصرف
    try:
        from config import load_exchange_rate
        await load_exchange_rate(db_pool)
        logging.info("✅ تم تحميل سعر الصرف")
    except Exception as e:
        logging.error(f"❌ خطأ في تحميل سعر الصرف: {e}")
    
    # إنشاء البوت
    bot = Bot(token=TOKEN)
    
    # إنشاء Dispatcher وتمرير db_pool
    dp = Dispatcher()
    dp["db_pool"] = db_pool

    
    # ========== Middleware للتحقق من حالة البوت (معدل) ==========
    @dp.message.middleware()
    async def check_bot_status_middleware(handler, event, data):
        """التحقق من حالة البوت قبل معالجة الأوامر"""
        from database import get_bot_status, get_maintenance_message
        
        # جلب db_pool من الـ data
        pool = data.get('db_pool')
        if not pool:
            return await handler(event, data)
        
        user = event.from_user
        from config import ADMIN_ID, MODERATORS
        
        # تحقق من حالة البوت
        bot_status = await get_bot_status(pool)
        
        # إذا البوت متوقف والمستخدم ليس مشرف
        if not bot_status and user.id != ADMIN_ID and user.id not in MODERATORS:
            msg = await get_maintenance_message(pool)
            
            if isinstance(event, types.Message):
                await event.answer(f"🛠 {msg}")
            elif isinstance(event, types.CallbackQuery):
                await event.answer(msg, show_alert=True)
            return  # منع معالجة الحدث
        
        return await handler(event, data)
    
    # نفس الميدل وير للـ callback queries
    @dp.callback_query.middleware()
    async def check_bot_status_callback_middleware(handler, event, data):
        """التحقق من حالة البوت قبل معالجة الأزرار"""
        from database import get_bot_status, get_maintenance_message
        
        pool = data.get('db_pool')
        if not pool:
            return await handler(event, data)
        
        user = event.from_user
        from config import ADMIN_ID, MODERATORS
        
        bot_status = await get_bot_status(pool)
        
        if not bot_status and user.id != ADMIN_ID and user.id not in MODERATORS:
            msg = await get_maintenance_message(pool)
            await event.answer(msg, show_alert=True)
            return
        
        return await handler(event, data)
    # =========================================================
    
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
    
    # إضافة مسار webhook مع تمرير البيانات
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        **{"db_pool": db_pool}  # تمرير db_pool هنا أيضاً
    )
    webhook_requests_handler.register(app, path="/webhook")
    
    # إعداد التطبيق
    setup_application(app, dp, bot=bot)
    
    # إضافة مسار للتحقق من الصحة
    async def health(request):
        return web.Response(text="OK")
    app.router.add_get('/health', health)
    
    # إضافة مسار للصفحة الرئيسية (يعطي رسالة بسيطة)
    async def index(request):
        return web.Response(text="🤖 البوت شغال! هذا هو رابط webhook للبوت.")
    app.router.add_get('/', index)
    
    logging.info(f"✅ البوت جاهز للاستخدام على {BASE_URL}")
    
    # تشغيل الخادم
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    
    # تعيين webhook عند بدء التشغيل
    await on_startup(bot, BASE_URL, db_pool)
    
    try:
        await site.start()
        logging.info(f"✅ الخادم يعمل على المنفذ {PORT}")
        await asyncio.Event().wait()  # الانتظار إلى الأبد
    except KeyboardInterrupt:
        logging.info("⏹️ تم إيقاف البوت")
    finally:
        await on_shutdown(bot)
        await runner.cleanup()
        await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())
