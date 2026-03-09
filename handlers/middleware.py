# handlers/middleware.py
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
import logging
import time

logger = logging.getLogger(__name__)

# كاش لحالة البوت - خارج الكلاس
bot_status_cache = {
    'status': True, 
    'last_check': 0,
    'maintenance_message': 'البوت قيد الصيانة حالياً'
}

# مدة صلاحية الكاش بالثواني (60 ثانية)
CACHE_TTL = 60

class BotStatusMiddleware(BaseMiddleware):
    """ميدل وير للتحقق من حالة البوت قبل معالجة الرسائل مع نظام كاش"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # التحقق من حالة البوت من قاعدة البيانات مع استخدام الكاش
        from database import get_bot_status, get_maintenance_message
        
        # استثناء المشرفين من التحقق
        from config import ADMIN_ID, MODERATORS
        
        user_id = event.from_user.id
        is_admin = user_id == ADMIN_ID or user_id in MODERATORS
        
        # إذا كان المستخدم مشرف، يسمح له بالدخول دائماً
        if is_admin:
            return await handler(event, data)
        
        # التحقق من أوامر الإلغاء والبدء - السماح بها دائماً
        if isinstance(event, Message):
            if event.text and event.text.startswith(('/cancel', '/الغاء', '/رجوع', '/start', '/help')):
                return await handler(event, data)
        
        if isinstance(event, CallbackQuery):
            if event.data in ['back_to_main', 'back_to_admin', 'check_subscription', 'cancel']:
                return await handler(event, data)
        
        # استخدام الكاش - التحقق كل 60 ثانية فقط
        current_time = time.time()
        
        # إذا مر وقت أقل من CACHE_TTL على آخر تحديث، استخدم القيمة المخزنة
        if current_time - bot_status_cache['last_check'] < CACHE_TTL:
            bot_status = bot_status_cache['status']
            maintenance_msg = bot_status_cache.get('maintenance_message', 'البوت قيد الصيانة حالياً')
        else:
            # جلب البيانات الجديدة من قاعدة البيانات
            try:
                bot_status = await get_bot_status(self.db_pool)
                maintenance_msg = await get_maintenance_message(self.db_pool)
                
                # تحديث الكاش
                bot_status_cache['status'] = bot_status
                bot_status_cache['maintenance_message'] = maintenance_msg
                bot_status_cache['last_check'] = current_time
                
                logger.info(f"✅ تم تحديث كاش حالة البوت: {'يعمل' if bot_status else 'متوقف'}")
            except Exception as e:
                # في حالة خطأ قاعدة البيانات، استخدم آخر قيمة مخزنة
                logger.error(f"❌ خطأ في جلب حالة البوت: {e}")
                bot_status = bot_status_cache['status']
                maintenance_msg = bot_status_cache.get('maintenance_message', 'البوت قيد الصيانة حالياً')
        
        if not bot_status:
            # البوت متوقف - إرسال رسالة الصيانة
            if isinstance(event, Message):
                await event.answer(f"⚠️ {maintenance_msg}")
            elif isinstance(event, CallbackQuery):
                await event.answer(maintenance_msg, show_alert=True)
            
            return  # منع معالجة الرسالة
        
        # البوت يعمل - السماح بمعالجة الرسالة
        return await handler(event, data)


async def refresh_bot_status_cache(db_pool):
    """تحديث كاش حالة البوت يدوياً"""
    from database import get_bot_status, get_maintenance_message
    
    try:
        bot_status = await get_bot_status(db_pool)
        maintenance_msg = await get_maintenance_message(db_pool)
        
        bot_status_cache['status'] = bot_status
        bot_status_cache['maintenance_message'] = maintenance_msg
        bot_status_cache['last_check'] = time.time()
        
        logger.info(f"✅ تم تحديث كاش حالة البوت يدوياً: {'يعمل' if bot_status else 'متوقف'}")
        return True
    except Exception as e:
        logger.error(f"❌ فشل تحديث كاش حالة البوت: {e}")
        return False


def reset_bot_status_cache():
    """إعادة ضبط كاش حالة البوت"""
    global bot_status_cache
    bot_status_cache = {
        'status': True,
        'last_check': 0,
        'maintenance_message': 'البوت قيد الصيانة حالياً'
    }
    logger.info("🔄 تم إعادة ضبط كاش حالة البوت")


# دالة مساعدة للحصول على حالة البوت من الكاش
def get_cached_bot_status():
    """الحصول على حالة البوت من الكاش"""
    return bot_status_cache.get('status', True)


# دالة مساعدة للحصول على رسالة الصيانة من الكاش
def get_cached_maintenance_message():
    """الحصول على رسالة الصيانة من الكاش"""
    return bot_status_cache.get('maintenance_message', 'البوت قيد الصيانة حالياً')
