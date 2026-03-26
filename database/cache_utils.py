# database/cache_utils.py
from cache import clear_cache

async def invalidate_user_cache(user_id: int):
    """مسح كاش المستخدم"""
    clear_cache(f"user_vip:{user_id}")
    clear_cache(f"user_balance:{user_id}")

async def invalidate_exchange_rate():
    """مسح كاش سعر الصرف"""
    clear_cache("exchange_rate")

async def invalidate_categories():
    """مسح كاش الأقسام"""
    clear_cache("categories")
    clear_cache("apps_by_category")
