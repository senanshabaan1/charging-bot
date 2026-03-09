# admin/stats.py
from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from utils import is_admin, format_amount, safe_edit_message, get_formatted_damascus_time
from database.stats import get_bot_stats
from database.core import get_bot_status, get_exchange_rate
from cache import cached, clear_cache  # ✅ استيراد الكاش

logger = logging.getLogger(__name__)
router = Router(name="admin_stats")

# ✅ ثوابت للأداء
CACHE_TTL_STATS = 60  # 60 ثانية
CACHE_TTL_TOP_USERS = 120  # دقيقتين
TOP_USERS_LIMIT = 15

# ✅ كاش للإحصائيات العامة
@cached(ttl=CACHE_TTL_STATS, key_prefix="bot_stats")
async def get_cached_bot_stats(db_pool) -> Optional[Dict[str, Any]]:
    """جلب إحصائيات البوت مع كاش دقيقة"""
    return await get_bot_stats(db_pool)

# ✅ كاش لأكثر المستخدمين إيداعاً
@cached(ttl=CACHE_TTL_TOP_USERS, key_prefix="top_deposits")
async def get_cached_top_deposits(db_pool, limit: int = TOP_USERS_LIMIT):
    """جلب أكثر المستخدمين إيداعاً مع كاش دقيقتين"""
    from database import get_top_users_by_deposits
    return await get_top_users_by_deposits(db_pool, limit)

# ✅ كاش لأكثر المستخدمين طلبات
@cached(ttl=CACHE_TTL_TOP_USERS, key_prefix="top_orders")
async def get_cached_top_orders(db_pool, limit: int = TOP_USERS_LIMIT):
    """جلب أكثر المستخدمين طلبات مع كاش دقيقتين"""
    from database import get_top_users_by_orders
    return await get_top_users_by_orders(db_pool, limit)

# ✅ كاش لأكثر المستخدمين إحالة
@cached(ttl=CACHE_TTL_TOP_USERS, key_prefix="top_referrals")
async def get_cached_top_referrals(db_pool, limit: int = TOP_USERS_LIMIT):
    """جلب أكثر المستخدمين إحالة مع كاش دقيقتين"""
    from database import get_top_users_by_referrals
    return await get_top_users_by_referrals(db_pool, limit)

# ✅ كاش لأكثر المستخدمين نقاط
@cached(ttl=CACHE_TTL_TOP_USERS, key_prefix="top_points")
async def get_cached_top_points(db_pool, limit: int = TOP_USERS_LIMIT):
    """جلب أكثر المستخدمين نقاط مع كاش دقيقتين"""
    from database import get_top_users_by_points
    return await get_top_users_by_points(db_pool, limit)

# ✅ كاش لإحصائيات VIP
@cached(ttl=CACHE_TTL_STATS, key_prefix="vip_stats")
async def get_cached_vip_stats(db_pool) -> Dict[str, Any]:
    """جلب إحصائيات VIP مع كاش دقيقة"""
    async with db_pool.acquire() as conn:
        vip_counts = await conn.fetch("SELECT vip_level, COUNT(*) as count FROM users GROUP BY vip_level ORDER BY vip_level")
        vip_spent = await conn.fetch("SELECT vip_level, SUM(total_spent) as total FROM users WHERE vip_level > 0 GROUP BY vip_level ORDER BY vip_level")
        
        return {
            'counts': vip_counts,
            'spent': vip_spent
        }

@router.callback_query(F.data == "bot_stats")
async def show_bot_stats(callback: types.CallbackQuery, db_pool):
    """عرض إحصائيات البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    start_time = time.time()
    
    # ✅ استخدام الكاش
    stats = await get_cached_bot_stats(db_pool)
    bot_status = await get_bot_status(db_pool)
    current_rate = await get_exchange_rate(db_pool)
    
    if not stats:
        return await callback.answer("❌ خطأ في جلب الإحصائيات", show_alert=True)
    
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"
    
    # حساب النسب المئوية
    total_users = stats['users'].get('total_users', 0)
    banned_users = stats['users'].get('banned_users', 0)
    active_users = total_users - banned_users
    
    # إحصائيات إضافية
    completion_rate = 0
    if stats['orders'].get('total_orders', 0) > 0:
        completion_rate = (stats['orders'].get('completed_orders', 0) / stats['orders'].get('total_orders', 0)) * 100
    
    stats_text = (
        f"📊 **إحصائيات البوت**\n\n"
        f"🤖 **حالة البوت:** {status_text}\n"
        f"🕐 **آخر تحديث:** {get_formatted_damascus_time()}\n\n"
        
        f"👥 **المستخدمين:**\n"
        f"• 📈 الإجمالي: {total_users}\n"
        f"• ✅ النشطين: {active_users}\n"
        f"• 🚫 المحظورين: {banned_users}\n"
        f"• 🆕 الجدد اليوم: {stats['users'].get('new_users_today', 0)}\n"
        f"• 💰 إجمالي الأرصدة: {stats['users'].get('total_balance', 0):,.0f} ل.س\n"
        f"• ⭐ إجمالي النقاط: {stats['users'].get('total_points', 0)}\n\n"
        
        f"💰 **الإيداعات:**\n"
        f"• 📋 الإجمالي: {stats['deposits'].get('total_deposits', 0)}\n"
        f"• 💸 إجمالي المبالغ: {stats['deposits'].get('total_deposit_amount', 0):,.0f} ل.س\n"
        f"• ⏳ المعلقة: {stats['deposits'].get('pending_deposits', 0)}\n"
        f"• ✅ المنجزة: {stats['deposits'].get('approved_deposits', 0)}\n"
        f"• ❌ المرفوضة: {stats['deposits'].get('rejected_deposits', 0)}\n\n"
        
        f"🛒 **الطلبات:**\n"
        f"• 📋 الإجمالي: {stats['orders'].get('total_orders', 0)}\n"
        f"• 💰 إجمالي المبالغ: {stats['orders'].get('total_completed_amount', 0):,.0f} ل.س\n"
        f"• ⏳ المعلقة: {stats['orders'].get('pending_orders', 0)}\n"
        f"• 🔄 قيد التنفيذ: {stats['orders'].get('processing_orders', 0)}\n"
        f"• ✅ المكتملة: {stats['orders'].get('completed_orders', 0)}\n"
        f"• ❌ الفاشلة: {stats['orders'].get('failed_orders', 0)}\n"
        f"• 📊 نسبة الإنجاز: {completion_rate:.1f}%\n"
        f"• ⭐ نقاط ممنوحة: {stats['orders'].get('total_points_given', 0)}\n\n"
        
        f"🎁 **نظام النقاط:**\n"
        f"• 💰 عمليات استرداد: {stats['points'].get('total_redemptions', 0)}\n"
        f"• ⭐ نقاط مستردة: {stats['points'].get('total_points_redeemed', 0)}\n"
        f"• 💵 قيمة المستردة: {stats['points'].get('total_redemption_amount', 0):,.0f} ل.س\n\n"
        
        f"💵 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n"
        f"⚡ وقت التحميل: {time.time() - start_time:.2f} ثانية"
    )
    
    # إضافة أزرار التنقل
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔄 تحديث", callback_data="refresh_stats"),
        types.InlineKeyboardButton(text="📊 تفاصيل", callback_data="stats_details")
    ) 
    builder.row(
        types.InlineKeyboardButton(text="💳 الأكثر إيداعاً", callback_data="top_deposits"),
        types.InlineKeyboardButton(text="🛒 الأكثر طلبات", callback_data="top_orders")
   )     
    builder.row(    
        types.InlineKeyboardButton(text="🔗 الأكثر إحالة", callback_data="top_referrals"),
        types.InlineKeyboardButton(text="⭐ الأكثر نقاط", callback_data="top_points")
   )  
   builder.row(
        types.InlineKeyboardButton(text="👥 إحصائيات VIP", callback_data="vip_stats")
   )
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await safe_edit_message(callback.message, stats_text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "refresh_stats")
async def refresh_stats(callback: types.CallbackQuery, db_pool):
    """تحديث الإحصائيات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer("🔄 جاري التحديث...")
    
    # ✅ مسح الكاش
    clear_cache("bot_stats")
    clear_cache("vip_stats")
    
    # ✅ العودة للإحصائيات
    await show_bot_stats(callback, db_pool)

@router.callback_query(F.data == "stats_details")
async def stats_details(callback: types.CallbackQuery, db_pool):
    """عرض تفاصيل إضافية"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        # إحصائيات اليوم
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        today_stats = await conn.fetchrow('''
            SELECT 
                (SELECT COUNT(*) FROM users WHERE DATE(created_at) = $1) as new_users,
                (SELECT COUNT(*) FROM deposit_requests WHERE DATE(created_at) = $1) as deposits,
                (SELECT COALESCE(SUM(amount_syp), 0) FROM deposit_requests WHERE DATE(created_at) = $1 AND status = 'approved') as deposit_amount,
                (SELECT COUNT(*) FROM orders WHERE DATE(created_at) = $1) as orders,
                (SELECT COALESCE(SUM(total_amount_syp), 0) FROM orders WHERE DATE(created_at) = $1 AND status = 'completed') as order_amount
        ''', today)
        
        # إحصائيات الأمس للمقارنة
        yesterday_stats = await conn.fetchrow('''
            SELECT 
                (SELECT COUNT(*) FROM users WHERE DATE(created_at) = $1) as new_users,
                (SELECT COUNT(*) FROM deposit_requests WHERE DATE(created_at) = $1) as deposits
        ''', yesterday)
        
        # أكثر التطبيقات طلباً
        top_apps = await conn.fetch('''
            SELECT a.name, COUNT(o.id) as order_count, COALESCE(SUM(o.total_amount_syp), 0) as total_revenue
            FROM applications a
            LEFT JOIN orders o ON a.id = o.app_id AND o.status = 'completed'
            GROUP BY a.id, a.name
            ORDER BY order_count DESC
            LIMIT 5
        ''')
    
    # حساب نسبة التغير
    users_change = 0
    if yesterday_stats and yesterday_stats['new_users'] > 0:
        users_change = ((today_stats['new_users'] - yesterday_stats['new_users']) / yesterday_stats['new_users']) * 100
    
    # بناء النص الجديد
    new_text = (
        f"📈 **تفاصيل إضافية**\n\n"
        f"**إحصائيات اليوم ({today.strftime('%Y-%m-%d')}):**\n"
        f"• 👤 مستخدمين جدد: {today_stats['new_users']} "
        f"({'📈+' if users_change > 0 else '📉'}{users_change:.1f}%)\n"
        f"• 💰 إيداعات: {today_stats['deposits']} عملية\n"
        f"• 💵 قيمة الإيداعات: {today_stats['deposit_amount']:,.0f} ل.س\n"
        f"• 📦 طلبات: {today_stats['orders']} طلب\n"
        f"• 💳 قيمة الطلبات: {today_stats['order_amount']:,.0f} ل.س\n\n"
        
        f"🏆 **أكثر التطبيقات طلباً:**\n"
    )
    
    for i, app in enumerate(top_apps, 1):
        new_text += f"{i}. {app['name']}: {app['order_count']} طلب ({app['total_revenue']:,.0f} ل.س)\n"
    
    # ✅ التحقق من أن النص تغير قبل التعديل
    current_text = callback.message.text or callback.message.caption or ""
    
    if current_text == new_text:
        # النص نفسه، نرسل إشعار صغير فقط
        await callback.answer("✅ البيانات محدثة بالفعل", show_alert=False)
        return
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔄 تحديث", callback_data="stats_details"),
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="bot_stats")
    )
    
    await safe_edit_message(callback.message, new_text, reply_markup=builder.as_markup())

# أكثر المستخدمين إيداعاً
@router.callback_query(F.data == "top_deposits")
async def show_top_deposits(callback: types.CallbackQuery, db_pool):
    """أكثر المستخدمين إيداعاً"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    users = await get_cached_top_deposits(db_pool, TOP_USERS_LIMIT)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "💳 **أكثر المستخدمين إيداعاً**\n\n"
    total_all = sum(user['total_deposits'] for user in users)
    
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        percentage = (user['total_deposits'] / total_all * 100) if total_all > 0 else 0
        text += f"{i}. {username}\n"
        text += f"   💰 {user['total_deposits']:,.0f} ل.س ({percentage:.1f}%)\n"
    
    text += f"\n📊 إجمالي الإيداعات: {total_all:,.0f} ل.س"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 تحديث", callback_data="refresh_top_deposits"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="bot_stats"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "refresh_top_deposits")
async def refresh_top_deposits(callback: types.CallbackQuery, db_pool):
    """تحديث قائمة أكثر المستخدمين إيداعاً"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer("🔄 جاري التحديث...")
    
    clear_cache("top_deposits")
    await show_top_deposits(callback, db_pool)

# أكثر المستخدمين طلبات
@router.callback_query(F.data == "top_orders")
async def show_top_orders(callback: types.CallbackQuery, db_pool):
    """أكثر المستخدمين طلبات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    users = await get_cached_top_orders(db_pool, TOP_USERS_LIMIT)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "🛒 **أكثر المستخدمين طلبات**\n\n"
    
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{i}. {username}\n   📦 {user['total_orders']} طلب\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 تحديث", callback_data="refresh_top_orders"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="bot_stats"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "refresh_top_orders")
async def refresh_top_orders(callback: types.CallbackQuery, db_pool):
    """تحديث قائمة أكثر المستخدمين طلبات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer("🔄 جاري التحديث...")
    
    clear_cache("top_orders")
    await show_top_orders(callback, db_pool)

# أكثر المستخدمين إحالة
@router.callback_query(F.data == "top_referrals")
async def show_top_referrals(callback: types.CallbackQuery, db_pool):
    """أكثر المستخدمين إحالة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    users = await get_cached_top_referrals(db_pool, TOP_USERS_LIMIT)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "🔗 **أكثر المستخدمين إحالة**\n\n"
    
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{i}. {username}\n"
        text += f"   👥 {user['referral_count']} إحالة | 💰 {user['referral_earnings']:,.0f} ل.س\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 تحديث", callback_data="refresh_top_referrals"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="bot_stats"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "refresh_top_referrals")
async def refresh_top_referrals(callback: types.CallbackQuery, db_pool):
    """تحديث قائمة أكثر المستخدمين إحالة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer("🔄 جاري التحديث...")
    
    clear_cache("top_referrals")
    await show_top_referrals(callback, db_pool)

# أكثر المستخدمين نقاط
@router.callback_query(F.data == "top_points")
async def show_top_points(callback: types.CallbackQuery, db_pool):
    """أكثر المستخدمين نقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    users = await get_cached_top_points(db_pool, TOP_USERS_LIMIT)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "⭐ **أكثر المستخدمين نقاط**\n\n"
    
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        text += f"{i}. {username}\n   ⭐ {user['total_points']} نقطة\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 تحديث", callback_data="refresh_top_points"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="bot_stats"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "refresh_top_points")
async def refresh_top_points(callback: types.CallbackQuery, db_pool):
    """تحديث قائمة أكثر المستخدمين نقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer("🔄 جاري التحديث...")
    
    clear_cache("top_points")
    await show_top_points(callback, db_pool)

# إحصائيات VIP
@router.callback_query(F.data == "vip_stats")
async def show_vip_stats(callback: types.CallbackQuery, db_pool):
    """إحصائيات VIP"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    vip_data = await get_cached_vip_stats(db_pool)
    vip_counts = vip_data['counts']
    vip_spent = vip_data['spent']
    
    vip_names = ["VIP 0 ⚪", "VIP 1 🔵", "VIP 2 🟣", "VIP 3 🟡"]
    total_users = sum(row['count'] for row in vip_counts)
    
    text = "👥 **إحصائيات VIP**\n\n"
    text += f"إجمالي المستخدمين: {total_users}\n\n"
    text += "**عدد المستخدمين:**\n"
    
    # إنشاء قاموس للعد
    counts_dict = {row['vip_level']: row['count'] for row in vip_counts}
    
    for level in range(4):
        count = counts_dict.get(level, 0)
        percentage = (count / total_users * 100) if total_users > 0 else 0
        text += f"• {vip_names[level]}: {count} مستخدم ({percentage:.1f}%)\n"
    
    if vip_spent:
        text += "\n**إجمالي الإنفاق:**\n"
        spent_dict = {row['vip_level']: row['total'] for row in vip_spent}
        total_spent = sum(row['total'] for row in vip_spent) if vip_spent else 0
        
        for level in range(1, 4):
            spent = spent_dict.get(level, 0)
            percentage = (spent / total_spent * 100) if total_spent > 0 else 0
            text += f"• {vip_names[level]}: {spent:,.0f} ل.س ({percentage:.1f}%)\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 تحديث", callback_data="refresh_vip_stats"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="bot_stats"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "refresh_vip_stats")
async def refresh_vip_stats(callback: types.CallbackQuery, db_pool):
    """تحديث إحصائيات VIP"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer("🔄 جاري التحديث...")
    
    clear_cache("vip_stats")
    await show_vip_stats(callback, db_pool)

# قائمة الإحصائيات الرئيسية
@router.callback_query(F.data == "stats_menu")
async def stats_menu(callback: types.CallbackQuery):
    """قائمة الإحصائيات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    text = (
        "📊 **قائمة الإحصائيات**\n\n"
        "اختر نوع الإحصائيات التي تريد عرضها:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📈 عامة", callback_data="bot_stats"),
        types.InlineKeyboardButton(text="💳 إيداعات", callback_data="top_deposits")
    )
    builder.row(
        types.InlineKeyboardButton(text="🛒 طلبات", callback_data="top_orders"),
        types.InlineKeyboardButton(text="🔗 إحالات", callback_data="top_referrals")
    )
    builder.row(
        types.InlineKeyboardButton(text="⭐ نقاط", callback_data="top_points"),
        types.InlineKeyboardButton(text="👑 VIP", callback_data="vip_stats")
    )
    builder.row(
        types.InlineKeyboardButton(text="📊 تفاصيل اليوم", callback_data="stats_details")
    )
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())
