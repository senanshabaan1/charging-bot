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
        """جلب المنتجات (للتوافق القديم)"""
        content = await self.get_content_by_category(0)
        return content.get('products', [])

    async def get_content_by_category(self, category_id: int = 0) -> dict:
        """جلب الأقسام والمنتجات لتصنيف معين حسب الـ API الجديد"""
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
        """مزامنة الأقسام والتصنيفات والمنتجات تماماً كما تأتي من API الموقع"""
        main_content = await self.get_content_by_category(0)
        
        root_categories = main_content.get('categories', [])
        all_products = main_content.get('products', [])

        synced_cats_count = 0
        synced_prod_count = 0
        
        async with db_pool.acquire() as conn:
            cat_mapping = {} # لتخزين معرف القسم في الموقع مقابل معرفه في قاعدة البيانات
            categories_to_process = list(root_categories)
            
            # جلب محتوى الأقسام الفرعية والتصنيفات تلو الأخرى
            for cat in root_categories:
                cat_id_in_api = cat['id']
                sub_content = await self.get_content_by_category(cat_id_in_api)
                
                # إضافة منتجات هذا القسم إلى القائمة الشاملة
                if 'products' in sub_content and isinstance(sub_content['products'], list):
                    for p in sub_content['products']:
                        p['parent_id'] = cat_id_in_api
                        all_products.append(p)
                
                # إضافة الأقسام الفرعية إن وجدت
                sub_cats = sub_content.get('categories', [])
                if isinstance(sub_cats, list):
                    categories_to_process.extend(sub_cats)

            # حفظ الأقسام في قاعدة البيانات
            for cat in categories_to_process:
                api_cat_id = cat['id']
                cat_name = cat.get('name', 'تصنيف غير معروف')
                sort_order = cat.get('sort_order', 1)
                icon = "📁"
                
                # إعطاء أيقونات حسب اسم القسم تلقائياً
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
                    # تحديث اسم القسم إن طرأ عليه تغيير
                    await conn.execute("UPDATE categories SET display_name = $1 WHERE id = $2", cat_name, db_cat_id)
                
                cat_mapping[api_cat_id] = db_cat_id

            # قسم افتراضي احتياطي في حال وجد منتج بدون قسم
            default_cat_id = await conn.fetchval("SELECT id FROM categories LIMIT 1")
            if not default_cat_id:
                default_cat_id = await conn.fetchval('''
                    INSERT INTO categories (name, display_name, icon, sort_order)
                    VALUES ($1, $2, $3, $4) RETURNING id
                ''', 'default', 'خدمات عامة', '📁', 99)

            # حفظ المنتجات وربطها بأقسامها الصحيحة
            for product in all_products:
                prod_id = product.get('id')
                if not prod_id:
                    continue
                
                prod_name = product.get('name', 'خدمة بدون اسم')
                base_price_syp = float(product.get('price', 0))
                
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
                            category_id = $3,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = $4
                    ''', prod_name, base_price_syp, target_db_cat_id, existing)
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
                        1, 
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
        
        logger.info(f"✅ تمت المزامنة حسب أقسام الموقع: {synced_cats_count} قسم, {synced_prod_count} منتج")
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
    """إنشاء وتجهيز نسخة من عميل الـ API بالاعتماد على إعدادات القاعدة أو الكونفج"""
    import os
    api_url = os.getenv("MOUSA_API_URL", "https://mousacard.com")
    # الـ Token الخاص بك
    api_token = "eVbvddm6ATc7pVsSMtakM5hTpZzd9RtvP6GRYPMByDQb5fWtfZKQPCsqEzYPBM1q"
    return MousaCardClient(api_url, api_token)
