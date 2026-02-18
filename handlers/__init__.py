# handlers/__init__.py
from .start import router as start_router
from .services import router as services_router
from .deposit import router as deposit_router
from .admin import router as admin_router

__all__ = ['start_router', 'services_router', 'deposit_router', 'admin_router']