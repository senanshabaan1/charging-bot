# api/__init__.py
from .client import UniversalAPIClient, get_api_client, close_all_api_clients

__all__ = [
    'UniversalAPIClient',
    'get_api_client',
    'close_all_api_clients'
]
