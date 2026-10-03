# database/connection.py
import asyncpg
import logging
import pytz
from datetime import datetime
from config import DB_CONFIG, DATABASE_URL

DAMASCUS_TZ = pytz.timezone('Asia/Damascus')

def format_local_time(dt):
    if dt is None: return "غير معروف"
    if isinstance(dt, str):
        try: dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except: return dt
    if dt.tzinfo is None: dt = pytz.UTC.localize(dt)
    return dt.astimezone(DAMASCUS_TZ).strftime("%Y-%m-%d %H:%M:%S")

async def set_database_timezone(pool):
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في ضبط توقيت قاعدة البيانات: {e}")
        return False

async def get_pool():
    try:
        from config import DATABASE_URL, DB_CONFIG
        dsn_link = DATABASE_URL if DATABASE_URL else DB_CONFIG.get("dsn")
        async def init_connection(conn): await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")

        pool_settings = {
            "min_size": 5, "max_size": 20, "max_queries": 50000, "command_timeout": 30,
            "init": init_connection, "server_settings": {'timezone': 'Asia/Damascus'}
        }
        if dsn_link: pool = await asyncpg.create_pool(dsn=dsn_link, **pool_settings)
        else: pool = await asyncpg.create_pool(**DB_CONFIG, **pool_settings)
        return pool
    except Exception as e:
        logging.error(f"❌ فشل إنشاء مجمع الاتصالات: {e}")
        return None

async def update_old_records_timezone(pool):
    try:
        async with pool.acquire() as conn:
            tables = ['users', 'deposit_requests', 'orders', 'points_history', 'redemption_requests']
            for table in tables:
                try:
                    await conn.execute(f"UPDATE {table} SET created_at = created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Damascus' WHERE created_at IS NOT NULL AND EXTRACT(HOUR FROM created_at) < 3")
                    if table in ['deposit_requests', 'orders', 'redemption_requests']:
                        await conn.execute(f"UPDATE {table} SET updated_at = updated_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Damascus' WHERE updated_at IS NOT NULL AND EXTRACT(HOUR FROM updated_at) < 3")
                except: pass
            return True
    except: return False

async def init_db(pool=None):
    conn = None
    need_release = False
    try:
        if pool:
            conn = await pool.acquire()
            need_release = True
        else:
            conn = await asyncpg.connect(**DB_CONFIG)
            need_release = False
            
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, balance FLOAT DEFAULT 0, username TEXT, first_name TEXT, last_name TEXT,
                is_banned BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, total_deposits FLOAT DEFAULT 0,
                total_orders FLOAT DEFAULT 0, total_points INTEGER DEFAULT 0, referral_code TEXT UNIQUE, referred_by BIGINT,
                referral_count INTEGER DEFAULT 0, referral_earnings FLOAT DEFAULT 0, total_points_earned INTEGER DEFAULT 0,
                total_points_redeemed INTEGER DEFAULT 0, last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP, vip_level INTEGER DEFAULT 0,
                total_spent FLOAT DEFAULT 0, discount_percent INTEGER DEFAULT 0, manual_vip BOOLEAN DEFAULT FALSE, currency VARCHAR(10) DEFAULT 'USD'
            );
        ''')

        await conn.execute('''CREATE TABLE IF NOT EXISTS categories (id SERIAL PRIMARY KEY, name TEXT UNIQUE, display_name TEXT, icon TEXT DEFAULT '📁', sort_order INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS api_providers (id SERIAL PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL, base_url TEXT NOT NULL, api_token TEXT NOT NULL, balance FLOAT DEFAULT 0, is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')
        
        await conn.execute('''INSERT INTO api_providers (id, name, base_url, api_token) VALUES (1, 'Mousa Card', 'https://mousa-card.com', 'ضع_التوكن_هنا') ON CONFLICT (name) DO NOTHING;''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id SERIAL PRIMARY KEY, name TEXT UNIQUE, unit_price_usd FLOAT, min_units INTEGER, profit_percentage FLOAT DEFAULT 10,
                category_id INTEGER REFERENCES categories(id), type VARCHAR(50) DEFAULT 'service', api_service_id TEXT,
                provider_id INTEGER REFERENCES api_providers(id) DEFAULT 1, api_url TEXT, api_token TEXT, description TEXT,
                is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        await conn.execute('''CREATE TABLE IF NOT EXISTS app_variants (id SERIAL PRIMARY KEY, app_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE, name VARCHAR(255) NOT NULL, display_name TEXT, description TEXT, quantity INTEGER, duration_days INTEGER, price_usd DECIMAL(10, 6) NOT NULL, sort_order INTEGER DEFAULT 0, is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS product_options (id SERIAL PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE, name VARCHAR(255) NOT NULL, description TEXT, quantity INTEGER, price_usd DECIMAL(10, 6) NOT NULL, sort_order INTEGER DEFAULT 0, is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS service_types (id SERIAL PRIMARY KEY, name VARCHAR(50) UNIQUE, display_name VARCHAR(100), description TEXT);''')
        await conn.execute('''INSERT INTO service_types (name, display_name, description) VALUES ('regular', 'رشق عادي', 'متابعين عاديين'), ('high_quality', 'جودة عالية', 'متابعين بجودة عالية'), ('telegram_stars', 'نجوم تليجرام', 'شراء نجوم تيليجرام') ON CONFLICT (name) DO NOTHING;''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS deposit_requests (id SERIAL PRIMARY KEY, user_id BIGINT, username TEXT, method TEXT, amount FLOAT, amount_syp FLOAT, tx_info TEXT, status TEXT DEFAULT 'pending', admin_notes TEXT, photo_file_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, group_message_id BIGINT);''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, user_id BIGINT, username TEXT, app_id INTEGER, app_name TEXT, variant_id INTEGER, variant_name TEXT, quantity INTEGER, duration_days INTEGER, unit_price_usd FLOAT, total_amount_syp FLOAT, target_id TEXT, status TEXT DEFAULT 'pending', points_earned INTEGER DEFAULT 0, api_response TEXT, admin_notes TEXT, group_message_id BIGINT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS points_history (id SERIAL PRIMARY KEY, user_id BIGINT, points INTEGER, action TEXT, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS redemption_requests (id SERIAL PRIMARY KEY, user_id BIGINT, username TEXT, points INTEGER, amount_usd FLOAT, amount_syp FLOAT, status TEXT DEFAULT 'pending', admin_notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT, description TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS vip_levels (level INTEGER PRIMARY KEY, name TEXT NOT NULL, min_spent FLOAT NOT NULL, discount_percent INTEGER NOT NULL, icon TEXT DEFAULT '⭐');''')
        await conn.execute('''INSERT INTO vip_levels (level, name, min_spent, discount_percent, icon) VALUES (0, 'VIP 0', 0, 0, '⚪'), (1, 'VIP 1', 3500, 1, '🔵'), (2, 'VIP 2', 6500, 2, '🟣'), (3, 'VIP 3', 12000, 3, '🟡') ON CONFLICT (level) DO UPDATE SET min_spent = EXCLUDED.min_spent, discount_percent = EXCLUDED.discount_percent, icon = EXCLUDED.icon;''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS logs (id SERIAL PRIMARY KEY, user_id BIGINT, action TEXT, details TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS report_settings (id SERIAL PRIMARY KEY, setting_key TEXT UNIQUE, setting_value TEXT, description TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')
        await conn.execute('''INSERT INTO report_settings (setting_key, setting_value, description) VALUES ('daily_report_enabled', 'true', 'تفعيل التقرير اليومي'), ('report_time', '00:00', 'وقت إرسال التقرير'), ('report_recipients', 'owner_only', 'مستلمو التقرير (all_admins/owner_only)') ON CONFLICT (setting_key) DO NOTHING;''')
        await conn.execute('''INSERT INTO categories (name, display_name, icon, sort_order) VALUES ('chat_apps', '💬 تطبيقات دردشة', '💬', 1) ON CONFLICT (name) DO NOTHING;''')
        await conn.execute('''INSERT INTO bot_settings (key, value, description) VALUES ('bot_status', 'running', 'حالة البوت (running/stopped)'), ('maintenance_message', 'البوت قيد الصيانة حالياً، يرجى المحاولة لاحقاً', 'رسالة الصيانة'), ('points_per_order', '1', 'نقاط لكل عملية شراء'), ('points_per_referral', '1', 'نقاط لكل عملية من خلال الإحالة'), ('redemption_rate', '100', 'عدد النقاط مقابل 1 دولار'), ('last_restart', CURRENT_TIMESTAMP::TEXT, 'آخر تشغيل للبوت'), ('syriatel_nums', '74091109,63826779', 'أرقام سيرياتل كاش') ON CONFLICT (key) DO NOTHING;''')

        tables_columns = {
            'applications': [('provider_id', 'INTEGER REFERENCES api_providers(id) DEFAULT 1')],
            'users': [('currency', "VARCHAR(10) DEFAULT 'USD'")]
        }
        for table, columns in tables_columns.items():
            for column_name, column_type in columns:
                try:
                    exists = await conn.fetchval(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' AND column_name='{column_name}'")
                    if not exists: await conn.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_name} {column_type};')
                except: pass
        
        try:
            users = await conn.fetch("SELECT user_id FROM users WHERE referral_code IS NULL")
            for user in users:
                import random, string
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                await conn.execute("UPDATE users SET referral_code = $1 WHERE user_id = $2", code, user['user_id'])
        except: pass

        if need_release and pool: await pool.release(conn)
        elif not need_release: await conn.close()
        return True
    except Exception as e:
        logging.error(f"❌ خطأ أثناء تهيئة قاعدة البيانات: {e}")
        return False
