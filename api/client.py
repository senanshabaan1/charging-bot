# api/client.py
import aiohttp
import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from cache import cached

logger = logging.getLogger(__name__)


class MousaCardAPI:
    """
    عميل للتواصل مع API موقع Mousa Card
    الوثائق: https://mousa-card.com/api-docs
    """
    
    def __init__(self, base_url: str = "https://mousa-card.com", api_token: str = None):
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """الحصول على جلسة HTTP مع إعادة استخدام"""
        if self.session is None or self.session.closed:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'api-token': self.api_token or ''
            }
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session
    
    async def close(self):
        """إغلاق الجلسة"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    # ============= ملف المستخدم والرصيد =============
    async def get_profile(self) -> Optional[Dict]:
        """
        استرجاع بيانات الملف الشخصي والرصيد
        GET /client/api/profile/
        """
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/client/api/profile/", timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        'balance': float(data.get('balance', 0)),
                        'email': data.get('email', ''),
                        'raw': data
                    }
                else:
                    logger.error(f"فشل جلب الملف الشخصي: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"خطأ في جلب الملف الشخصي: {e}")
            return None
    
    async def get_balance(self) -> Optional[float]:
        """جلب الرصيد المتاح"""
        profile = await self.get_profile()
        return profile['balance'] if profile else None
    
    # ============= المنتجات =============
    @cached(ttl=300, key_prefix="mousa_products")
    async def get_products(self, products_id: str = None, base_only: bool = False) -> List[Dict]:
        """
        استرجاع جميع المنتجات المتاحة
        GET /client/api/products/
        
        Args:
            products_id: فلتر بمعرفات المنتجات (مثل "365,18,42")
            base_only: إرجاع id واسم المنتج فقط
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/client/api/products/"
            
            params = {}
            if products_id:
                params['products_id'] = products_id
            if base_only:
                params['base'] = '1'
            
            async with session.get(url, params=params, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # البيانات تأتي كمصفوفة من المنتجات
                    if isinstance(data, list):
                        return self._normalize_products(data)
                    return []
                else:
                    logger.error(f"فشل جلب المنتجات: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"خطأ في جلب المنتجات: {e}")
            return []
    
    async def get_product_details(self, product_id: int) -> Optional[Dict]:
        """جلب تفاصيل منتج محدد"""
        products = await self.get_products(products_id=str(product_id))
        for product in products:
            if product.get('id') == product_id:
                return product
        return None
    
    @cached(ttl=300, key_prefix="mousa_categories")
    async def get_categories_content(self, category_id: int = 0) -> Dict:
        """
        استرجاع المنتجات والتصنيفات الفرعية لتصنيف معين
        GET /client/api/content/{category_id}/
        
        Args:
            category_id: 0 للصفحة الرئيسية
        """
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/client/api/content/{category_id}/", timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._normalize_categories_data(data)
                return {}
        except Exception as e:
            logger.error(f"خطأ في جلب المحتوى للتصنيف {category_id}: {e}")
            return {}
    
    # ============= إنشاء الطلبات =============
    async def create_order(
        self, 
        product_id: int, 
        quantity: int = 1,
        player_id: str = None,
        order_uuid: str = None,
        extra_params: Dict = None
    ) -> Dict:
        """
        إنشاء طلب جديد في موقع Mousa Card
        POST /client/api/newOrder/{product_id}/params/
        
        Args:
            product_id: معرف المنتج
            quantity: الكمية (qt)
            player_id: معرف اللاعب (للألعاب)
            order_uuid: UUID للطلب (سيتم إنشاؤه تلقائياً إذا لم يُقدم)
            extra_params: معاملات إضافية
        
        Returns:
            {
                'success': bool,
                'order_id': str,
                'status': str,  # accept, reject, wait
                'price': float,
                'data': dict,
                'error': str (optional)
            }
        """
        try:
            session = await self._get_session()
            
            # إنشاء UUID للطلب إذا لم يُقدم
            if not order_uuid:
                order_uuid = str(uuid.uuid4())
            
            # بناء المعاملات
            params = {
                'qt': quantity,
                'order_uuid': order_uuid
            }
            
            if player_id:
                params['playerId'] = player_id
            
            if extra_params:
                params.update(extra_params)
            
            url = f"{self.base_url}/client/api/newOrder/{product_id}/params/"
            
            logger.info(f"📤 إنشاء طلب في Mousa Card: product_id={product_id}, quantity={quantity}, order_uuid={order_uuid}")
            
            async with session.post(url, params=params, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"📥 رد Mousa Card: {data}")
                    
                    # تحليل الاستجابة
                    if data.get('status') == 'OK':
                        response_data = data.get('data', {})
                        return {
                            'success': True,
                            'order_id': response_data.get('ID', order_uuid),
                            'status': response_data.get('status', 'wait'),
                            'price': float(response_data.get('price', 0)),
                            'data': response_data.get('data', {}),
                            'reply_api': data.get('reply_api', []),
                            'raw': data
                        }
                    else:
                        return {
                            'success': False,
                            'error': data.get('message', 'فشل إنشاء الطلب'),
                            'raw': data
                        }
                else:
                    error_text = await resp.text()
                    logger.error(f"فشل إنشاء الطلب: {resp.status} - {error_text}")
                    return {
                        'success': False,
                        'error': f'خطأ HTTP {resp.status}',
                        'raw': error_text
                    }
        except asyncio.TimeoutError:
            return {'success': False, 'error': 'انتهت مهلة الاتصال بالموقع'}
        except Exception as e:
            logger.error(f"خطأ في إنشاء الطلب: {e}")
            return {'success': False, 'error': str(e)}
    
    # ============= الاستعلام عن الطلبات =============
    async def check_orders(self, order_ids: List[str]) -> List[Dict]:
        """
        التحقق من حالة مجموعة طلبات
        GET /client/api/check?orders=[ID1,ID2]/
        
        Args:
            order_ids: قائمة بمعرفات الطلبات
        """
        try:
            session = await self._get_session()
            orders_param = ','.join(order_ids)
            url = f"{self.base_url}/client/api/check?orders=[{orders_param}]/"
            
            async with session.get(url, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get('status') == 'OK':
                        orders_data = data.get('data', [])
                        results = []
                        for order in orders_data:
                            results.append({
                                'order_id': order.get('order_id') or order.get('ID'),
                                'quantity': int(order.get('quantity', 1)),
                                'data': order.get('data', {}),
                                'created_at': order.get('created_at'),
                                'product_name': order.get('product_name'),
                                'price': float(order.get('price', 0)),
                                'status': order.get('status', 'unknown'),
                                'reply_api': order.get('replay_api', [])
                            })
                        return results
                    return []
                else:
                    logger.error(f"فشل الاستعلام عن الطلبات: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"خطأ في الاستعلام عن الطلبات {order_ids}: {e}")
            return []
    
    async def check_order_status(self, order_id: str) -> Optional[Dict]:
        """الاستعلام عن حالة طلب واحد"""
        results = await self.check_orders([order_id])
        return results[0] if results else None
    
    # ============= دوال مساعدة للتنسيق =============
    def _normalize_products(self, products: List[Dict]) -> List[Dict]:
        """توحيد تنسيق المنتجات"""
        normalized = []
        for item in products:
            # استخراج min/max من qty_values
            qty_values = item.get('qty_values', {})
            if isinstance(qty_values, dict):
                min_qty = int(qty_values.get('min', 1))
                max_qty = int(qty_values.get('max', 99999)) if qty_values.get('max') else 99999
            else:
                min_qty = 1
                max_qty = 99999
            
            normalized.append({
                'id': int(item.get('id', 0)),
                'name': item.get('name', 'غير معروف'),
                'price': float(item.get('price', 0)),
                'category_name': item.get('category_name', ''),
                'available': item.get('available', True),
                'min_quantity': min_qty,
                'max_quantity': max_qty,
                'raw': item
            })
        return normalized
    
    def _normalize_categories_data(self, data: Dict) -> Dict:
        """توحيد تنسيق بيانات التصنيفات"""
        result = {
            'categories': [],
            'products': []
        }
        
        # معالجة التصنيفات
        categories = data.get('categories', [])
        if isinstance(categories, list):
            for cat in categories:
                result['categories'].append({
                    'id': cat.get('id'),
                    'name': cat.get('name'),
                    'image_url': cat.get('image_url'),
                    'parent_id': cat.get('parent_id', 0),
                    'sort_order': cat.get('sort_order', 0)
                })
        
        # معالجة المنتجات (قد تكون في keys مختلفة)
        for key, value in data.items():
            if key not in ['categories', 'image_url', 'parent_id', 'sort_order']:
                if isinstance(value, dict) and 'id' in value:
                    result['products'].append({
                        'id': value.get('id'),
                        'name': key,
                        'price': float(value.get('price', 0)) if value.get('price') else 0,
                        'available': value.get('available', True),
                        'product_type': value.get('product_type', 'service'),
                        'base_price': float(value.get('base_price', 0)) if value.get('base_price') else 0
                    })
        
        return result
    
    # ============= مزامنة البيانات مع قاعدة البيانات =============
    async def sync_services_to_db(self, db_pool, default_profit: int = 10):
        """
        مزامنة الخدمات من Mousa Card مع قاعدة البيانات المحلية
        """
        products = await self.get_products()
        
        if not products:
            logger.error("❌ لا توجد منتجات للمزامنة من Mousa Card")
            return 0
        
        synced_count = 0
        updated_count = 0
        
        async with db_pool.acquire() as conn:
            for product in products:
                if not product['available']:
                    continue
                
                # حساب سعر البيع بعد إضافة نسبة الربح
                selling_price = product['price'] * (1 + default_profit / 100)
                
                # التحقق إذا كان المنتج موجوداً
                existing = await conn.fetchval(
                    "SELECT id FROM applications WHERE api_service_id = $1",
                    str(product['id'])
                )
                
                if existing:
                    # تحديث المنتج الموجود
                    await conn.execute('''
                        UPDATE applications 
                        SET unit_price_usd = $1,
                            min_units = $2,
                            profit_percentage = $3,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE api_service_id = $4
                    ''', selling_price, product['min_quantity'], default_profit, str(product['id']))
                    updated_count += 1
                else:
                    # إضافة منتج جديد
                    await conn.execute('''
                        INSERT INTO applications 
                        (name, unit_price_usd, min_units, profit_percentage, 
                         type, api_service_id, is_active, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP)
                    ''',
                    product['name'],
                    selling_price,
                    product['min_quantity'],
                    default_profit,
                    'service',
                    str(product['id']),
                    True
                    )
                    synced_count += 1
        
        logger.info(f"✅ مزامنة Mousa Card: {synced_count} خدمات جديدة, {updated_count} تحديث")
        return synced_count + updated_count


# ============= Singleton Pattern =============
_api_client: Optional[MousaCardAPI] = None
_api_token: str = None


def set_api_token(token: str):
    """تحديث توكن API"""
    global _api_token, _api_client
    _api_token = token
    if _api_client:
        _api_client.api_token = token


def get_api_client() -> MousaCardAPI:
    """الحصول على عميل API (Singleton)"""
    global _api_client, _api_token
    if _api_client is None:
        from config import API_TOKEN, API_BASE_URL
        _api_token = API_TOKEN or "4lqzCLWniWuQwkYjO6YIVPtpnbMguw8JXyVvfvO6OoS1aUNI9IYQNDUJFN-Ittev"
        _api_client = MousaCardAPI(API_BASE_URL or "https://mousa-card.com", _api_token)
    return _api_client


async def close_api_client():
    """إغلاق عميل API"""
    global _api_client
    if _api_client:
        await _api_client.close()
        _api_client = None