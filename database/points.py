# database/points.py
import logging
import pytz
from .connection import DAMASCUS_TZ

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

async def add_points_history(db_pool, user_id, points, action, description):
    """إضافة سجل نقاط جديد مع توقيت دمشق"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Damascus')
            ''', user_id, points, action, description)
            
            logging.info(f"✅ تم إضافة سجل نقاط للمستخدم {user_id}: {points} نقطة - {action}")
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في إضافة سجل نقاط للمستخدم {user_id}: {e}")
        return False

async def add_points(pool, user_id, points, action, description):
    """إضافة نقاط للمستخدم وتسجيلها في السجل"""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2",
                points, user_id
            )
            
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
            current = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                user_id
            )
            
            if current < points:
                return False, "نقاط غير كافية"
            
            await conn.execute(
                "UPDATE users SET total_points = total_points - $1, total_points_redeemed = total_points_redeemed + $1 WHERE user_id = $2",
                points, user_id
            )
            
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description)
                VALUES ($1, $2, $3, $4)
            ''', user_id, -points, action, description)
            
            return True, None
    except Exception as e:
        logging.error(f"❌ خطأ في خصم نقاط من المستخدم {user_id}: {e}")
        return False, str(e)

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
        logging.error(f"❌ خطأ في إنشاء طلب استرداد نقاط: {e}")
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
                return False, "الطلب غير موجود أو تمت معالجته مسبقاً"
            
            current_points = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                req['user_id']
            )
            
            if current_points < req['points']:
                return False, "رصيد النقاط غير كافي (تغير منذ تقديم الطلب)"
            
            await conn.execute(
                "UPDATE redemption_requests SET status = 'approved', updated_at = CURRENT_TIMESTAMP, admin_notes = $1 WHERE id = $2",
                f"تمت الموافقة بواسطة {admin_id}", request_id
            )
            
            await conn.execute(
                "UPDATE users SET total_points = total_points - $1, total_points_redeemed = total_points_redeemed + $1 WHERE user_id = $2",
                req['points'], req['user_id']
            )
            
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ''', req['user_id'], -req['points'], 'redemption', f'استرداد نقاط بقيمة {req["amount_syp"]:,.0f} ل.س')
            
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
            exchange_rate = await get_exchange_rate(pool)
            redemption_rate = await get_redemption_rate(pool)
            
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

# لتجنب circular import
from .core import get_exchange_rate