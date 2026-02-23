# database.py
import asyncpg
import logging
import pytz
import random
import string
from datetime import datetime
from config import DB_CONFIG

# ============= الإعدادات الأساسية =============

DAMASCUS_TZ = pytz.timezone('Asia/Damascus')
logger = logging.getLogger(__name__)

# ============= دوال تنسيق الوقت =============

def format_local_time(dt):
    """تنسيق الوقت حسب توقيت دمشق للعرض"""
    if dt is None:
        return "غير معروف"
    
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    local_dt = dt.astimezone(DAMASCUS_TZ)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")

async def set_database_timezone(pool):
    """ضبط المنطقة الزمنية لقاعدة البيانات"""
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            db_time = await conn.fetchval("SELECT NOW()")
            logger.info(f"🕒 وقت DB بعد الضبط: {db_time}")
            return True
    except Exception as e:
        logger.error(f"❌ خطأ في ضبط توقيت قاعدة البيانات: {e}")
        return False

# ============= تهيئة قاعدة البيانات =============

async def init_db():
    """تهيئة قاعدة البيانات وإنشاء الجداول إذا لم تكن موجودة"""
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        
        # 1. جدول المستخدمين
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                balance FLOAT DEFAULT 0,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_banned BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- إحصائيات مالية
                total_deposits FLOAT DEFAULT 0,
                total_orders FLOAT DEFAULT 0,
                total_spent FLOAT DEFAULT 0,
                
                -- نظام النقاط
                total_points INTEGER DEFAULT 0,
                total_points_earned INTEGER DEFAULT 0,
                total_points_redeemed INTEGER DEFAULT 0,
                
                -- نظام الإحالة
                referral_code TEXT UNIQUE,
                referred_by BIGINT,
                referral_count INTEGER DEFAULT 0,
                referral_earnings FLOAT DEFAULT 0,
                
                -- نظام VIP
                vip_level INTEGER DEFAULT 0,
                discount_percent INTEGER DEFAULT 0,
                manual_vip BOOLEAN DEFAULT FALSE
            );
        ''')
        logger.info("✅ تم إنشاء جدول users")

        # 2. جدول الأقسام
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                display_name TEXT,
                icon TEXT DEFAULT '📁',
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("✅ تم إنشاء جدول categories")

        # 3. جدول التطبيقات
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                unit_price_usd FLOAT,
                min_units INTEGER,
                profit_percentage FLOAT DEFAULT 10,
                category_id INTEGER REFERENCES categories(id),
                type VARCHAR(50) DEFAULT 'service',
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("✅ تم إنشاء جدول applications")

        # 4. جدول خيارات المنتجات (للألعاب والاشتراكات)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS product_options (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                quantity INTEGER,
                price_usd DECIMAL(10, 6) NOT NULL,
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("✅ تم إنشاء جدول product_options")

        # 5. جدول طلبات الشحن
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS deposit_requests (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                method TEXT,
                amount FLOAT,
                amount_syp FLOAT,
                tx_info TEXT,
                status TEXT DEFAULT 'pending',
                admin_notes TEXT,
                photo_file_id TEXT,
                group_message_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("✅ تم إنشاء جدول deposit_requests")

        # 6. جدول طلبات التطبيقات
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                app_id INTEGER,
                app_name TEXT,
                variant_id INTEGER,
                variant_name TEXT,
                quantity INTEGER,
                duration_days INTEGER,
                unit_price_usd FLOAT,
                total_amount_syp FLOAT,
                target_id TEXT,
                status TEXT DEFAULT 'pending',
                points_earned INTEGER DEFAULT 0,
                group_message_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("✅ تم إنشاء جدول orders")

        # 7. جدول سجل النقاط
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS points_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                points INTEGER,
                action TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("✅ تم إنشاء جدول points_history")

        # 8. جدول طلبات استرداد النقاط
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS redemption_requests (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                points INTEGER,
                amount_usd FLOAT,
                amount_syp FLOAT,
                status TEXT DEFAULT 'pending',
                admin_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("✅ تم إنشاء جدول redemption_requests")

        # 9. جدول إعدادات البوت
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("✅ تم إنشاء جدول bot_settings")

        # 10. جدول مستويات VIP
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS vip_levels (
                level INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                min_spent FLOAT NOT NULL,
                discount_percent INTEGER NOT NULL,
                icon TEXT DEFAULT '⭐'
            );
        ''')
        logger.info("✅ تم إنشاء جدول vip_levels")

        # 11. جدول السجلات
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                action TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("✅ تم إنشاء جدول logs")

        # 12. جدول إعدادات التقارير
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS report_settings (
                id SERIAL PRIMARY KEY,
                setting_key TEXT UNIQUE,
                setting_value TEXT,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("✅ تم إنشاء جدول report_settings")

        # ============= إدراج البيانات الافتراضية =============

        # إضافة مستويات VIP الافتراضية
        await conn.execute('''
            INSERT INTO vip_levels (level, name, min_spent, discount_percent, icon) 
            VALUES 
                (0, 'VIP 0', 0, 0, '🟢'),
                (1, 'VIP 1', 1000, 1, '🔵'),
                (2, 'VIP 2', 2000, 2, '🟣'),
                (3, 'VIP 3', 4000, 3, '🟡'),
                (4, 'VIP 4', 8000, 5, '🔴')
            ON CONFLICT (level) DO UPDATE SET 
                min_spent = EXCLUDED.min_spent,
                discount_percent = EXCLUDED.discount_percent,
                icon = EXCLUDED.icon;
        ''')

        # إضافة إعدادات البوت الأساسية
        await conn.execute('''
            INSERT INTO bot_settings (key, value, description) 
            VALUES 
                ('bot_status', 'running', 'حالة البوت (running/stopped)'),
                ('maintenance_message', 'البوت قيد الصيانة حالياً', 'رسالة الصيانة'),
                ('points_per_order', '1', 'نقاط لكل عملية شراء'),
                ('points_per_referral', '1', 'نقاط لكل إحالة'),
                ('redemption_rate', '100', 'عدد النقاط مقابل 1 دولار'),
                ('usd_to_syp', '118', 'سعر صرف الدولار مقابل الليرة'),
                ('syriatel_nums', '74091109,63826779', 'أرقام سيرياتل كاش')
            ON CONFLICT (key) DO NOTHING;
        ''')

        # إضافة إعدادات التقارير
        await conn.execute('''
            INSERT INTO report_settings (setting_key, setting_value, description) 
            VALUES 
                ('daily_report_enabled', 'true', 'تفعيل التقرير اليومي'),
                ('report_time', '00:00', 'وقت إرسال التقرير'),
                ('report_recipients', 'owner_only', 'مستلمو التقرير')
            ON CONFLICT (setting_key) DO NOTHING;
        ''')

        # إضافة قسم افتراضي إذا لم تكن هناك أقسام
        existing_cats = await conn.fetchval("SELECT COUNT(*) FROM categories")
        if existing_cats == 0:
            await conn.execute('''
                INSERT INTO categories (name, display_name, icon, sort_order) 
                VALUES 
                    ('games', '🎮 ألعاب', '🎮', 1),
                    ('chat_apps', '💬 تطبيقات دردشة', '💬', 2)
                ON CONFLICT (name) DO NOTHING;
            ''')
            logger.info("✅ تم إضافة الأقسام الافتراضية")

        await conn.close()
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")
        
    except Exception as e:
        logger.error(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}")
        raise

# ============= إنشاء مجمع الاتصالات =============

async def get_pool():
    """إنشاء مجمع اتصالات مع ضبط المنطقة الزمنية"""
    try:
        async def init_connection(conn):
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
        
        pool_kwargs = {
            'command_timeout': 60,
            'server_settings': {'timezone': 'Asia/Damascus'},
            'init': init_connection,
            'statement_cache_size': 0,
            'max_cached_statement_lifetime': 0
        }
        
        if "dsn" in DB_CONFIG:
            pool = await asyncpg.create_pool(dsn=DB_CONFIG["dsn"], **pool_kwargs)
        else:
            pool = await asyncpg.create_pool(**DB_CONFIG, **pool_kwargs)
        
        logger.info("✅ تم إنشاء مجمع الاتصالات")
        return pool
    except Exception as e:
        logger.error(f"❌ فشل إنشاء مجمع الاتصالات: {e}")
        return None

# ============= دوال الإحالة =============

async def generate_referral_code(pool, user_id):
    """إنشاء كود إحالة فريد للمستخدم"""
    async with pool.acquire() as conn:
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            exists = await conn.fetchval(
                "SELECT user_id FROM users WHERE referral_code = $1",
                code
            )
            if not exists:
                await conn.execute(
                    "UPDATE users SET referral_code = $1 WHERE user_id = $2",
                    code, user_id
                )
                return code

async def process_referral(pool, referred_user_id, referrer_code):
    """معالجة الإحالة عند تسجيل مستخدم جديد"""
    try:
        async with pool.acquire() as conn:
            # البحث عن المُحيل
            referrer = await conn.fetchrow(
                "SELECT user_id FROM users WHERE referral_code = $1",
                referrer_code
            )
            
            if not referrer or referrer['user_id'] == referred_user_id:
                return None
            
            # تحديث بيانات المُحيل
            points = await conn.fetchval(
                "SELECT value::integer FROM bot_settings WHERE key = 'points_per_referral'"
            ) or 1
            
            await conn.execute('''
                UPDATE users 
                SET referral_count = referral_count + 1,
                    total_points = total_points + $1,
                    referral_earnings = referral_earnings + $1
                WHERE user_id = $2
            ''', points, referrer['user_id'])
            
            # تحديث المستخدم الجديد
            await conn.execute(
                "UPDATE users SET referred_by = $1 WHERE user_id = $2",
                referrer['user_id'], referred_user_id
            )
            
            # تسجيل في سجل النقاط
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description)
                VALUES ($1, $2, $3, $4)
            ''', referrer['user_id'], points, 'referral', f'إحالة المستخدم {referred_user_id}')
            
            # جلب الرصيد الجديد
            new_points = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                referrer['user_id']
            )
            
            return {
                'referrer_id': referrer['user_id'],
                'points': points,
                'new_total': new_points
            }
            
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة الإحالة: {e}")
        return None

async def get_user_referral_info(pool, user_id):
    """جلب معلومات الإحالة للمستخدم"""
    try:
        async with pool.acquire() as conn:
            # معلومات المستخدم
            user = await conn.fetchrow('''
                SELECT referral_code, referral_count, referral_earnings, referred_by
                FROM users WHERE user_id = $1
            ''', user_id)
            
            if not user:
                return None
            
            # قائمة المحالين
            referrals = await conn.fetch('''
                SELECT user_id, username, created_at AT TIME ZONE 'Asia/Damascus' as created_at
                FROM users WHERE referred_by = $1
                ORDER BY created_at DESC
                LIMIT 10
            ''', user_id)
            
            return {
                'code': user['referral_code'],
                'count': user['referral_count'] or 0,
                'earnings': user['referral_earnings'] or 0,
                'referred_by': user['referred_by'],
                'referrals_list': referrals
            }
            
    except Exception as e:
        logger.error(f"❌ خطأ في جلب معلومات الإحالة: {e}")
        return None

# ============= دوال النقاط =============

async def add_points(pool, user_id, points, action, description):
    """إضافة نقاط للمستخدم"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET total_points = total_points + $1, 
                    total_points_earned = total_points_earned + $1 
                WHERE user_id = $2
            ''', points, user_id)
            
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description)
                VALUES ($1, $2, $3, $4)
            ''', user_id, points, action, description)
            
            return True
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة نقاط للمستخدم {user_id}: {e}")
        return False

async def deduct_points(pool, user_id, points, action, description):
    """خصم نقاط من المستخدم"""
    try:
        async with pool.acquire() as conn:
            current = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                user_id
            )
            
            if current < points:
                return False, "نقاط غير كافية"
            
            await conn.execute('''
                UPDATE users 
                SET total_points = total_points - $1, 
                    total_points_redeemed = total_points_redeemed + $1 
                WHERE user_id = $2
            ''', points, user_id)
            
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description)
                VALUES ($1, $2, $3, $4)
            ''', user_id, -points, action, description)
            
            return True, None
    except Exception as e:
        logger.error(f"❌ خطأ في خصم نقاط من المستخدم {user_id}: {e}")
        return False, str(e)

async def get_user_points(pool, user_id):
    """جلب نقاط المستخدم"""
    try:
        async with pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                user_id
            ) or 0
    except Exception as e:
        logger.error(f"❌ خطأ في جلب نقاط المستخدم {user_id}: {e}")
        return 0

async def get_points_history(pool, user_id, limit=20):
    """جلب سجل نقاط المستخدم"""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT points, action, description, 
                       created_at AT TIME ZONE 'Asia/Damascus' as created_at
                FROM points_history
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            ''', user_id, limit)
            
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"❌ خطأ في جلب سجل النقاط للمستخدم {user_id}: {e}")
        return []

# ============= دوال طلبات استرداد النقاط =============

async def create_redemption_request(pool, user_id, username, points, amount_usd, amount_syp):
    """إنشاء طلب استرداد نقاط"""
    try:
        async with pool.acquire() as conn:
            current_points = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                user_id
            )
            
            if current_points < points:
                return None, "نقاط غير كافية"
            
            request_id = await conn.fetchval('''
                INSERT INTO redemption_requests 
                (user_id, username, points, amount_usd, amount_syp, status)
                VALUES ($1, $2, $3, $4, $5, 'pending')
                RETURNING id
            ''', user_id, username, points, amount_usd, amount_syp)
            
            return request_id, None
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء طلب استرداد نقاط: {e}")
        return None, str(e)

async def approve_redemption(pool, request_id, admin_id):
    """الموافقة على طلب استرداد نقاط"""
    try:
        async with pool.acquire() as conn:
            req = await conn.fetchrow(
                "SELECT * FROM redemption_requests WHERE id = $1 AND status = 'pending'",
                request_id
            )
            
            if not req:
                return False, "الطلب غير موجود"
            
            current_points = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                req['user_id']
            )
            
            if current_points < req['points']:
                return False, "رصيد النقاط غير كافي"
            
            # تحديث حالة الطلب
            await conn.execute('''
                UPDATE redemption_requests 
                SET status = 'approved', updated_at = CURRENT_TIMESTAMP, admin_notes = $1 
                WHERE id = $2
            ''', f"تمت الموافقة بواسطة {admin_id}", request_id)
            
            # خصم النقاط وإضافة الرصيد
            await conn.execute('''
                UPDATE users 
                SET total_points = total_points - $1,
                    total_points_redeemed = total_points_redeemed + $1,
                    balance = balance + $2
                WHERE user_id = $3
            ''', req['points'], req['amount_syp'], req['user_id'])
            
            # تسجيل في سجل النقاط
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description)
                VALUES ($1, $2, $3, $4)
            ''', req['user_id'], -req['points'], 'redemption', f'استرداد نقاط بقيمة {req["amount_syp"]:,.0f} ل.س')
            
            return True, None
    except Exception as e:
        logger.error(f"❌ خطأ في الموافقة على طلب استرداد {request_id}: {e}")
        return False, str(e)

async def reject_redemption(pool, request_id, admin_id, reason=""):
    """رفض طلب استرداد نقاط"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE redemption_requests 
                SET status = 'rejected', updated_at = CURRENT_TIMESTAMP, admin_notes = $1 
                WHERE id = $2
            ''', f"تم الرفض بواسطة {admin_id}. السبب: {reason}", request_id)
            return True, None
    except Exception as e:
        logger.error(f"❌ خطأ في رفض طلب استرداد {request_id}: {e}")
        return False, str(e)

# ============= دوال إعدادات البوت =============

async def get_exchange_rate(pool):
    """جلب سعر الصرف"""
    try:
        async with pool.acquire() as conn:
            rate = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'usd_to_syp'"
            )
            return float(rate) if rate else 118
    except Exception as e:
        logger.error(f"❌ خطأ في جلب سعر الصرف: {e}")
        return 118

async def set_exchange_rate(pool, rate):
    """تحديث سعر الصرف"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO bot_settings (key, value, description) 
                VALUES ('usd_to_syp', $1, 'سعر صرف الدولار مقابل الليرة')
                ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = CURRENT_TIMESTAMP
            ''', str(rate))
            return True
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث سعر الصرف: {e}")
        return False

async def get_redemption_rate(pool):
    """جلب معدل استرداد النقاط"""
    try:
        async with pool.acquire() as conn:
            rate = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'redemption_rate'"
            )
            return int(rate) if rate else 100
    except Exception as e:
        logger.error(f"❌ خطأ في جلب معدل الاسترداد: {e}")
        return 100

async def get_points_per_referral(pool):
    """جلب نقاط الإحالة"""
    try:
        async with pool.acquire() as conn:
            points = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_referral'"
            )
            return int(points) if points else 1
    except Exception as e:
        logger.error(f"❌ خطأ في جلب نقاط الإحالة: {e}")
        return 1

async def get_points_per_order(pool):
    """جلب نقاط الطلب"""
    try:
        async with pool.acquire() as conn:
            points = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_order'"
            )
            return int(points) if points else 1
    except Exception as e:
        logger.error(f"❌ خطأ في جلب نقاط الطلب: {e}")
        return 1

async def get_bot_status(pool):
    """جلب حالة البوت"""
    try:
        async with pool.acquire() as conn:
            status = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'bot_status'"
            )
            return status == 'running'
    except Exception as e:
        logger.error(f"❌ خطأ في جلب حالة البوت: {e}")
        return True

async def set_bot_status(pool, status):
    """تغيير حالة البوت"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE bot_settings SET value = $1, updated_at = CURRENT_TIMESTAMP 
                WHERE key = 'bot_status'
            ''', 'running' if status else 'stopped')
            return True
    except Exception as e:
        logger.error(f"❌ خطأ في تغيير حالة البوت: {e}")
        return False

async def get_maintenance_message(pool):
    """جلب رسالة الصيانة"""
    try:
        async with pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'maintenance_message'"
            ) or "البوت قيد الصيانة حالياً"
    except Exception as e:
        logger.error(f"❌ خطأ في جلب رسالة الصيانة: {e}")
        return "البوت قيد الصيانة حالياً"

async def get_syriatel_numbers(pool):
    """جلب أرقام سيرياتل"""
    try:
        async with pool.acquire() as conn:
            numbers = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'syriatel_nums'"
            )
            return numbers.split(',') if numbers else ["74091109", "63826779"]
    except Exception as e:
        logger.error(f"❌ خطأ في جلب أرقام سيرياتل: {e}")
        return ["74091109", "63826779"]

async def set_syriatel_numbers(pool, numbers):
    """حفظ أرقام سيرياتل"""
    try:
        async with pool.acquire() as conn:
            numbers_str = ','.join(numbers)
            await conn.execute('''
                INSERT INTO bot_settings (key, value, description) 
                VALUES ('syriatel_nums', $1, 'أرقام سيرياتل كاش')
                ON CONFLICT (key) DO UPDATE SET value = $1
            ''', numbers_str)
            return True
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ أرقام سيرياتل: {e}")
        return False

# ============= دوال المستخدمين =============

async def get_user_by_id(pool, user_id):
    """جلب مستخدم محدد"""
    try:
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1",
                user_id
            )
    except Exception as e:
        logger.error(f"❌ خطأ في جلب المستخدم {user_id}: {e}")
        return None

async def get_all_users(pool):
    """جلب جميع المستخدمين"""
    try:
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM users ORDER BY user_id")
    except Exception as e:
        logger.error(f"❌ خطأ في جلب المستخدمين: {e}")
        return []

async def update_user_balance(pool, user_id, amount):
    """تحديث رصيد المستخدم"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET balance = balance + $1, last_activity = CURRENT_TIMESTAMP 
                WHERE user_id = $2
            ''', amount, user_id)
            return True
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث رصيد المستخدم {user_id}: {e}")
        return False

# ============= دوال VIP =============

async def get_user_vip(pool, user_id):
    """جلب مستوى VIP للمستخدم"""
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow('''
                SELECT vip_level, total_spent, discount_percent 
                FROM users WHERE user_id = $1
            ''', user_id)
            return user or {'vip_level': 0, 'total_spent': 0, 'discount_percent': 0}
    except Exception as e:
        logger.error(f"❌ خطأ في جلب مستوى VIP: {e}")
        return {'vip_level': 0, 'total_spent': 0, 'discount_percent': 0}

async def update_user_vip(pool, user_id):
    """تحديث مستوى VIP للمستخدم"""
    try:
        async with pool.acquire() as conn:
            # التحقق من المستوى اليدوي
            user = await conn.fetchrow(
                "SELECT manual_vip FROM users WHERE user_id = $1",
                user_id
            )
            
            if user and user['manual_vip']:
                return None
            
            # حساب إجمالي المشتريات
            total_spent = await conn.fetchval('''
                SELECT COALESCE(SUM(total_amount_syp), 0) 
                FROM orders 
                WHERE user_id = $1 AND status = 'completed'
            ''', user_id) or 0
            
            # تحديد المستوى
            levels = [
                (8000, 4, 5),
                (4000, 3, 3),
                (2000, 2, 2),
                (1000, 1, 1)
            ]
            
            level = 0
            discount = 0
            for spent, lvl, dsc in levels:
                if total_spent >= spent:
                    level = lvl
                    discount = dsc
                    break
            
            await conn.execute('''
                UPDATE users 
                SET vip_level = $1, total_spent = $2, discount_percent = $3
                WHERE user_id = $4
            ''', level, total_spent, discount, user_id)
            
            return {'level': level, 'discount': discount, 'total_spent': total_spent}
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث VIP للمستخدم {user_id}: {e}")
        return None

def get_next_vip_level(total_spent):
    """حساب المستوى التالي"""
    levels = [
        (1000, 1, "VIP 1 🔵 (خصم 1%)"),
        (2000, 2, "VIP 2 🟣 (خصم 2%)"),
        (4000, 3, "VIP 3 🟡 (خصم 3%)"),
        (8000, 4, "VIP 4 🔴 (خصم 5%)")
    ]
    
    for required, level, name in levels:
        if total_spent < required:
            return {
                'next_level': level,
                'next_level_name': name,
                'remaining': required - total_spent,
                'next_discount': level
            }
    return None

# ============= دوال التطبيقات والخيارات =============

async def get_all_applications(pool):
    """جلب جميع التطبيقات"""
    try:
        async with pool.acquire() as conn:
            return await conn.fetch('''
                SELECT a.*, c.display_name as category_name, c.icon as category_icon
                FROM applications a
                LEFT JOIN categories c ON a.category_id = c.id
                WHERE a.is_active = TRUE
                ORDER BY c.sort_order, a.name
            ''')
    except Exception as e:
        logger.error(f"❌ خطأ في جلب التطبيقات: {e}")
        return []

async def get_product_options(pool, product_id):
    """جلب خيارات المنتج"""
    try:
        async with pool.acquire() as conn:
            options = await conn.fetch('''
                SELECT * FROM product_options 
                WHERE product_id = $1 AND is_active = TRUE 
                ORDER BY sort_order, price_usd
            ''', product_id)
            
            return [dict(opt, price_usd=float(opt['price_usd'])) for opt in options]
    except Exception as e:
        logger.error(f"❌ خطأ في جلب خيارات المنتج {product_id}: {e}")
        return []

async def get_product_option(pool, option_id):
    """جلب خيار محدد"""
    try:
        async with pool.acquire() as conn:
            option = await conn.fetchrow(
                "SELECT * FROM product_options WHERE id = $1",
                option_id
            )
            if option:
                return dict(option, price_usd=float(option['price_usd']))
            return None
    except Exception as e:
        logger.error(f"❌ خطأ في جلب الخيار {option_id}: {e}")
        return None

async def add_product_option(pool, product_id, name, quantity, price_usd, description=None, sort_order=0):
    """إضافة خيار جديد"""
    try:
        async with pool.acquire() as conn:
            return await conn.fetchval('''
                INSERT INTO product_options 
                (product_id, name, quantity, price_usd, description, sort_order, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                RETURNING id
            ''', product_id, name, quantity, price_usd, description, sort_order)
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة خيار: {e}")
        return None

async def update_product_option(pool, option_id, updates):
    """تحديث خيار"""
    try:
        async with pool.acquire() as conn:
            allowed = ['name', 'quantity', 'price_usd', 'description', 'is_active']
            set_parts = []
            values = []
            
            for i, (key, value) in enumerate(updates.items(), 1):
                if key in allowed:
                    set_parts.append(f"{key} = ${i}")
                    values.append(value)
            
            if not set_parts:
                return False
            
            values.append(option_id)
            query = f"UPDATE product_options SET {', '.join(set_parts)}, updated_at = CURRENT_TIMESTAMP WHERE id = ${len(values)}"
            await conn.execute(query, *values)
            return True
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث الخيار: {e}")
        return False

# ============= دوال الإحصائيات =============

async def get_user_profile(pool, user_id):
    """جلب الملف الشخصي للمستخدم"""
    try:
        async with pool.acquire() as conn:
            # معلومات المستخدم
            user = await conn.fetchrow('''
                SELECT user_id, username, first_name, last_name, balance, is_banned,
                       created_at AT TIME ZONE 'Asia/Damascus' as created_at,
                       last_activity AT TIME ZONE 'Asia/Damascus' as last_activity,
                       total_deposits, total_orders, total_points,
                       referral_code, referred_by, referral_count, referral_earnings,
                       vip_level, total_spent, discount_percent
                FROM users WHERE user_id = $1
            ''', user_id)
            
            if not user:
                return None
            
            # إحصائيات الإيداعات
            deposits = await conn.fetchrow('''
                SELECT COUNT(*) as total_count,
                       COALESCE(SUM(amount_syp), 0) as total_amount,
                       COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_count,
                       COALESCE(SUM(CASE WHEN status = 'approved' THEN amount_syp END), 0) as approved_amount
                FROM deposit_requests WHERE user_id = $1
            ''', user_id)
            
            # إحصائيات الطلبات
            orders = await conn.fetchrow('''
                SELECT COUNT(*) as total_count,
                       COALESCE(SUM(total_amount_syp), 0) as total_amount,
                       COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_count,
                       COALESCE(SUM(CASE WHEN status = 'completed' THEN total_amount_syp END), 0) as completed_amount,
                       COALESCE(SUM(points_earned), 0) as total_points_earned
                FROM orders WHERE user_id = $1
            ''', user_id)
            
            return {
                'user': dict(user),
                'deposits': dict(deposits) if deposits else {},
                'orders': dict(orders) if orders else {}
            }
    except Exception as e:
        logger.error(f"❌ خطأ في جلب الملف الشخصي: {e}")
        return None

async def get_bot_stats(pool):
    """جلب إحصائيات البوت"""
    try:
        async with pool.acquire() as conn:
            users = await conn.fetchrow('''
                SELECT COUNT(*) as total_users,
                       COALESCE(SUM(balance), 0) as total_balance,
                       COUNT(CASE WHEN is_banned THEN 1 END) as banned_users,
                       COUNT(CASE WHEN DATE(created_at) = CURRENT_DATE THEN 1 END) as new_users_today,
                       COALESCE(SUM(total_points), 0) as total_points
                FROM users
            ''')
            
            deposits = await conn.fetchrow('''
                SELECT COUNT(*) as total_deposits,
                       COALESCE(SUM(amount_syp), 0) as total_deposit_amount,
                       COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_deposits,
                       COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_deposits
                FROM deposit_requests
            ''')
            
            orders = await conn.fetchrow('''
                SELECT COUNT(*) as total_orders,
                       COALESCE(SUM(total_amount_syp), 0) as total_order_amount,
                       COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_orders,
                       COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_orders,
                       COALESCE(SUM(points_earned), 0) as total_points_given
                FROM orders
            ''')
            
            return {
                'users': dict(users) if users else {},
                'deposits': dict(deposits) if deposits else {},
                'orders': dict(orders) if orders else {}
            }
    except Exception as e:
        logger.error(f"❌ خطأ في جلب الإحصائيات: {e}")
        return None
