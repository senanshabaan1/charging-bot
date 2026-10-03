# admin/group_handlers.py
from aiogram import Router, F, types, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import asyncio
from handlers.time_utils import get_damascus_time_now
from utils import get_formatted_damascus_time, format_amount
from database.cache_utils import invalidate_user_cache
from database.points import get_points_per_order
from database.vip import update_user_vip

logger = logging.getLogger(__name__)
router = Router(name="admin_group")

processing_orders = set()
processing_deposits = set()

# ============= معالجة طلبات التطبيقات من المجموعة =============
@router.callback_query(F.data.startswith("appr_order_"))
async def approve_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    order_id = int(callback.data.split("_")[2])
    
    if order_id in processing_orders:
        return await callback.answer("⚠️ الطلب قيد المعالجة بالفعل", show_alert=True)
    
    processing_orders.add(order_id)
    
    try:
        await callback.answer("✅ جاري معالجة الطلب...", show_alert=False)
        try:
            new_text = f"{callback.message.text}\n\n⏳ <b>جاري المعالجة...</b>"
            await callback.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")
        except Exception as e:
            logger.error(f"⚠️ فشل تحديث الرسالة: {e}")
        
        asyncio.create_task(process_order_approval(order_id, callback, db_pool, bot))
    except Exception as e:
        logger.error(f"❌ خطأ في موافقة الطلب: {e}")
        processing_orders.discard(order_id)

async def process_order_approval(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username, a.api_service_id
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                JOIN applications a ON o.app_id = a.id
                WHERE o.id = $1
            ''', order_id)
            
            if not order:
                await callback.message.answer("❌ الطلب غير موجود")
                processing_orders.discard(order_id)
                return
            
            await conn.execute("UPDATE orders SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
            await invalidate_user_cache(order['user_id'])
        
        # ✅ التصحيح الجذري هنا: الاستدعاء الجديد للدالة الموحدة
        if order['api_service_id']:
            from handlers.services import send_order_to_api
            success = await send_order_to_api(order_id, db_pool, bot)
            
            if success:
                await callback.message.edit_text(
                    f"{callback.message.text}\n\n✅ **تم إرسال الطلب إلى API المزوّد وتنفيذه بنجاح**",
                    reply_markup=None
                )
                return
        
        await notify_user_order_approved(bot, order)
        
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ تم التنفيذ", callback_data=f"compl_order_{order_id}"),
            types.InlineKeyboardButton(text="❌ تعذر التنفيذ", callback_data=f"fail_order_{order_id}"),
            width=2
        )
        
        await callback.message.edit_text(
            f"{callback.message.text}\n\n🔄 <b>الطلب قيد التنفيذ...</b>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة الطلب: {e}")
    finally:
        processing_orders.discard(order_id)

async def notify_user_order_approved(bot, order):
    try:
        points = order['points_earned'] or 0
        await bot.send_message(
            order['user_id'],
            f"✅ تمت الموافقة على طلبك #{order['id']}\n\n"
            f"📱 التطبيق: {order['app_name']}\n"
            f"📦 الكمية: {order['quantity']}\n"
            f"🎯 المستهدف: {order['target_id']}\n"
            f"⭐ نقاط مكتسبة: +{points}\n\n"
            f"⏳ جاري تنفيذ طلبك عبر النظام..."
        )
    except Exception as e:
        logger.error(f"❌ فشل إرسال إشعار للمستخدم {order['user_id']}: {e}")

# ============= معالجة طلبات الشحن من المجموعة =============
@router.callback_query(F.data.startswith("appr_dep_"))
async def approve_deposit_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        parts = callback.data.split("_")
        if len(parts) >= 4:
            user_id = int(parts[2])
            amount = float(parts[3])
        else:
            return await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
    except:
        return await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
    
    dep_key = f"{user_id}_{amount}"
    if dep_key in processing_deposits:
        return await callback.answer("⚠️ الطلب قيد المعالجة بالفعل", show_alert=True)
    
    processing_deposits.add(dep_key)
    
    try:
        await callback.answer("✅ جاري معالجة الطلب...", show_alert=False)
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text + "\n\n⏳ <b>جاري المعالجة...</b>"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None, parse_mode="HTML")
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None, parse_mode="HTML")
        except Exception as e:
            logger.error(f"⚠️ فشل تحديث الرسالة: {e}")
            
        asyncio.create_task(process_deposit_approval(user_id, amount, callback, db_pool, bot))
    except Exception as e:
        logger.error(f"❌ خطأ في موافقة الشحن: {e}")
        processing_deposits.discard(dep_key)

async def process_deposit_approval(user_id: int, amount: float, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT username, balance FROM users WHERE user_id = $1", user_id)
            if not user:
                await conn.execute("INSERT INTO users (user_id, balance, created_at) VALUES ($1, 0, CURRENT_TIMESTAMP)", user_id)
                user = {'username': None, 'balance': 0}
            
            new_balance = user['balance'] + amount
            await conn.execute("UPDATE users SET balance = $1, total_deposits = total_deposits + $2, last_activity = CURRENT_TIMESTAMP WHERE user_id = $3", new_balance, amount, user_id)
            await conn.execute('''
                UPDATE deposit_requests 
                SET status = 'approved', updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM deposit_requests 
                    WHERE user_id = $1 AND status = 'pending' AND amount_syp = $2
                    ORDER BY created_at DESC LIMIT 1
                )
            ''', user_id, amount)
            await invalidate_user_cache(user_id)
        
        damascus_time = get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')
        asyncio.create_task(notify_user_deposit_approved(bot, user_id, amount, new_balance, damascus_time))
        
        try:
            current_text = callback.message.text or callback.message.caption or ""
            clean_text = current_text.replace("⏳ <b>جاري المعالجة...</b>", "")
            new_text = f"{clean_text}\n\n✅ <b>تمت الموافقة على الطلب</b>\n📅 <b>بتاريخ:</b> {damascus_time}"
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None, parse_mode="HTML")
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None, parse_mode="HTML")
        except Exception as e:
            logger.error(f"❌ فشل تحديث رسالة المجموعة: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة موافقة الشحن: {e}")
    finally:
        processing_deposits.discard(f"{user_id}_{amount}")

async def notify_user_deposit_approved(bot: Bot, user_id: int, amount: float, new_balance: float, timestamp: str):
    try:
        await bot.send_message(
            user_id,
            f"✅ **تم تأكيد عملية الشحن بنجاح!**\n\n"
            f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
            f"💳 **الرصيد الحالي:** {new_balance:,.0f} ل.س\n"
            f"📅 **التاريخ:** {timestamp}\n\n"
            f"🔸 **شكراً لاستخدامك خدماتنا**",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ فشل إرسال رسالة للمستخدم {user_id}: {e}")

@router.callback_query(F.data.startswith("reje_dep_"))
async def reject_deposit_from_group(callback: types.CallbackQuery, bot: Bot, db_pool):
    try:
        user_id = int(callback.data.split("_")[2])
        await callback.answer("❌ جاري رفض الطلب...", show_alert=False)
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text + "\n\n⏳ <b>جاري الرفض...</b>"
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None, parse_mode="HTML")
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None, parse_mode="HTML")
        except Exception as e:
            pass
        asyncio.create_task(process_deposit_rejection(user_id, callback, db_pool, bot))
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

async def process_deposit_rejection(user_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE deposit_requests SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
                WHERE id = (SELECT id FROM deposit_requests WHERE user_id = $1 AND status = 'pending' ORDER BY created_at DESC LIMIT 1)
            ''', user_id)
        damascus_time = get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')
        asyncio.create_task(notify_user_deposit_rejected(bot, user_id, damascus_time))
        try:
            current_text = callback.message.text or callback.message.caption or ""
            clean_text = current_text.replace("⏳ <b>جاري الرفض...</b>", "")
            new_text = f"{clean_text}\n\n❌ <b>تم رفض الطلب</b>\n📅 <b>بتاريخ:</b> {damascus_time}"
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None, parse_mode="HTML")
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None, parse_mode="HTML")
        except Exception as e:
            pass
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة رفض الشحن: {e}")

async def notify_user_deposit_rejected(bot: Bot, user_id: int, timestamp: str):
    try:
        await bot.send_message(
            user_id,
            f"❌ نعتذر، تم رفض طلب الشحن الخاص بك.\n\n"
            f"📅 **تاريخ الرفض:** {timestamp}\n"
            f"🔸 **الأسباب المحتملة:**\n"
            f"• بيانات التحويل غير صحيحة\n"
            f"• لم يتم العثور على التحويل\n\n"
            f"📞 **للمساعدة تواصل مع الدعم.**",
            parse_mode="Markdown"
        )
    except Exception as e:
        pass

@router.callback_query(F.data.startswith("reje_order_"))
async def reject_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        order_id = int(callback.data.split("_")[2])
        await callback.answer("❌ جاري رفض الطلب...", show_alert=False)
        try:
            new_text = f"{callback.message.text}\n\n⏳ <b>جاري الرفض...</b>"
            await callback.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")
        except: pass
        asyncio.create_task(process_order_rejection(order_id, callback, db_pool, bot))
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

async def process_order_rejection(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT id, user_id, total_amount_syp FROM orders WHERE id = $1", order_id)
            if order:
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", order['total_amount_syp'], order['user_id'])
                await conn.execute("UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
                await invalidate_user_cache(order['user_id'])
                await notify_user_order_rejected(bot, order)
        
        clean_text = callback.message.text.replace("⏳ <b>جاري الرفض...</b>", "")
        await callback.message.edit_text(f"{clean_text}\n\n❌ <b>تم رفض الطلب وإعادة الرصيد</b>", reply_markup=None, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة رفض الطلب: {e}")

async def notify_user_order_rejected(bot, order):
    try:
        await bot.send_message(
            order['user_id'],
            f"❌ تم رفض طلبك #{order.get('id', '')}\n\n"
            f"💰 **تم إعادة:** {order['total_amount_syp']:,.0f} ل.س لرصيدك\n\n"
            f"📞 **للمساعدة تواصل مع الدعم.**",
            parse_mode="Markdown"
        )
    except: pass

@router.callback_query(F.data.startswith("compl_order_"))
async def complete_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        order_id = int(callback.data.split("_")[2])
        await callback.answer("✅ جاري تأكيد التنفيذ...", show_alert=False)
        asyncio.create_task(process_order_completion(order_id, callback, db_pool, bot))
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

async def process_order_completion(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT o.*, u.user_id, u.username FROM orders o JOIN users u ON o.user_id = u.user_id WHERE o.id = $1", order_id)
            if not order: return
            
            from database.points import get_points_per_order
            points = await get_points_per_order(db_pool)
            await conn.execute("UPDATE orders SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
            await conn.execute("UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2", points, order['user_id'])
            await conn.execute("UPDATE orders SET points_earned = $1 WHERE id = $2", points, order_id)
            await conn.execute("INSERT INTO points_history (user_id, points, action, description, created_at) VALUES ($1, $2, 'order_completed', $3, CURRENT_TIMESTAMP)", order['user_id'], points, f'نقاط من طلب مكتمل #{order_id}')
            
            from database.vip import update_user_vip
            vip_info = await update_user_vip(db_pool, order['user_id'])
            vip_discount = vip_info.get('discount', 0) if vip_info else 0
            vip_level = vip_info.get('level', 0) if vip_info else 0
            vip_icons = ["⚪", "🔵", "🟣", "🟡"]
            vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "⚪"
            user_points = await conn.fetchval("SELECT total_points FROM users WHERE user_id = $1", order['user_id']) or 0
            
            await invalidate_user_cache(order['user_id'])
            
        asyncio.create_task(notify_user_order_completed(bot, order, points, user_points, vip_icon, vip_level, vip_discount))
        clean_text = callback.message.text.replace("🔄 <b>جاري التنفيذ...</b>", "")
        await callback.message.edit_text(f"{clean_text}\n\n✅ <b>تم التنفيذ بنجاح</b>", reply_markup=None, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة تأكيد التنفيذ: {e}")

async def notify_user_order_completed(bot, order, points, user_points, vip_icon, vip_level, vip_discount):
    try:
        await bot.send_message(
            order['user_id'],
            f"✅ تم تنفيذ طلبك #{order['id']} بنجاح!\n\n"
            f"📱 التطبيق: {order['app_name']}\n"
            f"⭐ نقاط مكتسبة: +{points}\n"
            f"👑 مستواك: {vip_icon} VIP {vip_level} (خصم {vip_discount}%)\n"
        )
    except: pass

@router.callback_query(F.data.startswith("fail_order_"))
async def fail_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        order_id = int(callback.data.split("_")[2])
        await callback.answer("❌ جاري معالجة الفشل...", show_alert=False)
        try:
            clean_text = callback.message.text.replace("🔄 <b>جاري التنفيذ...</b>", "")
            await callback.message.edit_text(f"{clean_text}\n\n⏳ <b>جاري معالجة الفشل...</b>", reply_markup=None, parse_mode="HTML")
        except: pass
        asyncio.create_task(process_order_failure(order_id, callback, db_pool, bot))
    except Exception as e:
        pass

async def process_order_failure(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT id, user_id, total_amount_syp FROM orders WHERE id = $1", order_id)
            if order:
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", order['total_amount_syp'], order['user_id'])
                await conn.execute("UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
                await invalidate_user_cache(order['user_id'])
                await notify_user_order_failed(bot, order)
                
        clean_text = callback.message.text.replace("⏳ <b>جاري معالجة الفشل...</b>", "")
        await callback.message.edit_text(f"{clean_text}\n\n❌ <b>تعذر التنفيذ وتم إعادة الرصيد</b>", reply_markup=None, parse_mode="HTML")
    except Exception as e:
        pass

async def notify_user_order_failed(bot, order):
    try:
        await bot.send_message(
            order['user_id'],
            f"❌ تعذر تنفيذ طلبك #{order.get('id', '')}\n\n"
            f"💰 **تم إعادة المبلغ إلى رصيدك:** {order['total_amount_syp']:,.0f} ل.س\n\n"
            f"📞 **للمساعدة تواصل مع الدعم.**",
            parse_mode="Markdown"
        )
    except: pass
