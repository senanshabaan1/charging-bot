# database/cache_utils.py
from cache import clear_cache
import logging

logger = logging.getLogger(__name__)


async def invalidate_user_cache(user_id: int):
    """مسح كاش المستخدم"""
    clear_cache(f"user_vip:{user_id}")
    clear_cache(f"user_balance:{user_id}")
    clear_cache(f"user_basic:{user_id}")
    clear_cache(f"user_points:{user_id}")
    clear_cache(f"user_profile:{user_id}")


async def invalidate_exchange_rate():
    """مسح كاش سعر الصرف"""
    clear_cache("exchange_rate")
    clear_cache("exchange_rate:purchase")
    clear_cache("exchange_rate:deposit")
    clear_cache("exchange_rate:points")


async def invalidate_categories():
    """مسح كاش الأقسام"""
    clear_cache("categories")
    clear_cache("apps_by_category")


async def invalidate_product_options(product_id: int = None):
    """مسح كاش خيارات المنتج"""
    if product_id:
        clear_cache(f"product_options:{product_id}")
        clear_cache(f"product_option:*")
    else:
        clear_cache(prefix="product_options")
    logger.info(f"🗑️ تم مسح كاش خيارات المنتج {product_id if product_id else 'الكل'}")


async def invalidate_offers():
    """مسح كاش العروض والمكافآت"""
    clear_cache("global_offers")
    clear_cache("deposit_bonuses")
    clear_cache("offer_usage")
    logger.info("🗑️ تم مسح كاش العروض والمكافآت")


async def invalidate_products():
    """مسح كاش المنتجات"""
    clear_cache("applications")
    clear_cache("applications_by_category")
    logger.info("🗑️ تم مسح كاش المنتجات")


async def invalidate_api_settings():
    """مسح كاش إعدادات API"""
    clear_cache("api_base_url")
    clear_cache("api_token")
    logger.info("🗑️ تم مسح كاش إعدادات API")
