# database.py
import asyncpg
import logging
import pytz
from datetime import datetime
from config import DB_CONFIG

DAMASCUS_TZ = pytz.timezone('Asia/Damascus')
def format_local_time(dt):
    """تنسيق الوقت حسب توقيت دمشق للعرض"""
    if dt is None:
        return "غير معروف"
    
    if isinstance(dt, str):
        try:
            # محاولة تحويل النص إلى datetime
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    
    # إذا كان الوقت بدون منطقة زمنية، نضيف UTC
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    # نحول إلى توقيت دمشق
    local_dt = dt.astimezone(DAMASCUS_TZ)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")

async def set_database_timezone(pool):
    """ضبط المنطقة الزمنية لقاعدة البيانات لجميع الاتصالات"""
    try:
        async with pool.acquire() as conn:
            # ضبط المنطقة الزمنية للاتصال الحالي
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
            # التحقق من الوقت بعد الضبط
            db_time = await conn.fetchval("SELECT NOW()")
            
            # جلب الوقت الحقيقي من قاعدة البيانات (بدون تحويل)
            db_time_utc = await conn.fetchval("SELECT NOW() AT TIME ZONE 'UTC'")
            
            logging.info(f"🕒 وقت DB بعد الضبط (Asia/Damascus): {db_time}")
            logging.info(f"🕒 وقت DB بصيغة UTC: {db_time_utc}")
            
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في ضبط توقيت قاعدة البيانات: {e}")
        return False

async def init_db():
    """تهيئة قاعدة البيانات وإنشاء الجداول إذا لم تكن موجودة"""
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        
        # جدول المستخدمين
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                balance FLOAT DEFAULT 0,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_banned BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_deposits FLOAT DEFAULT 0,
                total_orders FLOAT DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by BIGINT,
                referral_count INTEGER DEFAULT 0,
                referral_earnings FLOAT DEFAULT 0,
                total_points_earned INTEGER DEFAULT 0,
                total_points_redeemed INTEGER DEFAULT 0,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                vip_level INTEGER DEFAULT 0,
                total_spent FLOAT DEFAULT 0,
                discount_percent INTEGER DEFAULT 0
            );
        ''')

        # جدول الأقسام
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

        # جدول التطبيقات
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                unit_price_usd FLOAT,
                min_units INTEGER,
                profit_percentage FLOAT DEFAULT 10,
                category_id INTEGER REFERENCES categories(id),
                type VARCHAR(50) DEFAULT 'service',
                api_service_id TEXT,
                api_url TEXT,
                api_token TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # جدول الفئات الفرعية (للألعاب والاشتراكات)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS app_variants (
                id SERIAL PRIMARY KEY,
                app_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                quantity INTEGER,
                duration_days INTEGER,
                price_usd DECIMAL(10, 6) NOT NULL,
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # ===== إضافة الجداول الجديدة هنا =====
        
        # جدول خيارات المنتجات (للألعاب والاشتراكات)
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logging.info("✅ تم التأكد من وجود جدول product_options")

        # جدول أنواع الخدمات (لتمييز رشق عادي / جودة عالية)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS service_types (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) UNIQUE,
                display_name VARCHAR(100),
                description TEXT
            );
        ''')
        logging.info("✅ تم التأكد من وجود جدول service_types")

        # إضافة أنواع الخدمات الأساسية
        await conn.execute('''
            INSERT INTO service_types (name, display_name, description) 
            VALUES 
                ('regular', 'رشق عادي', 'متابعين عاديين'),
                ('high_quality', 'جودة عالية', 'متابعين بجودة عالية'),
                ('telegram_stars', 'نجوم تليجرام', 'شراء نجوم تيليجرام')
            ON CONFLICT (name) DO NOTHING;
        ''')
        logging.info("✅ تم إضافة أنواع الخدمات الأساسية")
        
        # ===== نهاية الجداول الجديدة =====
        # جدول طلبات الشحن
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                group_message_id BIGINT
            );
        ''')

        # جدول طلبات التطبيقات
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
                api_response TEXT,
                admin_notes TEXT,
                group_message_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # جدول سجل النقاط
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

        # جدول طلبات استرداد النقاط
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

        # جدول إعدادات البوت
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # جدول مستويات VIP
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS vip_levels (
                level INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                min_spent FLOAT NOT NULL,
                discount_percent INTEGER NOT NULL,
                icon TEXT DEFAULT '⭐'
            );
        ''')

        # إضافة المستويات الافتراضية
        await conn.execute('''
            INSERT INTO vip_levels (level, name, min_spent, discount_percent, icon) 
                VALUES 
                    (0, 'VIP 0', 0, 0, '⚪'),
                    (1, 'VIP 1', 2000, 1, '🔵'),
                    (2, 'VIP 2', 4000, 2, '🟣'),
                    (3, 'VIP 3', 8000, 4, '🟡')
                ON CONFLICT (level) DO UPDATE SET
                    min_spent = EXCLUDED.min_spent,
                    discount_percent = EXCLUDED.discount_percent,
                    icon = EXCLUDED.icon;
        ''')

        # جدول السجلات
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                action TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # جدول إعدادات التقارير
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS report_settings (
                id SERIAL PRIMARY KEY,
                setting_key TEXT UNIQUE,
                setting_value TEXT,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # إضافة الإعدادات الافتراضية
        await conn.execute('''
            INSERT INTO report_settings (setting_key, setting_value, description) 
            VALUES 
                ('daily_report_enabled', 'true', 'تفعيل التقرير اليومي'),
                ('report_time', '00:00', 'وقت إرسال التقرير'),
                ('report_recipients', 'owner_only', 'مستلمو التقرير (all_admins/owner_only)')
            ON CONFLICT (setting_key) DO NOTHING;
        ''')

        # إضافة قسم تطبيقات الدردشة فقط إذا لم تكن هناك أقسام
        existing_cats = await conn.fetchval("SELECT COUNT(*) FROM categories")
        if existing_cats == 0:
            await conn.execute('''
                INSERT INTO categories (name, display_name, icon, sort_order) 
                VALUES ('chat_apps', '💬 تطبيقات دردشة', '💬', 1)
                ON CONFLICT (name) DO NOTHING;
            ''')
            logging.info("✅ تم إضافة قسم تطبيقات الدردشة")

        # إضافة إعدادات البوت الأساسية
        await conn.execute('''
            INSERT INTO bot_settings (key, value, description) 
            VALUES 
                ('bot_status', 'running', 'حالة البوت (running/stopped)'),
                ('maintenance_message', 'البوت قيد الصيانة حالياً، يرجى المحاولة لاحقاً', 'رسالة الصيانة'),
                ('points_per_order', '1', 'نقاط لكل عملية شراء'),
                ('points_per_referral', '1', 'نقاط لكل عملية من خلال الإحالة'),
                ('redemption_rate', '100', 'عدد النقاط مقابل 1 دولار'),
                ('last_restart', CURRENT_TIMESTAMP::TEXT, 'آخر تشغيل للبوت')
            ON CONFLICT (key) DO NOTHING;
        ''')
       
        # ===== إضافة مفتاح أرقام سيرياتل إلى قاعدة البيانات =====
        await conn.execute('''
            INSERT INTO bot_settings (key, value, description) 
            VALUES ('syriatel_nums', '74091109,63826779', 'أرقام سيرياتل كاش')
            ON CONFLICT (key) DO NOTHING;
        ''')
        
        # إضافة الأعمدة إذا لم تكن موجودة (للتحديثات)
        tables_columns = {
            'applications': [
                ('api_url', 'TEXT'),
                ('api_token', 'TEXT'),
                ('profit_percentage', 'FLOAT DEFAULT 10'),
                ('category_id', 'INTEGER REFERENCES categories(id)'),
                ('type', "VARCHAR(50) DEFAULT 'service'"),
                ('is_active', 'BOOLEAN DEFAULT TRUE')
            ],
            'deposit_requests': [
                ('group_message_id', 'BIGINT'),
                ('photo_file_id', 'TEXT'),
                ('admin_notes', 'TEXT')
            ],
            'orders': [
                ('group_message_id', 'BIGINT'),
                ('api_response', 'TEXT'),
                ('admin_notes', 'TEXT'),
                ('variant_id', 'INTEGER'),
                ('variant_name', 'TEXT'),
                ('duration_days', 'INTEGER'),
                ('points_earned', 'INTEGER DEFAULT 0')
            ],
            'users': [
                ('total_deposits', 'FLOAT DEFAULT 0'),
                ('total_orders', 'FLOAT DEFAULT 0'),
                ('total_points', 'INTEGER DEFAULT 0'),
                ('referral_code', 'TEXT'),
                ('referred_by', 'BIGINT'),
                ('referral_count', 'INTEGER DEFAULT 0'),
                ('referral_earnings', 'FLOAT DEFAULT 0'),
                ('first_name', 'TEXT'),
                ('last_name', 'TEXT'),
                ('total_points_earned', 'INTEGER DEFAULT 0'),
                ('total_points_redeemed', 'INTEGER DEFAULT 0'),
                ('last_activity', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            ]
        }

        for table, columns in tables_columns.items():
            for column_name, column_type in columns:
                try:
                    check_query = f'''
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name='{table}' AND column_name='{column_name}'
                    '''
                    exists = await conn.fetchval(check_query)
                    
                    if not exists:
                        await conn.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_name} {column_type};')
                        logging.info(f"✅ تم إضافة العمود {column_name} إلى جدول {table}")
                except Exception as e:
                    logging.warning(f"⚠️ لم يتم إضافة العمود {column_name} لـ {table}: {e}")

        # إنشاء كود إحالة فريد لكل مستخدم موجود
        try:
            users = await conn.fetch("SELECT user_id FROM users WHERE referral_code IS NULL")
            for user in users:
                import random
                import string
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                await conn.execute(
                    "UPDATE users SET referral_code = $1 WHERE user_id = $2",
                    code, user['user_id']
                )
        except Exception as e:
            logging.warning(f"⚠️ لم يتم إنشاء أكواد الإحالة للمستخدمين الحاليين: {e}")

        # ========== إضافة أعمدة VIP إذا لم تكن موجودة (للتحديثات) ==========
        try:
            await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_level INTEGER DEFAULT 0')
            logging.info("✅ تم التأكد من وجود عمود vip_level")
        except Exception as e:
            logging.warning(f"⚠️ خطأ في إضافة عمود vip_level: {e}")

        try:
            await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS total_spent FLOAT DEFAULT 0')
            logging.info("✅ تم التأكد من وجود عمود total_spent")
        except Exception as e:
            logging.warning(f"⚠️ خطأ في إضافة عمود total_spent: {e}")

        try:
            await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS discount_percent INTEGER DEFAULT 0')
            logging.info("✅ تم التأكد من وجود عمود discount_percent")
        except Exception as e:
            logging.warning(f"⚠️ خطأ في إضافة عمود discount_percent: {e}")
            
        # ===== إضافة عمود manual_vip =====
        try:
            await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS manual_vip BOOLEAN DEFAULT FALSE')
            logging.info("✅ تم إضافة عمود manual_vip")
        except Exception as e:
            logging.warning(f"⚠️ خطأ في إضافة عمود manual_vip: {e}")
            
        # ===== إضافة عمود description إلى جدول applications =====
        try:
            await conn.execute('ALTER TABLE applications ADD COLUMN IF NOT EXISTS description TEXT')
            logging.info("✅ تم إضافة عمود description إلى جدول applications")
        except Exception as e:
            logging.warning(f"⚠️ خطأ في إضافة عمود description: {e}")
            
        # ========== إصلاح الأعمدة المفقودة في الجداول الجديدة ==========
        try:
            # إضافة عمود display_name إلى app_variants
            await conn.execute('ALTER TABLE app_variants ADD COLUMN IF NOT EXISTS display_name TEXT')
            logging.info("✅ تم إضافة عمود display_name إلى app_variants")
        except Exception as e:
            logging.warning(f"⚠️ خطأ في إضافة display_name إلى app_variants: {e}")
            
        try:
            # إضافة عمود updated_at إلى product_options
            await conn.execute('ALTER TABLE product_options ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            logging.info("✅ تم إضافة عمود updated_at إلى product_options")
        except Exception as e:
            logging.warning(f"⚠️ خطأ في إضافة updated_at إلى product_options: {e}")
            
        try:
            # إضافة عمود created_at إلى product_options إذا لم يكن موجوداً
            await conn.execute('ALTER TABLE product_options ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            logging.info("✅ تم التأكد من وجود created_at في product_options")
        except Exception as e:
            logging.warning(f"⚠️ خطأ في إضافة created_at إلى product_options: {e}")

        await conn.close()
        logging.info("✅ تم تهيئة قاعدة البيانات والجداول بنجاح مع جميع الإصلاحات.")
    except Exception as e:
        logging.error(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}")

async def get_pool():
    """إنشاء مجمع اتصالات (Pool) مع ضبط المنطقة الزمنية"""
    try:
        # تعريف دالة التهيئة لكل اتصال جديد
        async def init_connection(conn):
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
        
        # التحقق من وجود dsn في الإعدادات
        if "dsn" in DB_CONFIG:
            pool = await asyncpg.create_pool(
                dsn=DB_CONFIG["dsn"],
                command_timeout=60,
                server_settings={
                    'timezone': 'Asia/Damascus'
                },
                init=init_connection,
                statement_cache_size=0,
                max_cached_statement_lifetime=0
            )
            logging.info("✅ تم إنشاء مجمع الاتصالات مع تعطيل prepared statements")
        else:
            pool = await asyncpg.create_pool(
                **DB_CONFIG,
                command_timeout=60,
                server_settings={
                    'timezone': 'Asia/Damascus'
                },
                init=init_connection,
                statement_cache_size=0,
                max_cached_statement_lifetime=0
            )
            logging.info("✅ تم إنشاء مجمع الاتصالات مع تعطيل prepared statements")
        return pool
    except Exception as e:
        logging.error(f"❌ فشل إنشاء مجمع الاتصالات: {e}")
        return None

async def test_connection():
    """اختبار الاتصال بقاعدة البيانات"""
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        await conn.close()
        logging.info("✅ تم الاتصال بقاعدة البيانات بنجاح")
        return True
    except Exception as e:
        logging.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
        return False

# ============= دوال ضبط المنطقة الزمنية =============

async def set_database_timezone(pool):
    """ضبط المنطقة الزمنية لقاعدة البيانات لجميع الاتصالات"""
    try:
        async with pool.acquire() as conn:
            # ضبط المنطقة الزمنية للاتصال الحالي
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
            # التحقق من الوقت بعد الضبط
            db_time = await conn.fetchval("SELECT NOW()")
            
            # جلب الوقت الحقيقي من قاعدة البيانات (بدون تحويل)
            db_time_utc = await conn.fetchval("SELECT NOW() AT TIME ZONE 'UTC'")
            
            logging.info(f"🕒 وقت DB بعد الضبط (Asia/Damascus): {db_time}")
            logging.info(f"🕒 وقت DB بصيغة UTC: {db_time_utc}")
            
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في ضبط توقيت قاعدة البيانات: {e}")
        return False

def format_local_time(dt):
    """تنسيق الوقت حسب توقيت دمشق للعرض"""
    if dt is None:
        return "غير معروف"
    
    if isinstance(dt, str):
        try:
            # محاولة تحويل النص إلى datetime
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    
    # إذا كان الوقت بدون منطقة زمنية، نضيف UTC
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    # نحول إلى توقيت دمشق
    local_dt = dt.astimezone(DAMASCUS_TZ)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")

async def update_old_records_timezone(pool):
    """تحديث السجلات القديمة إلى التوقيت الصحيح (مرة واحدة)"""
    try:
        async with pool.acquire() as conn:
            # التحقق من وجود سجلات قديمة
            tables = ['users', 'deposit_requests', 'orders', 'points_history', 'redemption_requests']
            
            for table in tables:
                try:
                    # تحديث created_at إذا كان موجوداً
                    await conn.execute(f"""
                        UPDATE {table} 
                        SET created_at = created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Damascus'
                        WHERE created_at IS NOT NULL
                          AND EXTRACT(HOUR FROM created_at) < 3
                    """)
                    
                    # تحديث updated_at إذا كان موجوداً
                    if table in ['deposit_requests', 'orders', 'redemption_requests']:
                        await conn.execute(f"""
                            UPDATE {table} 
                            SET updated_at = updated_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Damascus'
                            WHERE updated_at IS NOT NULL
                              AND EXTRACT(HOUR FROM updated_at) < 3
                        """)
                    
                    logging.info(f"✅ تم تحديث توقيت الجدول {table}")
                except Exception as e:
                    logging.warning(f"⚠️ خطأ في تحديث الجدول {table}: {e}")
            
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث السجلات القديمة: {e}")
        return False

# ============= دوال حالة البوت =============

async def get_bot_status(pool):
    """جلب حالة البوت"""
    try:
        async with pool.acquire() as conn:
            status = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'bot_status'"
            )
            return status == 'running'
    except Exception as e:
        logging.error(f"❌ خطأ في جلب حالة البوت: {e}")
        return True

async def set_bot_status(pool, status):
    """تغيير حالة البوت"""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE bot_settings SET value = $1, updated_at = CURRENT_TIMESTAMP WHERE key = 'bot_status'",
                'running' if status else 'stopped'
            )
            logging.info(f"✅ تم تغيير حالة البوت إلى: {'running' if status else 'stopped'}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تغيير حالة البوت: {e}")
        return False

async def get_maintenance_message(pool):
    """جلب رسالة الصيانة"""
    try:
        async with pool.acquire() as conn:
            message = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'maintenance_message'"
            )
            return message or "البوت قيد الصيانة حالياً"
    except Exception as e:
        logging.error(f"❌ خطأ في جلب رسالة الصيانة: {e}")
        return "البوت قيد الصيانة حالياً"

# ============= دوال النقاط والإحالة =============

async def generate_referral_code(pool, user_id):
    """إنشاء كود إحالة فريد للمستخدم"""
    import random
    import string
    
    async with pool.acquire() as conn:
        # إنشاء كود عشوائي
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # التأكد من عدم تكرار الكود
        existing = await conn.fetchval(
            "SELECT user_id FROM users WHERE referral_code = $1",
            code
        )
        while existing:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            existing = await conn.fetchval(
                "SELECT user_id FROM users WHERE referral_code = $1",
                code
            )
        
        # تحديث كود الإحالة للمستخدم
        await conn.execute(
            "UPDATE users SET referral_code = $1 WHERE user_id = $2",
            code, user_id
        )
        return code

# في database.py - أضف في قسم الإحالة

async def check_duplicate_referral(pool, referrer_id, referred_id):
    """التحقق من عدم تكرار الإحالة"""
    try:
        async with pool.acquire() as conn:
            # التحقق من السجل
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM points_history 
                WHERE user_id = $1 
                  AND action = 'referral' 
                  AND description LIKE $2
            ''', referrer_id, f'%{referred_id}%')
            
            if count > 0:
                return True, "تمت إحالة هذا المستخدم مسبقاً"
            
            # التحقق من referred_by
            referred_by = await conn.fetchval(
                "SELECT referred_by FROM users WHERE user_id = $1",
                referred_id
            )
            
            if referred_by:
                return True, f"المستخدم لديه إحالة سابقة ({referred_by})"
            
            return False, None
    except Exception as e:
        logging.error(f"❌ خطأ في التحقق من تكرار الإحالة: {e}")
        return True, str(e)

async def get_referral_stats(pool, user_id):
    """إحصائيات مفصلة عن الإحالات"""
    try:
        async with pool.acquire() as conn:
            # عدد المحالين الفريدين
            unique_referrals = await conn.fetchval('''
                SELECT COUNT(DISTINCT description) 
                FROM points_history 
                WHERE user_id = $1 AND action = 'referral'
            ''', user_id) or 0
            
            # آخر 5 إحالات
            recent = await conn.fetch('''
                SELECT description, created_at 
                FROM points_history 
                WHERE user_id = $1 AND action = 'referral'
                ORDER BY created_at DESC
                LIMIT 5
            ''', user_id)
            
            # مجموع النقاط من الإحالات
            total_points = await conn.fetchval('''
                SELECT COALESCE(SUM(points), 0)
                FROM points_history 
                WHERE user_id = $1 AND action = 'referral'
            ''', user_id) or 0
            
            return {
                'unique_referrals': unique_referrals,
                'total_points': total_points,
                'recent': recent
            }
    except Exception as e:
        logging.error(f"❌ خطأ في جلب إحصائيات الإحالة: {e}")
        return None
# في database.py - كشف النشاط المشبوه

async def detect_suspicious_referrals(pool, user_id, threshold=5):
    """كشف محاولات الإحالة المشبوهة (نفس المستخدم عدة مرات)"""
    try:
        async with pool.acquire() as conn:
            # البحث عن أنماط مشبوهة
            suspicious = await conn.fetch('''
                SELECT 
                    description,
                    COUNT(*) as attempts,
                    MIN(created_at) as first_attempt,
                    MAX(created_at) as last_attempt
                FROM points_history 
                WHERE user_id = $1 
                  AND action = 'referral'
                GROUP BY description
                HAVING COUNT(*) > $2
                ORDER BY attempts DESC
            ''', user_id, threshold)
            
            if suspicious:
                logging.warning(f"⚠️ نشاط إحالة مشبوه للمستخدم {user_id}: {suspicious}")
                
            return suspicious
    except Exception as e:
        logging.error(f"❌ خطأ في كشف النشاط المشبوه: {e}")
        return []

async def add_points(pool, user_id, points, action, description):
    """إضافة نقاط للمستخدم وتسجيلها في السجل"""
    try:
        async with pool.acquire() as conn:
            # إضافة النقاط للمستخدم
            await conn.execute(
                "UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2",
                points, user_id
            )
            
            # تسجيل في سجل النقاط
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description)
                VALUES ($1, $2, $3, $4)
            ''', user_id, points, action, description)
            
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في إضافة نقاط للمستخدم {user_id}: {e}")
        return False

async def deduct_points(pool, user_id, points, action, description):
    """خصم نقاط من المستخدم وتسجيلها في السجل"""
    try:
        async with pool.acquire() as conn:
            # التحقق من وجود نقاط كافية
            current = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                user_id
            )
            
            if current < points:
                return False, "نقاط غير كافية"
            
            # خصم النقاط
            await conn.execute(
                "UPDATE users SET total_points = total_points - $1, total_points_redeemed = total_points_redeemed + $1 WHERE user_id = $2",
                points, user_id
            )
            
            # تسجيل في سجل النقاط (بإشارة سالبة)
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description)
                VALUES ($1, $2, $3, $4)
            ''', user_id, -points, action, description)
            
            return True, None
    except Exception as e:
        logging.error(f"❌ خطأ في خصم نقاط من المستخدم {user_id}: {e}")
        return False, str(e)
async def add_points_history(db_pool, user_id, points, action, description):
    """إضافة سجل نقاط جديد مع توقيت دمشق"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Damascus')
            ''', user_id, points, action, description)
            
            # تسجيل في اللوق للتوثيق
            logging.info(f"✅ تم إضافة سجل نقاط للمستخدم {user_id}: {points} نقطة - {action}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في إضافة سجل نقاط للمستخدم {user_id}: {e}")
        return False

# في database.py - تحديث دالة process_referral

async def process_referral(pool, referred_user_id, referrer_code):
    """معالجة الإحالة عند تسجيل مستخدم جديد - مع منع التكرار"""
    try:
        async with pool.acquire() as conn:
            # البحث عن المستخدم الذي قام بالإحالة
            referrer = await conn.fetchrow(
                "SELECT user_id FROM users WHERE referral_code = $1",
                referrer_code
            )
            
            if not referrer or referrer['user_id'] == referred_user_id:
                return None, "كود إحالة غير صالح"
            
            # التحقق من عدم وجود إحالة سابقة
            existing = await conn.fetchval(
                "SELECT referred_by FROM users WHERE user_id = $1",
                referred_user_id
            )
            
            if existing:
                return None, f"المستخدم لديه إحالة سابقة ({existing})"
            
            # التحقق من عدم تكرار الإحالة في السجل
            already_referred = await conn.fetchval('''
                SELECT COUNT(*) FROM points_history 
                WHERE user_id = $1 
                  AND action = 'referral' 
                  AND description LIKE $2
            ''', referrer['user_id'], f'%{referred_user_id}%')
            
            if already_referred > 0:
                return None, "تمت إحالة هذا المستخدم مسبقاً"
            
            # ====== تطبيق الإحالة ======
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
            }, None
            
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة الإحالة: {e}")
        return None, str(e)

async def get_user_points(pool, user_id):
    """جلب عدد نقاط المستخدم"""
    try:
        async with pool.acquire() as conn:
            points = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                user_id
            )
            return points or 0
    except Exception as e:
        logging.error(f"❌ خطأ في جلب نقاط المستخدم {user_id}: {e}")
        return 0

async def get_points_history(db_pool, user_id, limit=20):
    """جلب سجل نقاط المستخدم مع توقيت دمشق"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
            rows = await conn.fetch('''
                SELECT points, action, description, 
                       to_char(created_at AT TIME ZONE 'Asia/Damascus', 'YYYY-MM-DD HH24:MI:SS') as date,
                       created_at AT TIME ZONE 'Asia/Damascus' as created_at
                FROM points_history
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            ''', user_id, limit)
            
            history = []
            for row in rows:
                history.append({
                    'points': row['points'],
                    'action': row['action'],
                    'description': row['description'],
                    'date': row['date'],
                    'created_at': row['created_at']
                })
            return history
    except Exception as e:
        logging.error(f"❌ خطأ في جلب سجل النقاط للمستخدم {user_id}: {e}")
        return []

async def create_redemption_request(pool, user_id, username, points, amount_usd, amount_syp):
    """إنشاء طلب استرداد نقاط"""
    try:
        async with pool.acquire() as conn:
            # التحقق من أن المستخدم لديه نقاط كافية
            current_points = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                user_id
            )
            
            if current_points < points:
                return None, "نقاط غير كافية"
            
            # إنشاء الطلب
            request_id = await conn.fetchval('''
                INSERT INTO redemption_requests 
                (user_id, username, points, amount_usd, amount_syp, status)
                VALUES ($1, $2, $3, $4, $5, 'pending')
                RETURNING id
            ''', user_id, username, points, amount_usd, amount_syp)
            
            return request_id, None
    except Exception as e:
        logging.error(f"❌ خطأ في إنشاء طلب استرداد نقاط: {e}")
        return None, str(e)

async def approve_redemption(pool, request_id, admin_id):
    """الموافقة على طلب استرداد نقاط"""
    try:
        async with pool.acquire() as conn:
            # جلب معلومات الطلب
            req = await conn.fetchrow(
                "SELECT * FROM redemption_requests WHERE id = $1 AND status = 'pending'",
                request_id
            )
            
            if not req:
                return False, "الطلب غير موجود أو تمت معالجته مسبقاً"
            
            # التحقق من أن المستخدم لديه نقاط كافية (قد يكون تغير منذ تقديم الطلب)
            current_points = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                req['user_id']
            )
            
            if current_points < req['points']:
                return False, "رصيد النقاط غير كافي (تغير منذ تقديم الطلب)"
            
            # تحديث حالة الطلب
            await conn.execute(
                "UPDATE redemption_requests SET status = 'approved', updated_at = CURRENT_TIMESTAMP, admin_notes = $1 WHERE id = $2",
                f"تمت الموافقة بواسطة {admin_id}", request_id
            )
            
            # خصم النقاط من المستخدم
            await conn.execute(
                "UPDATE users SET total_points = total_points - $1, total_points_redeemed = total_points_redeemed + $1 WHERE user_id = $2",
                req['points'], req['user_id']
            )
            
            # تسجيل في سجل النقاط (بإشارة سالبة)
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ''', req['user_id'], -req['points'], 'redemption', f'استرداد نقاط بقيمة {req["amount_syp"]:,.0f} ل.س')
            
            # إضافة الرصيد للمستخدم
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                req['amount_syp'], req['user_id']
            )
            
            return True, None
    except Exception as e:
        logging.error(f"❌ خطأ في الموافقة على طلب استرداد {request_id}: {e}")
        return False, str(e)

async def reject_redemption(pool, request_id, admin_id, reason=""):
    """رفض طلب استرداد نقاط"""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE redemption_requests SET status = 'rejected', updated_at = CURRENT_TIMESTAMP, admin_notes = $1 WHERE id = $2",
                f"تم الرفض بواسطة {admin_id}. السبب: {reason}", request_id
            )
            return True, None
    except Exception as e:
        logging.error(f"❌ خطأ في رفض طلب استرداد {request_id}: {e}")
        return False, str(e)

async def calculate_points_value(pool, points):
    """حساب قيمة النقاط بالليرة السورية حسب سعر الصرف الحالي"""
    try:
        async with pool.acquire() as conn:
            # جلب سعر الصرف الحالي
            exchange_rate = await get_exchange_rate(pool)
            
            # جلب معدل الاسترداد (كم نقطة مقابل 1 دولار)
            redemption_rate = await get_redemption_rate(pool)
            
            # حساب قيمة النقاط
            # مثال: 100 نقطة = 1 دولار
            usd_value = (points / redemption_rate) 
            syp_value = usd_value * exchange_rate
            
            return {
                'points': points,
                'redemption_rate': redemption_rate,
                'exchange_rate': exchange_rate,
                'usd_value': usd_value,
                'syp_value': syp_value
            }
    except Exception as e:
        logging.error(f"❌ خطأ في حساب قيمة النقاط: {e}")
        return None

# ============= دوال VIP =============

async def get_vip_levels(pool):
    """جلب جميع مستويات VIP"""
    try:
        async with pool.acquire() as conn:
            levels = await conn.fetch('''
                SELECT * FROM vip_levels ORDER BY level
            ''')
            return levels
    except Exception as e:
        logging.error(f"❌ خطأ في جلب مستويات VIP: {e}")
        return []

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
        logging.error(f"❌ خطأ في جلب مستوى VIP للمستخدم {user_id}: {e}")
        return {'vip_level': 0, 'total_spent': 0, 'discount_percent': 0}

async def update_user_vip(pool, user_id):
    """تحديث مستوى VIP للمستخدم - حسب طلبك"""
    try:
        async with pool.acquire() as conn:
            # التحقق أولاً إذا كان المستخدم يدوياً
            user = await conn.fetchrow(
                "SELECT manual_vip, vip_level, discount_percent FROM users WHERE user_id = $1",
                user_id
            )
            
            # إذا كان المستخدم يدوياً، لا تغير مستواه
            if user and user['manual_vip']:
                logging.info(f"👑 المستخدم {user_id} لديه مستوى يدوي VIP {user['vip_level']}")
                return {
                    'level': user['vip_level'],
                    'discount': user['discount_percent'],
                    'total_spent': 0,
                    'next_level': None,
                    'manual': True
                }
            
            # حساب إجمالي مشتريات المستخدم
            total_spent = await conn.fetchval('''
                SELECT COALESCE(SUM(total_amount_syp), 0) 
                FROM orders 
                WHERE user_id = $1 AND status = 'completed'
            ''', user_id) or 0
            
            # ===== نظام VIP حسب طلبك =====
            level = 0
            discount = 0
            
            # المستويات بالضبط كما طلبت
            vip_levels = [
                (2000, 1, 1),   # VIP 1: 2000 ل.س - خصم 1%
                (4000, 2, 2),   # VIP 2: 4000 ل.س - خصم 2%
                (8000, 3, 4),   # VIP 3: 8000 ل.س - خصم 4%
            ]
            
            # ترتيب تنازلي للبحث
            for spent, lvl, disc in reversed(vip_levels):
                if total_spent >= spent:
                    level = lvl
                    discount = disc
                    break
            
            # تحديث المستخدم
            await conn.execute('''
                UPDATE users 
                SET vip_level = $1, 
                    total_spent = $2, 
                    discount_percent = $3,
                    manual_vip = FALSE
                WHERE user_id = $4 AND (manual_vip IS NULL OR manual_vip = FALSE)
            ''', level, total_spent, discount, user_id)
            
            logging.info(f"✅ تم تحديث VIP للمستخدم {user_id} إلى المستوى {level} (خصم {discount}%) - إنفاق: {total_spent:,.0f} ل.س")
            
            return {
                'level': level,
                'discount': discount,
                'total_spent': total_spent,
                'next_level': get_next_vip_level_custom(total_spent),
                'manual': False
            }
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث VIP للمستخدم {user_id}: {e}")
        return None

def get_next_vip_level_custom(total_spent):
    """حساب المستوى التالي حسب النظام المطلوب"""
    vip_levels = [
        (2000, 1, "VIP 1 🔵 (خصم 1%)", 1),
        (4000, 2, "VIP 2 🟣 (خصم 2%)", 2),
        (8000, 3, "VIP 3 🟡 (خصم 4%)", 4),
    ]
    
    for required, level, name, discount in vip_levels:
        if total_spent < required:
            remaining = required - total_spent
            return {
                'next_level': level,
                'next_level_name': name,
                'remaining': remaining,
                'next_discount': discount
            }
    
    # وصل لأعلى مستوى
    return {
        'next_level': 3,
        'next_level_name': "VIP 3 🟡 (الأقصى)",
        'remaining': 0,
        'next_discount': 4
    }

async def get_top_users_by_deposits(pool, limit=10):
    """أكثر المستخدمين إيداعاً"""
    try:
        async with pool.acquire() as conn:
            users = await conn.fetch('''
                SELECT user_id, username, total_deposits, vip_level 
                FROM users 
                ORDER BY total_deposits DESC 
                LIMIT $1
            ''', limit)
            return users
    except Exception as e:
        logging.error(f"❌ خطأ في جلب أكثر المستخدمين إيداعاً: {e}")
        return []

async def get_top_users_by_orders(pool, limit=10):
    """أكثر المستخدمين طلبات"""
    try:
        async with pool.acquire() as conn:
            users = await conn.fetch('''
                SELECT user_id, username, total_orders, vip_level 
                FROM users 
                ORDER BY total_orders DESC 
                LIMIT $1
            ''', limit)
            return users
    except Exception as e:
        logging.error(f"❌ خطأ في جلب أكثر المستخدمين طلبات: {e}")
        return []

async def get_top_users_by_referrals(pool, limit=10):
    """أكثر المستخدمين إحالة"""
    try:
        async with pool.acquire() as conn:
            users = await conn.fetch('''
                SELECT user_id, username, referral_count, referral_earnings, vip_level 
                FROM users 
                ORDER BY referral_count DESC 
                LIMIT $1
            ''', limit)
            return users
    except Exception as e:
        logging.error(f"❌ خطأ في جلب أكثر المستخدمين إحالة: {e}")
        return []

async def get_top_users_by_points(pool, limit=10):
    """أكثر المستخدمين نقاط"""
    try:
        async with pool.acquire() as conn:
            users = await conn.fetch('''
                SELECT user_id, username, total_points, vip_level 
                FROM users 
                ORDER BY total_points DESC 
                LIMIT $1
            ''', limit)
            return users
    except Exception as e:
        logging.error(f"❌ خطأ في جلب أكثر المستخدمين نقاط: {e}")
        return []

# ============= دوال الفئات الفرعية =============
# في database.py - دوال app_variants
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
# ============= دوال خيارات المنتجات (product_options) =============

async def get_product_options(db_pool, product_id):
    """جلب جميع الخيارات النشطة لمنتج معين"""
    try:
        async with db_pool.acquire() as conn:
            options = await conn.fetch(
                "SELECT * FROM product_options WHERE product_id = $1 AND is_active = TRUE ORDER BY sort_order, price_usd",
                product_id
            )
            
            # تحويل Decimal إلى float للسهولة
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
                # تحويل Decimal إلى float
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
        # الحقول المسموح بتعديلها فقط
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

# ============= دوال الإحصائيات =============

async def get_user_profile(pool, user_id):
    """جلب معلومات الملف الشخصي للمستخدم بشكل كامل مع توقيت محلي"""
    try:
        async with pool.acquire() as conn:
            # ضبط التوقيت لكل استعلام
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
            # معلومات المستخدم الأساسية مع تحويل التوقيت
            user = await conn.fetchrow('''
                SELECT 
                    user_id, username, first_name, last_name, balance, is_banned, 
                    created_at AT TIME ZONE 'Asia/Damascus' as created_at,
                    total_deposits, total_orders, total_points,
                    referral_code, referred_by, referral_count, referral_earnings,
                    total_points_earned, total_points_redeemed, 
                    last_activity AT TIME ZONE 'Asia/Damascus' as last_activity,
                    vip_level, total_spent, discount_percent
                FROM users 
                WHERE user_id = $1
            ''', user_id)
            
            if not user:
                return None
            
            # إحصائيات الإيداعات
            deposits = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_count,
                    COALESCE(SUM(amount_syp), 0) as total_amount,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_count,
                    COALESCE(SUM(CASE WHEN status = 'approved' THEN amount_syp END), 0) as approved_amount
                FROM deposit_requests 
                WHERE user_id = $1
            ''', user_id)
            
            # إحصائيات الطلبات
            orders = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_count,
                    COALESCE(SUM(total_amount_syp), 0) as total_amount,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_count,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN total_amount_syp END), 0) as completed_amount,
                    COALESCE(SUM(points_earned), 0) as total_points_earned
                FROM orders 
                WHERE user_id = $1
            ''', user_id)
            
            # معلومات الإحالة
            referrals = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_referrals,
                    COALESCE(SUM(total_deposits), 0) as referrals_deposits,
                    COALESCE(SUM(total_orders), 0) as referrals_orders
                FROM users 
                WHERE referred_by = $1
            ''', user_id)
            
            # آخر 5 طلبات مع توقيت محلي
            recent_orders = await conn.fetch('''
                SELECT 
                    app_name, variant_name, quantity, total_amount_syp, status, 
                    created_at AT TIME ZONE 'Asia/Damascus' as created_at
                FROM orders
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 5
            ''', user_id)
            
            return {
                'user': dict(user),
                'deposits': dict(deposits) if deposits else {},
                'orders': dict(orders) if orders else {},
                'referrals': dict(referrals) if referrals else {},
                'recent_orders': recent_orders
            }
            
    except Exception as e:
        logging.error(f"❌ خطأ في جلب الملف الشخصي للمستخدم {user_id}: {e}")
        return None

async def get_user_full_stats(pool, user_id):
    """جلب إحصائيات كاملة للمستخدم - للتوافق مع الكود القديم"""
    return await get_user_profile(pool, user_id)

async def get_bot_stats(pool):
    """جلب إحصائيات البوت مع توقيت محلي"""
    try:
        async with pool.acquire() as conn:
            # ضبط التوقيت
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
            users_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_users,
                    COALESCE(SUM(balance), 0) as total_balance,
                    COUNT(CASE WHEN is_banned THEN 1 END) as banned_users,
                    COUNT(CASE WHEN DATE(created_at) = CURRENT_DATE THEN 1 END) as new_users_today,
                    COALESCE(SUM(total_points), 0) as total_points,
                    COALESCE(SUM(total_points_earned), 0) as total_points_earned,
                    COALESCE(SUM(total_points_redeemed), 0) as total_points_redeemed,
                    COALESCE(SUM(referral_count), 0) as total_referrals
                FROM users
            ''')
            
            deposits_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_deposits,
                    COALESCE(SUM(amount_syp), 0) as total_deposit_amount,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_deposits,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_deposits
                FROM deposit_requests
            ''')
            
            orders_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_orders,
                    COALESCE(SUM(total_amount_syp), 0) as total_order_amount,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_orders,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_orders,
                    COALESCE(SUM(points_earned), 0) as total_points_given
                FROM orders
            ''')
            
            points_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_redemptions,
                    COALESCE(SUM(points), 0) as total_points_redeemed,
                    COALESCE(SUM(amount_syp), 0) as total_redemption_amount
                FROM redemption_requests
                WHERE status = 'approved'
            ''')
            
            apps_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_apps,
                    COUNT(CASE WHEN type = 'game' THEN 1 END) as games,
                    COUNT(CASE WHEN type = 'subscription' THEN 1 END) as subscriptions,
                    COUNT(CASE WHEN type = 'service' THEN 1 END) as services
                FROM applications
                WHERE is_active = TRUE
            ''')
            
            # جلب إعدادات النقاط
            points_per_order = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_order'"
            ) or 1
            
            points_per_deposit = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_deposit'"
            ) or 1
            
            points_per_referral = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_referral'"
            ) or 1
            
            return {
                'users': dict(users_stats) if users_stats else {},
                'deposits': dict(deposits_stats) if deposits_stats else {},
                'orders': dict(orders_stats) if orders_stats else {},
                'points': dict(points_stats) if points_stats else {},
                'apps': dict(apps_stats) if apps_stats else {},
                'points_per_order': int(points_per_order),
                'points_per_deposit': int(points_per_deposit),
                'points_per_referral': int(points_per_referral)
            }
    except Exception as e:
        logging.error(f"❌ خطأ في جلب الإحصائيات: {e}")
        return None

# ============= دوال أساسية للمستخدمين =============

async def get_all_users(pool):
    """جلب جميع المستخدمين من قاعدة البيانات"""
    try:
        async with pool.acquire() as conn:
            users = await conn.fetch("SELECT * FROM users ORDER BY user_id")
            return users
    except Exception as e:
        logging.error(f"❌ خطأ في جلب المستخدمين: {e}")
        return []

async def get_user_by_id(pool, user_id):
    """جلب مستخدم محدد"""
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            return user
    except Exception as e:
        logging.error(f"❌ خطأ في جلب المستخدم {user_id}: {e}")
        return None

async def update_user_balance(pool, user_id, amount):
    """تحديث رصيد المستخدم"""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET balance = balance + $1, last_activity = CURRENT_TIMESTAMP WHERE user_id = $2",
                amount, user_id
            )
            logging.info(f"✅ تم تحديث رصيد المستخدم {user_id}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث رصيد المستخدم {user_id}: {e}")
        return False

# ============= دوال التطبيقات والأقسام =============

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

async def get_all_categories(pool):
    """جلب جميع الأقسام"""
    try:
        async with pool.acquire() as conn:
            categories = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
            return categories
    except Exception as e:
        logging.error(f"❌ خطأ في جلب الأقسام: {e}")
        return []

# ============= دوال إنشاء الطلبات =============

async def create_deposit_request(pool, user_id, username, method, amount, amount_syp, tx_info, photo_file_id=None):
    """إنشاء طلب شحن جديد"""
    try:
        async with pool.acquire() as conn:
            deposit_id = await conn.fetchval('''
                INSERT INTO deposit_requests 
                (user_id, username, method, amount, amount_syp, tx_info, photo_file_id, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', CURRENT_TIMESTAMP)
                RETURNING id
            ''', user_id, username, method, amount, amount_syp, tx_info, photo_file_id)
            
            logging.info(f"✅ تم إنشاء طلب شحن جديد رقم {deposit_id}")
            return deposit_id
    except Exception as e:
        logging.error(f"❌ خطأ في إنشاء طلب شحن: {e}")
        return None

async def create_order(pool, user_id, username, app_id, app_name, quantity, unit_price_usd, total_amount_syp, target_id, points_earned=0):
    """إنشاء طلب تطبيق عادي"""
    try:
        async with pool.acquire() as conn:
            order_id = await conn.fetchval('''
                INSERT INTO orders 
                (user_id, username, app_id, app_name, quantity, unit_price_usd, 
                 total_amount_syp, target_id, points_earned, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending', CURRENT_TIMESTAMP)
                RETURNING id
            ''', user_id, username, app_id, app_name, quantity, unit_price_usd, 
                total_amount_syp, target_id, points_earned)
            
            logging.info(f"✅ تم إنشاء طلب تطبيق جديد رقم {order_id}")
            return order_id
    except Exception as e:
        logging.error(f"❌ خطأ في إنشاء طلب تطبيق: {e}")
        return None

async def create_order_with_variant(pool, user_id, username, app_id, app_name, variant, total_amount_syp, target_id, points_earned=0):
    """إنشاء طلب مع فئة فرعية (للألعاب والاشتراكات)"""
    try:
        async with pool.acquire() as conn:
            order_id = await conn.fetchval('''
                INSERT INTO orders 
                (user_id, username, app_id, app_name, variant_id, variant_name, 
                 quantity, duration_days, unit_price_usd, total_amount_syp, target_id, 
                 points_earned, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'pending')
                RETURNING id
            ''',
            user_id,
            username,
            app_id,
            app_name,
            variant['id'],
            variant['name'],
            variant.get('quantity', 0),
            variant.get('duration_days', 0),
            variant['price_usd'],
            total_amount_syp,
            target_id,
            points_earned
            )
            
            return order_id
    except Exception as e:
        logging.error(f"❌ خطأ في إنشاء طلب بفئة: {e}")
        return None

# ============= دوال تحديث رسائل المجموعة =============

async def update_order_group_message(pool, order_id, message_id):
    """تحديث معرف رسالة المجموعة للطلب"""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE orders SET group_message_id = $1 WHERE id = $2",
                message_id, order_id
            )
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث رسالة المجموعة للطلب {order_id}: {e}")
        return False

async def update_deposit_group_message(pool, deposit_id, message_id):
    """تحديث معرف رسالة المجموعة لطلب الشحن"""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE deposit_requests SET group_message_id = $1 WHERE id = $2",
                message_id, deposit_id
            )
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث رسالة المجموعة لطلب الشحن {deposit_id}: {e}")
        return False

# ============= دوال إضافية للإصلاح =============

async def fix_referral_columns(pool):
    """إصلاح أعمدة الإحالة في جدول users"""
    try:
        async with pool.acquire() as conn:
            # إضافة الأعمدة المفقودة
            columns_to_add = [
                ('referral_count', 'INTEGER DEFAULT 0'),
                ('referral_earnings', 'INTEGER DEFAULT 0')
            ]
            
            for col_name, col_type in columns_to_add:
                try:
                    await conn.execute(f'''
                        ALTER TABLE users 
                        ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                    ''')
                    print(f"✅ تم إضافة عمود {col_name}")
                except Exception as e:
                    print(f"⚠️ {e}")
            
            return True
    except Exception as e:
        print(f"❌ خطأ في إصلاح أعمدة الإحالة: {e}")
        return False

# ============= دوال النقاط الإضافية =============

async def add_points_for_order(pool, user_id, order_id, points):
    """إضافة نقاط للمستخدم عند إتمام طلب شراء"""
    try:
        async with pool.acquire() as conn:
            # إضافة النقاط للمستخدم
            await conn.execute(
                "UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2",
                points, user_id
            )
            
            # تسجيل في سجل النقاط
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description)
                VALUES ($1, $2, $3, $4)
            ''', user_id, points, 'order', f'نقاط من طلب #{order_id}')
            
            # تحديث نقاط الطلب في جدول orders
            await conn.execute(
                "UPDATE orders SET points_earned = $1 WHERE id = $2",
                points, order_id
            )
            
            logging.info(f"✅ تم إضافة {points} نقاط للمستخدم {user_id} من الطلب {order_id}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في إضافة نقاط الطلب للمستخدم {user_id}: {e}")
        return False

async def add_points_for_deposit(pool, user_id, deposit_id, points):
    """إضافة نقاط للمستخدم عند إتمام عملية شحن"""
    try:
        async with pool.acquire() as conn:
            # إضافة النقاط للمستخدم
            await conn.execute(
                "UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2",
                points, user_id
            )
            
            # تسجيل في سجل النقاط
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description)
                VALUES ($1, $2, $3, $4)
            ''', user_id, points, 'deposit', f'نقاط من شحن #{deposit_id}')
            
            logging.info(f"✅ تم إضافة {points} نقاط للمستخدم {user_id} من الشحن {deposit_id}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في إضافة نقاط الشحن للمستخدم {user_id}: {e}")
        return False

async def get_points_per_order(pool):
    """جلب عدد النقاط لكل عملية شراء من الإعدادات"""
    try:
        async with pool.acquire() as conn:
            points = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_order'"
            )
            return int(points) if points else 1
    except Exception as e:
        logging.error(f"❌ خطأ في جلب نقاط الطلب: {e}")
        return 1

async def get_points_per_deposit(pool):
    """جلب عدد النقاط لكل عملية شحن من الإعدادات"""
    try:
        async with pool.acquire() as conn:
            points = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_deposit'"
            )
            return int(points) if points else 1
    except Exception as e:
        logging.error(f"❌ خطأ في جلب نقاط الشحن: {e}")
        return 1

async def get_points_per_referral(pool):
    """جلب عدد النقاط لكل إحالة من الإعدادات"""
    try:
        async with pool.acquire() as conn:
            points = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_referral'"
            )
            return int(points) if points else 1
    except Exception as e:
        logging.error(f"❌ خطأ في جلب نقاط الإحالة: {e}")
        return 1

async def get_user_points_summary(db_pool, user_id):
    """جلب ملخص نقاط المستخدم"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
            summary = await conn.fetchrow('''
                SELECT 
                    COALESCE(SUM(CASE WHEN points > 0 THEN points ELSE 0 END), 0) as total_earned,
                    COALESCE(SUM(CASE WHEN points < 0 THEN ABS(points) ELSE 0 END), 0) as total_spent,
                    COUNT(*) as total_transactions,
                    MAX(created_at) as last_transaction
                FROM points_history
                WHERE user_id = $1
            ''', user_id)
            
            if summary:
                result = {
                    'total_earned': summary['total_earned'],
                    'total_spent': summary['total_spent'],
                    'total_transactions': summary['total_transactions'],
                    'last_transaction': None
                }
                
                if summary['last_transaction']:
                    # تحويل التوقيت إذا لزم الأمر
                    last_tx = summary['last_transaction']
                    if last_tx.tzinfo is None:
                        last_tx = pytz.UTC.localize(last_tx)
                    result['last_transaction'] = last_tx.astimezone(DAMASCUS_TZ)
                
                return result
            return None
    except Exception as e:
        logging.error(f"❌ خطأ في جلب ملخص النقاط للمستخدم {user_id}: {e}")
        return None

async def get_total_points_redeemed(pool, user_id):
    """جلب إجمالي النقاط المستردة للمستخدم"""
    try:
        async with pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT total_points_redeemed FROM users WHERE user_id = $1",
                user_id
            )
            return total or 0
    except Exception as e:
        logging.error(f"❌ خطأ في جلب إجمالي النقاط المستردة للمستخدم {user_id}: {e}")
        return 0

async def get_user_referral_info(pool, user_id):
    """جلب معلومات الإحالة للمستخدم"""
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            info = await conn.fetchrow('''
                SELECT referral_code, referral_count, referral_earnings, referred_by
                FROM users WHERE user_id = $1
            ''', user_id)
            
            if info:
                # جلب قائمة المحالين
                referrals = await conn.fetch('''
                    SELECT user_id, username, created_at AT TIME ZONE 'Asia/Damascus' as created_at
                    FROM users WHERE referred_by = $1
                    ORDER BY created_at DESC
                    LIMIT 10
                ''', user_id)
                
                return {
                    'code': info['referral_code'],
                    'count': info['referral_count'] or 0,
                    'earnings': info['referral_earnings'] or 0,
                    'referred_by': info['referred_by'],
                    'referrals_list': referrals
                }
            return None
    except Exception as e:
        logging.error(f"❌ خطأ في جلب معلومات الإحالة للمستخدم {user_id}: {e}")
        return None

async def get_redemption_rate(pool):
    """جلب معدل استرداد النقاط (كم نقطة مقابل 1 دولار)"""
    try:
        async with pool.acquire() as conn:
            rate = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'redemption_rate'"
            )
            return int(rate) if rate else 100
    except Exception as e:
        logging.error(f"❌ خطأ في جلب معدل الاسترداد: {e}")
        return 100

# ============= دوال سعر الصرف =============

async def get_exchange_rate(pool):
    """جلب سعر الصرف من قاعدة البيانات"""
    try:
        async with pool.acquire() as conn:
            rate = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'usd_to_syp'"
            )
            return float(rate) if rate else 118
    except Exception as e:
        logging.error(f"❌ خطأ في جلب سعر الصرف: {e}")
        return 118

async def set_exchange_rate(pool, rate):
    """تحديث سعر الصرف في قاعدة البيانات"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO bot_settings (key, value, description) 
                VALUES ('usd_to_syp', $1, 'سعر صرف الدولار مقابل الليرة')
                ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = CURRENT_TIMESTAMP
            ''', str(rate), str(rate))
            logging.info(f"✅ تم تحديث سعر الصرف إلى {rate}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث سعر الصرف: {e}")
        return False

async def get_syriatel_numbers(pool):
    """جلب أرقام سيرياتل من قاعدة البيانات"""
    try:
        async with pool.acquire() as conn:
            numbers_str = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'syriatel_nums'"
            )
            if numbers_str:
                return numbers_str.split(',')
            else:
                default_nums = ["74091109", "63826779"]
                await conn.execute('''
                    INSERT INTO bot_settings (key, value, description) 
                    VALUES ('syriatel_nums', $1, 'أرقام سيرياتل كاش')
                    ON CONFLICT (key) DO UPDATE SET value = $1
                ''', ','.join(default_nums))
                return default_nums
    except Exception as e:
        logging.error(f"❌ خطأ في جلب أرقام سيرياتل: {e}")
        return ["74091109", "63826779"]

async def set_syriatel_numbers(pool, numbers):
    """حفظ أرقام سيرياتل في قاعدة البيانات"""
    try:
        async with pool.acquire() as conn:
            numbers_str = ','.join(numbers)
            await conn.execute('''
                INSERT INTO bot_settings (key, value, description) 
                VALUES ('syriatel_nums', $1, 'أرقام سيرياتل كاش')
                ON CONFLICT (key) DO UPDATE SET value = $1
            ''', numbers_str)
            logging.info(f"✅ تم تحديث أرقام سيرياتل: {numbers_str}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في حفظ أرقام سيرياتل: {e}")
        return False

async def fix_points_history_table(pool):
    """إصلاح جدول النقاط للتأكد من وجود الأعمدة المطلوبة"""
    try:
        async with pool.acquire() as conn:
            # التحقق من وجود الأعمدة وإضافتها إذا لزم الأمر
            await conn.execute('ALTER TABLE points_history ADD COLUMN IF NOT EXISTS action TEXT')
            await conn.execute('ALTER TABLE points_history ADD COLUMN IF NOT EXISTS description TEXT')
            logging.info("✅ تم التأكد من وجود أعمدة points_history")
            
            # إضافة إعدادات النقاط إذا لم تكن موجودة
            settings = [
                ('points_per_referral', '1'),
                ('points_per_order', '1'),
                ('redemption_rate', '100'),
            ]
            
            for key, value in settings:
                await conn.execute('''
                    INSERT INTO bot_settings (key, value, description) 
                    VALUES ($1, $2, $3)
                    ON CONFLICT (key) DO UPDATE SET value = $2
                ''', key, value, f'نقاط {key}')
            
            logging.info("✅ تم التأكد من وجود إعدادات النقاط")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في إصلاح جدول النقاط: {e}")
# ============= دوال إدارة المشرفين =============

async def get_all_admins(pool):
    """جلب جميع المشرفين من قاعدة البيانات"""
    try:
        async with pool.acquire() as conn:
            from config import ADMIN_ID, MODERATORS
            
            # قائمة بجميع آيدي المشرفين
            admin_ids = [ADMIN_ID] + MODERATORS
            
            if not admin_ids:
                return []
            
            # جلب معلومات المشرفين من جدول users
            admins = await conn.fetch('''
                SELECT user_id, username, first_name, last_name, 
                       created_at, last_activity,
                       CASE 
                           WHEN user_id = $1 THEN 'owner'
                           ELSE 'admin'
                       END as role
                FROM users 
                WHERE user_id = ANY($2::bigint[])
                ORDER BY 
                    CASE WHEN user_id = $1 THEN 0 ELSE 1 END,
                    username
            ''', ADMIN_ID, admin_ids)
            
            return admins
    except Exception as e:
        logging.error(f"❌ خطأ في جلب المشرفين: {e}")
        return []

async def add_admin(pool, user_id, added_by):
    """إضافة مشرف جديد"""
    try:
        async with pool.acquire() as conn:
            # التحقق من وجود المستخدم
            user = await conn.fetchrow(
                "SELECT user_id, username FROM users WHERE user_id = $1",
                user_id
            )
            
            if not user:
                return False, "المستخدم غير موجود في قاعدة البيانات"
            
            # تحديث ملف config - هذا يتطلب إعادة تشغيل
            from config import MODERATORS
            if user_id in MODERATORS:
                return False, "المستخدم مشرف بالفعل"
            
            # إضافة للقائمة المؤقتة
            MODERATORS.append(user_id)
            
            # تسجيل العملية في جدول logs
            await conn.execute('''
                INSERT INTO logs (user_id, action, details, created_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
            ''', added_by, 'add_admin', f'تمت إضافة المشرف {user_id} (@{user["username"]})')
            
            return True, "تمت إضافة المشرف بنجاح"
    except Exception as e:
        logging.error(f"❌ خطأ في إضافة مشرف: {e}")
        return False, str(e)

async def remove_admin(pool, user_id, removed_by):
    """إزالة مشرف"""
    try:
        async with pool.acquire() as conn:
            from config import ADMIN_ID, MODERATORS
            
            # منع إزالة المالك
            if user_id == ADMIN_ID:
                return False, "لا يمكن إزالة المالك"
            
            # التحقق من وجوده في القائمة
            if user_id not in MODERATORS:
                return False, "المستخدم ليس مشرفاً"
            
            # جلب معلومات المستخدم للتسجيل
            user = await conn.fetchrow(
                "SELECT username FROM users WHERE user_id = $1",
                user_id
            )
            username = user['username'] if user else 'غير معروف'
            
            # إزالته من القائمة
            MODERATORS.remove(user_id)
            
            # تسجيل العملية
            await conn.execute('''
                INSERT INTO logs (user_id, action, details, created_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
            ''', removed_by, 'remove_admin', f'تمت إزالة المشرف {user_id} (@{username})')
            
            return True, "تمت إزالة المشرف بنجاح"
    except Exception as e:
        logging.error(f"❌ خطأ في إزالة مشرف: {e}")
        return False, str(e)

async def get_admin_info(pool, user_id):
    """جلب معلومات مفصلة عن مشرف"""
    try:
        async with pool.acquire() as conn:
            from config import ADMIN_ID, MODERATORS
            
            # التحقق إذا كان المستخدم مشرفاً
            if user_id != ADMIN_ID and user_id not in MODERATORS:
                return None
            
            # معلومات المستخدم
            user = await conn.fetchrow('''
                SELECT user_id, username, first_name, last_name, 
                       created_at, last_activity,
                       total_deposits, total_orders, total_points,
                       referral_count
                FROM users 
                WHERE user_id = $1
            ''', user_id)
            
            if not user:
                return None
            
            # آخر نشاطات المشرف
            recent_actions = await conn.fetch('''
                SELECT action, details, created_at
                FROM logs
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 10
            ''', user_id)
            
            # عدد العمليات التي قام بها
            stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_actions,
                    COUNT(CASE WHEN action LIKE '%approve%' OR action LIKE '%موافقة%' THEN 1 END) as approvals,
                    COUNT(CASE WHEN action LIKE '%reject%' OR action LIKE '%رفض%' THEN 1 END) as rejections,
                    COUNT(CASE WHEN action = 'add_admin' THEN 1 END) as admins_added,
                    COUNT(CASE WHEN action = 'remove_admin' THEN 1 END) as admins_removed
                FROM logs
                WHERE user_id = $1
            ''', user_id)
            
            # تحديد الدور
            role = "owner" if user_id == ADMIN_ID else "admin"
            
            return {
                'user': dict(user),
                'recent_actions': recent_actions,
                'stats': dict(stats) if stats else {},
                'role': role
            }
    except Exception as e:
        logging.error(f"❌ خطأ في جلب معلومات المشرف {user_id}: {e}")
        return None

async def get_admin_logs(pool, limit=50):
    """جلب سجل نشاطات المشرفين"""
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
            logs = await conn.fetch('''
                SELECT l.*, u.username 
                FROM logs l
                LEFT JOIN users u ON l.user_id = u.user_id
                WHERE l.action IN ('add_admin', 'remove_admin', 'approve_deposit', 'reject_deposit', 
                                   'approve_order', 'reject_order', 'approve_redemption', 'reject_redemption')
                ORDER BY l.created_at DESC
                LIMIT $1
            ''', limit)
            
            return logs
    except Exception as e:
        logging.error(f"❌ خطأ في جلب سجل النشاطات: {e}")
        return []

async def is_admin_user(pool, user_id):
    """التحقق مما إذا كان المستخدم مشرفاً"""
    try:
        from config import ADMIN_ID, MODERATORS
        return user_id == ADMIN_ID or user_id in MODERATORS
    except Exception as e:
        logging.error(f"❌ خطأ في التحقق من المشرف: {e}")
async def fix_manual_vip_for_existing_users(pool):
    """تحديث المستخدمين اليدويين القدامى - يشغل مرة واحدة"""
    try:
        async with pool.acquire() as conn:
            # افترض أن أي مستخدم مستوى أعلى من 4 هو يدوي
            await conn.execute('''
                UPDATE users 
                SET manual_vip = TRUE 
                WHERE vip_level >= 5 AND (manual_vip IS NULL OR manual_vip = FALSE)
            ''')
            
            # أو ممكن تحديث مستويات محددة يدوياً
            # await conn.execute('''
            #     UPDATE users 
            #     SET manual_vip = TRUE 
            #     WHERE user_id IN (8227444931, 123456789, 987654321)  -- ضيف الآيديهن
            # ''')
            
            logging.info("✅ تم تحديث المستخدمين اليدويين القدامى")
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث المستخدمين القدامى: {e}")

# ============= دوال إعدادات التقارير =============

async def get_report_settings(pool):
    """جلب إعدادات التقارير"""
    try:
        async with pool.acquire() as conn:
            settings = {}
            rows = await conn.fetch("SELECT setting_key, setting_value FROM report_settings")
            for row in rows:
                settings[row['setting_key']] = row['setting_value']
            return settings
    except Exception as e:
        logging.error(f"❌ خطأ في جلب إعدادات التقارير: {e}")
        return {
            'daily_report_enabled': 'true',
            'report_time': '00:00',
            'report_recipients': 'owner_only'
        }

async def update_report_setting(pool, key, value):
    """تحديث إعداد تقرير"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO report_settings (setting_key, setting_value, updated_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT (setting_key) DO UPDATE 
                SET setting_value = $2, updated_at = CURRENT_TIMESTAMP
            ''', key, value)
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث إعداد التقرير {key}: {e}")
        return False  # 👈 هذا السطر يجب أن يكون داخل الـ except
     # أضف الألعاب الأساسية
# ============= دوال تهيئة الألعاب =============

async def init_games(pool):
    """إضافة الألعاب الأساسية مع خياراتها (تشغل مرة واحدة)"""
    try:
        async with pool.acquire() as conn:
            # التحقق إذا كانت الألعاب موجودة مسبقاً
            existing_games = await conn.fetchval("SELECT COUNT(*) FROM applications WHERE type = 'game'")
            if existing_games > 0:
                logging.info("🎮 الألعاب موجودة مسبقاً، تخطي الإضافة")
                return
            
            # جلب قسم الألعاب
            games_cat = await conn.fetchval("SELECT id FROM categories WHERE name = 'games'")
            
            if not games_cat:
                games_cat = await conn.fetchval('''
                    INSERT INTO categories (name, display_name, icon, sort_order)
                    VALUES ('games', '🎮 ألعاب', '🎮', 2)
                    RETURNING id
                ''')
                logging.info("✅ تم إضافة قسم الألعاب")
            
            # 1. ببجي موبايل - مع unit_price_usd (سعر رمزي)
            pubg_id = await conn.fetchval('''
                INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, category_id, type, is_active)
                VALUES ($1, $2, $3, $4, $5, 'game', true)
                RETURNING id
            ''', 'PUBG Mobile', 0.01, 1, 10, games_cat)
            
            # خيارات ببجي
            pubg_options = [
                ('60 UC', 60, 0.99),
                ('325 UC', 325, 4.9),
                ('660 UC', 660, 9.9),
                ('1800 UC', 1800, 18),
                ('3850 UC', 3850, 48),
            ]
            
            for i, (name, qty, price) in enumerate(pubg_options):
                await conn.execute('''
                    INSERT INTO product_options (product_id, name, quantity, price_usd, sort_order)
                    VALUES ($1, $2, $3, $4, $5)
                ''', pubg_id, name, qty, price, i)
            
            # 2. فري فاير - مع unit_price_usd
            ff_id = await conn.fetchval('''
                INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, category_id, type, is_active)
                VALUES ($1, $2, $3, $4, $5, 'game', true)
                RETURNING id
            ''', 'Free Fire', 0.01, 1, 10, games_cat)
            
            ff_options = [
                ('110 ماسة', 110, 0.99),
                ('570 ماسة + 50 هدية', 620, 4.99),
                ('1220 ماسة + 150 هدية', 1370, 9.99),
                ('2420 ماسة + 450 هدية', 2870, 24.99),
            ]
            
            for i, (name, qty, price) in enumerate(ff_options):
                await conn.execute('''
                    INSERT INTO product_options (product_id, name, quantity, price_usd, sort_order)
                    VALUES ($1, $2, $3, $4, $5)
                ''', ff_id, name, qty, price, i)
            
            # 3. كلاش أوف كلانس - مع unit_price_usd
            coc_id = await conn.fetchval('''
                INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, category_id, type, is_active)
                VALUES ($1, $2, $3, $4, $5, 'game', true)
                RETURNING id
            ''', 'Clash of Clans', 0.01, 1, 10, games_cat)
            
            coc_options = [
                ('80 جوهرة', 80, 0.99),
                ('500 جوهرة', 500, 4.99),
                ('1200 جوهرة', 1200, 9.99),
                ('2500 جوهرة', 2500, 19.99),
                ('التذكرة الذهبية (شهر)', 1, 4.99),
            ]
            
            for i, (name, qty, price) in enumerate(coc_options):
                await conn.execute('''
                    INSERT INTO product_options (product_id, name, quantity, price_usd, sort_order)
                    VALUES ($1, $2, $3, $4, $5)
                ''', coc_id, name, qty, price, i)
            
            logging.info("✅ تم إضافة الألعاب بنجاح")
            
    except Exception as e:
        logging.error(f"❌ خطأ في إضافة الألعاب: {e}")
# ============= دوال خيارات المنتجات (product_options) =============

async def update_product_option(db_pool, option_id, updates):
    """تعديل خيار (سعر، اسم، كمية) - مع تحديد الحقول المسموحة"""
    async with db_pool.acquire() as conn:
        set_parts = []
        values = []
        # الحقول المسموح بتعديلها فقط
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
        return False
