# database.py
import asyncpg
import logging
from config import DB_CONFIG

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
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                ('points_per_order', '5', 'نقاط لكل عملية شراء'),
                ('points_per_referral', '5', 'نقاط لكل عملية من خلال الإحالة'),
                ('redemption_rate', '500', 'عدد النقاط مقابل 5 دولار'),
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

        await conn.close()
        logging.info("✅ تم تهيئة قاعدة البيانات والجداول بنجاح.")
    except Exception as e:
        logging.error(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}")

async def get_pool():
    """إنشاء مجمع اتصالات (Pool)"""
    try:
        # التحقق من وجود dsn في الإعدادات
        if "dsn" in DB_CONFIG:
            pool = await asyncpg.create_pool(dsn=DB_CONFIG["dsn"])
            logging.info("✅ تم إنشاء مجمع الاتصالات باستخدام DSN")
        else:
            pool = await asyncpg.create_pool(**DB_CONFIG)
            logging.info("✅ تم إنشاء مجمع الاتصالات بنجاح")
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

async def process_referral(pool, referred_user_id, referrer_code):
    """معالجة الإحالة عند تسجيل مستخدم جديد"""
    try:
        async with pool.acquire() as conn:
            # البحث عن المستخدم الذي قام بالإحالة
            referrer = await conn.fetchrow(
                "SELECT user_id FROM users WHERE referral_code = $1",
                referrer_code
            )
            
            if referrer and referrer['user_id'] != referred_user_id:
                # تسجيل من أحال المستخدم
                await conn.execute(
                    "UPDATE users SET referred_by = $1, referral_count = referral_count + 1 WHERE user_id = $2",
                    referrer['user_id'], referred_user_id
                )
                
                # الحصول على قيمة النقاط من الإعدادات
                points = await conn.fetchval(
                    "SELECT value FROM bot_settings WHERE key = 'points_per_referral'"
                )
                points = int(points) if points else 5
                
                # إضافة نقاط للمستخدم الذي قام بالإحالة
                await add_points(pool, referrer['user_id'], points, 'referral', 
                                 f'نقاط إحالة للمستخدم {referred_user_id}')
                
                # تحديث أرباح الإحالة
                await conn.execute(
                    "UPDATE users SET referral_earnings = referral_earnings + $1 WHERE user_id = $2",
                    points, referrer['user_id']
                )
                
                return referrer['user_id']
            return None
    except Exception as e:
        logging.error(f"❌ خطأ في معالجة الإحالة: {e}")
        return None

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

async def get_points_history(pool, user_id, limit=10):
    """جلب سجل نقاط المستخدم"""
    try:
        async with pool.acquire() as conn:
            history = await conn.fetch('''
                SELECT points, action, description, created_at
                FROM points_history
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            ''', user_id, limit)
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
            
            # جلب معدل الاسترداد (كم نقطة مقابل 5 دولار)
            redemption_rate = await get_redemption_rate(pool)
            
            # حساب قيمة النقاط
            # مثال: 500 نقطة = 5 دولار
            usd_value = (points / redemption_rate) * 5
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

# ============= دوال الفئات الفرعية =============

async def get_app_variants(pool, app_id):
    """جلب الفئات الفرعية لتطبيق معين"""
    try:
        async with pool.acquire() as conn:
            variants = await conn.fetch('''
                SELECT * FROM app_variants 
                WHERE app_id = $1 AND is_active = TRUE 
                ORDER BY sort_order, price_usd
            ''', app_id)
            return variants
    except Exception as e:
        logging.error(f"❌ خطأ في جلب الفئات للتطبيق {app_id}: {e}")
        return []

async def get_app_variant(pool, variant_id):
    """جلب فئة فرعية محددة"""
    try:
        async with pool.acquire() as conn:
            variant = await conn.fetchrow(
                "SELECT * FROM app_variants WHERE id = $1",
                variant_id
            )
            return variant
    except Exception as e:
        logging.error(f"❌ خطأ في جلب الفئة {variant_id}: {e}")
        return None

# ============= دوال الإحصائيات =============

async def get_user_profile(pool, user_id):
    """جلب معلومات الملف الشخصي للمستخدم بشكل كامل"""
    try:
        async with pool.acquire() as conn:
            # معلومات المستخدم الأساسية
            user = await conn.fetchrow('''
                SELECT user_id, username, first_name, last_name, balance, is_banned, 
                       created_at, total_deposits, total_orders, total_points,
                       referral_code, referred_by, referral_count, referral_earnings,
                       total_points_earned, total_points_redeemed, last_activity
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
            
            # آخر 5 طلبات
            recent_orders = await conn.fetch('''
                SELECT app_name, variant_name, quantity, total_amount_syp, status, created_at
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
    """جلب إحصائيات البوت"""
    try:
        async with pool.acquire() as conn:
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
            ) or 5
            
            points_per_deposit = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_deposit'"
            ) or 5
            
            points_per_referral = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_referral'"
            ) or 5
            
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
            return int(points) if points else 5
    except Exception as e:
        logging.error(f"❌ خطأ في جلب نقاط الطلب: {e}")
        return 5

async def get_points_per_deposit(pool):
    """جلب عدد النقاط لكل عملية شحن من الإعدادات"""
    try:
        async with pool.acquire() as conn:
            points = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_deposit'"
            )
            return int(points) if points else 5
    except Exception as e:
        logging.error(f"❌ خطأ في جلب نقاط الشحن: {e}")
        return 5

async def get_points_per_referral(pool):
    """جلب عدد النقاط لكل إحالة من الإعدادات"""
    try:
        async with pool.acquire() as conn:
            points = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_referral'"
            )
            return int(points) if points else 5
    except Exception as e:
        logging.error(f"❌ خطأ في جلب نقاط الإحالة: {e}")
        return 5

async def get_user_points_history(pool, user_id, limit=20):
    """جلب سجل نقاط المستخدم مع تفاصيل أكثر"""
    try:
        async with pool.acquire() as conn:
            history = await conn.fetch('''
                SELECT points, action, description, created_at
                FROM points_history
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            ''', user_id, limit)
            return history
    except Exception as e:
        logging.error(f"❌ خطأ في جلب سجل النقاط للمستخدم {user_id}: {e}")
        return []

async def get_total_points_earned(pool, user_id):
    """جلب إجمالي النقاط المكتسبة للمستخدم"""
    try:
        async with pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT total_points_earned FROM users WHERE user_id = $1",
                user_id
            )
            return total or 0
    except Exception as e:
        logging.error(f"❌ خطأ في جلب إجمالي النقاط المكتسبة للمستخدم {user_id}: {e}")
        return 0

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
            info = await conn.fetchrow('''
                SELECT referral_code, referral_count, referral_earnings, referred_by
                FROM users WHERE user_id = $1
            ''', user_id)
            
            if info:
                # جلب قائمة المحالين
                referrals = await conn.fetch('''
                    SELECT user_id, username, created_at
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
    """جلب معدل استرداد النقاط (كم نقطة مقابل 5 دولار)"""
    try:
        async with pool.acquire() as conn:
            rate = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'redemption_rate'"
            )
            return int(rate) if rate else 500
    except Exception as e:
        logging.error(f"❌ خطأ في جلب معدل الاسترداد: {e}")
        return 500

# ============= دوال سعر الصرف =============

async def get_exchange_rate(pool):
    """جلب سعر الصرف من قاعدة البيانات"""
    try:
        async with pool.acquire() as conn:
            rate = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'usd_to_syp'"
            )
            return float(rate) if rate else 25000
    except Exception as e:
        logging.error(f"❌ خطأ في جلب سعر الصرف: {e}")
        return 25000

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
    """جلب أرقام سيرياتل من قاعدة البيانات"""  # هذه السطر لازم يكون عنده 4 مسافات
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

