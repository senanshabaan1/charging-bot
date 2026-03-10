# database/orders.py
import logging

async def create_deposit_request(pool, user_id, username, method, amount, amount_syp, tx_info, photo_file_id=None):
    """إنشاء طلب شحن جديد"""
    try:
        async with pool.acquire() as conn:
            deposit_id = await conn.fetchval('''
                INSERT INTO deposit_requests 
                (user_id, username, method, amount, amount_syp, tx_info, photo_file_id, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', CURRENT_TIMESTAMP)
                RETURNING id
            ''', user_id, username, method, amount, amount_syp, tx_info, photo_file_id)
            
            logging.info(f"✅ تم إنشاء طلب شحن جديد رقم {deposit_id}")
            return deposit_id
    except Exception as e:
        logging.error(f"❌ خطأ في إنشاء طلب شحن: {e}")
        return None

async def create_order(pool, user_id, username, app_id, app_name, quantity, unit_price_usd, total_amount_syp, target_id, points_earned=0):
    """إنشاء طلب تطبيق عادي"""
    try:
        async with pool.acquire() as conn:
            order_id = await conn.fetchval('''
                INSERT INTO orders 
                (user_id, username, app_id, app_name, quantity, unit_price_usd, 
                 total_amount_syp, target_id, points_earned, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending', CURRENT_TIMESTAMP)
                RETURNING id
            ''', user_id, username, app_id, app_name, quantity, unit_price_usd, 
                total_amount_syp, target_id, points_earned)
            
            logging.info(f"✅ تم إنشاء طلب تطبيق جديد رقم {order_id}")
            return order_id
    except Exception as e:
        logging.error(f"❌ خطأ في إنشاء طلب تطبيق: {e}")
        return None

async def create_order_with_variant(pool, user_id, username, app_id, app_name, variant, total_amount_syp, target_id, points_earned=0):
    """إنشاء طلب مع فئة فرعية (للألعاب والاشتراكات)"""
    try:
        async with pool.acquire() as conn:
            order_id = await conn.fetchval('''
                INSERT INTO orders 
                (user_id, username, app_id, app_name, variant_id, variant_name, 
                 quantity, duration_days, unit_price_usd, total_amount_syp, target_id, 
                 points_earned, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'pending')
                RETURNING id
            ''',
            user_id,
            username,
            app_id,
            app_name,
            variant['id'],
            variant['name'],
            variant.get('quantity', 0),
            variant.get('duration_days', 0),
            variant['price_usd'],
            total_amount_syp,
            target_id,
            points_earned
            )
            
            return order_id
    except Exception as e:
        logging.error(f"❌ خطأ في إنشاء طلب بفئة: {e}")
        return None

async def update_order_group_message(pool, order_id, message_id):
    """تحديث معرف رسالة المجموعة للطلب"""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE orders SET group_message_id = $1 WHERE id = $2",
                message_id, order_id
            )
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث رسالة المجموعة للطلب {order_id}: {e}")
        return False

async def update_deposit_group_message(pool, deposit_id, message_id):
    """تحديث معرف رسالة المجموعة لطلب الشحن"""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE deposit_requests SET group_message_id = $1 WHERE id = $2",
                message_id, deposit_id
            )
            return True
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث رسالة المجموعة لطلب الشحن {deposit_id}: {e}")
        return False