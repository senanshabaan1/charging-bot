# database/users.py
import logging
import pytz
from datetime import datetime
from .connection import DAMASCUS_TZ

async def get_user_profile(pool, user_id):
    """جلب معلومات الملف الشخصي للمستخدم بشكل كامل مع توقيت محلي"""
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
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
            
            deposits = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_count,
                    COALESCE(SUM(amount_syp), 0) as total_amount,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_count,
                    COALESCE(SUM(CASE WHEN status = 'approved' THEN amount_syp END), 0) as approved_amount
                FROM deposit_requests 
                WHERE user_id = $1
            ''', user_id)
            
            orders = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_count,
                    COALESCE(SUM(total_amount_syp), 0) as total_amount,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_count,
                    COUNT(CASE WHEN status = 'processing' THEN 1 END) as processing_count,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_count,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN total_amount_syp END), 0) as completed_amount,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN points_earned END), 0) as total_points_earned
                FROM orders 
                WHERE user_id = $1
            ''', user_id)
            
            referrals = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_referrals,
                    COALESCE(SUM(total_deposits), 0) as referrals_deposits,
                    COALESCE(SUM(total_orders), 0) as referrals_orders
                FROM users 
                WHERE referred_by = $1
            ''', user_id)
            
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

async def get_all_users(pool):
    """جلب جميع المستخدمين من قاعدة البيانات"""
    try:
        async with pool.acquire() as conn:
            users = await conn.fetch("SELECT * FROM users ORDER BY user_id")
            return users
    except Exception as e:
        logging.error(f"❌ خطأ في جلب المستخدمين: {e}")
        return []

async def is_admin_user(pool, user_id):
    """التحقق مما إذا كان المستخدم مشرفاً"""
    try:
        from config import ADMIN_ID, MODERATORS
        return user_id == ADMIN_ID or user_id in MODERATORS
    except Exception as e:
        logging.error(f"❌ خطأ في التحقق من المشرف: {e}")
        return False
        # database/users.py - Add this function

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
