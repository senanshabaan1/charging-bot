# webhook_handler.py
import asyncio
import logging
import json
import threading
import time
from queue import Queue
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class NotificationSystem:
    """نظام الإشعارات بين لوحة التحكم والبوت"""
    
    def __init__(self, bot_instance=None):
        self.bot = bot_instance
        self.notification_queue = Queue()
        self.running = False
        self.thread = None
        self.handlers = {}
        self.pending_notifications = []
        
    def register_handler(self, event_type: str, handler_func):
        """تسجيل معالج لأحداث معينة"""
        self.handlers[event_type] = handler_func
        
    def send_notification(self, event_type: str, data: Dict[str, Any]):
        """إرسال إشعار إلى البوت"""
        notification = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        
        # إضافة إلى قائمة الانتظار
        self.notification_queue.put(notification)
        
        # إذا كان هناك بوت متصل، أرسل فوراً
        if self.bot:
            asyncio.create_task(self._send_to_bot(notification))
        else:
            # حفظ للإرسال لاحقاً
            self.pending_notifications.append(notification)
            
    async def _send_to_bot(self, notification: Dict[str, Any]):
        """إرسال الإشعار إلى البوت"""
        try:
            event_type = notification['type']
            data = notification['data']
            
            if event_type in self.handlers:
                await self.handlers[event_type](data)
            else:
                logger.warning(f"لا يوجد معالج للحدث: {event_type}")
                
        except Exception as e:
            logger.error(f"خطأ في إرسال الإشعار: {e}")
            
    def start(self):
        """بدء تشغيل نظام الإشعارات"""
        self.running = True
        self.thread = threading.Thread(target=self._process_queue, daemon=True)
        self.thread.start()
        logger.info("✅ نظام الإشعارات بدأ العمل")
        
    def stop(self):
        """إيقاف نظام الإشعارات"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("⏹️ نظام الإشعارات توقف")
        
    def _process_queue(self):
        """معالجة قائمة الانتظار"""
        while self.running:
            try:
                if not self.notification_queue.empty():
                    notification = self.notification_queue.get(timeout=1)
                    # معالجة الإشعار
                    logger.info(f"📨 إشعار جديد: {notification['type']}")
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"خطأ في معالجة قائمة الانتظار: {e}")
                
    def connect_bot(self, bot_instance):
        """ربط البوت بنظام الإشعارات"""
        self.bot = bot_instance
        # إرسال الإشعارات المعلقة
        for notification in self.pending_notifications:
            asyncio.create_task(self._send_to_bot(notification))
        self.pending_notifications.clear()
        logger.info("✅ تم ربط البوت بنظام الإشعارات")

# إنشاء كائن عام للنظام
notification_system = NotificationSystem()