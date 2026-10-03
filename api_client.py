import aiohttp
import uuid
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class UniversalAPI:
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {api_token}',
        }

    async def get_balance(self) -> Optional[float]:
        """فحص رصيد الموقع المرتبط"""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(f"{self.base_url}/client/api/profile/", timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data.get('balance', 0))
        except Exception as e:
            logger.error(f"API Error ({self.base_url}): {e}")
        return None

    async def create_order(self, service_id: int, target_id: str, quantity: int = 1) -> Dict:
        """إرسال الطلب للموقع"""
        try:
            order_uuid = str(uuid.uuid4())
            params = {'qt': quantity, 'order_uuid': order_uuid, 'playerId': target_id}
            
            async with aiohttp.ClientSession(headers=self.headers) as session:
                url = f"{self.base_url}/client/api/newOrder/{service_id}/params/"
                async with session.post(url, params=params, timeout=30) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data.get('status') == 'OK':
                        return {'success': True, 'remote_id': data.get('data', {}).get('ID')}
                    return {'success': False, 'error': data.get('message', 'Unknown error')}
        except Exception as e:
            return {'success': False, 'error': str(e)}