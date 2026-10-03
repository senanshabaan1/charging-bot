# api/client.py
import aiohttp
import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Any
from cache import cached

logger = logging.getLogger(__name__)

class UniversalAPIClient:
    """
    عميل ديناميكي للتواصل مع أي موقع API يدعم نفس هيكلية Mousa Card
    """
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {self.api_token}',
            }
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def get_balance(self) -> Optional[float]:
        """جلب الرصيد المتاح من المزود"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/client/api/profile/", timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data.get('balance', 0))
                return None
        except Exception as e:
            logger.error(f"خطأ في جلب الرصيد من {self.base_url}: {e}")
            return None

    async def create_order(self, product_id: int, quantity: int = 1, player_id: str = None, extra_params: Dict = None) -> Dict:
        """إنشاء طلب وتوجيهه للموقع المطلوب"""
        try:
            session = await self._get_session()
            order_uuid = str(uuid.uuid4())
            
            params = {'qt': quantity, 'order_uuid': order_uuid}
            if player_id: params['playerId'] = player_id
            if extra_params: params.update(extra_params)
            
            url = f"{self.base_url}/client/api/newOrder/{product_id}/params/"
            logger.info(f"📤 توجيه طلب إلى {self.base_url}: product_id={product_id}")
            
            async with session.post(url, params=params, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('status') == 'OK':
                        response_data = data.get('data', {})
                        return {
                            'success': True,
                            'order_id': response_data.get('ID', order_uuid),
                            'price': float(response_data.get('price', 0)),
                            'raw': data
                        }
                    else:
                        return {'success': False, 'error': data.get('message', 'فشل إنشاء الطلب'), 'raw': data}
                else:
                    return {'success': False, 'error': f'خطأ HTTP {resp.status}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

# ============= إدارة الجلسات (Session Manager) =============
_api_clients = {}

def get_api_client(base_url: str, api_token: str) -> UniversalAPIClient:
    """الحصول على عميل API ديناميكي وإعادة استخدامه إذا كان موجوداً لتخفيف الضغط"""
    key = f"{base_url}_{api_token}"
    if key not in _api_clients:
        _api_clients[key] = UniversalAPIClient(base_url, api_token)
    return _api_clients[key]

async def close_all_api_clients():
    """إغلاق جميع الاتصالات المفتوحة عند إطفاء البوت"""
    for client in _api_clients.values():
        await client.close()
    _api_clients.clear()
