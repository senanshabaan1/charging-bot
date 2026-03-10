# database/stats.py
import logging

async def get_bot_stats(pool):
    """جلب إحصائيات البوت مع توقيت محلي"""
    try:
        async with pool.acquire() as conn:
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
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_deposits,
                    COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_deposits
                FROM deposit_requests
            ''')
            
            orders_stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_orders,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN total_amount_syp END), 0) as total_completed_amount,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_orders,
                    COUNT(CASE WHEN status = 'processing' THEN 1 END) as processing_orders,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_orders,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_orders,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN points_earned END), 0) as total_points_given
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
        return False