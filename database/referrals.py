# database/referrals.py
import random
import string
import logging

async def generate_referral_code(pool, user_id):
    """إنشاء كود إحالة فريد للمستخدم"""
    async with pool.acquire() as conn:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
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
        
        await conn.execute(
            "UPDATE users SET referral_code = $1 WHERE user_id = $2",
            code, user_id
        )
        return code

async def check_duplicate_referral(pool, referrer_id, referred_id):
    """التحقق من عدم تكرار الإحالة"""
    try:
        async with pool.acquire() as conn:
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM points_history 
                WHERE user_id = $1 
                  AND action = 'referral' 
                  AND description LIKE $2
            ''', referrer_id, f'%{referred_id}%')
            
            if count > 0:
                return True, "تمت إحالة هذا المستخدم مسبقاً"
            
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

async def check_existing_referral(pool, referrer_id, referred_id):
    """التحقق إذا كان المستخدم قد تمت إحالته مسبقاً"""
    try:
        async with pool.acquire() as conn:
            referred_by = await conn.fetchval(
                "SELECT referred_by FROM users WHERE user_id = $1",
                referred_id
            )
            
            if referred_by:
                return True, f"هذا المستخدم تمت إحالته مسبقاً بواسطة {referred_by}"
            
            exists = await conn.fetchval('''
                SELECT COUNT(*) FROM points_history 
                WHERE user_id = $1 
                  AND action = 'referral' 
                  AND description LIKE $2
            ''', referrer_id, f'%{referred_id}%')
            
            if exists > 0:
                return True, "تم تسجيل هذه الإحالة مسبقاً"
            
            return False, None
    except Exception as e:
        logging.error(f"❌ خطأ في التحقق من الإحالة: {e}")
        return True, str(e)

async def process_referral(pool, referred_user_id, referrer_code):
    """معالجة الإحالة عند تسجيل مستخدم جديد - مع منع التكرار"""
    try:
        async with pool.acquire() as conn:
            referrer = await conn.fetchrow(
                "SELECT user_id FROM users WHERE referral_code = $1",
                referrer_code
            )
            
            if not referrer or referrer['user_id'] == referred_user_id:
                return None, "كود إحالة غير صالح"
            
            existing = await conn.fetchval(
                "SELECT referred_by FROM users WHERE user_id = $1",
                referred_user_id
            )
            
            if existing:
                return None, f"المستخدم لديه إحالة سابقة ({existing})"
            
            already_referred = await conn.fetchval('''
                SELECT COUNT(*) FROM points_history 
                WHERE user_id = $1 
                  AND action = 'referral' 
                  AND description LIKE $2
            ''', referrer['user_id'], f'%{referred_user_id}%')
            
            if already_referred > 0:
                return None, "تمت إحالة هذا المستخدم مسبقاً"
            
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
            
            await conn.execute(
                "UPDATE users SET referred_by = $1 WHERE user_id = $2",
                referrer['user_id'], referred_user_id
            )
            
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description)
                VALUES ($1, $2, $3, $4)
            ''', referrer['user_id'], points, 'referral', f'إحالة المستخدم {referred_user_id}')
            
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
        logging.error(f"❌ خطأ في معالجة الإحالة: {e}")
        return None, str(e)

async def get_referral_stats(pool, user_id):
    """إحصائيات مفصلة عن الإحالات"""
    try:
        async with pool.acquire() as conn:
            unique_referrals = await conn.fetchval('''
                SELECT COUNT(DISTINCT description) 
                FROM points_history 
                WHERE user_id = $1 AND action = 'referral'
            ''', user_id) or 0
            
            recent = await conn.fetch('''
                SELECT description, created_at 
                FROM points_history 
                WHERE user_id = $1 AND action = 'referral'
                ORDER BY created_at DESC
                LIMIT 5
            ''', user_id)
            
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

async def detect_suspicious_referrals(pool, user_id, threshold=5):
    """كشف محاولات الإحالة المشبوهة (نفس المستخدم عدة مرات)"""
    try:
        async with pool.acquire() as conn:
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
async def update_referrer_stats(pool, referrer_id, points, referred_id):
    """تحديث إحصائيات المُحيل بعد إحالة ناجحة"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET referral_count = referral_count + 1,
                    total_points = total_points + $1,
                    referral_earnings = referral_earnings + $1
                WHERE user_id = $2
            ''', points, referrer_id)
            
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ''', referrer_id, points, 'referral', f'إحالة المستخدم {referred_id}')
            
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث إحصائيات المُحيل: {e}")
        return False
