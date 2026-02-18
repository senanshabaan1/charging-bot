# main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from config import TOKEN, BOT_STATUS, ADMIN_ID
from database import init_db, get_pool
from handlers import start, deposit, services, admin

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    # تهيئة قاعدة البيانات
    await init_db()
    
    # إنشاء مجمع الاتصالات
    db_pool = await get_pool()
    if not db_pool:
        logging.error("❌ فشل الاتصال بقاعدة البيانات. إيقاف البوت.")
        return
    
    # إنشاء البوت والمتغيرات
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp["db_pool"] = db_pool
    
    # Middleware للتحقق من الحظر وحالة البوت
    @dp.message.middleware()
    async def check_user_status(handler, event, data):
        # إذا كان الحدث ليس رسالة، أكمل
        if not isinstance(event, types.Message):
            return await handler(event, data)
        
        # التحقق من الحظر
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT is_banned FROM users WHERE user_id = $1", 
                event.from_user.id
            )
            if user and user['is_banned']:
                await event.answer("🚫 حسابك محظور من استخدام البوت.")
                return
        
        # التحقق من حالة البوت
        if not BOT_STATUS and event.from_user.id != ADMIN_ID:
            await event.answer("🛠 البوت في حالة صيانة حالياً، عد لاحقاً.")
            return
            
        return await handler(event, data)
    
    # تسجيل الهاندلرز
    dp.include_routers(
        admin.router,
        start.router,
        deposit.router,
        services.router
    )
    
    logging.info("✅ بدأ تشغيل البوت...")
    logging.info(f"👑 آيدي المدير: {ADMIN_ID}")
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logging.info("⏹️ إيقاف البوت...")
    except Exception as e:
        logging.error(f"❌ خطأ غير متوقع: {e}")

if __name__ == "__main__":
    asyncio.run(main())