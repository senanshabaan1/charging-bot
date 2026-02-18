# run_bot.py
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from config import TOKEN, ADMIN_ID
from database import init_db, get_pool
from handlers import start, deposit, services, admin

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    logging.info("🚀 بدأ تشغيل البوت...")
    
    # تهيئة قاعدة البيانات
    try:
        await init_db()
        logging.info("✅ تم تهيئة قاعدة البيانات")
    except Exception as e:
        logging.error(f"❌ خطأ في قاعدة البيانات: {e}")
        return
    
    # إنشاء مجمع الاتصالات
    try:
        db_pool = await get_pool()
        if not db_pool:
            logging.error("❌ فشل الاتصال بقاعدة البيانات.")
            return
    except Exception as e:
        logging.error(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")
        return
    
    # تحميل سعر الصرف
    try:
        from config import load_exchange_rate
        await load_exchange_rate(db_pool)
        logging.info("✅ تم تحميل سعر الصرف من قاعدة البيانات")
    except Exception as e:
        logging.error(f"❌ خطأ في تحميل سعر الصرف: {e}")
    
    # إنشاء البوت
    try:
        bot = Bot(token=TOKEN)
        me = await bot.get_me()
        logging.info(f"✅ تم الاتصال بالبوت: @{me.username}")
    except Exception as e:
        logging.error(f"❌ فشل الاتصال بTelegram: {e}")
        return
    
    # إنشاء Dispatcher
    dp = Dispatcher()
    
    # Middleware للتحقق من الحظر
    @dp.message.middleware()
    async def check_user_status(handler, event, data):
        if not isinstance(event, types.Message):
            return await handler(event, data)
        
        try:
            async with db_pool.acquire() as conn:
                user = await conn.fetchrow(
                    "SELECT is_banned FROM users WHERE user_id = $1", 
                    event.from_user.id
                )
                if user and user['is_banned']:
                    await event.answer("🚫 حسابك محظور من استخدام البوت.")
                    return
        except:
            pass
        
        try:
            from database import get_bot_status
            bot_status = await get_bot_status(db_pool)
            if not bot_status and event.from_user.id != ADMIN_ID:
                from database import get_maintenance_message
                msg = await get_maintenance_message(db_pool)
                await event.answer(f"🛠 {msg}")
                return
        except:
            pass
            
        return await handler(event, data)
    
    # تسجيل الهاندلرز
    dp.include_routers(
        admin.router,
        start.router,
        deposit.router,
        services.router
    )
    
    logging.info("✅ البوت جاهز للاستخدام!")
    
    try:
        await dp.start_polling(bot, db_pool=db_pool)
    except KeyboardInterrupt:
        logging.info("⏹️ تم إيقاف البوت.")
    except Exception as e:
        logging.error(f"❌ خطأ أثناء التشغيل: {e}")
    finally:
        await bot.session.close()
        await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())