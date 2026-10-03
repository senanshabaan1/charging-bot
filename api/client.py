# api/client.py
import aiohttp
import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Any
from cache import cached

logger = logging.getLogger(__name__)

class UniversalAPIClient:
    """عميل ديناميكي للتواصل مع أي موقع API يدعم هيكلية V1"""
    
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

    async def get_profile(self) -> Optional[Dict]:
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/client/api/profile/", timeout=30) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"خطأ اتصال {self.base_url}: {e}")
        return None

    async def get_balance(self) -> Optional[float]:
        profile = await self.get_profile()
        return float(profile.get('balance', 0)) if profile else None

    async def get_products(self) -> List[Dict]:
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/client/api/products/", timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._normalize_products(data) if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"خطأ جلب منتجات {self.base_url}: {e}")
        return []
        
    def _normalize_products(self, products: List[Dict]) -> List[Dict]:
        normalized = []
        for item in products:
            try:
                qty = item.get('qty_values', {})
                if isinstance(qty, dict):
                    min_q = int(float(qty.get('min', 1)))
                    max_q = int(float(qty.get('max', 99999)))
                else:
                    min_q, max_q = 1, 99999
            except:
                min_q, max_q = 1, 99999
                
            normalized.append({
                'id': int(item.get('id', 0)),
                'name': item.get('name', 'غير معروف'),
                'price': float(item.get('price', 0)),
                'category_name': item.get('category_name', ''),
                'available': item.get('available', True),
                'min_quantity': min_q,
                'max_quantity': max_q,
                'raw': item
            })
        return normalized

    async def create_order(self, product_id: int, quantity: int = 1, player_id: str = None, extra_params: Dict = None) -> Dict:
        try:
            session = await self._get_session()
            order_uuid = str(uuid.uuid4())
            params = {'qt': quantity, 'order_uuid': order_uuid}
            if player_id: params['playerId'] = player_id
            if extra_params: params.update(extra_params)
            
            url = f"{self.base_url}/client/api/newOrder/{product_id}/params/"
            async with session.post(url, params=params, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('status') == 'OK':
                        return {'success': True, 'order_id': data.get('data', {}).get('ID', order_uuid), 'raw': data}
                    return {'success': False, 'error': data.get('message', 'فشل')}
                return {'success': False, 'error': f'HTTP {resp.status}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def sync_services_to_db(self, db_pool, default_profit: int = 10, provider_id: int = 1):
        """مزامنة خدمات هذا المزود مع قاعدة البيانات"""
        products = await self.get_products()
        if not products: return 0
        
        count = 0
        async with db_pool.acquire() as conn:
            for p in products:
                if not p['available']: continue
                selling_price = p['price'] * (1 + default_profit / 100)
                
                existing = await conn.fetchval(
                    "SELECT id FROM applications WHERE api_service_id = $1 AND provider_id = $2", 
                    str(p['id']), provider_id
                )
                
                if existing:
                    await conn.execute('''
                        UPDATE applications SET unit_price_usd = $1, min_units = $2, updated_at = CURRENT_TIMESTAMP WHERE id = $3
                    ''', selling_price, p['min_quantity'], existing)
                else:
                    await conn.execute('''
                        INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, type, api_service_id, provider_id, is_active) 
                        VALUES ($1, $2, $3, $4, 'service', $5, $6, TRUE)
                    ''', p['name'], selling_price, p['min_quantity'], default_profit, str(p['id']), provider_id)
                count += 1
        return count

# ============= إدارة الاتصالات (Router) =============
_api_clients = {}

def get_api_client(base_url: str, api_token: str) -> UniversalAPIClient:
    key = f"{base_url}_{api_token}"
    if key not in _api_clients:
        _api_clients[key] = UniversalAPIClient(base_url, api_token)
    return _api_clients[key]

async def close_all_api_clients():
    for client in _api_clients.values():
        await client.close()
    _api_clients.clear()
