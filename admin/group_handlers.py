# admin/group_handlers.py
from aiogram import Router, F, types, Bot
import logging
from handlers.time_utils import get_damascus_time_now
from utils import get_formatted_damascus_time, format_amount
logger = logging.getLogger(__name__)
router = Router(name="admin_group")

@router.callback_query(F.data.startswith("appr_dep_"))
async def approve_deposit_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """موافقة على طلب شحن من المجموعة"""
    try:
        logger.info(f"📩 استقبال موافقة شحن: {callback.data}")
        
        parts = callback.data.split("_")
        if len(parts) >= 4:
            _, _, uid, amt = parts
            user_id = int(uid)
            amount = float(amt)
        else:
            await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
            return
        
        logger.info(f"✅ موافقة على شحن: user={user_id}, amount={amount}")
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT username, balance FROM users WHERE user_id = $1", user_id)
            
            if not user:
                await conn.execute("INSERT INTO users (user_id, balance, created_at) VALUES ($1, 0, CURRENT_TIMESTAMP)", user_id)
                user = {'username': None, 'balance': 0}
            
            new_balance = user['balance'] + amount
            await conn.execute(
                "UPDATE users SET balance = $1, total_deposits = total_deposits + $2, last_activity = CURRENT_TIMESTAMP WHERE user_id = $3",
                new_balance, amount, user_id
            )
            
            await conn.execute('''
                UPDATE deposit_requests 
                SET status = 'approved', updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM deposit_requests 
                    WHERE user_id = $1 AND status = 'pending' AND amount_syp = $2
                    ORDER BY created_at DESC 
                    LIMIT 1
                )
            ''', user_id, amount)
        
        damascus_time = get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            await bot.send_message(
                user_id,
                f"✅ **تم تأكيد عملية الشحن بنجاح!**\n\n"
                f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
                f"💳 **الرصيد الحالي:** {new_balance:,.0f} ل.س\n"
                f"📅 **التاريخ:** {damascus_time}\n\n"
                f"🔸 **شكراً لاستخدامك خدماتنا**",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة للمستخدم {user_id}: {e}")
        
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text + f"\n\n✅ **تمت الموافقة على الطلب**\n📅 **بتاريخ:** {damascus_time}"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None)
        except Exception as e:
            logger.error(f"❌ فشل تحديث رسالة المجموعة: {e}")
        
        await callback.answer("✅ تمت الموافقة بنجاح")
        
    except Exception as e:
        logger.error(f"❌ خطأ عام في موافقة الشحن: {e}")
        import traceback
        traceback.print_exc()
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reje_dep_"))
async def reject_deposit_from_group(callback: types.CallbackQuery, bot: Bot, db_pool):
    """رفض طلب شحن من المجموعة"""
    try:
        logger.info(f"📩 استقبال رفض شحن: {callback.data}")
        user_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE deposit_requests 
                SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM deposit_requests 
                    WHERE user_id = $1 AND status = 'pending'
                    ORDER BY created_at DESC 
                    LIMIT 1
                )
            ''', user_id)
        
        damascus_time = get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            await bot.send_message(
                user_id,
                f"❌ **نعتذر، تم رفض طلب الشحن الخاص بك.**\n\n"
                f"📅 **تاريخ الرفض:** {damascus_time}\n"
                f"🔸 **الأسباب المحتملة:**\n"
                f"• بيانات التحويل غير صحيحة\n"
                f"• لم يتم العثور على التحويل\n"
                f"• المشكلة فنية\n\n"
                f"📞 **للمساعدة تواصل مع الدعم.**",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة الرفض للمستخدم {user_id}: {e}")
        
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text + f"\n\n❌ **تم رفض الطلب**\n📅 **بتاريخ:** {damascus_time}"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None)
        except Exception as e:
            logger.error(f"❌ فشل تحديث رسالة المجموعة: {e}")
        
        await callback.answer("❌ تم رفض الطلب")
        
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الشحن: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# ============= معالجة طلبات التطبيقات من المجموعة =============

@router.callback_query(F.data.startswith("appr_order_"))
async def approve_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """موافقة على طلب تطبيق من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.id = $1
            ''', order_id)
            
            if order:
                await conn.execute("UPDATE orders SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
                
                points = order['points_earned'] or 0
                
                try:
                    message_text = (
                        f"✅ تمت الموافقة على طلبك #{order_id}\n\n"
                        f"📱 التطبيق: {order['app_name']}\n"
                        f"📦 الكمية: {order['quantity']}\n"
                        f"🎯 المستهدف: {order['target_id']}\n"
                        f"⭐ نقاط مكتسبة: +{points}\n\n"
                        f"⏳ جاري تنفيذ طلبك عبر النظام..."
                    )
                    await bot.send_message(order['user_id'], message_text)
                except Exception as e:
                    logger.error(f"❌ فشل إرسال رسالة للمستخدم: {e}")
                
                builder = InlineKeyboardBuilder()
                builder.row(
                    types.InlineKeyboardButton(text="✅ تم التنفيذ", callback_data=f"compl_order_{order_id}"),
                    types.InlineKeyboardButton(text="❌ تعذر التنفيذ", callback_data=f"fail_order_{order_id}"),
                    width=2
                )
                
                new_text = callback.message.text + "\n\n🔄 **جاري التنفيذ...**"
                await callback.message.edit_text(new_text, reply_markup=builder.as_markup())
                
                await callback.answer("✅ تمت الموافقة على الطلب")
            else:
                await callback.answer("❌ الطلب غير موجود", show_alert=True)
                
    except Exception as e:
        logger.error(f"❌ خطأ في موافقة الطلب: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reje_order_"))
async def reject_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """رفض طلب تطبيق من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT user_id, total_amount_syp FROM orders WHERE id = $1", order_id)
            
            if order:
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", order['total_amount_syp'], order['user_id'])
                await conn.execute("UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
                
                try:
                    await bot.send_message(
                        order['user_id'],
                        f"❌ **تم رفض طلبك #{order_id}**\n\n"
                        f"💰 **تم إعادة:** {order['total_amount_syp']:,.0f} ل.س لرصيدك\n\n"
                        f"🔸 **الأسباب المحتملة:**\n"
                        "• مشكلة في معلومات الحساب المستهدف\n"
                        "• الخدمة غير متوفرة حالياً\n"
                        "• مشكلة فنية في النظام\n\n"
                        f"📞 **للمساعدة تواصل مع الدعم.**",
                        parse_mode="Markdown"
                    )
                except:
                    pass
                
                await callback.message.edit_text(
                    callback.message.text + "\n\n❌ **تم رفض الطلب وإعادة الرصيد**",
                    reply_markup=None
                )
            else:
                await callback.answer("الطلب غير موجود", show_alert=True)
                
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الطلب: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("compl_order_"))
async def complete_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """تأكيد تنفيذ الطلب من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.id = $1
            ''', order_id)
            
            if not order:
                await callback.answer("❌ الطلب غير موجود", show_alert=True)
                return
            
            from database import get_points_per_order
            points = await get_points_per_order(db_pool)
            
            await conn.execute("UPDATE orders SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
            
            await conn.execute(
                "UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2",
                points, order['user_id']
            )
            
            await conn.execute("UPDATE orders SET points_earned = $1 WHERE id = $2", points, order_id)
            
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ''', order['user_id'], points, 'order_completed', f'نقاط من طلب مكتمل #{order_id}')
            
            from database import update_user_vip
            vip_info = await update_user_vip(db_pool, order['user_id'])
            
            total_spent = await conn.fetchval('''
                SELECT COALESCE(SUM(total_amount_syp), 0) 
                FROM orders 
                WHERE user_id = $1 AND status = 'completed'
            ''', order['user_id'])
            
            if vip_info:
                vip_discount = vip_info.get('discount', 0)
                vip_level = vip_info.get('level', 0)
            else:
                vip_discount = 0
                vip_level = 0
                
            vip_icons = ["⚪", "🔵", "🟣", "🟡"]
            vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "⚪"
            
            user_points = await conn.fetchval("SELECT total_points FROM users WHERE user_id = $1", order['user_id']) or 0
            
            try:
                await bot.send_message(
                    order['user_id'],
                    f"✅ **تم تنفيذ طلبك #{order_id} بنجاح!**\n\n"
                    f"📱 التطبيق: {order['app_name']}\n"
                    f"⭐ نقاط مكتسبة: +{points}\n"
                    f"💰 رصيد النقاط الجديد: {user_points}\n"
                    f"👑 مستواك: {vip_icon} VIP {vip_level} (خصم {vip_discount}%)\n\n"
                    f"شكراً لاستخدامك خدماتنا"
                )
            except Exception as e:
                logger.error(f"❌ فشل إرسال رسالة للمستخدم: {e}")
            
            await callback.message.edit_text(
                callback.message.text.replace("🔄 **جاري التنفيذ...**", "") + "\n\n✅ **تم التنفيذ بنجاح**",
                reply_markup=None
            )
            
            await callback.answer("✅ تم تأكيد التنفيذ")
                
    except Exception as e:
        logger.error(f"❌ خطأ في تأكيد التنفيذ: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("fail_order_"))
async def fail_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """تعذر تنفيذ الطلب من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT user_id, total_amount_syp FROM orders WHERE id = $1", order_id)
            
            if order:
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", order['total_amount_syp'], order['user_id'])
                await conn.execute("UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
                
                try:
                    await bot.send_message(
                        order['user_id'],
                        f"❌ **تعذر تنفيذ طلبك #{order_id}**\n\n"
                        f"💰 تم إعادة {order['total_amount_syp']:,.0f} ل.س لرصيدك\n"
                        f"⭐ لم تتم إضافة نقاط لهذا الطلب\n\n"
                        f"نعتذر عن الإزعاج، يرجى المحاولة لاحقاً"
                    )
                except Exception as e:
                    logger.error(f"❌ فشل إرسال رسالة للمستخدم: {e}")
                
                await callback.message.edit_text(
                    callback.message.text.replace("🔄 **جاري التنفيذ...**", "") + "\n\n❌ **تعذر التنفيذ وتم إعادة الرصيد**",
                    reply_markup=None
                )
                
                await callback.answer("❌ تم تحديث حالة الطلب")
            else:
                await callback.answer("❌ الطلب غير موجود", show_alert=True)
                
    except Exception as e:
        logger.error(f"❌ خطأ في تعذر التنفيذ: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)
