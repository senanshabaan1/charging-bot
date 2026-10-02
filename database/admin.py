# database/admin.py
import logging
from config import ADMIN_ID, MODERATORS

async def get_all_admins(pool):
    """جلب جميع المشرفين من قاعدة البيانات"""
    try:
        async with pool.acquire() as conn:
            admin_ids = [ADMIN_ID] + MODERATORS
            
            if not admin_ids:
                return []
            
            admins = await conn.fetch('''
                SELECT user_id, username, first_name, last_name, 
                       created_at, last_activity,
                       CASE 
                           WHEN user_id = $1 THEN 'owner'
                           ELSE 'admin'
                       END as role
                FROM users 
                WHERE user_id = ANY($2::bigint[])
                ORDER BY 
                    CASE WHEN user_id = $1 THEN 0 ELSE 1 END,
                    username
            ''', ADMIN_ID, admin_ids)
            
            return admins
    except Exception as e:
        logging.error(f"❌ خطأ في جلب المشرفين: {e}")
        return []

async def add_admin(pool, user_id, added_by):
    """إضافة مشرف جديد"""
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT user_id, username FROM users WHERE user_id = $1",
                user_id
            )
            
            if not user:
                return False, "المستخدم غير موجود في قاعدة البيانات"
            
            from config import MODERATORS
            if user_id in MODERATORS:
                return False, "المستخدم مشرف بالفعل"
            
            MODERATORS.append(user_id)
            
            await conn.execute('''
                INSERT INTO logs (user_id, action, details, created_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
            ''', added_by, 'add_admin', f'تمت إضافة المشرف {user_id} (@{user["username"]})')
            
            return True, "تمت إضافة المشرف بنجاح"
    except Exception as e:
        logging.error(f"❌ خطأ في إضافة مشرف: {e}")
        return False, str(e)

async def remove_admin(pool, user_id, removed_by):
    """إزالة مشرف"""
    try:
        async with pool.acquire() as conn:
            from config import ADMIN_ID, MODERATORS
            
            if user_id == ADMIN_ID:
                return False, "لا يمكن إزالة المالك"
            
            if user_id not in MODERATORS:
                return False, "المستخدم ليس مشرفاً"
            
            user = await conn.fetchrow(
                "SELECT username FROM users WHERE user_id = $1",
                user_id
            )
            username = user['username'] if user else 'غير معروف'
            
            MODERATORS.remove(user_id)
            
            await conn.execute('''
                INSERT INTO logs (user_id, action, details, created_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
            ''', removed_by, 'remove_admin', f'تمت إزالة المشرف {user_id} (@{username})')
            
            return True, "تمت إزالة المشرف بنجاح"
    except Exception as e:
        logging.error(f"❌ خطأ في إزالة مشرف: {e}")
        return False, str(e)

async def get_admin_info(pool, user_id):
    """جلب معلومات مفصلة عن مشرف"""
    try:
        async with pool.acquire() as conn:
            from config import ADMIN_ID, MODERATORS
            
            if user_id != ADMIN_ID and user_id not in MODERATORS:
                return None
            
            user = await conn.fetchrow('''
                SELECT user_id, username, first_name, last_name, 
                       created_at, last_activity,
                       total_deposits, total_orders, total_points,
                       referral_count
                FROM users 
                WHERE user_id = $1
            ''', user_id)
            
            if not user:
                return None
            
            recent_actions = await conn.fetch('''
                SELECT action, details, created_at
                FROM logs
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 10
            ''', user_id)
            
            stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_actions,
                    COUNT(CASE WHEN action LIKE '%approve%' OR action LIKE '%موافقة%' THEN 1 END) as approvals,
                    COUNT(CASE WHEN action LIKE '%reject%' OR action LIKE '%رفض%' THEN 1 END) as rejections,
                    COUNT(CASE WHEN action = 'add_admin' THEN 1 END) as admins_added,
                    COUNT(CASE WHEN action = 'remove_admin' THEN 1 END) as admins_removed
                FROM logs
                WHERE user_id = $1
            ''', user_id)
            
            role = "owner" if user_id == ADMIN_ID else "admin"
            
            return {
                'user': dict(user),
                'recent_actions': recent_actions,
                'stats': dict(stats) if stats else {},
                'role': role
            }
    except Exception as e:
        logging.error(f"❌ خطأ في جلب معلومات المشرف {user_id}: {e}")
        return None

async def get_admin_logs(pool, limit=50):
    """جلب سجل نشاطات المشرفين"""
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
            logs = await conn.fetch('''
                SELECT l.*, u.username 
                FROM logs l
                LEFT JOIN users u ON l.user_id = u.user_id
                WHERE l.action IN ('add_admin', 'remove_admin', 'approve_deposit', 'reject_deposit', 
                                   'approve_order', 'reject_order', 'approve_redemption', 'reject_redemption')
                ORDER BY l.created_at DESC
                LIMIT $1
            ''', limit)
            
            return logs
    except Exception as e:
        logging.error(f"❌ خطأ في جلب سجل النشاطات: {e}")
        return []

async def fix_manual_vip_for_existing_users(pool):
    """تحديث المستخدمين اليدويين القدامى - يشغل مرة واحدة"""
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET manual_vip = TRUE 
                WHERE vip_level >= 5 AND (manual_vip IS NULL OR manual_vip = FALSE)
            ''')
            
            logging.info("✅ تم تحديث المستخدمين اليدويين القدامى")
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث المستخدمين القدامى: {e}")