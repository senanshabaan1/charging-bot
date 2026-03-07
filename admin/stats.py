# admin/stats.py
from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from utils import is_admin, format_amount
from database import get_bot_stats, get_bot_status, get_exchange_rate

logger = logging.getLogger(__name__)
router = Router(name="admin_stats")

@router.callback_query(F.data == "bot_stats")
async def show_bot_stats(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    stats = await get_bot_stats(db_pool)
    bot_status = await get_bot_status(db_pool)
    current_rate = await get_exchange_rate(db_pool)
    
    if not stats:
        return await callback.answer("❌ خطأ في جلب الإحصائيات", show_alert=True)
    
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"
    
    # ✅ استخدم نص عادي بدون f-string
    stats_text = (
        "📊 **إحصائيات البوت**\n\n"
        f"🤖 **حالة البوت:** {status_text}\n\n"
        "👥 **المستخدمين:**\n"
        f"• 📈 الإجمالي: {stats['users'].get('total_users', 0)}\n"
        f"• 💰 إجمالي الأرصدة: {stats['users'].get('total_balance', 0):,.0f} ل.س\n"
        f"• 🚫 المحظورين: {stats['users'].get('banned_users', 0)}\n"
        f"• 🆕 الجدد اليوم: {stats['users'].get('new_users_today', 0)}\n"
        f"• ⭐ إجمالي النقاط: {stats['users'].get('total_points', 0)}\n\n"
        
        "💰 **الإيداعات:**\n"
        f"• 📋 الإجمالي: {stats['deposits'].get('total_deposits', 0)}\n"
        f"• 💸 إجمالي المبالغ: {stats['deposits'].get('total_deposit_amount', 0):,.0f} ل.س\n"
        f"• ⏳ المعلقة: {stats['deposits'].get('pending_deposits', 0)}\n"
        f"• ✅ المنجزة: {stats['deposits'].get('approved_deposits', 0)}\n"
        f"• ❌ المرفوضة: {stats['deposits'].get('rejected_deposits', 0)}\n\n"
        
        "🛒 **الطلبات:**\n"
        f"• 📋 الإجمالي: {stats['orders'].get('total_orders', 0)}\n"
        f"• 💰 إجمالي المبالغ: {stats['orders'].get('total_completed_amount', 0):,.0f} ل.س\n"
        f"• ⏳ المعلقة: {stats['orders'].get('pending_orders', 0)}\n"
        f"• 🔄 قيد التنفيذ: {stats['orders'].get('processing_orders', 0)}\n"
        f"• ✅ المكتملة: {stats['orders'].get('completed_orders', 0)}\n"
        f"• ❌ الفاشلة: {stats['orders'].get('failed_orders', 0)}\n"
        f"• ⭐ نقاط ممنوحة: {stats['orders'].get('total_points_given', 0)}\n\n"
        
        "🎁 **نظام النقاط:**\n"
        f"• 💰 عمليات استرداد: {stats['points'].get('total_redemptions', 0)}\n"
        f"• ⭐ نقاط مستردة: {stats['points'].get('total_points_redeemed', 0)}\n"
        f"• 💵 قيمة المستردة: {stats['points'].get('total_redemption_amount', 0):,.0f} ل.س\n\n"
        
        f"💵 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n"
    )
    
    await callback.message.answer(stats_text, parse_mode="Markdown")

# أكثر المستخدمين إيداعاً
@router.callback_query(F.data == "top_deposits")
async def show_top_deposits(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_deposits
    users = await get_top_users_by_deposits(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "💳 **أكثر المستخدمين إيداعاً**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{i}. {username}\n   💰 {user['total_deposits']:,.0f} ل.س\n"
    
    try:
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطأ في تنسيق Markdown: {e}")
        plain_text = text.replace('**', '').replace('*', '').replace('`', '')
        await callback.message.answer(plain_text)

# أكثر المستخدمين طلبات
@router.callback_query(F.data == "top_orders")
async def show_top_orders(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_orders
    users = await get_top_users_by_orders(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "🛒 **أكثر المستخدمين طلبات**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{i}. {username}\n   📦 {user['total_orders']} طلب\n"
    
    try:
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطأ في تنسيق Markdown: {e}")
        plain_text = text.replace('**', '').replace('*', '').replace('`', '')
        await callback.message.answer(plain_text)

# أكثر المستخدمين إحالة
@router.callback_query(F.data == "top_referrals")
async def show_top_referrals(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_referrals
    users = await get_top_users_by_referrals(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "🔗 **أكثر المستخدمين إحالة**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{i}. {username}\n   👥 {user['referral_count']} إحالة | 💰 {user['referral_earnings']:,.0f} ل.س\n"
    
    try:
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطأ في تنسيق Markdown: {e}")
        plain_text = text.replace('**', '').replace('*', '').replace('`', '')
        await callback.message.answer(plain_text)

# أكثر المستخدمين نقاط
@router.callback_query(F.data == "top_points")
async def show_top_points(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_points
    users = await get_top_users_by_points(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "⭐ **أكثر المستخدمين نقاط**\n\n"
    
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{i}. {username}\n   ⭐ {user['total_points']} نقطة\n"
    
    try:
        await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطأ في تنسيق Markdown: {e}")
        plain_text = text.replace('**', '').replace('*', '').replace('`', '')
        await callback.message.answer(plain_text)

# إحصائيات VIP
@router.callback_query(F.data == "vip_stats")
async def show_vip_stats(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        vip_counts = await conn.fetch("SELECT vip_level, COUNT(*) as count FROM users GROUP BY vip_level ORDER BY vip_level")
        vip_spent = await conn.fetch("SELECT vip_level, SUM(total_spent) as total FROM users WHERE vip_level > 0 GROUP BY vip_level ORDER BY vip_level")
    
    vip_names = ["VIP 0 ⚪", "VIP 1 🔵", "VIP 2 🟣", "VIP 3 🟡"]
    text = "👥 **إحصائيات VIP**\n\n**عدد المستخدمين:**\n"
    
    for row in vip_counts:
        level = row['vip_level']
        if level <= 5:
            text += f"• {vip_names[level]}: {row['count']} مستخدم\n"
    
    if vip_spent:
        text += "\n**إجمالي الإنفاق:**\n"
        for row in vip_spent:
            level = row['vip_level']
            if level <= 5:
                text += f"• {vip_names[level]}: {row['total']:,.0f} ل.س\n"
    
    await callback.message.answer(text, parse_mode="Markdown")
