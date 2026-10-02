# database/products.py
import logging
from cache import cached

# ============= دوال app_variants =============

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

# ============= دوال product_options =============

async def get_product_options(db_pool, product_id):
    """جلب جميع الخيارات النشطة لمنتج معين"""
    try:
        async with db_pool.acquire() as conn:
            options = await conn.fetch(
                "SELECT * FROM product_options WHERE product_id = $1 AND is_active = TRUE ORDER BY sort_order, price_usd",
                product_id
            )
            
            result = []
            for opt in options:
                opt_dict = dict(opt)
                opt_dict['price_usd'] = float(opt_dict['price_usd']) if opt_dict['price_usd'] else 0.0
                result.append(opt_dict)
            return result
    except Exception as e:
        logging.error(f"❌ خطأ في جلب خيارات المنتج {product_id}: {e}")
        return []

async def get_product_option(db_pool, option_id):
    """جلب معلومات خيار معين من product_options"""
    try:
        async with db_pool.acquire() as conn:
            option = await conn.fetchrow(
                "SELECT * FROM product_options WHERE id = $1",
                option_id
            )
            if option:
                opt_dict = dict(option)
                opt_dict['price_usd'] = float(opt_dict['price_usd']) if opt_dict['price_usd'] else 0.0
                return opt_dict
            return None
    except Exception as e:
        logging.error(f"❌ خطأ في جلب الخيار {option_id}: {e}")
        return None

async def update_product_option(db_pool, option_id, updates):
    """تعديل خيار (سعر، اسم، كمية) - مع تحديد الحقول المسموحة"""
    async with db_pool.acquire() as conn:
        set_parts = []
        values = []
        allowed_fields = ['name', 'quantity', 'price_usd', 'sort_order', 'description', 'is_active']
        
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
        return True

async def add_product_option(db_pool, product_id, name, quantity, price_usd, description=None, sort_order=0):
    """إضافة خيار جديد"""
    async with db_pool.acquire() as conn:
        option_id = await conn.fetchval('''
            INSERT INTO product_options (product_id, name, quantity, price_usd, description, sort_order, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, TRUE)
            RETURNING id
        ''', product_id, name, quantity, price_usd, description, sort_order)
        return option_id

@cached(ttl=20, key_prefix="product_options")
async def get_product_options_cached(pool, product_id):
    """جلب خيارات المنتج مع كاش 20 ثانية"""
    return await get_product_options(pool, product_id)

# ============= دوال التطبيقات =============

async def get_all_applications(pool):
    """جلب جميع التطبيقات مع معلومات الأقسام"""
    try:
        async with pool.acquire() as conn:
            apps = await conn.fetch('''
                SELECT a.*, c.display_name as category_name, c.icon as category_icon
                FROM applications a
                LEFT JOIN categories c ON a.category_id = c.id
                WHERE a.is_active = TRUE
                ORDER BY c.sort_order, a.name
            ''')
            return apps
    except Exception as e:
        logging.error(f"❌ خطأ في جلب التطبيقات: {e}")
        return []

async def get_applications_by_category(pool, category_id):
    """جلب التطبيقات التابعة لقسم محدد"""
    try:
        async with pool.acquire() as conn:
            apps = await conn.fetch(
                "SELECT * FROM applications WHERE category_id = $1 AND is_active = TRUE ORDER BY name",
                category_id
            )
            return apps
    except Exception as e:
        logging.error(f"❌ خطأ في جلب تطبيقات القسم {category_id}: {e}")
        return []

# ============= دوال الأقسام =============

async def get_all_categories(pool):
    """جلب جميع الأقسام"""
    try:
        async with pool.acquire() as conn:
            categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
            return categories
    except Exception as e:
        logging.error(f"❌ خطأ في جلب الأقسام: {e}")
        return []

async def update_category(db_pool, category_id, **kwargs):
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
            
            logging.info(f"✅ تم تحديث القسم {category_id}: {kwargs}")
            return True, updated
            
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث القسم {category_id}: {e}")
        return False, str(e)

async def get_category_by_id(db_pool, category_id):
    """جلب معلومات قسم محدد"""
    try:
        async with db_pool.acquire() as conn:
            category = await conn.fetchrow(
                "SELECT * FROM categories WHERE id = $1",
                category_id
            )
            return category
    except Exception as e:
        logging.error(f"❌ خطأ في جلب القسم {category_id}: {e}")
        return None

async def delete_category(db_pool, category_id):
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
                    logging.info(f"📦 تم نقل {apps_count} تطبيق من القسم {category_id} إلى {default_cat}")
                else:
                    await conn.execute(
                        "DELETE FROM applications WHERE category_id = $1",
                        category_id
                    )
                    logging.warning(f"⚠️ تم حذف {apps_count} تطبيق تابع للقسم {category_id}")
            
            result = await conn.execute(
                "DELETE FROM categories WHERE id = $1",
                category_id
            )
            
            if result == "DELETE 1":
                logging.info(f"✅ تم حذف القسم {category_id}")
                return True, f"تم حذف القسم بنجاح"
            else:
                return False, "القسم غير موجود"
                
    except Exception as e:
        logging.error(f"❌ خطأ في حذف القسم {category_id}: {e}")
        return False, str(e)

async def reorder_categories(db_pool, category_orders):
    """إعادة ترتيب الأقسام (استقبال قائمة تحتوي على (id, sort_order))"""
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                for cat_id, sort_order in category_orders:
                    await conn.execute(
                        "UPDATE categories SET sort_order = $1 WHERE id = $2",
                        sort_order, cat_id
                    )
            
            logging.info(f"✅ تم إعادة ترتيب {len(category_orders)} قسم")
            return True, None
            
    except Exception as e:
        logging.error(f"❌ خطأ في إعادة ترتيب الأقسام: {e}")
        return False, str(e)

async def add_category(db_pool, name, display_name, icon="📁", sort_order=0):
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
            
            logging.info(f"✅ تم إضافة قسم جديد: {display_name} (ID: {cat_id})")
            return True, cat_id
            
    except Exception as e:
        logging.error(f"❌ خطأ في إضافة قسم: {e}")
        return False, str(e)
