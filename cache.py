# cache.py
import time
import logging
from functools import wraps
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# كاش بسيط
_cache = {}
_cache_time = {}

def cached(ttl: int = 60, key_prefix: str = ""):
    """
    ديكوريتر بسيط للتخزين المؤقت
    
    Args:
        ttl: مدة الصلاحية بالثواني
        key_prefix: بادئة للمفتاح (مهم جداً!)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # بناء مفتاح الكاش باستخدام البادئة
            if args and len(args) > 1:  # first arg is usually db_pool
                key = f"{key_prefix}:{str(args[1])}"  # user_id عادة يكون ثاني باراميتر
            else:
                key = f"{key_prefix}:{func.__name__}"
            
            # إضافة kwargs للمفتاح إذا وجدت
            if kwargs:
                key += f":{str(sorted(kwargs.items()))}"
            
            # التحقق من الكاش
            now = time.time()
            if key in _cache and (now - _cache_time.get(key, 0)) < ttl:
                logger.debug(f"✅ Cache hit: {key}")
                return _cache[key]
            
            # تنفيذ الدالة
            logger.debug(f"❌ Cache miss: {key}")
            start = time.time()
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            
            # حفظ في الكاش
            _cache[key] = result
            _cache_time[key] = now
            
            if elapsed > 1.0:
                logger.info(f"🐢 عملية بطيئة: {key} استغرقت {elapsed:.2f} ثانية")
            
            return result
        return async_wrapper
    return decorator

def clear_cache(pattern: str = None):
    """مسح الكاش"""
    global _cache, _cache_time
    
    if pattern is None:
        _cache.clear()
        _cache_time.clear()
        logger.info("✅ تم مسح كل الكاش")
        return
    
    # مسح حسب النمط
    keys_to_delete = [k for k in _cache.keys() if pattern in k]
    for k in keys_to_delete:
        _cache.pop(k, None)
        _cache_time.pop(k, None)
    
    logger.info(f"✅ تم مسح {len(keys_to_delete)} مفتاح من الكاش: {pattern}")

def get_cache_stats():
    """إحصائيات الكاش"""
    return {
        'total_keys': len(_cache),
        'keys': list(_cache.keys())[:10]
    }

def invalidate_key(key: str):
    """إبطال مفتاح معين"""
    if key in _cache:
        _cache.pop(key, None)
        _cache_time.pop(key, None)
        return True
    return False

def warm_cache(key: str, value: Any, ttl: int = 60):
    """تسخين الكاش"""
    _cache[key] = value
    _cache_time[key] = time.time()
