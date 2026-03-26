# database/core.py
import logging
from cache import cached
from typing import Optional, Dict, Any
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# ============= ثوابت المنطقة الزمنية =============
DAMASCUS_TZ = pytz.timezone('Asia/Damascus')


# ============= دوال مساعدة للتواريخ =============
def get_current_time_naive():
    """الحصول على الوقت الحالي بدون منطقة زمنية (offset-naive)"""
    return datetime.now(DAMASCUS_TZ).replace(tzinfo=None)


def make_naive(dt):
    """تحويل أي تاريخ إلى offset-naive (بدون منطقة زمنية)"""
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        return dt.astimezone(DAMASCUS_TZ).replace(tzinfo=None)
    return dt


# ============= حالة البوت =============

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


# ============= أسعار الصرف المنفصلة =============

@cached(ttl=30, key_prefix="exchange_rate")
async def get_exchange_rate(pool, rate_type: str = 'deposit') -> float:
    """
    جلب سعر الصرف حسب النوع
    rate_type: 'purchase' (شراء - مخفي), 'deposit' (إيداع - ظاهر), 'points' (نقاط)
    """
    try:
        async with pool.acquire() as conn:
            rate = await conn.fetchval(
                "SELECT rate_value FROM exchange_rates WHERE rate_type = $1",
                rate_type
            )
            if rate:
                return float(rate)
            return 118.0
    except Exception as e:
        logging.error(f"❌ خطأ في جلب سعر الصرف ({rate_type}): {e}")
        return 118.0


async def get_all_exchange_rates(pool) -> Dict[str, float]:
    """جلب جميع أسعار الصرف"""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT rate_type, rate_value FROM exchange_rates")
            return {row['rate_type']: float(row['rate_value']) for row in rows}
    except Exception as e:
        logging.error(f"❌ خطأ في جلب جميع الأسعار: {e}")
        return {'purchase': 118, 'deposit': 118, 'points': 118}


async def update_exchange_rate(pool, rate_type: str, rate_value: float, updated_by: int = None) -> bool:
    """تحديث سعر صرف معين"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE exchange_rates 
                SET rate_value = $1, updated_at = CURRENT_TIMESTAMP, updated_by = $2
                WHERE rate_type = $3
            ''', rate_value, updated_by, rate_type)
            logging.info(f"✅ تم تحديث سعر الصرف ({rate_type}) إلى {rate_value}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث سعر الصرف ({rate_type}): {e}")
        return False


# ============= الدوال القديمة للتوافق =============

async def get_old_exchange_rate(pool):
    """جلب سعر الصرف القديم (للتوافق مع الكود القديم)"""
    return await get_exchange_rate(pool, 'deposit')

async def set_exchange_rate(pool, rate):
    """تحديث سعر الصرف (يحدث سعر الإيداع فقط)"""
    return await update_exchange_rate(pool, 'deposit', rate)


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


# ============= دوال مكافآت الإيداع فقط =============

async def get_db_now_naive(pool):
    """جلب الوقت الحالي من قاعدة البيانات بدون منطقة زمنية"""
    try:
        async with pool.acquire() as conn:
            now = await conn.fetchval("SELECT NOW()")
            return make_naive(now)
    except Exception as e:
        logging.error(f"❌ خطأ في جلب الوقت: {e}")
        return get_current_time_naive()


async def get_active_deposit_bonus(pool, deposit_amount: float = None) -> Optional[Dict]:
    """جلب مكافأة الإيداع النشطة حالياً"""
    try:
        now = await get_db_now_naive(pool)
        
        async with pool.acquire() as conn:
            query = '''
                SELECT * FROM deposit_bonuses 
                WHERE is_active = TRUE 
                AND start_date <= $1::timestamp 
                AND end_date >= $1::timestamp
            '''
            params = [now]
            
            if deposit_amount is not None:
                query += " AND (min_deposit_amount IS NULL OR min_deposit_amount <= $2)"
                params.append(deposit_amount)
            
            query += " ORDER BY bonus_percent DESC LIMIT 1"
            
            bonus = await conn.fetchrow(query, *params)
            return dict(bonus) if bonus else None
    except Exception as e:
        logging.error(f"❌ خطأ في جلب مكافأة الإيداع: {e}")
        return None


async def get_all_deposit_bonuses(pool) -> list:
    """جلب جميع مكافآت الإيداع"""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM deposit_bonuses ORDER BY created_at DESC")
            return [dict(row) for row in rows]
    except Exception as e:
        logging.error(f"❌ خطأ في جلب مكافآت الإيداع: {e}")
        return []


async def create_deposit_bonus(
    pool,
    name: str,
    bonus_percent: int,
    start_date,
    end_date,
    min_deposit_amount: float = None,
    max_bonus_amount: float = None,
    description: str = None,
    created_by: int = None
) -> Optional[int]:
    """إنشاء مكافأة إيداع جديدة"""
    try:
        start_date = make_naive(start_date)
        end_date = make_naive(end_date)
        
        async with pool.acquire() as conn:
            bonus_id = await conn.fetchval('''
                INSERT INTO deposit_bonuses 
                (name, bonus_percent, start_date, end_date, min_deposit_amount, max_bonus_amount, description, created_by)
                VALUES ($1, $2, $3::timestamp, $4::timestamp, $5, $6, $7, $8)
                RETURNING id
            ''', name, bonus_percent, start_date, end_date, min_deposit_amount, max_bonus_amount, description, created_by)
            logging.info(f"✅ تم إنشاء مكافأة إيداع #{bonus_id}: {bonus_percent}%")
            return bonus_id
    except Exception as e:
        logging.error(f"❌ خطأ في إنشاء مكافأة الإيداع: {e}")
        return None


async def deactivate_deposit_bonus(pool, bonus_id: int) -> bool:
    """إلغاء تنشيط مكافأة إيداع"""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE deposit_bonuses SET is_active = FALSE WHERE id = $1",
                bonus_id
            )
            logging.info(f"✅ تم إلغاء تنشيط مكافأة الإيداع #{bonus_id}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في إلغاء تنشيط مكافأة الإيداع: {e}")
        return False


# ============= دوال سجل استخدام المكافآت =============

async def record_offer_usage(
    pool,
    user_id: int,
    offer_id: int,
    offer_type: str,
    order_id: int = None,
    deposit_id: int = None
) -> bool:
    """تسجيل استخدام مكافأة"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO offer_usage (user_id, offer_id, offer_type, order_id, deposit_id)
                VALUES ($1, $2, $3, $4, $5)
            ''', user_id, offer_id, offer_type, order_id, deposit_id)
            logging.info(f"✅ تم تسجيل استخدام {offer_type} #{offer_id} للمستخدم {user_id}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تسجيل استخدام المكافأة: {e}")
        return False


async def has_user_used_offer(pool, user_id: int, offer_id: int, offer_type: str) -> bool:
    """التحقق مما إذا كان المستخدم قد استخدم مكافأة معينة"""
    try:
        async with pool.acquire() as conn:
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM offer_usage 
                WHERE user_id = $1 AND offer_id = $2 AND offer_type = $3
            ''', user_id, offer_id, offer_type)
            return count > 0
    except Exception as e:
        logging.error(f"❌ خطأ في التحقق من استخدام المكافأة: {e}")
        return False


async def get_offer_usage_stats(pool, offer_id: int, offer_type: str) -> Dict:
    """جلب إحصائيات استخدام مكافأة"""
    try:
        async with pool.acquire() as conn:
            stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_uses,
                    COUNT(DISTINCT user_id) as unique_users
                FROM offer_usage 
                WHERE offer_id = $1 AND offer_type = $2
            ''', offer_id, offer_type)
            return dict(stats) if stats else {'total_uses': 0, 'unique_users': 0}
    except Exception as e:
        logging.error(f"❌ خطأ في جلب إحصائيات المكافأة: {e}")
        return {'total_uses': 0, 'unique_users': 0}


# ============= دوال التوافق (للمكافآت فقط) =============

async def get_deposit_bonus_percent(pool, amount: float = None) -> int:
    """جلب نسبة مكافأة الإيداع"""
    bonus = await get_active_deposit_bonus(pool, amount)
    return bonus['bonus_percent'] if bonus else 0


# ============= الدوال المهملة (للعروض العامة - غير مستخدمة) =============
# تم إزالة دوال العروض العامة لأنها غير مستخدمة حالياً
# إذا احتجتها لاحقاً، يمكن إضافتها مرة أخرى
