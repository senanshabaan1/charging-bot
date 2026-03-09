# run_bot_webhook.py
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from config import TOKEN, ADMIN_ID
from database.connection import get_pool, set_database_timezone, update_old_records_timezone, DAMASCUS_TZ
from database import init_db  # init_db موجود في __init__.py
from database.points import fix_points_history_table
from database.stats import get_report_settings

from handlers import (
    start, deposit, services, reports, profile_handlers
)
from admin import router as admin_router  
from handlers.middleware import BotStatusMiddleware, refresh_bot_status_cache
import pytz
from datetime import datetime
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from handlers.reports import send_daily_report
from cache import clear_cache, get_cache_stats
import time
# متغيرات عامة
scheduler = None
db_pool = None
bot = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ضبط المنطقة الزمنية لدمشق
DAMASCUS_TZ = pytz.timezone('Asia/Damascus')

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
    
    await bot.set_my_commands(commands)
    logger.info("✅ تم تعيين أوامر البوت في القائمة الجانبية")

async def on_startup(bot: Bot, base_url: str, db_pool):
    """تشغيل عند بدء التشغيل"""
    try:
        # تعيين الأوامر
        await set_bot_commands(bot)
        
        # تحديث كاش حالة البوت
        await refresh_bot_status_cache(db_pool)
                # مسح الكاش عند بدء التشغيل
        clear_cache()
        
        # ✅ تحسين webhook
        await bot.set_webhook(
            f"{base_url}/webhook",
            max_connections=50,  # زيادة الاتصالات
            allowed_updates=["message", "callback_query", "chat_member"],
            drop_pending_updates=True  # تجاهل التحديثات القديمة
        )
        
        logger.info(f"✅ تم تعيين webhook: {base_url}/webhook")
        logger.info(f"📊 إحصائيات الكاش: {get_cache_stats()}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في بدء التشغيل: {e}")


async def on_shutdown(bot: Bot):
    """تشغيل عند الإيقاف"""
    try:
        await bot.delete_webhook()
        clear_cache()
        logger.info("✅ تم حذف webhook ومسح الكاش")
    except Exception as e:
        logger.error(f"❌ خطأ في حذف webhook: {e}")

async def set_timezone_for_connection(conn):
    """ضبط المنطقة الزمنية لاتصال قاعدة البيانات"""
    try:
        await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
        current_time = await conn.fetchval("SELECT NOW()")
        logger.info(f"🕒 وقت قاعدة البيانات بعد الضبط: {current_time}")
    except Exception as e:
        logger.error(f"⚠️ خطأ في ضبط المنطقة الزمنية: {e}")

async def init_scheduler(bot: Bot, db_pool):
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
            replace_existing=True
        )
        
        scheduler.start()
        logger.info(f"✅ تم تفعيل التقرير اليومي (الساعة {report_time})")
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة الجدولة: {e}")

async def main():
    """الدالة الرئيسية لتشغيل البوت"""
    global db_pool, bot
    
    logger.info("🚀 بدأ تشغيل البوت...")
    
    try:
        # 1. إنشاء مجمع الاتصالات
        db_pool = await get_pool()
        
        if not db_pool:
            logger.error("❌ فشل بدء البوت: تعذر الاتصال بقاعدة البيانات")
            return

        # 2. تهيئة قاعدة البيانات
        await init_db(db_pool) 
        
        # 3. إصلاح الجداول إذا لزم الأمر
        await fix_points_history_table(db_pool)
        
        logger.info("✅ تم تهيئة قاعدة البيانات وضبط المنطقة الزمنية بنجاح")
        
        # تحديث السجلات القديمة
        try:
            await update_old_records_timezone(db_pool)
            logger.info("✅ تم تحديث السجلات القديمة إلى التوقيت الصحيح")
        except Exception as e:
            logger.warning(f"⚠️ لم يتم تحديث السجلات القديمة: {e}")
        
        # التحقق من الوقت
        async with db_pool.acquire() as conn:
            db_time_now = await conn.fetchval("SELECT NOW()")
            db_time_damascus = await conn.fetchval("SELECT NOW() AT TIME ZONE 'Asia/Damascus'")
            current_local = datetime.now(DAMASCUS_TZ)
            
            logger.info(f"🕒 وقت السيرفر المحلي: {current_local.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"🕒 وقت DB (بعد الضبط): {db_time_now}")
            logger.info(f"🕒 وقت DB (دمشق): {db_time_damascus}")
        
        
        # تحميل سعر الصرف
        try:
            from config import load_exchange_rate
            await load_exchange_rate(db_pool)
            logger.info("✅ تم تحميل سعر الصرف")
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل سعر الصرف: {e}")
        
        # إنشاء Dispatcher وتمرير db_pool
        dp = Dispatcher()
        dp["db_pool"] = db_pool
        
        # إنشاء البوت
        bot = Bot(token=TOKEN)
        
        # ✅ إضافة ميدل وير
        dp.message.middleware(BotStatusMiddleware(db_pool))
        dp.callback_query.middleware(BotStatusMiddleware(db_pool))
        
        # تهيئة الجدولة
        await init_scheduler(bot, db_pool)
        
        # تسجيل الهاندلرز
        dp.include_routers(
            start.router,
            admin_router,
            deposit.router,
            services.router,
            reports.router
        )
        
        # إعدادات webhook
        PORT = int(os.environ.get('PORT', 8000))
        BASE_URL = os.environ.get('RENDER_EXTERNAL_URL', f'http://localhost:{PORT}')
        
        # إنشاء تطبيق aiohttp
        app = web.Application()
        
        # إضافة مسار webhook
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            **{"db_pool": db_pool}
        )
        webhook_requests_handler.register(app, path="/webhook")
        
        # إعداد التطبيق
        setup_application(app, dp, bot=bot)
        
        # مسار للتحقق من الصحة
        async def health(request):
            return web.Response(text="OK")
        app.router.add_get('/health', health)
        
        # الصفحة الرئيسية
        async def index(request):
            return web.Response(text="🤖 البوت شغال! هذا هو رابط webhook للبوت.")
        app.router.add_get('/', index)
        
        logger.info(f"✅ البوت جاهز للاستخدام على {BASE_URL}")
        
        # تشغيل الخادم
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        
        # تعيين webhook
        await on_startup(bot, BASE_URL, db_pool)
        
        try:
            await site.start()
            logger.info(f"✅ الخادم يعمل على المنفذ {PORT}")
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("⏹️ تم إيقاف البوت")
        finally:
            await on_shutdown(bot)
            await runner.cleanup()
            if db_pool:
                await db_pool.close()
                logger.info("✅ تم إغلاق مجمع اتصالات قاعدة البيانات بنجاح")
            if 'scheduler' in locals() and scheduler and scheduler.running:
                scheduler.shutdown()
    
    except Exception as e:
        logger.error(f"❌ خطأ عام: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
