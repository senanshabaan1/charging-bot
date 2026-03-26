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
    load_exchange_rate, load_bot_settings, load_all_exchange_rates  # ✅ إضافة load_all_exchange_rates
)
from database.connection import get_pool, init_db, DAMASCUS_TZ
from database.points import fix_points_history_table
from database.stats import get_report_settings
from database.admin import fix_manual_vip_for_existing_users
from database.core import get_all_exchange_rates, get_active_global_offer, get_active_deposit_bonus  # ✅ إضافة دوال العروض
from utils.api_client import api_client  # ✅ استيراد عميل API

from handlers import start, deposit, services, reports
from admin import router as admin_router
from handlers.middleware import BotStatusMiddleware, refresh_bot_status_cache
from handlers.reports import send_daily_report
from cache import clear_cache, get_cache_stats

# ============= إعداد التسجيل (Logging) =============

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
    
    try:
        db_pool = await get_pool()
        
        if not db_pool:
            logger.error("❌ فشل إنشاء مجمع الاتصالات")
            return False

        async with db_pool.acquire() as conn:
            test = await conn.fetchval("SELECT 1")
            if test != 1:
                logger.error("❌ فشل اختبار الاتصال بقاعدة البيانات")
                return False
            logger.info("✅ تم اختبار الاتصال بقاعدة البيانات بنجاح")

        await init_db(db_pool)
        logger.info("✅ تم تهيئة قاعدة البيانات")
        
        try:
            await fix_points_history_table(db_pool)
            logger.info("✅ تم إصلاح جداول النقاط")
        except Exception as e:
            logger.warning(f"⚠️ خطأ في إصلاح جداول النقاط: {e}")
        
        try:
            await fix_manual_vip_for_existing_users(db_pool)
            logger.info("✅ تم إصلاح مستويات VIP اليدوية")
        except Exception as e:
            logger.warning(f"⚠️ خطأ في إصلاح VIP: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_timezone():
    """التحقق من المنطقة الزمنية"""
    try:
        async with db_pool.acquire() as conn:
            db_time_now = await conn.fetchval("SELECT NOW()")
            db_time_damascus = await conn.fetchval("SELECT NOW() AT TIME ZONE 'Asia/Damascus'")
            current_local = datetime.now(DAMASCUS_TZ)
            
            logger.info(f"🕒 وقت السيرفر المحلي: {current_local.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"🕒 وقت DB (خام): {db_time_now}")
            logger.info(f"🕒 وقت DB (دمشق): {db_time_damascus}")
    except Exception as e:
        logger.error(f"❌ خطأ في التحقق من الوقت: {e}")


async def load_all_settings():
    """تحميل جميع الإعدادات من قاعدة البيانات"""
    try:
        # ✅ تحميل أسعار الصرف المنفصلة
        rates = await get_all_exchange_rates(db_pool)
        logger.info(f"💰 تم تحميل أسعار الصرف: شراء={rates.get('purchase', 118)}, إيداع={rates.get('deposit', 118)}, نقاط={rates.get('points', 118)}")
        
        # ✅ تحميل رابط API
        async with db_pool.acquire() as conn:
            api_url = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'api_base_url'")
            if api_url:
                api_client.base_url = api_url.rstrip('/')
                logger.info(f"🌐 تم تحميل رابط API: {api_client.base_url}")
        
        # ✅ تحميل العروض النشطة
        active_offer = await get_active_global_offer(db_pool)
        if active_offer:
            logger.info(f"🎁 عرض نشط: {active_offer['discount_percent']}% خصم حتى {active_offer['end_date']}")
        
        active_bonus = await get_active_deposit_bonus(db_pool)
        if active_bonus:
            logger.info(f"💰 مكافأة نشطة: {active_bonus['bonus_percent']}% على الإيداع")
        
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في تحميل الإعدادات: {e}")
        return False


async def init_bot():
    """تهيئة البوت"""
    global bot, dp
    
    try:
        bot = Bot(token=TOKEN)
        
        dp = Dispatcher()
        dp["db_pool"] = db_pool
        
        dp.message.middleware(BotStatusMiddleware(db_pool))
        dp.callback_query.middleware(BotStatusMiddleware(db_pool))
        
        dp.include_routers(
            start.router,
            admin_router,
            deposit.router,
            services.router,
            reports.router
        )
        
        logger.info("✅ تم تهيئة البوت والـ Dispatcher")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة البوت: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============= مهام التحديث التلقائي =============
async def auto_sync_services():
    """تحديث قائمة الخدمات تلقائياً"""
    try:
        async with db_pool.acquire() as conn:
            auto_sync = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'auto_sync_services'"
            )
            
            if auto_sync == "enabled":
                logger.info("🔄 بدء التحديث التلقائي للخدمات...")
                products = await api_client.get_products(force_refresh=True)
                if products:
                    logger.info(f"✅ تم تحديث {len(products)} خدمة تلقائياً")
                else:
                    logger.warning("⚠️ فشل التحديث التلقائي للخدمات")
    except Exception as e:
        logger.error(f"❌ خطأ في التحديث التلقائي: {e}")


async def check_pending_orders_auto():
    """التحقق من الطلبات المعلقة وتحديث حالتها تلقائياً"""
    try:
        async with db_pool.acquire() as conn:
            orders = await conn.fetch('''
                SELECT id, api_order_id, user_id, app_name
                FROM orders 
                WHERE status IN ('processing', 'pending') 
                AND api_order_id IS NOT NULL
                AND api_order_id != ''
                AND api_order_id != 'null'
            ''')
            
            if orders:
                order_ids = [order['api_order_id'] for order in orders]
                api_result = await api_client.check_orders(order_ids)
                
                if api_result:
                    for order in orders:
                        if isinstance(api_result, list):
                            order_data = next((item for item in api_result if str(item.get('order_id')) == str(order['api_order_id'])), None)
                        else:
                            order_data = api_result.get(order['api_order_id'])
                        
                        if order_data and isinstance(order_data, dict):
                            status = order_data.get('status', '')
                            
                            if status in ['completed', 'done', 'finished']:
                                await conn.execute(
                                    "UPDATE orders SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                                    order['id']
                                )
                                
                                points = await conn.fetchval(
                                    "SELECT value::integer FROM bot_settings WHERE key = 'points_per_order'"
                                ) or 1
                                
                                await conn.execute(
                                    "UPDATE users SET total_points = total_points + $1 WHERE user_id = $2",
                                    points, order['user_id']
                                )
                                
                                await bot.send_message(
                                    order['user_id'],
                                    f"✅ **تم اكتمال طلبك #{order['id']} بنجاح!**\n\n"
                                    f"📱 **التطبيق:** {order['app_name']}\n"
                                    f"⭐ **نقاط مكتسبة:** +{points}\n"
                                    f"🎉 شكراً لاستخدامك خدماتنا",
                                    parse_mode="Markdown"
                                )
                                
                                logger.info(f"✅ تم تحديث الطلب #{order['id']} إلى completed تلقائياً")
                                
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث الطلبات التلقائي: {e}")


async def check_api_balance_alert():
    """مراقبة الرصيد وإشعار عند انخفاضه"""
    try:
        balance = await api_client.get_balance()
        
        if balance is not None:
            if balance < 10:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ **تحذير: رصيد API منخفض!**\n\n"
                    f"💰 الرصيد الحالي: ${balance:.2f}\n"
                    f"🔴 يرجى شحن الرصيد قريباً لتجنب توقف الخدمات.",
                    parse_mode="Markdown"
                )
                logger.warning(f"⚠️ رصيد API منخفض: ${balance:.2f}")
    except Exception as e:
        logger.error(f"❌ خطأ في مراقبة رصيد API: {e}")


async def init_scheduler():
    """تهيئة جدولة المهام"""
    global scheduler
    
    try:
        if scheduler and scheduler.running:
            scheduler.shutdown()
        
        settings = await get_report_settings(db_pool)
        report_time = settings.get('report_time', '00:00')
        hour, minute = map(int, report_time.split(':'))
        
        # جلب فترة التحديث التلقائي
        async with db_pool.acquire() as conn:
            sync_interval = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'sync_interval'"
            ) or "60"
        
        scheduler = AsyncIOScheduler(timezone='Asia/Damascus')
        
        # التقرير اليومي
        scheduler.add_job(
            send_daily_report,
            'cron',
            hour=hour,
            minute=minute,
            args=[bot, db_pool],
            id='daily_report',
            replace_existing=True,
            misfire_grace_time=3600
        )
        
        # تحديث الطلبات التلقائي (كل دقيقتين)
        scheduler.add_job(
            check_pending_orders_auto,
            'interval',
            minutes=2,
            id='check_orders_auto',
            replace_existing=True
        )
        
        # تحديث الخدمات التلقائي
        scheduler.add_job(
            auto_sync_services,
            'interval',
            minutes=int(sync_interval),
            id='auto_sync_services',
            replace_existing=True
        )
        
        # مراقبة رصيد API (كل ساعة)
        scheduler.add_job(
            check_api_balance_alert,
            'interval',
            hours=1,
            id='check_api_balance',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info(f"✅ تم تفعيل الجدولة (التقرير الساعة {report_time}، تحديث الخدمات كل {sync_interval} دقيقة)")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة الجدولة: {e}")
        return False


async def setup_webhook():
    """إعداد webhook"""
    try:
        port = int(os.environ.get('PORT', WEBHOOK_PORT))
        host = os.environ.get('RENDER_EXTERNAL_URL', WEBHOOK_HOST)
        
        if not host:
            host = f"http://localhost:{port}"
            logger.warning("⚠️ لم يتم تحديد WEBHOOK_HOST، استخدام localhost")
        
        base_url = host.rstrip('/')
        webhook_url = f"{base_url}{WEBHOOK_PATH}"
        
        await bot.set_webhook(
            webhook_url,
            max_connections=50,
            allowed_updates=["message", "callback_query", "chat_member"],
            drop_pending_updates=True,
            secret_token=os.getenv("WEBHOOK_SECRET", "")
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
    
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        **{"db_pool": db_pool}
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
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
    
    async def info(request):
        return web.json_response({
            "name": "LINK Charger Bot",
            "version": "1.0.0",
            "description": "Telegram bot for charging services",
            "webhook": f"{base_url}{WEBHOOK_PATH}"
        })
    app.router.add_get('/info', info)
    
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
    
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("✅ تم إيقاف الجدولة")
    
    if runner:
        await runner.cleanup()
        logger.info("✅ تم إيقاف خادم الويب")
    
    if db_pool:
        await db_pool.close()
        logger.info("✅ تم إغلاق مجمع اتصالات قاعدة البيانات")
    
    clear_cache()
    logger.info("✅ تم مسح الكاش")
    
    if bot:
        try:
            await bot.delete_webhook()
            logger.info("✅ تم حذف webhook")
        except Exception as e:
            logger.error(f"❌ خطأ في حذف webhook: {e}")
        await bot.session.close()
    
    logger.info("👋 تم إيقاف البوت بنجاح")
    sys.exit(0)


async def main():
    """الدالة الرئيسية لتشغيل البوت"""
    global start_time
    start_time = time.time()
    
    logger.info("🚀 بدأ تشغيل البوت...")
    logger.info(f"🔧 وضع التطوير: {'نعم' if DEBUG else 'لا'}")
    
    try:
        # ✅ 1. تهيئة قاعدة البيانات
        if not await init_database():
            logger.error("❌ فشل تهيئة قاعدة البيانات، إعادة المحاولة...")
            await asyncio.sleep(2)
            if not await init_database():
                logger.critical("❌ فشل تهيئة قاعدة البيانات بعد المحاولتين")
                return
        
        # ✅ 2. التحقق من الوقت
        await check_timezone()
        
        # ✅ 3. تحميل جميع الإعدادات (أسعار الصرف، رابط API، العروض)
        await load_all_settings()
        
        # ✅ 4. تحميل الإعدادات القديمة للتوافق
        try:
            await load_exchange_rate(db_pool)
            await load_bot_settings(db_pool)
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل الإعدادات القديمة: {e}")
        
        # ✅ 5. تهيئة البوت
        if not await init_bot():
            logger.error("❌ فشل تهيئة البوت")
            return
        
        # ✅ 6. تحديث كاش حالة البوت
        await refresh_bot_status_cache(db_pool)
        
        # ✅ 7. مسح الكاش
        clear_cache()
        
        # ✅ 8. تعيين الأوامر
        await set_bot_commands(bot)
        
        # ✅ 9. تهيئة الجدولة
        await init_scheduler()
        
        # ✅ 10. إعداد webhook
        port, base_url = await setup_webhook()
        
        # ✅ 11. إنشاء تطبيق الويب
        await create_web_app(base_url)
        
        # ✅ 12. تشغيل الخادم
        await start_server(port)
        
        # ✅ 13. إحصائيات البداية
        elapsed = time.time() - start_time
        logger.info(f"✅ تم بدء التشغيل بنجاح في {elapsed:.2f} ثانية")
        logger.info(f"📊 إحصائيات الكاش: {get_cache_stats()}")
        
        # ✅ 14. الانتظار
        await asyncio.Event().wait()
        
    except asyncio.CancelledError:
        logger.info("⏹️ تم إلغاء المهمة")
    except Exception as e:
        logger.error(f"❌ خطأ عام: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await shutdown()


if __name__ == "__main__":
    try:
        setup_signal_handlers()
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
        import traceback
        traceback.print_exc()
