# run_bot_webhook.py
import asyncio
import logging
import os
import sys
import signal
import time
from typing import Optional
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.types import BotCommand
from aiohttp import web
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    TOKEN, ADMIN_ID, DEBUG, LOG_LEVEL, LOG_FORMAT, LOG_FILE,
    WEBHOOK_PATH, WEBHOOK_PORT, WEBHOOK_HOST, WEBHOOK_URL,
    load_exchange_rate, load_bot_settings
)
from database.connection import get_pool, init_db, DAMASCUS_TZ
from database.points import fix_points_history_table
from database.stats import get_report_settings
from database.admin import fix_manual_vip_for_existing_users

from handlers import start, deposit, services, reports
from admin import router as admin_router
from handlers.middleware import BotStatusMiddleware, refresh_bot_status_cache
from handlers.reports import send_daily_report
from cache import clear_cache, get_cache_stats, Cache

# ============= إعداد التسجيل (Logging) =============

# إعداد تنسيق التسجيل
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        *([logging.FileHandler(LOG_FILE)] if LOG_FILE else [])
    ]
)

logger = logging.getLogger(__name__)

# ============= متغيرات عامة =============
scheduler: Optional[AsyncIOScheduler] = None
db_pool = None
bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None
app: Optional[web.Application] = None
runner: Optional[web.AppRunner] = None
start_time = time.time()

# ============= معالجة إشارات الإيقاف =============

def handle_exit_signal():
    """معالجة إشارات الإيقاف"""
    logger.info("📥 استقبال إشارة إيقاف...")
    asyncio.create_task(shutdown())

def setup_signal_handlers():
    """إعداد معالجات الإشارات"""
    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_exit_signal)

# ============= دوال التشغيل الأساسية =============

async def set_bot_commands(bot: Bot):
    """تعيين أوامر البوت في القائمة الجانبية"""
    commands = [
        BotCommand(command="start", description="🚀 بدء استخدام البوت"),
        BotCommand(command="cancel", description="❌ إلغاء العملية الحالية"),
        BotCommand(command="help", description="❓ مساعدة"),
    ]
    
    # أوامر إضافية للمشرفين
    if ADMIN_ID:
        commands.append(BotCommand(command="admin", description="🛠 لوحة التحكم"))
    
    try:
        await bot.set_my_commands(commands)
        logger.info("✅ تم تعيين أوامر البوت في القائمة الجانبية")
    except Exception as e:
        logger.error(f"❌ خطأ في تعيين الأوامر: {e}")

async def init_database():
    """تهيئة قاعدة البيانات"""
    global db_pool
    
    logger.info("📦 جاري الاتصال بقاعدة البيانات...")
    
    # إنشاء مجمع الاتصالات
    db_pool = await get_pool()
    
    if not db_pool:
        logger.error("❌ فشل بدء البوت: تعذر الاتصال بقاعدة البيانات")
        return False

    # تهيئة قاعدة البيانات
    try:
        await init_db(db_pool)
        logger.info("✅ تم تهيئة قاعدة البيانات")
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
        return False
    
    # إصلاح الجداول
    try:
        await fix_points_history_table(db_pool)
        logger.info("✅ تم إصلاح جداول النقاط")
    except Exception as e:
        logger.warning(f"⚠️ خطأ في إصلاح جداول النقاط: {e}")
    
    # إصلاح الـ VIP اليدوي
    try:
        await fix_manual_vip_for_existing_users(db_pool)
        logger.info("✅ تم إصلاح مستويات VIP اليدوية")
    except Exception as e:
        logger.warning(f"⚠️ خطأ في إصلاح VIP: {e}")
    
    return True

async def check_timezone():
    """التحقق من المنطقة الزمنية"""
    async with db_pool.acquire() as conn:
        db_time_now = await conn.fetchval("SELECT NOW()")
        db_time_damascus = await conn.fetchval("SELECT NOW() AT TIME ZONE 'Asia/Damascus'")
        current_local = datetime.now(DAMASCUS_TZ)
        
        logger.info(f"🕒 وقت السيرفر المحلي: {current_local.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"🕒 وقت DB (خام): {db_time_now}")
        logger.info(f"🕒 وقت DB (دمشق): {db_time_damascus}")

async def init_bot():
    """تهيئة البوت"""
    global bot, dp
    
    # إنشاء البوت
    bot = Bot(token=TOKEN)
    
    # إنشاء Dispatcher وتمرير db_pool
    dp = Dispatcher()
    dp["db_pool"] = db_pool
    
    # إضافة ميدل وير
    dp.message.middleware(BotStatusMiddleware(db_pool))
    dp.callback_query.middleware(BotStatusMiddleware(db_pool))
    
    # تسجيل الهاندلرز
    dp.include_routers(
        start.router,
        admin_router,
        deposit.router,
        services.router,
        reports.router
    )
    
    logger.info("✅ تم تهيئة البوت والـ Dispatcher")
    return True

async def init_scheduler():
    """تهيئة جدولة التقرير اليومي"""
    global scheduler
    
    try:
        # إيقاف الجدولة القديمة إذا كانت موجودة
        if scheduler and scheduler.running:
            scheduler.shutdown()
        
        # جلب إعدادات الوقت من قاعدة البيانات
        settings = await get_report_settings(db_pool)
        report_time = settings.get('report_time', '00:00')
        hour, minute = map(int, report_time.split(':'))
        
        scheduler = AsyncIOScheduler(timezone='Asia/Damascus')
        
        scheduler.add_job(
            send_daily_report,
            'cron',
            hour=hour,
            minute=minute,
            args=[bot, db_pool],
            id='daily_report',
            replace_existing=True,
            misfire_grace_time=3600  # ساعة واحدة سماح
        )
        
        scheduler.start()
        logger.info(f"✅ تم تفعيل التقرير اليومي (الساعة {report_time})")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة الجدولة: {e}")
        return False

async def setup_webhook():
    """إعداد webhook"""
    try:
        # إعدادات webhook
        port = int(os.environ.get('PORT', WEBHOOK_PORT))
        host = os.environ.get('RENDER_EXTERNAL_URL', WEBHOOK_HOST)
        
        if not host:
            host = f"http://localhost:{port}"
            logger.warning("⚠️ لم يتم تحديد WEBHOOK_HOST، استخدام localhost")
        
        base_url = host.rstrip('/')
        webhook_url = f"{base_url}{WEBHOOK_PATH}"
        
        # تعيين webhook
        await bot.set_webhook(
            webhook_url,
            max_connections=50,
            allowed_updates=["message", "callback_query", "chat_member"],
            drop_pending_updates=True,
            secret_token=os.getenv("WEBHOOK_SECRET", "")  # أمان إضافي
        )
        
        logger.info(f"✅ تم تعيين webhook: {webhook_url}")
        return port, base_url
    except Exception as e:
        logger.error(f"❌ خطأ في إعداد webhook: {e}")
        raise

async def create_web_app(base_url: str) -> web.Application:
    """إنشاء تطبيق الويب"""
    global app
    
    app = web.Application()
    
    # إضافة مسار webhook
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        **{"db_pool": db_pool}
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # إعداد التطبيق
    setup_application(app, dp, bot=bot)
    
    # مسار للتحقق من الصحة
    async def health(request):
        uptime = time.time() - start_time
        cache_stats = get_cache_stats()
        
        return web.json_response({
            "status": "OK",
            "uptime": f"{uptime:.2f} seconds",
            "cache": {
                "total_keys": cache_stats.get('total_keys', 0),
                "hit_rate": cache_stats.get('hit_rate', '0%')
            },
            "bot": "running"
        })
    app.router.add_get('/health', health)
    
    # مسار المعلومات
    async def info(request):
        return web.json_response({
            "name": "LINK Charger Bot",
            "version": "1.0.0",
            "description": "Telegram bot for charging services",
            "webhook": f"{base_url}{WEBHOOK_PATH}"
        })
    app.router.add_get('/info', info)
    
    # الصفحة الرئيسية
    async def index(request):
        uptime = time.time() - start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        return web.Response(
            text=f"""
            <html>
                <head><title>LINK Charger Bot</title></head>
                <body style="font-family: Arial; text-align: center; margin-top: 50px;">
                    <h1>🤖 LINK Charger Bot</h1>
                    <p>البوت يعمل بنجاح!</p>
                    <p>⏱️ وقت التشغيل: {hours} ساعة {minutes} دقيقة</p>
                    <p>🔗 Webhook: <a href="{base_url}{WEBHOOK_PATH}">{base_url}{WEBHOOK_PATH}</a></p>
                    <p>📊 <a href="/health">فحص الصحة</a> | ℹ️ <a href="/info">معلومات</a></p>
                </body>
            </html>
            """,
            content_type="text/html"
        )
    app.router.add_get('/', index)
    
    logger.info(f"✅ تم إنشاء تطبيق الويب على {base_url}")
    return app

async def start_server(port: int):
    """تشغيل الخادم"""
    global runner
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"✅ الخادم يعمل على المنفذ {port}")
    return runner

async def shutdown():
    """إيقاف التشغيل بشكل آمن"""
    logger.info("🛑 جاري إيقاف البوت...")
    
    # إيقاف الجدولة
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("✅ تم إيقاف الجدولة")
    
    # إيقاف الـ runner
    if runner:
        await runner.cleanup()
        logger.info("✅ تم إيقاف خادم الويب")
    
    # إغلاق مجمع الاتصالات
    if db_pool:
        await db_pool.close()
        logger.info("✅ تم إغلاق مجمع اتصالات قاعدة البيانات")
    
    # مسح الكاش
    clear_cache()
    logger.info("✅ تم مسح الكاش")
    
    # حذف webhook
    if bot:
        try:
            await bot.delete_webhook()
            logger.info("✅ تم حذف webhook")
        except Exception as e:
            logger.error(f"❌ خطأ في حذف webhook: {e}")
        await bot.session.close()
    
    logger.info("👋 تم إيقاف البوت بنجاح")
    
    # إنهاء العملية
    sys.exit(0)

async def main():
    """الدالة الرئيسية لتشغيل البوت"""
    global start_time
    start_time = time.time()
    
    logger.info("🚀 بدأ تشغيل البوت...")
    logger.info(f"🔧 وضع التطوير: {'نعم' if DEBUG else 'لا'}")
    
    try:
        # 1. تهيئة قاعدة البيانات
        if not await init_database():
            logger.error("❌ فشل تهيئة قاعدة البيانات")
            return
        
        # 2. التحقق من الوقت
        await check_timezone()
        
        # 3. تحميل الإعدادات من قاعدة البيانات
        try:
            await load_exchange_rate(db_pool)
            await load_bot_settings(db_pool)
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل الإعدادات: {e}")
        
        # 4. تهيئة البوت
        if not await init_bot():
            logger.error("❌ فشل تهيئة البوت")
            return
        
        # 5. تحديث كاش حالة البوت
        await refresh_bot_status_cache(db_pool)
        
        # 6. مسح الكاش عند بدء التشغيل
        clear_cache()
        
        # 7. تعيين الأوامر
        await set_bot_commands(bot)
        
        # 8. تهيئة الجدولة
        await init_scheduler()
        
        # 9. إعداد webhook
        port, base_url = await setup_webhook()
        
        # 10. إنشاء تطبيق الويب
        await create_web_app(base_url)
        
        # 11. تشغيل الخادم
        await start_server(port)
        
        # 12. إحصائيات البداية
        elapsed = time.time() - start_time
        logger.info(f"✅ تم بدء التشغيل بنجاح في {elapsed:.2f} ثانية")
        logger.info(f"📊 إحصائيات الكاش: {get_cache_stats()}")
        
        # 13. الانتظار إلى أجل غير مسمى
        await asyncio.Event().wait()
        
    except asyncio.CancelledError:
        logger.info("⏹️ تم إلغاء المهمة")
    except Exception as e:
        logger.error(f"❌ خطأ عام: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await shutdown()

# ============= نقطة الدخول الرئيسية =============

if __name__ == "__main__":
    try:
        # إعداد معالجات الإشارات
        setup_signal_handlers()
        
        # تشغيل البوت
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
        import traceback
        traceback.print_exc()