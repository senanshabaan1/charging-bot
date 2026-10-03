# admin/group_handlers.py
from aiogram import Router, F, types, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import asyncio
from utils import get_formatted_damascus_time, format_amount
from handlers.time_utils import get_damascus_time_now
from database.cache_utils import invalidate_user_cache
from database.points import get_points_per_order
from database.vip import update_user_vip

logger = logging.getLogger(__name__)
router = Router(name="admin_group")

processing_orders = set()
processing_deposits = set()

@router.callback_query(F.data.startswith("appr_order_"))
async def approve_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    order_id = int(callback.data.split("_")[2])
    if order_id in processing_orders: return await callback.answer("⚠️ الطلب قيد المعالجة بالفعل", show_alert=True)
    processing_orders.add(order_id)
    try:
        await callback.answer("✅ جاري معالجة الطلب...", show_alert=False)
        try: await callback.message.edit_text(f"{callback.message.text}\n\n⏳ <b>جاري المعالجة...</b>", reply_markup=None, parse_mode="HTML")
        except: pass
        asyncio.create_task(process_order_approval(order_id, callback, db_pool, bot))
    except Exception as e:
        processing_orders.discard(order_id)

async def process_order_approval(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username, a.api_service_id
                FROM orders o JOIN users u ON o.user_id = u.user_id JOIN applications a ON o.app_id = a.id WHERE o.id = $1
            ''', order_id)
            if not order:
                await callback.message.answer("❌ الطلب غير موجود")
                processing_orders.discard(order_id)
                return
            await conn.execute("UPDATE orders SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
            await invalidate_user_cache(order['user_id'])
        
        # استدعاء دالة API الصحيحة
        if order['api_service_id']:
            from handlers.services import send_order_to_api
            if await send_order_to_api(order_id, db_pool, bot):
                return await callback.message.edit_text(f"{callback.message.text}\n\n✅ **تم إرسال الطلب إلى المزوّد وتنفيذه**", reply_markup=None)
        
        await bot.send_message(order['user_id'], f"✅ تمت الموافقة على طلبك #{order['id']}\n📱 التطبيق: {order['app_name']}\n🎯 المستهدف: {order['target_id']}\n⏳ جاري التنفيذ...")
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="✅ تم التنفيذ", callback_data=f"compl_order_{order_id}"), types.InlineKeyboardButton(text="❌ تعذر التنفيذ", callback_data=f"fail_order_{order_id}"))
        await callback.message.edit_text(f"{callback.message.text}\n\n🔄 <b>الطلب قيد التنفيذ...</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e: pass
    finally: processing_orders.discard(order_id)

@router.callback_query(F.data.startswith("appr_dep_"))
async def approve_deposit_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    parts = callback.data.split("_")
    user_id, amount = int(parts[2]), float(parts[3])
    dep_key = f"{user_id}_{amount}"
    if dep_key in processing_deposits: return await callback.answer("⚠️ قيد المعالجة", show_alert=True)
    processing_deposits.add(dep_key)
    try:
        await callback.answer("✅ جاري معالجة الطلب...", show_alert=False)
        try: await callback.message.edit_text(text=callback.message.text + "\n\n⏳ <b>جاري المعالجة...</b>", reply_markup=None, parse_mode="HTML")
        except: pass
        asyncio.create_task(process_deposit_approval(user_id, amount, callback, db_pool, bot))
    except: processing_deposits.discard(dep_key)

async def process_deposit_approval(user_id: int, amount: float, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT username, balance FROM users WHERE user_id = $1", user_id)
            if not user:
                await conn.execute("INSERT INTO users (user_id, balance) VALUES ($1, 0)", user_id)
                user = {'balance': 0}
            new_balance = user['balance'] + amount
            await conn.execute("UPDATE users SET balance = $1, total_deposits = total_deposits + $2 WHERE user_id = $3", new_balance, amount, user_id)
            await conn.execute("UPDATE deposit_requests SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = (SELECT id FROM deposit_requests WHERE user_id = $1 AND status = 'pending' AND amount_syp = $2 ORDER BY created_at DESC LIMIT 1)", user_id, amount)
            await invalidate_user_cache(user_id)
        damascus_time = get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')
        await bot.send_message(user_id, f"✅ **تم تأكيد الشحن!**\n💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n💳 **الرصيد:** {new_balance:,.0f} ل.س", parse_mode="Markdown")
        try: await callback.message.edit_text(text=callback.message.text.replace("⏳ <b>جاري المعالجة...</b>", "") + f"\n\n✅ <b>تمت الموافقة</b>\n📅 <b>{damascus_time}</b>", reply_markup=None, parse_mode="HTML")
        except: pass
    except: pass
    finally: processing_deposits.discard(f"{user_id}_{amount}")

@router.callback_query(F.data.startswith("reje_dep_"))
async def reject_deposit_from_group(callback: types.CallbackQuery, bot: Bot, db_pool):
    user_id = int(callback.data.split("_")[2])
    await callback.answer("❌ جاري الرفض...", show_alert=False)
    asyncio.create_task(process_deposit_rejection(user_id, callback, db_pool, bot))

async def process_deposit_rejection(user_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE deposit_requests SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = (SELECT id FROM deposit_requests WHERE user_id = $1 AND status = 'pending' ORDER BY created_at DESC LIMIT 1)", user_id)
        await bot.send_message(user_id, f"❌ نعتذر، تم رفض طلب الشحن الخاص بك.\n📞 تواصل مع الدعم.")
        try: await callback.message.edit_text(text=callback.message.text + "\n\n❌ <b>تم الرفض</b>", reply_markup=None, parse_mode="HTML")
        except: pass
    except: pass

@router.callback_query(F.data.startswith("reje_order_"))
async def reject_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    order_id = int(callback.data.split("_")[2])
    await callback.answer("❌ جاري الرفض...", show_alert=False)
    asyncio.create_task(process_order_rejection(order_id, callback, db_pool, bot))

async def process_order_rejection(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT id, user_id, total_amount_syp FROM orders WHERE id = $1", order_id)
            if order:
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", order['total_amount_syp'], order['user_id'])
                await conn.execute("UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
                await bot.send_message(order['user_id'], f"❌ تم رفض طلبك #{order_id}\n💰 **أُعيد:** {order['total_amount_syp']:,.0f} ل.س", parse_mode="Markdown")
        await callback.message.edit_text(f"{callback.message.text}\n\n❌ <b>تم الرفض وإعادة الرصيد</b>", reply_markup=None, parse_mode="HTML")
    except: pass

@router.callback_query(F.data.startswith("compl_order_"))
async def complete_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    order_id = int(callback.data.split("_")[2])
    await callback.answer("✅ جاري التأكيد...", show_alert=False)
    asyncio.create_task(process_order_completion(order_id, callback, db_pool, bot))

async def process_order_completion(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
            await conn.execute("UPDATE orders SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", order_id)
            await bot.send_message(order['user_id'], f"✅ تم تنفيذ طلبك #{order_id} بنجاح!")
        await callback.message.edit_text(f"{callback.message.text.replace('🔄 <b>الطلب قيد التنفيذ...</b>', '')}\n\n✅ <b>تم التنفيذ بنجاح</b>", reply_markup=None, parse_mode="HTML")
    except: pass

@router.callback_query(F.data.startswith("fail_order_"))
async def fail_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    order_id = int(callback.data.split("_")[2])
    await callback.answer("❌ جاري معالجة الفشل...", show_alert=False)
    asyncio.create_task(process_order_failure(order_id, callback, db_pool, bot))

async def process_order_failure(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT id, user_id, total_amount_syp FROM orders WHERE id = $1", order_id)
            if order:
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", order['total_amount_syp'], order['user_id'])
                await conn.execute("UPDATE orders SET status = 'failed' WHERE id = $1", order_id)
                await bot.send_message(order['user_id'], f"❌ تعذر تنفيذ طلبك #{order_id}\n💰 أُعيد رصيدك.")
        await callback.message.edit_text(f"{callback.message.text.replace('🔄 <b>الطلب قيد التنفيذ...</b>', '')}\n\n❌ <b>تعذر التنفيذ وتم إعادة الرصيد</b>", reply_markup=None, parse_mode="HTML")
    except: pass
