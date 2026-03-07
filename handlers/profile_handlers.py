# handlers/profile_handlers.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from handlers.time_utils import get_damascus_time_now
from handlers.keyboards import get_main_menu_keyboard
from database import (
    get_redemption_rate, get_exchange_rate, get_next_vip_level,
    generate_referral_code, create_redemption_request
)
from utils import is_admin

logger = logging.getLogger(__name__)
router = Router(name="profile")

# ========== الملف الشخصي ==========
# handlers/profile_handlers.py - دالة my_account كاملة مع HTML

@router.message(F.text == "👤 حسابي")
async def my_account(message: types.Message, db_pool):
    """عرض الملف الشخصي مع أزرار النقاط وسجل العمليات وتفاصيل VIP"""
    user_id = message.from_user.id
    
    async with db_pool.acquire() as conn:
        try:
            user_data = await conn.fetchrow(
                "SELECT is_banned, balance, total_points, referral_code, username, first_name, vip_level, discount_percent, total_spent FROM users WHERE user_id = $1",
                user_id
            )
            if user_data and user_data['is_banned']:
                return await message.answer("🚫 حسابك محظور من استخدام البوت.")
            
            balance = user_data['balance'] if user_data else 0
            points = user_data['total_points'] if user_data else 0
            referral_code = user_data['referral_code'] if user_data else None
            username = user_data['username'] if user_data else None
            first_name = user_data['first_name'] if user_data else None
            vip_level = user_data['vip_level'] if user_data else 0
            vip_discount = user_data['discount_percent'] if user_data else 0
            total_spent = user_data['total_spent'] if user_data else 0
            
            # حساب إجمالي المشتريات من الطلبات المكتملة
            total_spent_from_orders = await conn.fetchval('''
                SELECT COALESCE(SUM(total_amount_syp), 0) 
                FROM orders 
                WHERE user_id = $1 AND status = 'completed'
            ''', user_id) or 0
            
            # تحديث total_spent إذا كان مختلفاً
            if total_spent != total_spent_from_orders:
                await conn.execute(
                    "UPDATE users SET total_spent = $1 WHERE user_id = $2",
                    total_spent_from_orders, user_id
                )
                total_spent = total_spent_from_orders
            
            # جلب إحصائيات النقاط
            points_from_referrals = await conn.fetchval(
                "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND action = 'referral'",
                user_id
            ) or 0
            
            points_from_orders = await conn.fetchval(
                "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND action = 'order_completed'",
                user_id
            ) or 0
            
            # جلب إحصائيات العمليات
            deposits_count = await conn.fetchval(
                "SELECT COUNT(*) FROM deposit_requests WHERE user_id = $1 AND status = 'approved'",
                user_id
            ) or 0
            
            orders_count = await conn.fetchval(
                "SELECT COUNT(*) FROM orders WHERE user_id = $1 AND status = 'completed'",
                user_id
            ) or 0
            
        except Exception as e:
            logger.error(f"خطأ في جلب بيانات المستخدم {user_id}: {e}")
            balance = 0
            points = 0
            referral_code = None
            username = None
            first_name = None
            vip_level = 0
            vip_discount = 0
            total_spent = 0
            points_from_referrals = 0
            points_from_orders = 0
            deposits_count = 0
            orders_count = 0
    
    # حساب قيمة النقاط بالسعر الحالي
    redemption_rate = await get_redemption_rate(db_pool)
    exchange_rate = await get_exchange_rate(db_pool)
    
    # قيمة النقاط
    points_value_usd = (points / redemption_rate) if redemption_rate > 0 else 0
    points_value_syp = points_value_usd * exchange_rate
    
    # قيمة 1 دولار بالليرة
    base_syp = 1 * exchange_rate
    
    # تحديد أيقونة VIP
    vip_icons = ["⚪", "🔵", "🟣", "🟡"]
    vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "⚪"

    # حساب التقدم للمستوى التالي
    next_level_info = get_next_vip_level(total_spent)
    
    if next_level_info and next_level_info.get('remaining', 0) > 0:
        remaining = next_level_info['remaining']
        next_level_name = next_level_info['next_level_name']
        progress_text = f"📊 {remaining:,.0f} ل.س للمستوى {next_level_name}"
    else:
        progress_text = "✨ وصلت لأعلى مستوى! (VIP 3)"
    
    # إنشاء أزرار إنلاين
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="show_referral"),
        types.InlineKeyboardButton(text="⭐ رصيد النقاط", callback_data="show_points_balance")
    )
    builder.row(
        types.InlineKeyboardButton(text="📊 سجل العمليات", callback_data="transactions_history"),
        types.InlineKeyboardButton(text="💰 استرداد نقاط", callback_data="redeem_points_menu")
    )
    
    # رسالة الملف الشخصي مع تفاصيل VIP - بصيغة HTML
    profile_text = (
        f"👤 <b>الملف الشخصي</b>\n\n"
        f"🆔 <b>الآيدي:</b> <code>{user_id}</code>\n"
        f"👤 <b>الاسم:</b> {first_name or message.from_user.full_name}\n"
        f"📅 <b>اليوزر:</b> @{username or message.from_user.username or 'غير متوفر'}\n"
        f"💰 <b>الرصيد:</b> {balance:,.0f} ل.س\n"
        f"⭐ <b>نقاطك:</b> {points}\n"
        f"💵 <b>قيمة نقاطك:</b> {points_value_syp:.0f} ل.س\n\n"
        f"📊 <b>تفاصيل النقاط:</b>\n"
        f"• من الإحالات: {points_from_referrals} نقطة\n"
        f"• من المشتريات: {points_from_orders} نقطة\n\n"
        f"📋 <b>سجل العمليات:</b>\n"
        f"• عدد عمليات الشحن: {deposits_count}\n"
        f"• عدد عمليات الشراء: {orders_count}\n\n"
        f"👑 <b>نظام VIP:</b>\n"
        f"• مستواك: {vip_icon} VIP {vip_level}\n"
        f"• خصمك الحالي: {vip_discount}%\n"
        f"• إجمالي مشترياتك: {total_spent:,.0f} ل.س\n"
        f"{progress_text}\n\n"
        f"💱 <b>سعر الصرف:</b> {exchange_rate:.0f} ل.س = 1$\n"
        f"🎁 <b>كل {redemption_rate} نقطة = 1$</b> ({base_syp:.0f} ل.س)\n\n"
        f"🔹 <b>اختر من الأزرار أدناه:</b>"
    )
    
    await message.answer(
        profile_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"  # ✅ تغيير إلى HTML
    )
# ========== رابط الإحالة ==========
@router.callback_query(F.data == "show_referral")
async def show_referral_button(callback: types.CallbackQuery, db_pool):
    """عرض رابط الإحالة مع سعر الصرف الحالي"""
    exchange_rate = await get_exchange_rate(db_pool)
    
    async with db_pool.acquire() as conn:
        try:
            code = await conn.fetchval(
                "SELECT referral_code FROM users WHERE user_id = $1",
                callback.from_user.id
            )
        except:
            code = None
    
    if not code:
        code = await generate_referral_code(db_pool, callback.from_user.id)
    
    bot_username = (await callback.bot.me()).username
    link = f"https://t.me/{bot_username}?start={code}"
    
    async with db_pool.acquire() as conn:
        referrals_count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE referred_by = $1",
            callback.from_user.id
        ) or 0
        
        try:
            points_from_referrals = await conn.fetchval(
                "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND action = 'referral'",
                callback.from_user.id
            ) or 0
        except:
            points_from_referrals = 0
    
    base_syp = 1 * exchange_rate
    
    text = (
        f"🔗 رابط الإحالة الخاص بك\n\n"
        f"{link}\n\n"
        f"📊 إحصائيات الإحالة:\n"
        f"• عدد المحالين: {referrals_count}\n"
        f"• النقاط المكتسبة: {points_from_referrals}\n\n"
        f"🎁 مميزات الإحالة:\n"
        f"• 1 نقطة لكل مشترك جديد\n"
        f"• كل 100 نقطة = 1$ ({base_syp:.0f} ل.س)\n"
        f"💰 **سعر الصرف الحالي:** {exchange_rate:.0f} ل.س = 1$\n\n"
        f"شارك الرابط مع أصدقائك!"
    )
    
    await callback.message.edit_text(text)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للحساب", callback_data="back_to_account"))
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

# ========== قائمة استرداد النقاط ==========
@router.callback_query(F.data == "redeem_points_menu")
async def redeem_points_menu(callback: types.CallbackQuery, db_pool):
    """قائمة استرداد النقاط"""
    async with db_pool.acquire() as conn:
        points = await conn.fetchval(
            "SELECT total_points FROM users WHERE user_id = $1",
            callback.from_user.id
        ) or 0
        
        redemption_rate = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = 'redemption_rate'"
        ) or '100'
        redemption_rate = int(redemption_rate)
        
        exchange_rate = await get_exchange_rate(db_pool)
    
    if points < redemption_rate:
        return await callback.answer(
            f"تحتاج {redemption_rate} نقطة على الأقل للاسترداد.\nلديك {points} نقطة فقط.", 
            show_alert=True
        )
    
    base_syp = 1 * exchange_rate
    max_redemptions = min(points // redemption_rate, 20)
    
    builder = InlineKeyboardBuilder()
    for i in range(1, max_redemptions + 1):
        points_needed = i * redemption_rate
        syp_amount = i * base_syp
        usd_amount = i * 1
        
        builder.row(types.InlineKeyboardButton(
            text=f"{usd_amount}$ ({syp_amount:.0f} ل.س) - {points_needed} نقطة",
            callback_data=f"redeem_{points_needed}_{syp_amount}_{exchange_rate}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للحساب", 
        callback_data="back_to_account"
    ))
    
    text = (
        f"🎁 **استرداد النقاط**\n\n"
        f"لديك {points} نقطة\n"
        f"💰 **سعر الصرف الحالي:** {exchange_rate:.0f} ل.س = 1$\n"
        f"🎯 **معدل الاسترداد:** كل {redemption_rate} نقطة = 1$ ({base_syp:.0f} ل.س)\n\n"
        f"اختر المبلغ الذي تريد استرداده:"
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ========== معالجة طلب الاسترداد ==========
@router.callback_query(F.data.startswith("redeem_"))
async def process_redeem_from_menu(callback: types.CallbackQuery, db_pool):
    """معالجة طلب الاسترداد"""
    try:
        parts = callback.data.split("_")
        points = int(parts[1])
        amount_syp = float(parts[2])
        exchange_rate = float(parts[3]) if len(parts) > 3 else None
        
        amount_usd = amount_syp / exchange_rate if exchange_rate else points / 100
        
        request_id, error = await create_redemption_request(
            db_pool, 
            callback.from_user.id,
            callback.from_user.username,
            points,
            amount_usd,
            amount_syp
        )
        
        if error:
            await callback.answer(f"❌ {error}", show_alert=True)
        else:
            current_time = get_damascus_time_now().strftime("%Y-%m-%d %H:%M:%S")
            
            await callback.message.edit_text(
                f"✅ **تم إرسال طلب الاسترداد بنجاح!**\n\n"
                f"⭐ النقاط: {points}\n"
                f"💰 المبلغ: {amount_syp:.0f} ل.س\n"
                f"💵 سعر الصرف: {exchange_rate:.0f} ل.س = 1$\n"
                f"🕐 وقت الطلب: {current_time} (دمشق)\n\n"
                f"⏳ في انتظار موافقة الإدارة.\n"
                f"📋 رقم الطلب: #{request_id}"
            )
            
            from .start import notify_admins
            await notify_admins(
                callback.bot,
                f"🆕 **طلب استرداد نقاط جديد**\n\n"
                f"👤 المستخدم: @{callback.from_user.username or 'غير معروف'}\n"
                f"🆔 الآيدي: `{callback.from_user.id}`\n"
                f"⭐ النقاط: {points}\n"
                f"💰 المبلغ: {amount_syp:.0f} ل.س\n"
                f"💵 سعر الصرف: {exchange_rate:.0f} ل.س\n"
                f"🕐 وقت الطلب: {current_time} (دمشق)\n"
                f"📋 رقم الطلب: #{request_id}"
            )
            
            builder = InlineKeyboardBuilder()
            builder.row(types.InlineKeyboardButton(
                text="🔙 رجوع للحساب", 
                callback_data="back_to_account"
            ))
            await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
                
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# ========== العودة للملف الشخصي ==========
# handlers/profile_handlers.py - السطر 331
@router.callback_query(F.data == "back_to_account")
async def back_to_account(callback: types.CallbackQuery, db_pool):
    """العودة إلى الملف الشخصي"""
    # ✅ منع خطأ حذف الرسالة
    try:
        await callback.message.delete()
    except:
        pass  # إذا فشل الحذف، نكمل
    
    # استدعاء الملف الشخصي مباشرة
    await my_account(callback.message, db_pool)

# ========== رصيد النقاط ==========
@router.callback_query(F.data == "show_points_balance")
async def show_points_balance(callback: types.CallbackQuery, db_pool):
    """عرض رصيد النقاط وتفاصيله"""
    async with db_pool.acquire() as conn:
        current_points = await conn.fetchval(
            "SELECT total_points FROM users WHERE user_id = $1",
            callback.from_user.id
        ) or 0
        
        points_from_referrals = await conn.fetchval(
            "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND action = 'referral'",
            callback.from_user.id
        ) or 0
        
        points_from_orders = await conn.fetchval(
            "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND action = 'order_completed'",
            callback.from_user.id
        ) or 0
        
        points_redeemed = await conn.fetchval(
            "SELECT COALESCE(SUM(ABS(points)), 0) FROM points_history WHERE user_id = $1 AND points < 0",
            callback.from_user.id
        ) or 0
        
        exchange_rate = await get_exchange_rate(db_pool)
        redemption_rate = await get_redemption_rate(db_pool)
    
    points_value_usd = (current_points / redemption_rate) if redemption_rate > 0 else 0
    points_value_syp = points_value_usd * exchange_rate
    base_syp = 1 * exchange_rate
    
    text = (
        f"⭐ **رصيد النقاط**\n\n"
        f"**نقاطك الحالية:** {current_points}\n"
        f"💰 **القيمة:** {points_value_syp:.0f} ل.س (${points_value_usd:.2f})\n\n"
        f"📊 **تفاصيل النقاط:**\n"
        f"• من الإحالات: {points_from_referrals} نقطة\n"
        f"• من المشتريات: {points_from_orders} نقطة\n"
        f"• تم استردادها: {points_redeemed} نقطة\n\n"
        f"💱 **سعر الصرف:** {exchange_rate:.0f} ل.س = 1$\n"
        f"🎁 **معدل الاسترداد:** كل {redemption_rate} نقطة = 1$ ({base_syp:.0f} ل.س)"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown")
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للحساب", callback_data="back_to_account"))
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

# ========== سجل العمليات ==========
@router.callback_query(F.data == "transactions_history")
async def transactions_history(callback: types.CallbackQuery, db_pool):
    """عرض سجل العمليات (آخر 3 شحن + آخر 3 شراء)"""
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        deposits = await conn.fetch('''
            SELECT amount_syp, status, created_at
            FROM deposit_requests 
            WHERE user_id = $1 
            ORDER BY created_at DESC 
            LIMIT 3
        ''', user_id)
        
        orders = await conn.fetch('''
            SELECT o.total_amount_syp, a.name as app_name, o.status, o.created_at
            FROM orders o
            JOIN applications a ON o.app_id = a.id
            WHERE o.user_id = $1 
            ORDER BY o.created_at DESC 
            LIMIT 3
        ''', user_id)
        
        deposits_count = await conn.fetchval(
            "SELECT COUNT(*) FROM deposit_requests WHERE user_id = $1 AND status = 'approved'",
            user_id
        ) or 0
        
        orders_count = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE user_id = $1 AND status = 'completed'",
            user_id
        ) or 0
        
        deposits_total = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_syp), 0) FROM deposit_requests WHERE user_id = $1 AND status = 'approved'",
            user_id
        ) or 0
        
        orders_total = await conn.fetchval(
            "SELECT COALESCE(SUM(total_amount_syp), 0) FROM orders WHERE user_id = $1 AND status = 'completed'",
            user_id
        ) or 0
    
    text = (
        f"📊 **سجل العمليات**\n\n"
        f"**إحصائيات سريعة:**\n"
        f"💰 إجمالي الشحن: {deposits_count} عملية | {deposits_total:,.0f} ل.س\n"
        f"🛒 إجمالي الشراء: {orders_count} عملية | {orders_total:,.0f} ل.س\n\n"
    )
    
    if deposits:
        text += "**🟢 آخر عمليات الشحن:**\n"
        for d in deposits:
            status_icon = "✅" if d['status'] == 'approved' else "⏳" if d['status'] == 'pending' else "❌"
            date = d['created_at'].strftime("%Y-%m-%d %H:%M") if d['created_at'] else "-"
            text += f"{status_icon} {d['amount_syp']:,.0f} ل.س - {date}\n"
    else:
        text += "**🟢 آخر عمليات الشحن:**\nلا توجد عمليات شحن بعد.\n"
    
    text += "\n"
    
    if orders:
        text += "**🔵 آخر عمليات الشراء:**\n"
        for o in orders:
            status_icon = "✅" if o['status'] == 'completed' else "⏳" if o['status'] == 'pending' else "❌"
            date = o['created_at'].strftime("%Y-%m-%d %H:%M") if o['created_at'] else "-"
            text += f"{status_icon} {o['app_name']} - {o['total_amount_syp']:,.0f} ل.س - {date}\n"
    else:
        text += "**🔵 آخر عمليات الشراء:**\nلا توجد عمليات شراء بعد.\n"
    
    await callback.message.edit_text(text, parse_mode="Markdown")
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للحساب", callback_data="back_to_account"))
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
