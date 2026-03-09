# handlers/middleware.py
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable, Union
import logging
import time
import asyncio

logger = logging.getLogger(__name__)

# كاش لحالة البوت - خارج الكلاس
bot_status_cache = {
    'status': True, 
    'last_check': 0,
    'maintenance_message': 'البوت قيد الصيانة حالياً'
}

# مدة صلاحية الكاش بالثواني (60 ثانية)
CACHE_TTL = 60

# ✅ قائمة بالأوامر المسموح بها حتى عند توقف البوت
ALLOWED_COMMANDS = {
    '/cancel', '/الغاء', '/رجوع', '/start', '/help',
    '❌ إلغاء', '🔙 رجوع للقائمة', '🏠 القائمة الرئيسية'
}

# ✅ قائمة بالـ callback data المسموح بها
ALLOWED_CALLBACKS = {
    'back_to_main', 'back_to_admin', 'check_subscription', 'cancel',
    'back_to_categories', 'back_to_account'
}

class BotStatusMiddleware(BaseMiddleware):
    """ميدل وير للتحقق من حالة البوت قبل معالجة الرسائل مع نظام كاش"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
        # ✅ قفل لمنع تحديث الكاش عدة مرات في نفس الوقت
        self._cache_lock = asyncio.Lock()
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
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
        
        # التحقق من الأوامر المسموح بها
        if self._is_allowed_event(event):
            return await handler(event, data)
        
        # استخدام الكاش - التحقق كل 60 ثانية فقط
        current_time = time.time()
        bot_status = bot_status_cache['status']
        
        # إذا انتهت صلاحية الكاش، قم بتحديثه
        if current_time - bot_status_cache['last_check'] >= CACHE_TTL:
            # ✅ استخدام lock لمنع التحديث المتزامن
            async with self._cache_lock:
                # التحقق مرة أخرى بعد الحصول على القفل
                if current_time - bot_status_cache['last_check'] >= CACHE_TTL:
                    await self._refresh_cache()
        
        # استخدام القيمة المخزنة (قد تكون محدثة أو قديمة)
        bot_status = bot_status_cache['status']
        maintenance_msg = bot_status_cache.get('maintenance_message', 'البوت قيد الصيانة حالياً')
        
        if not bot_status:
            # البوت متوقف - إرسال رسالة الصيانة
            await self._send_maintenance_message(event, maintenance_msg)
            return  # منع معالجة الرسالة
        
        # البوت يعمل - السماح بمعالجة الرسالة
        return await handler(event, data)
    
    def _is_allowed_event(self, event: Union[Message, CallbackQuery]) -> bool:
        """التحقق مما إذا كان الحدث مسموحاً به حتى عند توقف البوت"""
        if isinstance(event, Message):
            return event.text and event.text in ALLOWED_COMMANDS
        elif isinstance(event, CallbackQuery):
            return event.data in ALLOWED_CALLBACKS
        return False
    
    async def _send_maintenance_message(self, event: Union[Message, CallbackQuery], message: str):
        """إرسال رسالة الصيانة حسب نوع الحدث"""
        try:
            if isinstance(event, Message):
                await event.answer(f"⚠️ {message}")
            elif isinstance(event, CallbackQuery):
                await event.answer(message, show_alert=True)
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة الصيانة: {e}")
    
    async def _refresh_cache(self):
        """تحديث الكاش من قاعدة البيانات"""
        from database import get_bot_status, get_maintenance_message
        
        try:
            bot_status = await get_bot_status(self.db_pool)
            maintenance_msg = await get_maintenance_message(self.db_pool)
            
            bot_status_cache['status'] = bot_status
            bot_status_cache['maintenance_message'] = maintenance_msg
            bot_status_cache['last_check'] = time.time()
            
            logger.info(f"✅ تم تحديث كاش حالة البوت: {'يعمل' if bot_status else 'متوقف'}")
            return True
        except Exception as e:
            logger.error(f"❌ خطأ في تحديث كاش حالة البوت: {e}")
            # في حالة الخطأ، نبقي على القيم القديمة
            bot_status_cache['last_check'] = time.time()  # نحدث الوقت لمنع المحاولات المتكررة
            return False


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


# ✅ دوال جديدة للتحكم بالكاش
def is_bot_active() -> bool:
    """التحقق مما إذا كان البوت نشطاً"""
    return get_cached_bot_status()


def get_cache_stats() -> dict:
    """الحصول على إحصائيات الكاش"""
    return {
        'status': bot_status_cache.get('status'),
        'last_check': bot_status_cache.get('last_check'),
        'cache_age': time.time() - bot_status_cache.get('last_check', 0) if bot_status_cache.get('last_check') else None,
        'ttl': CACHE_TTL
    }