# database/core.py
import logging
from cache import cached

# ============= حالة البوت =============

async def get_bot_status(pool):
    """جلب حالة البوت"""
    try:
        async with pool.acquire() as conn:
            status = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'bot_status'"
            )
            # ✅ التحقق الصحيح: 'running' = True, أي شيء آخر = False
            return status == 'running'
    except Exception as e:
        logging.error(f"❌ خطأ في جلب حالة البوت: {e}")
        return True  # افتراضي يعمل

async def set_bot_status(pool, status: bool):
    """تغيير حالة البوت - status يجب أن يكون boolean"""
    try:
        async with pool.acquire() as conn:
            # ✅ تحويل boolean إلى النص المناسب
            status_text = 'running' if status else 'stopped'
            
            await conn.execute('''
                INSERT INTO bot_settings (key, value, description) 
                VALUES ('bot_status', $1, 'حالة البوت (running/stopped)')
                ON CONFLICT (key) DO UPDATE SET 
                    value = $2, 
                    updated_at = CURRENT_TIMESTAMP
            ''', status_text, status_text)
            
            logging.info(f"✅ تم تغيير حالة البوت إلى: {status_text} (status={status})")
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

# ============= سعر الصرف =============

@cached(ttl=30, key_prefix="exchange_rate")
async def get_exchange_rate(pool):
    """جلب سعر الصرف مع كاش 30 ثانية"""
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

# ============= أرقام سيرياتل =============

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
