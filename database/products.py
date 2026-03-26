# database/products.py
import logging
from cache import cached
from typing import Optional, Dict, Any, List
from decimal import Decimal

logger = logging.getLogger(__name__)


# ============= دوال app_variants (للتوافق مع الكود القديم) =============

async def get_app_variants(db_pool, app_id):
    """جلب فئات منتج معين"""
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM app_variants WHERE app_id = $1 AND is_active = TRUE ORDER BY price_usd",
            app_id
        )

async def get_app_variant(db_pool, variant_id):
    """جلب فئة محددة"""
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM app_variants WHERE id = $1",
            variant_id
        )

async def delete_app_variant(db_pool, variant_id):
    """حذف فئة"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE app_variants SET is_active = FALSE WHERE id = $1",
            variant_id
        )
        return True


# ============= دوال product_options المحسنة =============

async def get_product_options(db_pool, product_id, only_active: bool = True) -> List[Dict]:
    """
    جلب جميع خيارات المنتج مع نسبة الربح الخاصة بكل خيار
    Args:
        product_id: معرف المنتج
        only_active: جلب الخيارات النشطة فقط
    """
    try:
        async with db_pool.acquire() as conn:
            query = '''
                SELECT 
                    po.*,
                    a.profit_percentage as app_profit_percentage,
                    a.unit_price_usd as app_unit_price,
                    a.name as app_name
                FROM product_options po
                JOIN applications a ON po.product_id = a.id
                WHERE po.product_id = $1
            '''
            if only_active:
                query += " AND po.is_active = TRUE"
            query += " ORDER BY po.sort_order, po.price_usd"
            
            options = await conn.fetch(query, product_id)
            
            result = []
            for opt in options:
                opt_dict = dict(opt)
                # تحويل القيم إلى float
                opt_dict['price_usd'] = float(opt_dict['price_usd']) if opt_dict['price_usd'] else 0.0
                opt_dict['original_price_usd'] = float(opt_dict['original_price_usd']) if opt_dict.get('original_price_usd') else None
                opt_dict['profit_percentage'] = float(opt_dict['profit_percentage']) if opt_dict.get('profit_percentage') else 0.0
                opt_dict['app_profit_percentage'] = float(opt_dict['app_profit_percentage']) if opt_dict.get('app_profit_percentage') else 0.0
                opt_dict['quantity'] = int(opt_dict['quantity']) if opt_dict['quantity'] else 1
                result.append(opt_dict)
            return result
    except Exception as e:
        logger.error(f"❌ خطأ في جلب خيارات المنتج {product_id}: {e}")
        return []


async def get_product_option(db_pool, option_id: int) -> Optional[Dict]:
    """
    جلب معلومات خيار معين مع نسبة الربح الخاصة به
    """
    try:
        async with db_pool.acquire() as conn:
            option = await conn.fetchrow('''
                SELECT 
                    po.*,
                    a.profit_percentage as app_profit_percentage,
                    a.unit_price_usd as app_unit_price,
                    a.name as app_name
                FROM product_options po
                JOIN applications a ON po.product_id = a.id
                WHERE po.id = $1
            ''', option_id)
            
            if option:
                opt_dict = dict(option)
                opt_dict['price_usd'] = float(opt_dict['price_usd']) if opt_dict['price_usd'] else 0.0
                opt_dict['original_price_usd'] = float(opt_dict['original_price_usd']) if opt_dict.get('original_price_usd') else None
                opt_dict['profit_percentage'] = float(opt_dict['profit_percentage']) if opt_dict.get('profit_percentage') else 0.0
                opt_dict['app_profit_percentage'] = float(opt_dict['app_profit_percentage']) if opt_dict.get('app_profit_percentage') else 0.0
                opt_dict['quantity'] = int(opt_dict['quantity']) if opt_dict['quantity'] else 1
                return opt_dict
            return None
    except Exception as e:
        logger.error(f"❌ خطأ في جلب الخيار {option_id}: {e}")
        return None


async def update_product_option(db_pool, option_id: int, updates: Dict) -> bool:
    """
    تعديل خيار (سعر، اسم، كمية، نسبة ربح، سعر المورد)
    """
    try:
        async with db_pool.acquire() as conn:
            set_parts = []
            values = []
            allowed_fields = [
                'name', 'quantity', 'price_usd', 'sort_order', 
                'description', 'is_active', 'profit_percentage', 
                'original_price_usd'
            ]
            
            i = 1
            for key, value in updates.items():
                if key in allowed_fields:
                    set_parts.append(f"{key} = ${i}")
                    values.append(value)
                    i += 1
            
            if not set_parts:
                return False
            
            values.append(option_id)
            query = f"UPDATE product_options SET {', '.join(set_parts)}, updated_at = CURRENT_TIMESTAMP WHERE id = ${i}"
            await conn.execute(query, *values)
            logger.info(f"✅ تم تحديث الخيار {option_id}: {updates}")
            return True
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث الخيار {option_id}: {e}")
        return False


async def add_product_option(
    db_pool,
    product_id: int,
    name: str,
    quantity: int,
    price_usd: float,
    description: str = None,
    sort_order: int = 0,
    profit_percentage: float = None,
    original_price_usd: float = None
) -> Optional[int]:
    """
    إضافة خيار جديد مع نسبة ربح خاصة
    """
    try:
        async with db_pool.acquire() as conn:
            # إذا لم يتم تحديد نسبة ربح، استخدم نسبة التطبيق
            if profit_percentage is None:
                app_profit = await conn.fetchval(
                    "SELECT profit_percentage FROM applications WHERE id = $1",
                    product_id
                )
                profit_percentage = float(app_profit) if app_profit else 0.0
            
            # إذا لم يتم تحديد سعر المورد، استخدم price_usd كسعر المورد
            if original_price_usd is None:
                original_price_usd = price_usd
            
            option_id = await conn.fetchval('''
                INSERT INTO product_options 
                (product_id, name, quantity, price_usd, original_price_usd, 
                 profit_percentage, description, sort_order, is_active, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, TRUE, CURRENT_TIMESTAMP)
                RETURNING id
            ''', product_id, name, quantity, price_usd, original_price_usd, 
                profit_percentage, description, sort_order)
            
            logger.info(f"✅ تم إضافة خيار جديد: {name} (ID: {option_id})")
            return option_id
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة خيار: {e}")
        return None


async def update_option_profit(db_pool, option_id: int, profit_percentage: float) -> bool:
    """
    تحديث نسبة الربح لخيار معين
    إذا كان profit_percentage = 0 أو None، سيتم استخدام نسبة التطبيق
    """
    try:
        async with db_pool.acquire() as conn:
            if profit_percentage is None or profit_percentage == 0:
                await conn.execute(
                    "UPDATE product_options SET profit_percentage = NULL WHERE id = $1",
                    option_id
                )
                logger.info(f"✅ تم حذف نسبة الربح الخاصة للخيار {option_id} (سيستخدم نسبة التطبيق)")
            else:
                await conn.execute(
                    "UPDATE product_options SET profit_percentage = $1 WHERE id = $2",
                    profit_percentage, option_id
                )
                logger.info(f"✅ تم تحديث نسبة الربح للخيار {option_id} إلى {profit_percentage}%")
            return True
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث نسبة الربح للخيار {option_id}: {e}")
        return False


async def update_option_original_price(db_pool, option_id: int, original_price_usd: float) -> bool:
    """
    تحديث سعر المورد الأصلي للخيار
    """
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE product_options SET original_price_usd = $1 WHERE id = $2",
                original_price_usd, option_id
            )
            logger.info(f"✅ تم تحديث سعر المورد للخيار {option_id} إلى {original_price_usd}$")
            return True
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث سعر المورد للخيار {option_id}: {e}")
        return False


async def calculate_option_price(
    option: Dict,
    purchase_rate: float,
    user_discount: float = 0,
    use_option_profit: bool = True,
    offer_discount: int = 0
) -> Dict:
    """
    حساب سعر الخيار النهائي مع مراعاة:
    - سعر المورد الأصلي
    - نسبة ربح الخيار (أو نسبة التطبيق)
    - خصم المستخدم (VIP)
    - خصم العرض العام
    
    Args:
        option: بيانات الخيار (يحتوي على price_usd, original_price_usd, profit_percentage, app_profit_percentage)
        purchase_rate: سعر الصرف للشراء (مخفي)
        user_discount: خصم المستخدم من VIP (0-100)
        use_option_profit: استخدام نسبة ربح الخيار أم نسبة التطبيق
        offer_discount: خصم العرض العام (0-100)
    
    Returns:
        dict: {
            'supplier_price_usd': float,      # سعر المورد الأصلي
            'price_with_profit_usd': float,   # السعر بعد إضافة الربح
            'price_after_vip_usd': float,     # السعر بعد خصم VIP
            'price_after_offer_usd': float,   # السعر بعد خصم العرض
            'final_price_usd': float,         # السعر النهائي
            'final_price_syp': float,         # السعر النهائي بالليرة
            'profit_percentage': float,       # نسبة الربح المستخدمة
            'vip_discount_amount_usd': float, # قيمة خصم VIP
            'offer_discount_amount_usd': float, # قيمة خصم العرض
            'total_discount_amount_usd': float, # إجمالي الخصم
            'total_discount_percent': float    # إجمالي نسبة الخصم
        }
    """
    # سعر المورد الأصلي
    supplier_price_usd = option.get('original_price_usd') or option.get('price_usd', 0)
    supplier_price_usd = float(supplier_price_usd)
    
    # نسبة الربح (خاصة بالخيار أو من التطبيق)
    if use_option_profit and option.get('profit_percentage'):
        profit_percentage = float(option.get('profit_percentage', 0))
    else:
        profit_percentage = float(option.get('app_profit_percentage', 0))
    
    # حساب السعر بعد إضافة الربح
    price_with_profit_usd = supplier_price_usd * (1 + profit_percentage / 100)
    
    # حساب خصم VIP
    vip_discount_amount_usd = price_with_profit_usd * (user_discount / 100)
    price_after_vip_usd = price_with_profit_usd - vip_discount_amount_usd
    
    # حساب خصم العرض العام
    offer_discount_amount_usd = price_after_vip_usd * (offer_discount / 100)
    price_after_offer_usd = price_after_vip_usd - offer_discount_amount_usd
    
    # السعر النهائي
    final_price_usd = price_after_offer_usd
    final_price_syp = final_price_usd * purchase_rate
    
    # إجمالي الخصم
    total_discount_amount_usd = vip_discount_amount_usd + offer_discount_amount_usd
    total_discount_percent = (total_discount_amount_usd / price_with_profit_usd * 100) if price_with_profit_usd > 0 else 0
    
    return {
        'supplier_price_usd': supplier_price_usd,
        'price_with_profit_usd': price_with_profit_usd,
        'price_after_vip_usd': price_after_vip_usd,
        'price_after_offer_usd': price_after_offer_usd,
        'final_price_usd': final_price_usd,
        'final_price_syp': final_price_syp,
        'profit_percentage': profit_percentage,
        'vip_discount_amount_usd': vip_discount_amount_usd,
        'offer_discount_amount_usd': offer_discount_amount_usd,
        'total_discount_amount_usd': total_discount_amount_usd,
        'total_discount_percent': total_discount_percent
    }


# ============= دوال مساعدة مع كاش =============

@cached(ttl=20, key_prefix="product_options")
async def get_product_options_cached(pool, product_id: int, only_active: bool = True) -> List[Dict]:
    """جلب خيارات المنتج مع كاش 20 ثانية"""
    return await get_product_options(pool, product_id, only_active)


@cached(ttl=30, key_prefix="product_option")
async def get_product_option_cached(pool, option_id: int) -> Optional[Dict]:
    """جلب خيار معين مع كاش 30 ثانية"""
    return await get_product_option(pool, option_id)


# ============= دوال التطبيقات =============

async def get_all_applications(pool) -> List[Dict]:
    """جلب جميع التطبيقات مع معلومات الأقسام"""
    try:
        async with pool.acquire() as conn:
            apps = await conn.fetch('''
                SELECT a.*, c.display_name as category_name, c.icon as category_icon
                FROM applications a
                LEFT JOIN categories c ON a.category_id = c.id
                ORDER BY c.sort_order, a.name
            ''')
            result = []
            for app in apps:
                app_dict = dict(app)
                app_dict['unit_price_usd'] = float(app_dict['unit_price_usd']) if app_dict['unit_price_usd'] else 0.0
                app_dict['profit_percentage'] = float(app_dict['profit_percentage']) if app_dict['profit_percentage'] else 0.0
                result.append(app_dict)
            return result
    except Exception as e:
        logger.error(f"❌ خطأ في جلب التطبيقات: {e}")
        return []


async def get_applications_by_category(pool, category_id: int) -> List[Dict]:
    """جلب التطبيقات التابعة لقسم محدد"""
    try:
        async with pool.acquire() as conn:
            apps = await conn.fetch(
                "SELECT * FROM applications WHERE category_id = $1 AND is_active = TRUE ORDER BY name",
                category_id
            )
            result = []
            for app in apps:
                app_dict = dict(app)
                app_dict['unit_price_usd'] = float(app_dict['unit_price_usd']) if app_dict['unit_price_usd'] else 0.0
                app_dict['profit_percentage'] = float(app_dict['profit_percentage']) if app_dict['profit_percentage'] else 0.0
                result.append(app_dict)
            return result
    except Exception as e:
        logger.error(f"❌ خطأ في جلب تطبيقات القسم {category_id}: {e}")
        return []


async def get_application_by_id(pool, app_id: int) -> Optional[Dict]:
    """جلب تطبيق حسب معرفه"""
    try:
        async with pool.acquire() as conn:
            app = await conn.fetchrow(
                "SELECT * FROM applications WHERE id = $1",
                app_id
            )
            if app:
                app_dict = dict(app)
                app_dict['unit_price_usd'] = float(app_dict['unit_price_usd']) if app_dict['unit_price_usd'] else 0.0
                app_dict['profit_percentage'] = float(app_dict['profit_percentage']) if app_dict['profit_percentage'] else 0.0
                return app_dict
            return None
    except Exception as e:
        logger.error(f"❌ خطأ في جلب التطبيق {app_id}: {e}")
        return None


# ============= دوال الأقسام =============

async def get_all_categories(pool) -> List[Dict]:
    """جلب جميع الأقسام"""
    try:
        async with pool.acquire() as conn:
            categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
            return [dict(cat) for cat in categories]
    except Exception as e:
        logger.error(f"❌ خطأ في جلب الأقسام: {e}")
        return []


async def update_category(db_pool, category_id: int, **kwargs) -> tuple:
    """تحديث معلومات قسم معين"""
    try:
        async with db_pool.acquire() as conn:
            set_parts = []
            values = []
            allowed_fields = ['name', 'display_name', 'icon', 'sort_order']
            
            i = 1
            for key, value in kwargs.items():
                if key in allowed_fields:
                    set_parts.append(f"{key} = ${i}")
                    values.append(value)
                    i += 1
            
            if not set_parts:
                return False, "لا توجد بيانات للتحديث"
            
            values.append(category_id)
            query = f"UPDATE categories SET {', '.join(set_parts)} WHERE id = ${i}"
            
            await conn.execute(query, *values)
            
            updated = await conn.fetchrow(
                "SELECT * FROM categories WHERE id = $1",
                category_id
            )
            
            logger.info(f"✅ تم تحديث القسم {category_id}: {kwargs}")
            return True, dict(updated) if updated else None
            
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث القسم {category_id}: {e}")
        return False, str(e)


async def get_category_by_id(db_pool, category_id: int) -> Optional[Dict]:
    """جلب معلومات قسم محدد"""
    try:
        async with db_pool.acquire() as conn:
            category = await conn.fetchrow(
                "SELECT * FROM categories WHERE id = $1",
                category_id
            )
            return dict(category) if category else None
    except Exception as e:
        logger.error(f"❌ خطأ في جلب القسم {category_id}: {e}")
        return None


async def delete_category(db_pool, category_id: int) -> tuple:
    """حذف قسم (مع نقل التطبيقات التابعة لقسم افتراضي أو حذفها)"""
    try:
        async with db_pool.acquire() as conn:
            apps_count = await conn.fetchval(
                "SELECT COUNT(*) FROM applications WHERE category_id = $1",
                category_id
            )
            
            if apps_count > 0:
                default_cat = await conn.fetchval(
                    "SELECT id FROM categories WHERE name = 'chat_apps' LIMIT 1"
                )
                
                if default_cat:
                    await conn.execute(
                        "UPDATE applications SET category_id = $1 WHERE category_id = $2",
                        default_cat, category_id
                    )
                    logger.info(f"📦 تم نقل {apps_count} تطبيق من القسم {category_id} إلى {default_cat}")
                else:
                    await conn.execute(
                        "DELETE FROM applications WHERE category_id = $1",
                        category_id
                    )
                    logger.warning(f"⚠️ تم حذف {apps_count} تطبيق تابع للقسم {category_id}")
            
            result = await conn.execute(
                "DELETE FROM categories WHERE id = $1",
                category_id
            )
            
            if result == "DELETE 1":
                logger.info(f"✅ تم حذف القسم {category_id}")
                return True, "تم حذف القسم بنجاح"
            else:
                return False, "القسم غير موجود"
                
    except Exception as e:
        logger.error(f"❌ خطأ في حذف القسم {category_id}: {e}")
        return False, str(e)


async def reorder_categories(db_pool, category_orders: List[tuple]) -> tuple:
    """إعادة ترتيب الأقسام (استقبال قائمة تحتوي على (id, sort_order))"""
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                for cat_id, sort_order in category_orders:
                    await conn.execute(
                        "UPDATE categories SET sort_order = $1 WHERE id = $2",
                        sort_order, cat_id
                    )
            
            logger.info(f"✅ تم إعادة ترتيب {len(category_orders)} قسم")
            return True, None
            
    except Exception as e:
        logger.error(f"❌ خطأ في إعادة ترتيب الأقسام: {e}")
        return False, str(e)


async def add_category(db_pool, name: str, display_name: str, icon: str = "📁", sort_order: int = 0) -> tuple:
    """إضافة قسم جديد"""
    try:
        async with db_pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT id FROM categories WHERE name = $1",
                name
            )
            
            if existing:
                return False, f"يوجد قسم بنفس الاسم الداخلي: {name}"
            
            cat_id = await conn.fetchval('''
                INSERT INTO categories (name, display_name, icon, sort_order, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                RETURNING id
            ''', name, display_name, icon, sort_order)
            
            logger.info(f"✅ تم إضافة قسم جديد: {display_name} (ID: {cat_id})")
            return True, cat_id
            
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة قسم: {e}")
        return False, str(e)
