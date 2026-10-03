# database.py
import asyncpg
import logging

logger = logging.getLogger(__name__)

async def init_db():
    """إنشاء وتحديث الجداول تلقائياً مع تعطيل statement_cache لتوافق PgBouncer"""
    from config import DATABASE_URL
    
    # إنشاء مجمع الاتصالات مع تعطيل التخزين المؤقت للـ statements لتجنب مشاكل Supabase / PgBouncer
    pool = await asyncpg.create_pool(
        DATABASE_URL, 
        min_size=2, 
        max_size=10, 
        statement_cache_size=0
    )
    
    async with pool.acquire() as conn:
        # إعدادات البوت
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        await conn.execute("INSERT INTO settings (key, value) VALUES ('exchange_rate', '15000') ON CONFLICT DO NOTHING")

        # المستخدمين
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                balance FLOAT DEFAULT 0,
                currency VARCHAR(10) DEFAULT 'USD',
                is_banned BOOLEAN DEFAULT FALSE
            )
        ''')
        
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS balance FLOAT DEFAULT 0")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS currency VARCHAR(10) DEFAULT 'USD'")
        except:
            pass

        # مزودي الخدمة (مواقع الـ API)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS api_providers (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                base_url TEXT,
                api_token TEXT
            )
        ''')

        # الأقسام
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE
            )
        ''')

        # المنتجات
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
                provider_id INTEGER REFERENCES api_providers(id) ON DELETE SET NULL,
                remote_service_id INTEGER,
                name TEXT,
                price_usd FLOAT,
                min_qty INTEGER DEFAULT 1
            )
        ''')
        
        # الطلبات
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                product_name TEXT,
                target_id TEXT,
                qty INTEGER,
                cost_usd FLOAT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    return pool

async def get_exchange_rate(pool) -> float:
    async with pool.acquire() as conn:
        rate = await conn.fetchval("SELECT value FROM settings WHERE key = 'exchange_rate'")
        return float(rate) if rate else 15000.0

async def get_or_create_user(pool, user_id: int):
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not user:
            await conn.execute("INSERT INTO users (user_id) VALUES ($1)", user_id)
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return user
