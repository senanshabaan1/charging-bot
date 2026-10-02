from .client import MousaCardClient, get_api_client

# دوال مساعدة إضافية للتوافقية إن احتجتها في باقي الملفات
def set_api_token(token: str):
    pass

def close_api_client():
    pass

__all__ = [
    'MousaCardClient',
    'get_api_client',
    'set_api_token',
    'close_api_client'
]
