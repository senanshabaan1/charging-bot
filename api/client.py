import aiohttp
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class MousaCardClient:
    def __init__(self, api_url: str, api_token: str):
        self.api_url = api_url.rstrip('/')
        self.api_token = api_token.strip()
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def _make_request(self, method: str, endpoint: str, data: dict = None) -> Any:
        """تنفيذ طلبات HTTP مع التعامل مع الأخطاء"""
        url = f"{self.api_url}{endpoint}"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.request(method, url, json=data, timeout=30) as response:
                    if response.status == 200:
                        try:
                            return await response.json()
                        except Exception:
                            return await response.text()
                    else:
                        text = await response.text()
                        logger.error(f"❌ خطأ API من Mousa Card [{response.status}]: {text}")
                        return None
            except Exception as e:
                logger.error(f"❌ خطأ في الاتصال مع Mousa Card ({url}): {e}")
                return None

    async def get_products(self) -> List[Dict]:
        """جلب جميع المنتجات المتاحة مباشرة من مسار /client/api/products"""
        data = await self._make_request("GET", "/client/api/products")
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "products" in data:
            return data["products"]
        return []

    async def get_content_by_category(self, category_id: int = 0) -> dict:
        """جلب الأقسام والتصنيفات من مسار /client/api/content/{id}"""
        try:
            endpoint = f"/client/api/content/{category_id}"
            data = await self._make_request("GET", endpoint)
            if isinstance(data, dict):
                return data
            return {"categories": [], "products": []}
        except Exception as e:
            logger.error(f"❌ خطأ في جلب المحتوى للتصنيف {category_id}: {e}")
            return {"categories": [], "products": []}

    async def sync_services_to_db(self, db_pool, default_profit: int = 10):
        """مزامنة الأقسام والمنتجات بالاعتماد على مسار المنتجات والأقسام معاً"""
        # 1. جلب الأقسام الرئيسية والفرعية
        main_content = await self.get_content_by_category(0)
        root_categories = main_content.get('categories', [])
        
        # 2. جلب جميع المنتجات مباشرة من المسار الاحترافي /client/api/products
        all_products = await self.get_products()
        if not all_products:
            # خطة بديلة لو فشل المسار المباشر
            all_products = main_content.get('products', [])

        synced_cats_count = 0
        synced_prod_count = 0
        
        async with db_pool.acquire() as conn:
            cat_mapping = {}
            categories_to_process = list(root_categories)
            
            # جلب الأقسام الفرعية أيضاً لتكتمل الشجرة
            for cat in root_categories:
                cat_id_in_api = cat['id']
                sub_content = await self.get_content_by_category(cat_id_in_api)
                sub_cats = sub_content.get('categories', [])
                if isinstance(sub_cats, list):
                    categories_to_process.extend(sub_cats)

            # حفظ الأقسام في قاعدة البيانات
            for cat in categories_to_process:
                api_cat_id = cat['id']
                cat_name = cat.get('name', 'تصنيف غير معروف')
                sort_order = cat.get('sort_order', 1)
                icon = "📁"
                
                name_lower = cat_name.lower()
                if any(x in name_lower for x in ['pubg', 'ببجي', 'free fire', 'game', 'لعبة', 'شدات']):
                    icon = "🎮"
                elif any(x in name_lower for x in ['رصيد', 'سيرياتل', 'mtn', 'وحدات', 'صاعق']):
                    icon = "📞"
                elif any(x in name_lower for x in ['telegram', 'دردشة', 'stars', 'نجوم', 'whatsapp']):
                    icon = "💬"
                elif any(x in name_lower for x in ['netflix', 'spotify', 'اشتراك', 'vip', 'قنوات']):
                    icon = "📅"
                
                db_cat_id = await conn.fetchval(
                    "SELECT id FROM categories WHERE name = $1 OR display_name = $2", 
                    str(api_cat_id), cat_name
                )
                
                if not db_cat_id:
                    db_cat_id = await conn.fetchval('''
                        INSERT INTO categories (name, display_name, icon, sort_order)
                        VALUES ($1, $2, $3, $4) RETURNING id
                    ''', str(api_cat_id), cat_name, icon, sort_order)
                    synced_cats_count += 1
                else:
                    await conn.execute("UPDATE categories SET display_name = $1 WHERE id = $2", cat_name, db_cat_id)
                
                cat_mapping[api_cat_id] = db_cat_id

            # قسم افتراضي احتياطي
            default_cat_id = await conn.fetchval("SELECT id FROM categories LIMIT 1")
            if not default_cat_id:
                default_cat_id = await conn.fetchval('''
                    INSERT INTO categories (name, display_name, icon, sort_order)
                    VALUES ($1, $2, $3, $4) RETURNING id
                ''', 'default', 'خدمات عامة', '📁', 99)

            # حفظ المنتجات وتوزيعها حسب الـ parent_id أو القيمة القادمة من الـ API
            for product in all_products:
                if not product.get('available', True):
                    continue
                    
                prod_id = product.get('id')
                if not prod_id:
                    continue
                
                prod_name = product.get('name', 'خدمة بدون اسم')
                base_price_syp = float(product.get('price', 0))
                
                # استخراج الحدود للكمية لو وجدت (qty_values)
                qty_values = product.get('qty_values')
                min_units = 1
                if isinstance(qty_values, dict):
                    try:
                        min_units = int(float(qty_values.get('min', 1)))
                    except:
                        min_units = 1

                parent_api_cat_id = product.get('parent_id', product.get('category_id', 0))
                target_db_cat_id = cat_mapping.get(parent_api_cat_id, default_cat_id)
                
                existing = await conn.fetchval(
                    "SELECT id FROM applications WHERE api_service_id = $1",
                    str(prod_id)
                )
                
                if existing:
                    await conn.execute('''
                        UPDATE applications 
                        SET name = $1,
                            unit_price_usd = $2,
                            min_units = $3,
                            category_id = $4,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = $5
                    ''', prod_name, base_price_syp, min_units, target_db_cat_id, existing)
                    synced_prod_count += 1
                else:
                    try:
                        await conn.execute('''
                            INSERT INTO applications 
                            (name, unit_price_usd, min_units, profit_percentage, 
                             type, api_service_id, category_id, is_active)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ''',
                        prod_name,
                        base_price_syp,
                        min_units,
                        default_profit,
                        'service',
                        str(prod_id),
                        target_db_cat_id,
                        True
                        )
                        synced_prod_count += 1
                    except Exception as e:
                        logger.error(f"⚠️ خطأ في إدخال المنتج {prod_name}: {e}")
        
        from cache import clear_cache
        clear_cache("categories")
        clear_cache("apps_by_category")
        clear_cache("products_list")
        
        logger.info(f"✅ تمت مزامنة المنتجات والأقسام بنجاح: {synced_cats_count} قسم, {synced_prod_count} منتج")
        return synced_cats_count + synced_prod_count

    async def create_order(self, product_id: int, quantity: int, player_id: str, extra_params: dict = None) -> dict:
        """إرسال طلب شراء إلى Mousa Card API"""
        payload = {
            "product_id": product_id,
            "quantity": quantity,
            "player_id": player_id
        }
        if extra_params:
            payload.update(extra_params)
            
        result = await self._make_request("POST", "/client/api/order/create", payload)
        
        if isinstance(result, dict):
            if result.get("status") == "success" or result.get("success") == True or "order_id" in result:
                return {
                    "success": True,
                    "order_id": result.get("order_id", result.get("id", "N/A")),
                    "raw": result
                }
            else:
                error_msg = result.get("message", result.get("error", "خطأ غير معروف من المصدر"))
                return {"success": False, "error": error_msg}
        return {"success": False, "error": "استجابة غير صالحة من خادم الموقع"}


def get_api_client() -> MousaCardClient:
    import os
    api_url = os.getenv("MOUSA_API_URL", "https://mousacard.com")
    api_token = "eVbvddm6ATc7pVsSMtakM5hTpZzd9RtvP6GRYPMByDQb5fWtfZKQPCsqEzYPBM1q"
    return MousaCardClient(api_url, api_token)
