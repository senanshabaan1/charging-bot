# run_bot_webhook.py
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from config import TOKEN, ADMIN_ID
from database import (
    init_db, get_pool, fix_points_history_table, 
    set_database_timezone, update_old_records_timezone, 
    get_report_settings, get_bot_status, get_maintenance_message,
    DAMASCUS_TZ
)
from handlers import (
    start, deposit, services, admin, reports, profile
)
import pytz
from datetime import datetime
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from handlers.reports import send_daily_report

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
        
        # تعيين webhook
        webhook_url = f"{base_url}/webhook"
        await bot.set_webhook(webhook_url)
        logger.info(f"✅ تم تعيين webhook: {webhook_url}")
        logger.info("✅ البوت جاهز لاستقبال التحديثات")
    except Exception as e:
        logger.error(f"❌ خطأ في بدء التشغيل: {e}")

async def on_shutdown(bot: Bot):
    """تشغيل عند الإيقاف"""
    try:
        await bot.delete_webhook()
        logger.info("✅ تم حذف webhook")
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

# ============= Middleware للتحقق من حالة البوت =============

async def is_user_admin(user_id):
    """التحقق من صلاحيات المستخدم"""
    from config import ADMIN_ID, MODERATORS
    return user_id == ADMIN_ID or user_id in MODERATORS

async def bot_status_middleware(handler, event, data):
    """ميدل وير موحد للتحقق من حالة البوت"""
    # التحقق من أوامر الإلغاء - تمريرها فوراً
    if hasattr(event, 'text') and event.text:
        if event.text.startswith(('/cancel', '/الغاء', '/رجوع', '/start', '/help')):
            return await handler(event, data)
    
    # التحقق من الكولباك - السماح ببعض الأزرار الأساسية
    if hasattr(event, 'data') and event.data:
        if event.data in ['back_to_main', 'back_to_admin', 'check_subscription']:
            return await handler(event, data)
    
    pool = data.get('db_pool')
    if not pool:
        return await handler(event, data)
    
    user = event.from_user
    
    # التحقق من حالة البوت
    try:
        bot_status = await get_bot_status(pool)
        
        # إذا البوت متوقف والمستخدم ليس مشرف
        if not bot_status and not await is_user_admin(user.id):
            msg = await get_maintenance_message(pool)
            
            if isinstance(event, types.Message):
                await event.answer(f"🛠 {msg}")
            elif isinstance(event, types.CallbackQuery):
                await event.answer(msg, show_alert=True)
            return
    except Exception as e:
        logger.error(f"❌ خطأ في ميدل وير الحالة: {e}")
    
    return await handler(event, data)

# ============================================================

async def main():
    """الدالة الرئيسية لتشغيل البوت"""
    global db_pool, bot
    
    logger.info("🚀 بدأ تشغيل البوت...")
    
    try:
        # إنشاء مجمع الاتصالات
        db_pool = await get_pool()
        if not db_pool:
            logger.error("❌ فشل الاتصال بقاعدة البيانات")
            return
        
        # تهيئة قاعدة البيانات
        await init_db()
        await fix_points_history_table(db_pool)
        logger.info("✅ تم تهيئة قاعدة البيانات")
        
        # ضبط المنطقة الزمنية
        async with db_pool.acquire() as conn:
            await set_timezone_for_connection(conn)
        
        await set_database_timezone(db_pool)
        
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
        
        # إضافة الألعاب الأساسية
        try:
            from database import init_games
            await init_games(db_pool)
            logger.info("✅ تم التحقق من الألعاب")
        except Exception as e:
            logger.warning(f"⚠️ لم يتم إضافة الألعاب: {e}")
        
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
        
        # إضافة الميدل وير الموحد
        dp.message.middleware()(bot_status_middleware)
        dp.callback_query.middleware()(bot_status_middleware)
        
        # تهيئة الجدولة
        await init_scheduler(bot, db_pool)
        
        # تسجيل الهاندلرز - ترتيب مهم
        dp.include_routers(
            start.router,
            admin.router,
            deposit.router,
            services.router,
            profile.router,
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
        
        # تعيين webhook عند بدء التشغيل
        await on_startup(bot, BASE_URL, db_pool)
        
        try:
            await site.start()
            logger.info(f"✅ الخادم يعمل على المنفذ {PORT}")
            await asyncio.Event().wait()  # الانتظار إلى الأبد
        except KeyboardInterrupt:
            logger.info("⏹️ تم إيقاف البوت")
        finally:
            await on_shutdown(bot)
            await runner.cleanup()
            if db_pool:
                await db_pool.close()
            if scheduler and scheduler.running:
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
