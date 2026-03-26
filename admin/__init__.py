# admin/__init__.py
from aiogram import Router

from .main import router as main_router
from .settings import router as settings_router
from .products import router as products_router
from .categories import router as categories_router
from .options import router as options_router
from .users import router as users_router
from .points import router as points_router
from .admins import router as admins_router
from .stats import router as stats_router
from .vip import router as vip_router
from .broadcast import router as broadcast_router
from .group_handlers import router as group_router
from .reset import router as reset_router

router = Router(name="admin")

# ✅ Make sure each router is included only once
router.include_routers(
    main_router,
    settings_router,
    products_router,
    categories_router,
    options_router,
    users_router,
    points_router,
    admins_router,
    stats_router,
    vip_router,
    broadcast_router,
    group_router,
    reset_router
)

__all__ = ['router']
