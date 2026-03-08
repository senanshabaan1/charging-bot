# database/connection.py
import asyncpg
import logging
import pytz
from datetime import datetime
from config import DB_CONFIG, DATABASE_URL

DAMASCUS_TZ = pytz.timezone('Asia/Damascus')

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
    """ضبط المنطقة الزمنية لقاعدة البيانات لجميع الاتصالات"""
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            db_time = await conn.fetchval("SELECT NOW()")
            db_time_utc = await conn.fetchval("SELECT NOW() AT TIME ZONE 'UTC'")
            
            logging.info(f"🕒 وقت DB بعد الضبط (Asia/Damascus): {db_time}")
            logging.info(f"🕒 وقت DB بصيغة UTC: {db_time_utc}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في ضبط توقيت قاعدة البيانات: {e}")
        return False

async def get_pool():
    """إنشاء مجمع اتصالات ذكي يدعم الرابط أو المصفوفة مع قيود الخطة المجانية"""
    try:
        from config import DATABASE_URL, DB_CONFIG
        
        dsn_link = DATABASE_URL if DATABASE_URL else DB_CONFIG.get("dsn")
        
        async def init_connection(conn):
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")

        pool_settings = {
            "min_size": 1,
            "max_size": 5,
            "command_timeout": 60,
            "init": init_connection,
            "statement_cache_size": 0,
            "max_cached_statement_lifetime": 0,
            "server_settings": {'timezone': 'Asia/Damascus'}
        }

        if dsn_link:
            logging.info(f"🔌 محاولة الاتصال باستخدام DSN: {dsn_link[:50]}...")
            pool = await asyncpg.create_pool(dsn=dsn_link, **pool_settings)
        else:
            logging.info(f"🔌 محاولة الاتصال باستخدام الإعدادات: {DB_CONFIG.get('host')}")
            pool = await asyncpg.create_pool(**DB_CONFIG, **pool_settings)
            
        logging.info("✅ تم إنشاء مجمع الاتصالات بنجاح (الحد الأقصى: 5)")
        return pool
    except Exception as e:
        logging.error(f"❌ فشل إنشاء مجمع الاتصالات: {e}")
        return None

async def update_old_records_timezone(pool):
    """تحديث السجلات القديمة إلى التوقيت الصحيح (مرة واحدة)"""
    try:
        async with pool.acquire() as conn:
            tables = ['users', 'deposit_requests', 'orders', 'points_history', 'redemption_requests']
            
            for table in tables:
                try:
                    await conn.execute(f"""
                        UPDATE {table} 
                        SET created_at = created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Damascus'
                        WHERE created_at IS NOT NULL
                          AND EXTRACT(HOUR FROM created_at) < 3
                    """)
                    
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