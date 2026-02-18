# handlers/middleware.py
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
import logging

logger = logging.getLogger(__name__)

class BotStatusMiddleware(BaseMiddleware):
    """ميدل وير للتحقق من حالة البوت قبل معالجة الرسائل"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # التحقق من حالة البوت من قاعدة البيانات
        from database import get_bot_status, get_maintenance_message
        
        # استثناء المشرفين من التحقق
        from config import ADMIN_ID, MODERATORS
        
        user_id = event.from_user.id
        is_admin = user_id == ADMIN_ID or user_id in MODERATORS
        
        # إذا كان المستخدم مشرف، يسمح له بالدخول دائماً
        if is_admin:
            return await handler(event, data)
        
        # التحقق من حالة البوت
        bot_status = await get_bot_status(self.db_pool)
        
        if not bot_status:
            # البوت متوقف - إرسال رسالة الصيانة
            maintenance_msg = await get_maintenance_message(self.db_pool)
            
            if isinstance(event, Message):
                await event.answer(f"⚠️ {maintenance_msg}")
            elif isinstance(event, CallbackQuery):
                await event.answer(maintenance_msg, show_alert=True)
            
            return  # منع معالجة الرسالة
        
        # البوت يعمل - السماح بمعالجة الرسالة
        return await handler(event, data)