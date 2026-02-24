# handlers/profile.py
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import USD_TO_SYP, ADMIN_ID
from datetime import datetime
import logging
from handlers.keyboards import get_back_inline_keyboard, get_main_menu_keyboard
from database import get_user_profile, get_user_points, get_exchange_rate, get_redemption_rate, is_admin_user, get_next_vip_level

logger = logging.getLogger(__name__)
router = Router()

class ProfileStates(StatesGroup):
    waiting_referral_code = State()

# ============= الملف الشخصي الرئيسي =============

@router.message(F.text == "👤 حسابي")
async def show_profile(message: types.Message, db_pool):
    """عرض الملف الشخصي للمستخدم مع تفاصيل VIP والتنافس"""
    user_id = message.from_user.id
    
    # استخدم get_user_profile بدلاً من get_user_full_stats
    from database import get_user_profile
    profile = await get_user_profile(db_pool, user_id)
    
    if not profile:
        # إذا لم توجد إحصائيات، نعرض بيانات بسيطة
        points = await get_user_points(db_pool, user_id)
        balance = 0
        vip_level = 0
        vip_discount = 0
        total_spent = 0
        
        async with db_pool.acquire() as conn:
            try:
                user_data = await conn.fetchrow(
                    "SELECT balance, vip_level, discount_percent, total_spent FROM users WHERE user_id = $1",
                    user_id
                )
                if user_data:
                    balance = user_data['balance'] or 0
                    vip_level = user_data['vip_level'] or 0
                    vip_discount = user_data['discount_percent'] or 0
                    total_spent = user_data['total_spent'] or 0
            except:
                pass
        
        await show_simple_profile(message, user_id, balance, points, vip_level, vip_discount, total_spent, db_pool)
        return
    
    user = profile['user']
    
    # جلب الإعدادات
    redemption_rate = await get_redemption_rate(db_pool)
    exchange_rate = await get_exchange_rate(db_pool)
    
    # حساب قيمة النقاط
    points_value_usd = (user.get('total_points', 0) / redemption_rate)
    points_value_syp = points_value_usd * exchange_rate
    
    # تنسيق تاريخ التسجيل
    join_date = "غير معروف"
    if user.get('created_at'):
        if isinstance(user['created_at'], datetime):
            join_date = user['created_at'].strftime("%Y-%m-%d")
        else:
            join_date = str(user['created_at'])
    
    # تحديد أيقونة VIP
    vip_icons = ["🟢", "🔵", "🟣", "🟡", "🔴", "💎", "👑"]
    vip_level = user.get('vip_level', 0)
    vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "🟢"
    vip_discount = user.get('discount_percent', 0)
    total_spent = user.get('total_spent', 0)
    manual_status = " (يدوي)" if user.get('manual_vip') else ""
    
    # حساب التقدم للمستوى التالي
    next_level_info = get_next_vip_level(total_spent)
    
    if next_level_info and next_level_info.get('remaining', 0) > 0:
        remaining = next_level_info['remaining']
        next_level_name = next_level_info['next_level_name']
        progress_text = f"📊 {remaining:,.0f} ل.س للمستوى {next_level_name}"
    else:
        progress_text = "✨ وصلت لأعلى مستوى!"
    
    # بناء رسالة الملف الشخصي مع تفاصيل التنافس
    profile_text = (
        f"👤 **الملف الشخصي**\n\n"
        f"🆔 **الآيدي:** `{user['user_id']}`\n"
        f"👤 **الاسم:** {message.from_user.full_name}\n"
        f"📅 **اليوزر:** @{message.from_user.username or 'غير متوفر'}\n"
        f"📅 **تاريخ التسجيل:** {join_date}\n"
        f"🔒 **الحالة:** {'✅ نشط' if not user.get('is_banned', False) else '🚫 محظور'}\n\n"
        
        f"💰 **المحفظة:**\n"
        f"• الرصيد: {user.get('balance', 0):,.0f} ل.س\n"
        f"• إجمالي الإيداعات: {profile['deposits'].get('approved_amount', 0):,.0f} ل.س\n"
        f"• عدد الإيداعات: {profile['deposits'].get('approved_count', 0)}\n\n"
        
        f"👑 **نظام VIP{manual_status}:**\n"
        f"• مستواك: {vip_icon} VIP {vip_level}\n"
        f"• خصمك الحالي: {vip_discount}%\n"
        f"• إجمالي الإنفاق: {total_spent:,.0f} ل.س\n"
        f"{progress_text}\n\n"
        
        f"⭐ **نظام النقاط:**\n"
        f"• رصيد النقاط: {user.get('total_points', 0)}\n"
        f"• قيمة النقاط: {points_value_syp:,.0f} ل.س\n"
        f"• كل {redemption_rate} نقطة = 1$ ({redemption_rate * exchange_rate:,.0f} ل.س)\n"
        f"• نقاط مكتسبة من الطلبات: {profile['orders'].get('total_points_earned', 0)}\n"
        f"• النقاط المستردة: {user.get('total_points_redeemed', 0)}\n\n"
        
        f"🔗 **الإحالة:**\n"
        f"• كود الإحالة: `{user.get('referral_code', 'غير متوفر')}`\n"
        f"• عدد المحالين: {user.get('referral_count', 0)}\n"
        f"• نقاط من الإحالات: {user.get('referral_earnings', 0)}\n"
        f"• إيداعات المحالين: {profile['referrals'].get('referrals_deposits', 0):,.0f} ل.س\n"
        f"• طلبات المحالين: {profile['referrals'].get('referrals_orders', 0)}"
    )
    
    # أزرار التفاعل
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📋 سجل النقاط", callback_data="points_history"),
        types.InlineKeyboardButton(text="🎁 استرداد نقاط", callback_data="redeem_points")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="referral_link"),
        types.InlineKeyboardButton(text="📊 إحصائياتي", callback_data="my_stats")
    )
    builder.row(
        types.InlineKeyboardButton(text="📋 آخر 5 طلبات", callback_data="recent_orders"),
        types.InlineKeyboardButton(text="🏆 المتصدرين", callback_data="leaderboard_menu")
    )
    
    await message.answer(
        profile_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

async def show_simple_profile(message: types.Message, user_id, balance, points, vip_level, vip_discount, total_spent, db_pool):
    """نسخة مبسطة من الملف الشخصي مع تفاصيل VIP"""
    async with db_pool.acquire() as conn:
        try:
            referral_code = await conn.fetchval(
                "SELECT referral_code FROM users WHERE user_id = $1",
                user_id
            ) or "غير متوفر"
            
            # جلب إحصائيات إضافية
            deposits_count = await conn.fetchval(
                "SELECT COUNT(*) FROM deposit_requests WHERE user_id = $1 AND status = 'approved'",
                user_id
            ) or 0
            
            orders_count = await conn.fetchval(
                "SELECT COUNT(*) FROM orders WHERE user_id = $1 AND status = 'completed'",
                user_id
            ) or 0
            
            referrals_count = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE referred_by = $1",
                user_id
            ) or 0
        except:
            referral_code = "غير متوفر"
            deposits_count = 0
            orders_count = 0
            referrals_count = 0
    
    # جلب الإعدادات
    exchange_rate = await get_exchange_rate(db_pool)
    redemption_rate = await get_redemption_rate(db_pool)
    
    # تحديد أيقونة VIP
    vip_icons = ["🟢", "🔵", "🟣", "🟡", "🔴", "💎", "👑"]
    vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "🟢"
    
    # حساب التقدم للمستوى التالي
    next_level_info = get_next_vip_level(total_spent)
    
    if next_level_info and next_level_info.get('remaining', 0) > 0:
        remaining = next_level_info['remaining']
        next_level_name = next_level_info['next_level_name']
        progress_text = f"📊 {remaining:,.0f} ل.س للمستوى {next_level_name}"
    else:
        progress_text = "✨ وصلت لأعلى مستوى!"
    
    profile_text = (
        f"👤 **الملف الشخصي**\n\n"
        f"🆔 **الآيدي:** `{user_id}`\n"
        f"👤 **الاسم:** {message.from_user.full_name}\n"
        f"📅 **اليوزر:** @{message.from_user.username or 'غير متوفر'}\n"
        f"💰 **الرصيد:** {balance:,.0f} ل.س\n\n"
        
        f"👑 **نظام VIP:**\n"
        f"• مستواك: {vip_icon} VIP {vip_level}\n"
        f"• خصمك الحالي: {vip_discount}%\n"
        f"• إجمالي الإنفاق: {total_spent:,.0f} ل.س\n"
        f"{progress_text}\n\n"
        
        f"⭐ **النقاط:** {points}\n"
        f"💵 قيمة النقاط: {(points / redemption_rate) * exchange_rate:,.0f} ل.س\n\n"
        
        f"📊 **إحصائيات سريعة:**\n"
        f"• إيداعات ناجحة: {deposits_count}\n"
        f"• طلبات مكتملة: {orders_count}\n"
        f"• إحالات ناجحة: {referrals_count}\n\n"
        
        f"🔗 **كود الإحالة:**\n"
        f"`{referral_code}`"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="referral_link"),
        types.InlineKeyboardButton(text="📋 سجل النقاط", callback_data="points_history")
    )
    builder.row(
        types.InlineKeyboardButton(text="🏆 المتصدرين", callback_data="leaderboard_menu")
    )
    
    await message.answer(
        profile_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# ============= سجل النقاط =============

@router.callback_query(F.data == "points_history")
async def show_points_history(callback: types.CallbackQuery, db_pool):
    """عرض سجل النقاط مع توقيت دمشق"""
    try:
        async with db_pool.acquire() as conn:
            # ضبط المنطقة الزمنية للاتصال
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
            # جلب سجل النقاط مع تحويل التوقيت
            history = await conn.fetch('''
                SELECT points, action, description, 
                       created_at AT TIME ZONE 'Asia/Damascus' as created_at_local
                FROM points_history
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 20
            ''', callback.from_user.id)
            
            # جلب إحصائيات
            stats = await conn.fetchrow('''
                SELECT 
                    COALESCE(SUM(CASE WHEN points > 0 THEN points ELSE 0 END), 0) as total_earned,
                    COALESCE(SUM(CASE WHEN points < 0 THEN ABS(points) ELSE 0 END), 0) as total_spent
                FROM points_history
                WHERE user_id = $1
            ''', callback.from_user.id)
        
        if not history:
            await callback.answer("❌ لا يوجد سجل نقاط حالياً", show_alert=True)
            return
        
        total_earned = stats['total_earned'] if stats else 0
        total_spent = stats['total_spent'] if stats else 0
        current_balance = total_earned - total_spent
        
        text = "⭐ **سجل النقاط (توقيت دمشق)**\n\n"
        
        for i, item in enumerate(history[:10], 1):
            symbol = "➕" if item['points'] > 0 else "➖"
            points_abs = abs(item['points'])
            
            # تنسيق التاريخ
            if item['created_at_local']:
                if hasattr(item['created_at_local'], 'strftime'):
                    date = item['created_at_local'].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    date = str(item['created_at_local'])
            else:
                date = "وقت غير معروف"
            
            action_names = {
                'order_completed': 'طلب مكتمل',
                'order': 'طلب',
                'referral': 'إحالة',
                'admin_add': 'إضافة من الأدمن',
                'redemption': 'استرداد نقاط',
                'points_spent': 'خصم نقاط',
                'deposit': 'نقاط شحن'
            }
            
            action_text = action_names.get(item['action'], item['action'])
            description = item.get('description', action_text)
            
            text += f"{i}. {symbol} **{points_abs} نقطة**\n"
            text += f"   📝 {description}\n"
            text += f"   🕐 {date}\n\n"
        
        text += "📊 **الإحصائيات:**\n"
        text += f"• إجمالي المكتسب: {total_earned} نقطة\n"
        text += f"• إجمالي المستخدم: {total_spent} نقطة\n"
        text += f"• الرصيد الحالي: {current_balance} نقطة"
        
        await callback.message.edit_text(
            text,
            reply_markup=get_back_inline_keyboard("back_to_profile"),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"خطأ في سجل النقاط: {e}")
        await callback.answer("❌ حدث خطأ في جلب السجل", show_alert=True)

# ============= رابط الإحالة =============

@router.callback_query(F.data == "referral_link")
async def show_referral_link(callback: types.CallbackQuery, db_pool):
    """عرض رابط الإحالة"""
    from database import generate_referral_code
    
    async with db_pool.acquire() as conn:
        try:
            code = await conn.fetchval(
                "SELECT referral_code FROM users WHERE user_id = $1",
                callback.from_user.id
            )
        except:
            code = None
    
    if not code:
        # إنشاء كود جديد
        code = await generate_referral_code(db_pool, callback.from_user.id)
    
    bot_username = (await callback.bot.me()).username
    link = f"https://t.me/{bot_username}?start={code}"
    
    # إحصائيات الإحالة
    async with db_pool.acquire() as conn:
        referrals_count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE referred_by = $1",
            callback.from_user.id
        ) or 0
        
        points_from_referrals = await conn.fetchval(
            "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND action = 'referral'",
            callback.from_user.id
        ) or 0
        
        # إيداعات المحالين
        referrals_deposits = await conn.fetchval('''
            SELECT COALESCE(SUM(u.total_deposits), 0)
            FROM users u
            WHERE u.referred_by = $1
        ''', callback.from_user.id) or 0
    
    exchange_rate = await get_exchange_rate(db_pool)
    redemption_rate = await get_redemption_rate(db_pool)
    
    text = (
        f"🔗 **رابط الإحالة الخاص بك**\n\n"
        f"`{link}`\n\n"
        f"**📊 إحصائيات الإحالة:**\n"
        f"• عدد المحالين: {referrals_count}\n"
        f"• النقاط المكتسبة: {points_from_referrals}\n"
        f"• إيداعات المحالين: {referrals_deposits:,.0f} ل.س\n\n"
        f"**🎁 مميزات الإحالة:**\n"
        f"• {await get_points_per_referral(db_pool)} نقاط لكل مشترك جديد\n"
        f"• كل {redemption_rate} نقطة = 1$ ({redemption_rate * exchange_rate:,.0f} ل.س)\n"
        f"• المحالون يساهمون في رفع مستواك VIP!\n\n"
        f"شارك الرابط مع أصدقائك!"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("back_to_profile"),
        parse_mode="Markdown"
    )

async def get_points_per_referral(db_pool):
    """دالة مساعدة لجلب نقاط الإحالة"""
    try:
        async with db_pool.acquire() as conn:
            points = await conn.fetchval(
                "SELECT value FROM bot_settings WHERE key = 'points_per_referral'"
            )
            return int(points) if points else 1
    except:
        return 1

# ============= استرداد النقاط =============

@router.callback_query(F.data == "redeem_points")
async def start_redeem_points(callback: types.CallbackQuery, db_pool):
    """بدء عملية استرداد النقاط"""
    from database import get_user_points
    
    user_id = callback.from_user.id
    points = await get_user_points(db_pool, user_id)
    
    # جلب الإعدادات
    redemption_rate = await get_redemption_rate(db_pool)
    exchange_rate = await get_exchange_rate(db_pool)
    
    if points < redemption_rate:
        await callback.answer(
            f"❌ تحتاج {redemption_rate} نقطة على الأقل للاسترداد.\nلديك {points} نقطة فقط.", 
            show_alert=True
        )
        return
    
    # حساب المبالغ الممكنة
    possible_redemptions = []
    max_redemptions = min(points // redemption_rate, 10)  # حد أقصى 10 عمليات
    
    for i in range(1, max_redemptions + 1):
        points_needed = i * redemption_rate
        usd_amount = i * 1
        syp_amount = usd_amount * exchange_rate
        possible_redemptions.append((points_needed, usd_amount, syp_amount))
    
    builder = InlineKeyboardBuilder()
    for points_needed, usd_amount, syp_amount in possible_redemptions:
        builder.row(types.InlineKeyboardButton(
            text=f"{usd_amount}$ ({syp_amount:,.0f} ل.س) - {points_needed} نقطة",
            callback_data=f"redeem_{points_needed}_{syp_amount:.0f}_{exchange_rate}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data="back_to_profile"
    ))
    
    text = (
        f"🎁 **استرداد النقاط**\n\n"
        f"لديك {points} نقطة\n"
        f"كل {redemption_rate} نقطة = 1$ ({redemption_rate * exchange_rate:,.0f} ل.س)\n"
        f"💰 **سعر الصرف الحالي:** {exchange_rate:,.0f} ل.س = 1$\n\n"
        f"اختر المبلغ الذي تريد استرداده:"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("redeem_"))
async def process_redeem(callback: types.CallbackQuery, db_pool):
    """معالجة طلب الاسترداد"""
    try:
        parts = callback.data.split("_")
        if len(parts) < 3:
            await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
            return
            
        points = int(parts[1])
        amount_syp = float(parts[2])
        exchange_rate = float(parts[3]) if len(parts) > 3 else None
        
        amount_usd = amount_syp / exchange_rate if exchange_rate else points / 100
        
        from database import create_redemption_request
        
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
            await callback.message.edit_text(
                f"✅ **تم إرسال طلب الاسترداد بنجاح!**\n\n"
                f"⭐ النقاط: {points}\n"
                f"💰 المبلغ: {amount_syp:,.0f} ل.س\n"
                f"💵 سعر الصرف: {exchange_rate:,.0f} ل.س = 1$\n\n"
                f"⏳ في انتظار موافقة الإدارة.\n"
                f"📋 رقم الطلب: #{request_id}",
                reply_markup=get_back_inline_keyboard("back_to_profile"),
                parse_mode="Markdown"
            )
            
            # إشعار المشرفين
            from config import ADMIN_ID, MODERATORS
            
            admin_ids = [ADMIN_ID] + MODERATORS
            for admin_id in admin_ids:
                if admin_id:
                    try:
                        await callback.bot.send_message(
                            admin_id,
                            f"🆕 **طلب استرداد نقاط جديد**\n\n"
                            f"👤 المستخدم: @{callback.from_user.username or 'غير معروف'}\n"
                            f"🆔 الآيدي: `{callback.from_user.id}`\n"
                            f"⭐ النقاط: {points}\n"
                            f"💰 المبلغ: {amount_syp:,.0f} ل.س\n"
                            f"💵 سعر الصرف: {exchange_rate:,.0f} ل.س\n"
                            f"📋 رقم الطلب: #{request_id}",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                
    except ValueError as e:
        await callback.answer(f"❌ خطأ في البيانات: {str(e)}", show_alert=True)
    except Exception as e:
        logger.error(f"خطأ في معالجة الاسترداد: {e}")
        await callback.answer(f"❌ حدث خطأ: {str(e)}", show_alert=True)

# ============= إحصائيات مفصلة =============

@router.callback_query(F.data == "my_stats")
async def show_detailed_stats(callback: types.CallbackQuery, db_pool):
    """عرض إحصائيات مفصلة"""
    from database import get_user_profile
    
    profile = await get_user_profile(db_pool, callback.from_user.id)
    
    if not profile:
        await callback.answer("لا توجد إحصائيات كافية بعد", show_alert=True)
        return
    
    user = profile['user']
    
    # تحديد أيقونة VIP
    vip_icons = ["🟢", "🔵", "🟣", "🟡", "🔴", "💎", "👑"]
    vip_level = user.get('vip_level', 0)
    vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "🟢"
    
    text = (
        f"📊 **إحصائياتك التفصيلية**\n\n"
        f"👑 **مستوى VIP:** {vip_icon} VIP {vip_level}\n"
        f"💰 **نسبة الخصم:** {user.get('discount_percent', 0)}%\n"
        f"💵 **إجمالي الإنفاق:** {user.get('total_spent', 0):,.0f} ل.س\n\n"
        
        "💰 **الإيداعات:**\n"
        f"• إجمالي الإيداعات: {profile['deposits'].get('total_count', 0)} عملية\n"
        f"• إجمالي المبالغ: {profile['deposits'].get('total_amount', 0):,.0f} ل.س\n"
        f"• الإيداعات المقبولة: {profile['deposits'].get('approved_count', 0)} عملية\n"
        f"• قيمة المقبولة: {profile['deposits'].get('approved_amount', 0):,.0f} ل.س\n\n"
        
        "🛒 **الطلبات:**\n"
        f"• إجمالي الطلبات: {profile['orders'].get('total_count', 0)} طلب\n"
        f"• إجمالي المبالغ: {profile['orders'].get('total_amount', 0):,.0f} ل.س\n"
        f"• الطلبات المكتملة: {profile['orders'].get('completed_count', 0)} طلب\n"
        f"• قيمة المكتملة: {profile['orders'].get('completed_amount', 0):,.0f} ل.س\n"
        f"• نقاط من الطلبات: {profile['orders'].get('total_points_earned', 0)} نقطة\n\n"
        
        "👥 **الإحالات:**\n"
        f"• عدد المحالين: {profile['referrals'].get('total_referrals', 0)}\n"
        f"• إيداعات المحالين: {profile['referrals'].get('referrals_deposits', 0):,.0f} ل.س\n"
        f"• طلبات المحالين: {profile['referrals'].get('referrals_orders', 0)}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("back_to_profile"),
        parse_mode="Markdown"
    )

# ============= آخر الطلبات =============

@router.callback_query(F.data == "recent_orders")
async def show_recent_orders(callback: types.CallbackQuery, db_pool):
    """عرض آخر 5 طلبات"""
    from database import get_user_profile
    
    profile = await get_user_profile(db_pool, callback.from_user.id)
    
    if not profile or not profile.get('recent_orders'):
        await callback.answer("لا توجد طلبات حديثة", show_alert=True)
        return
    
    text = "📋 **آخر 5 طلبات**\n\n"
    
    for order in profile['recent_orders']:
        date = "تاريخ غير معروف"
        if order['created_at']:
            if hasattr(order['created_at'], 'strftime'):
                date = order['created_at'].strftime("%Y-%m-%d %H:%M")
            else:
                date = str(order['created_at'])
        
        status_emoji = {
            'pending': '⏳',
            'processing': '🔄',
            'completed': '✅',
            'failed': '❌'
        }.get(order['status'], '📌')
        
        text += f"{status_emoji} **{order['app_name']}**\n"
        if order.get('variant_name'):
            text += f"   الفئة: {order['variant_name']}\n"
        else:
            text += f"   الكمية: {order['quantity']}\n"
        text += f"   المبلغ: {order['total_amount_syp']:,.0f} ل.س\n"
        text += f"   الحالة: {order['status']}\n"
        text += f"   التاريخ: {date}\n\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("back_to_profile"),
        parse_mode="Markdown"
    )

# ============= قائمة المتصدرين =============

@router.callback_query(F.data == "leaderboard_menu")
async def leaderboard_menu(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المتصدرين"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="💰 الأكثر إيداعاً", callback_data="top_deposits_simple"),
        types.InlineKeyboardButton(text="🛒 الأكثر طلبات", callback_data="top_orders_simple")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔗 الأكثر إحالة", callback_data="top_referrals_simple"),
        types.InlineKeyboardButton(text="⭐ الأكثر نقاط", callback_data="top_points_simple")
    )
    builder.row(
        types.InlineKeyboardButton(text="👑 الأكثر إنفاق (VIP)", callback_data="top_spenders")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع للحساب", callback_data="back_to_profile")
    )
    
    text = (
        "🏆 **لوحة المتصدرين**\n\n"
        "اختر الفئة التي تريد عرض المتصدرين فيها:\n\n"
        "• 💰 الأكثر إيداعاً\n"
        "• 🛒 الأكثر طلبات\n"
        "• 🔗 الأكثر إحالة\n"
        "• ⭐ الأكثر نقاط\n"
        "• 👑 الأكثر إنفاق (VIP)"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "top_deposits_simple")
async def show_top_deposits_simple(callback: types.CallbackQuery, db_pool):
    """عرض أكثر المستخدمين إيداعاً"""
    from database import get_top_users_by_deposits
    
    users = await get_top_users_by_deposits(db_pool, 10)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "💰 **أكثر المستخدمين إيداعاً**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"مستخدم {user['user_id']}"
        vip_icons = ["🟢", "🔵", "🟣", "🟡"]
        vip_icon = vip_icons[user['vip_level']] if user['vip_level'] < len(vip_icons) else "🟢"
        
        text += f"{i}. {username} {vip_icon}\n   💰 {user['total_deposits']:,.0f} ل.س\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("leaderboard_menu"),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "top_orders_simple")
async def show_top_orders_simple(callback: types.CallbackQuery, db_pool):
    """عرض أكثر المستخدمين طلبات"""
    from database import get_top_users_by_orders
    
    users = await get_top_users_by_orders(db_pool, 10)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "🛒 **أكثر المستخدمين طلبات**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"مستخدم {user['user_id']}"
        vip_icons = ["🟢", "🔵", "🟣", "🟡"]
        vip_icon = vip_icons[user['vip_level']] if user['vip_level'] < len(vip_icons) else "🟢"
        
        text += f"{i}. {username} {vip_icon}\n   📦 {user['total_orders']} طلب\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("leaderboard_menu"),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "top_referrals_simple")
async def show_top_referrals_simple(callback: types.CallbackQuery, db_pool):
    """عرض أكثر المستخدمين إحالة"""
    from database import get_top_users_by_referrals
    
    users = await get_top_users_by_referrals(db_pool, 10)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "🔗 **أكثر المستخدمين إحالة**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"مستخدم {user['user_id']}"
        vip_icons = ["🟢", "🔵", "🟣", "🟡"]
        vip_icon = vip_icons[user['vip_level']] if user['vip_level'] < len(vip_icons) else "🟢"
        
        text += f"{i}. {username} {vip_icon}\n   👥 {user['referral_count']} إحالة\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("leaderboard_menu"),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "top_points_simple")
async def show_top_points_simple(callback: types.CallbackQuery, db_pool):
    """عرض أكثر المستخدمين نقاط"""
    from database import get_top_users_by_points
    
    users = await get_top_users_by_points(db_pool, 10)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "⭐ **أكثر المستخدمين نقاط**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"مستخدم {user['user_id']}"
        vip_icons = ["🟢", "🔵", "🟣", "🟡"]
        vip_icon = vip_icons[user['vip_level']] if user['vip_level'] < len(vip_icons) else "🟢"
        
        text += f"{i}. {username} {vip_icon}\n   ⭐ {user['total_points']} نقطة\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("leaderboard_menu"),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "top_spenders")
async def show_top_spenders(callback: types.CallbackQuery, db_pool):
    """عرض أكثر المستخدمين إنفاقاً (لنظام VIP)"""
    async with db_pool.acquire() as conn:
        users = await conn.fetch('''
            SELECT user_id, username, total_spent, vip_level 
            FROM users 
            WHERE total_spent > 0
            ORDER BY total_spent DESC 
            LIMIT 10
        ''')
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    vip_names = ["VIP 0", "VIP 1 🔵", "VIP 2 🟣", "VIP 3 🟡", "VIP 4 🔴", "VIP 5 💎", "VIP 6 👑"]
    vip_icons = ["🟢", "🔵", "🟣", "🟡", "🔴", "💎", "👑"]
    
    text = "👑 **الأكثر إنفاقاً (متصدرين VIP)**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"مستخدم {user['user_id']}"
        vip_icon = vip_icons[user['vip_level']] if user['vip_level'] < len(vip_icons) else "🟢"
        vip_name = vip_names[user['vip_level']] if user['vip_level'] < len(vip_names) else "VIP"
        
        text += f"{i}. {username} {vip_icon}\n   💵 {user['total_spent']:,.0f} ل.س ({vip_name})\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("leaderboard_menu"),
        parse_mode="Markdown"
    )

# ============= العودة للملف الشخصي =============

@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: types.CallbackQuery, db_pool):
    """العودة إلى الملف الشخصي"""
    try:
        # إنشاء رسالة جديدة بدلاً من تعديل القديمة
        await callback.message.delete()
        await show_profile(callback.message, db_pool)
    except Exception as e:
        logger.error(f"خطأ في العودة للملف الشخصي: {e}")
        # إذا فشل الحذف، نرسل رسالة جديدة
        await callback.message.answer("👋 تم العودة")
        await show_profile(callback.message, db_pool)

# ============= معالج الرجوع العام =============

@router.message(F.text.in_(["🔙 رجوع للقائمة", "/رجوع", "/cancel", "🏠 القائمة الرئيسية", "❌ إلغاء"]))
async def profile_back_handler(message: types.Message, state: FSMContext, db_pool):
    """معالج الرجوع من الملف الشخصي"""
    current_state = await state.get_state()
    
    if current_state is not None:
        await state.clear()
    
    is_admin = await is_admin_user(db_pool, message.from_user.id)
    
    await message.answer(
        "👋 أهلاً بك في القائمة الرئيسية",
        reply_markup=get_main_menu_keyboard(is_admin)
    )
