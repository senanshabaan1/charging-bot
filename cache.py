# cache.py
import time
import asyncio
import logging
import hashlib
import json
from functools import wraps
from typing import Any, Callable, Dict, Optional, List, Union
from collections import OrderedDict

logger = logging.getLogger(__name__)

# ============= إعدادات الكاش =============
DEFAULT_TTL = 60  # 60 ثانية
MAX_CACHE_SIZE = 1000  # الحد الأقصى لعدد العناصر في الكاش
CLEANUP_INTERVAL = 300  # تنظيف الكاش كل 5 دقائق

# ============= هيكل الكاش =============
class CacheEntry:
    """عنصر في الكاش مع بياناته"""
    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.created_at = time.time()
        self.ttl = ttl
        self.access_count = 0
        self.last_access = self.created_at
    
    def is_expired(self) -> bool:
        """التحقق من انتهاء صلاحية العنصر"""
        return time.time() - self.created_at > self.ttl
    
    def access(self):
        """تسجيل وصول للعنصر"""
        self.access_count += 1
        self.last_access = time.time()


class Cache:
    """نظام كاش متقدم مع LRU (Least Recently Used)"""
    
    def __init__(self, max_size: int = MAX_CACHE_SIZE):
        self._cache: Dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
        self._last_cleanup = time.time()
    
    def _cleanup_if_needed(self):
        """تنظيف الكاش إذا لزم الأمر"""
        now = time.time()
        
        # تنظيف العناصر منتهية الصلاحية
        expired_keys = [
            key for key, entry in self._cache.items() 
            if entry.is_expired()
        ]
        for key in expired_keys:
            del self._cache[key]
        
        # إذا كان الكاش أكبر من الحد الأقصى، احذف الأقل استخداماً
        if len(self._cache) > self._max_size:
            # ترتيب حسب آخر وصول
            sorted_items = sorted(
                self._cache.items(),
                key=lambda x: (x[1].last_access, x[1].access_count)
            )
            # احذف 20% من العناصر الأقل استخداماً
            to_remove = int(self._max_size * 0.2)
            for key, _ in sorted_items[:to_remove]:
                del self._cache[key]
        
        if expired_keys:
            logger.debug(f"🧹 تم تنظيف {len(expired_keys)} عنصر منتهي الصلاحية")
        
        self._last_cleanup = now
    
    def get(self, key: str) -> Optional[Any]:
        """الحصول على قيمة من الكاش"""
        if key not in self._cache:
            self._misses += 1
            return None
        
        entry = self._cache[key]
        
        # التحقق من الصلاحية
        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            return None
        
        # تسجيل وصول
        entry.access()
        self._hits += 1
        
        # تنظيف دوري
        if time.time() - self._last_cleanup > CLEANUP_INTERVAL:
            self._cleanup_if_needed()
        
        return entry.value
    
    def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL):
        """تخزين قيمة في الكاش"""
        # إذا كان الكاش ممتلئاً، قم بالتنظيف
        if len(self._cache) >= self._max_size:
            self._cleanup_if_needed()
        
        self._cache[key] = CacheEntry(value, ttl)
    
    def delete(self, key: str):
        """حذف عنصر من الكاش"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    def delete_pattern(self, pattern: str):
        """حذف العناصر التي تطابق نمطاً معيناً"""
        keys_to_delete = [key for key in self._cache.keys() if pattern in key]
        for key in keys_to_delete:
            del self._cache[key]
        return len(keys_to_delete)
    
    def clear(self):
        """مسح كل الكاش"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.info("✅ تم مسح كل الكاش")
    
    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات الكاش"""
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        # توزيع TTL
        ttl_distribution = {}
        for entry in self._cache.values():
            remaining = max(0, entry.ttl - (time.time() - entry.created_at))
            category = int(remaining / 10) * 10  # تجميع في فئات 10 ثواني
            ttl_distribution[category] = ttl_distribution.get(category, 0) + 1
        
        return {
            'total_keys': len(self._cache),
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': f"{hit_rate:.1f}%",
            'memory_estimate': sum(len(str(v.value)) for v in self._cache.values()),
            'ttl_distribution': ttl_distribution,
            'sample_keys': list(self._cache.keys())[:10]
        }


# ============= إنشاء نسخة عامة من الكاش =============
_cache_instance = Cache()


def cached(ttl: int = DEFAULT_TTL, key_prefix: str = ""):
    """
    ديكوريتر للتخزين المؤقت
    
    Args:
        ttl: مدة الصلاحية بالثواني
        key_prefix: بادئة للمفتاح (اختياري)
    
    Returns:
        Callable: الدالة المزخرفة
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # بناء مفتاح الكاش
            cache_key = _build_cache_key(func, key_prefix, args, kwargs)
            
            # محاولة الحصول من الكاش
            cached_value = _cache_instance.get(cache_key)
            if cached_value is not None:
                logger.debug(f"✅ Cache hit: {cache_key}")
                return cached_value
            
            # تنفيذ الدالة
            logger.debug(f"❌ Cache miss: {cache_key}")
            start_time = time.time()
            result = await func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            # تخزين النتيجة
            _cache_instance.set(cache_key, result, ttl)
            
            if elapsed > 1.0:
                logger.info(f"🐢 عملية بطيئة: {func.__name__} استغرقت {elapsed:.2f} ثانية")
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # للدوال المتزامنة
            cache_key = _build_cache_key(func, key_prefix, args, kwargs)
            
            cached_value = _cache_instance.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            start_time = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            _cache_instance.set(cache_key, result, ttl)
            
            if elapsed > 1.0:
                logger.info(f"🐢 عملية بطيئة: {func.__name__} استغرقت {elapsed:.2f} ثانية")
            
            return result
        
        # اختيار الدالة المناسبة
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def _build_cache_key(func: Callable, prefix: str, args: tuple, kwargs: dict) -> str:
    """
    بناء مفتاح كاش موحد
    
    Args:
        func: الدالة
        prefix: بادئة
        args: المعاملات الموضعية
        kwargs: المعاملات المسماة
    
    Returns:
        str: مفتاح الكاش
    """
    # استخدام اسم الوحدة والصف إذا وجد
    module_name = func.__module__
    func_name = func.__qualname__
    
    # تجميع المعاملات
    key_parts = [module_name, func_name]
    
    if prefix:
        key_parts.insert(0, prefix)
    
    # إضافة المعاملات الموضعية
    for arg in args:
        if hasattr(arg, '__dict__'):
            # للأشياء المعقدة، استخدم الـ id
            key_parts.append(str(id(arg)))
        else:
            key_parts.append(str(arg))
    
    # إضافة المعاملات المسماة بشكل مرتب
    if kwargs:
        sorted_kwargs = sorted(kwargs.items())
        for k, v in sorted_kwargs:
            key_parts.append(f"{k}={v}")
    
    # بناء المفتاح النهائي
    key_string = ":".join(key_parts)
    
    # استخدام hash إذا كان المفتاح طويلاً جداً
    if len(key_string) > 200:
        return f"{prefix}{func_name}:{hashlib.md5(key_string.encode()).hexdigest()}"
    
    return key_string


# ============= دوال مساعدة =============

def clear_cache(pattern: Optional[str] = None):
    """
    مسح الكاش
    
    Args:
        pattern: نمط لمسح مفاتيح محددة (مثلاً "get_user:*")
    """
    if pattern is None:
        _cache_instance.clear()
    else:
        deleted = _cache_instance.delete_pattern(pattern)
        logger.info(f"✅ تم مسح {deleted} مفتاح من الكاش: {pattern}")


def get_cache_stats() -> Dict[str, Any]:
    """الحصول على إحصائيات الكاش"""
    return _cache_instance.get_stats()


def invalidate_key(key: str):
    """إبطال مفتاح معين"""
    return _cache_instance.delete(key)


def warm_cache(key: str, value: Any, ttl: int = DEFAULT_TTL):
    """تسخين الكاش بقيمة محددة"""
    _cache_instance.set(key, value, ttl)


# ============= ديكوريترات متخصصة =============

def cached_ttl_by_args(ttl_func: Callable):
    """
    ديكوريتر مع TTL متغير حسب المعاملات
    
    Args:
        ttl_func: دالة تأخذ نفس معاملات الدالة الأصلية وتعيد TTL
    
    Example:
        @cached_ttl_by_args(lambda user_id: 300 if user_id == 1 else 60)
        async def get_user(user_id):
            return await fetch_user(user_id)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            ttl = ttl_func(*args, **kwargs)
            cache_key = _build_cache_key(func, "", args, kwargs)
            
            cached_value = _cache_instance.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            result = await func(*args, **kwargs)
            _cache_instance.set(cache_key, result, ttl)
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            ttl = ttl_func(*args, **kwargs)
            cache_key = _build_cache_key(func, "", args, kwargs)
            
            cached_value = _cache_instance.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            result = func(*args, **kwargs)
            _cache_instance.set(cache_key, result, ttl)
            return result
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def cache_result(ttl: int = DEFAULT_TTL):
    """
    ديكوريتر بسيط لتخزين نتيجة الدالة
    
    Example:
        @cache_result(ttl=30)
        async def expensive_operation():
            return await some_heavy_computation()
    """
    return cached(ttl=ttl)


# ============= تصدير الدوال الرئيسية =============
__all__ = [
    'cached',
    'clear_cache',
    'get_cache_stats',
    'invalidate_key',
    'warm_cache',
    'cache_result',
    'cached_ttl_by_args'
]