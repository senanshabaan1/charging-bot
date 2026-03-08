# database/vip.py
import logging

async def get_vip_levels(pool):
    """جلب جميع مستويات VIP"""
    try:
        async with pool.acquire() as conn:
            levels = await conn.fetch('''
                SELECT * FROM vip_levels ORDER BY level
            ''')
            return levels
    except Exception as e:
        logging.error(f"❌ خطأ في جلب مستويات VIP: {e}")
        return []

async def get_user_vip(pool, user_id):
    """جلب مستوى VIP للمستخدم"""
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow('''
                SELECT vip_level, total_spent, discount_percent 
                FROM users WHERE user_id = $1
            ''', user_id)
            return user or {'vip_level': 0, 'total_spent': 0, 'discount_percent': 0}
    except Exception as e:
        logging.error(f"❌ خطأ في جلب مستوى VIP للمستخدم {user_id}: {e}")
        return {'vip_level': 0, 'total_spent': 0, 'discount_percent': 0}

async def update_user_vip(pool, user_id):
    """تحديث مستوى VIP للمستخدم - حسب طلبك"""
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT manual_vip, vip_level, discount_percent FROM users WHERE user_id = $1",
                user_id
            )
            
            if user and user['manual_vip']:
                logging.info(f"👑 المستخدم {user_id} لديه مستوى يدوي VIP {user['vip_level']}")
                return {
                    'level': user['vip_level'],
                    'discount': user['discount_percent'],
                    'total_spent': 0,
                    'next_level': None,
                    'manual': True
                }
            
            total_spent = await conn.fetchval('''
                SELECT COALESCE(SUM(total_amount_syp), 0) 
                FROM orders 
                WHERE user_id = $1 AND status = 'completed'
            ''', user_id) or 0
            
            level = 0
            discount = 0
            
            vip_levels = [
                (3500, 1, 1),
                (6500, 2, 2),
                (12000, 3, 3),
            ]
            
            for spent, lvl, disc in reversed(vip_levels):
                if total_spent >= spent:
                    level = lvl
                    discount = disc
                    break
            
            await conn.execute('''
                UPDATE users 
                SET vip_level = $1, 
                    total_spent = $2, 
                    discount_percent = $3,
                    manual_vip = FALSE
                WHERE user_id = $4 AND (manual_vip IS NULL OR manual_vip = FALSE)
            ''', level, total_spent, discount, user_id)
            
            logging.info(f"✅ تم تحديث VIP للمستخدم {user_id} إلى المستوى {level} (خصم {discount}%) - إنفاق: {total_spent:,.0f} ل.س")
            
            return {
                'level': level,
                'discount': discount,
                'total_spent': total_spent,
                'next_level': get_next_vip_level(total_spent),
                'manual': False
            }
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث VIP للمستخدم {user_id}: {e}")
        return None

def get_next_vip_level(total_spent):
    """حساب المستوى التالي حسب النظام المطلوب"""
    vip_levels = [
        (3500, 1, "VIP 1 🔵 (خصم 1%)", 1),
        (6500, 2, "VIP 2 🟣 (خصم 2%)", 2),
        (12000, 3, "VIP 3 🟡 (خصم 3%)", 3),
    ]
    
    for required, level, name, discount in vip_levels:
        if total_spent < required:
            remaining = required - total_spent
            return {
                'next_level': level,
                'next_level_name': name,
                'remaining': remaining,
                'next_discount': discount
            }
    
    return {
        'next_level': 3,
        'next_level_name': "VIP 3 🟡 (الأقصى)",
        'remaining': 0,
        'next_discount': 3
    }