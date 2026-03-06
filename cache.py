# cache.py
import time
import asyncio
import logging
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)

# كاش بسيط للدوال
_cache = {}
_cache_times = {}
_cache_ttl = {}

def cached(ttl: int = 60, key_prefix: str = ""):
    """
    ديكوريتر للتخزين المؤقت
    
    Args:
        ttl: مدة الصلاحية بالثواني
        key_prefix: بادئة للمفتاح (اختياري)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # بناء مفتاح الكاش
            cache_key = f"{key_prefix}{func.__name__}:{str(args[0]) if args else ''}"
            if kwargs:
                cache_key += f":{str(sorted(kwargs.items()))}"
            
            # التحقق من وجود الكاش وصلاحيته
            current_time = time.time()
            if cache_key in _cache:
                if current_time - _cache_times.get(cache_key, 0) < _cache_ttl.get(cache_key, ttl):
                    logger.debug(f"✅ Cache hit: {cache_key}")
                    return _cache[cache_key]
            
            # تنفيذ الدالة
            logger.debug(f"❌ Cache miss: {cache_key}")
            result = await func(*args, **kwargs)
            
            # حفظ النتيجة في الكاش
            _cache[cache_key] = result
            _cache_times[cache_key] = current_time
            _cache_ttl[cache_key] = ttl
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # للدوال المتزامنة (لو احتجناها مستقبلاً)
            cache_key = f"{key_prefix}{func.__name__}:{str(args[0]) if args else ''}"
            
            current_time = time.time()
            if cache_key in _cache:
                if current_time - _cache_times.get(cache_key, 0) < _cache_ttl.get(cache_key, ttl):
                    return _cache[cache_key]
            
            result = func(*args, **kwargs)
            _cache[cache_key] = result
            _cache_times[cache_key] = current_time
            _cache_ttl[cache_key] = ttl
            
            return result
        
        # اختيار الدالة المناسبة
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def clear_cache(pattern: str = None):
    """
    مسح الكاش
    
    Args:
        pattern: نمط لمسح مفاتيح محددة (مثلاً "get_user:*")
    """
    global _cache, _cache_times, _cache_ttl
    
    if pattern is None:
        # مسح كل الكاش
        _cache.clear()
        _cache_times.clear()
        _cache_ttl.clear()
        logger.info("✅ تم مسح كل الكاش")
        return
    
    # مسح حسب النمط
    keys_to_delete = [key for key in _cache.keys() if pattern in key]
    for key in keys_to_delete:
        _cache.pop(key, None)
        _cache_times.pop(key, None)
        _cache_ttl.pop(key, None)
    
    logger.info(f"✅ تم مسح {len(keys_to_delete)} مفتاح من الكاش: {pattern}")


def get_cache_stats():
    """إحصائيات الكاش"""
    return {
        'total_keys': len(_cache),
        'total_size': sum(len(str(v)) for v in _cache.values()) if _cache else 0,
        'keys': list(_cache.keys())[:10]  # أول 10 مفاتيح
    }