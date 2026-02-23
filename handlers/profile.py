# handlers/profile.py
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import USD_TO_SYP, ADMIN_ID
from datetime import datetime
import logging
from handlers.keyboards import get_back_inline_keyboard

logger = logging.getLogger(__name__)
router = Router()

class ProfileStates(StatesGroup):
    waiting_referral_code = State()

@router.message(F.text == "👤 حسابي")
async def show_profile(message: types.Message, db_pool):
    """عرض الملف الشخصي للمستخدم"""
    user_id = message.from_user.id
    
    from database import get_user_full_stats, get_user_points
    
    # جلب إحصائيات المستخدم
    stats = await get_user_full_stats(db_pool, user_id)
    
    if not stats:
        # إذا لم توجد إحصائيات، نعرض بيانات بسيطة
        points = await get_user_points(db_pool, user_id)
        balance = 0
        
        async with db_pool.acquire() as conn:
            try:
                balance = await conn.fetchval(
                    "SELECT balance FROM users WHERE user_id = $1",
                    user_id
                ) or 0
            except:
                pass
        
        await show_simple_profile(message, user_id, balance, points, db_pool)
        return
    
    user = stats['user']
    
    # حساب قيمة النقاط
    async with db_pool.acquire() as conn:
        redemption_rate = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = 'redemption_rate'"
        ) or '500'
        redemption_rate = int(redemption_rate)
    
    points_value_usd = (user.get('total_points', 0) / redemption_rate) * 5
    points_value_syp = points_value_usd * USD_TO_SYP
    
    # تنسيق تاريخ التسجيل
    join_date = "غير معروف"
    if user.get('created_at'):
        if isinstance(user['created_at'], datetime):
            join_date = user['created_at'].strftime("%Y-%m-%d")
    
    # بناء رسالة الملف الشخصي
    profile_text = (
        f"👤 **الملف الشخصي**\n\n"
        f"🆔 **الآيدي:** `{user['user_id']}`\n"
        f"👤 **الاسم:** {message.from_user.full_name}\n"
        f"📅 **اليوزر:** @{message.from_user.username or 'غير متوفر'}\n"
        f"📅 **تاريخ التسجيل:** {join_date}\n"
        f"🔒 **الحالة:** {'✅ نشط' if not user.get('is_banned', False) else '🚫 محظور'}\n\n"
        
        f"💰 **المحفظة:**\n"
        f"• الرصيد: {user.get('balance', 0):,.0f} ل.س\n"
        f"• إجمالي الإيداعات: {stats['deposits'].get('total_amount', 0):,.0f} ل.س\n"
        f"• عدد الإيداعات: {stats['deposits'].get('approved_count', 0)}\n"
        f"• عدد الطلبات: {stats['orders'].get('completed_count', 0)}\n\n"
        
        f"⭐ **نظام النقاط:**\n"
        f"• رصيد النقاط: {user.get('total_points', 0)}\n"
        f"• قيمة النقاط: {points_value_syp:,.0f} ل.س\n"
        f"• كل {redemption_rate} نقطة = 5$ ({redemption_rate * USD_TO_SYP:,.0f} ل.س)\n\n"
        
        f"🔗 **الإحالة:**\n"
        f"• كود الإحالة: `{user.get('referral_code', 'غير متوفر')}`\n"
        f"• عدد المحالين: {stats['referrals'].get('total_referrals', 0)}\n"
        f"• نقاط من الإحالات: {user.get('referral_earnings', 0)}\n\n"
        
        f"📊 **إحصائيات إضافية:**\n"
        f"• نقاط مكتسبة من الطلبات: {stats['orders'].get('total_points_earned', 0)}\n"
        f"• إجمالي النقاط المكتسبة: {user.get('total_points_earned', 0)}\n"
        f"• النقاط المستردة: {user.get('total_points_redeemed', 0)}"
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
        types.InlineKeyboardButton(text="📋 آخر 5 طلبات", callback_data="recent_orders")
    )
    
    await message.answer(
        profile_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

async def show_simple_profile(message: types.Message, user_id, balance, points, db_pool):
    """نسخة مبسطة من الملف الشخصي"""
    async with db_pool.acquire() as conn:
        try:
            referral_code = await conn.fetchval(
                "SELECT referral_code FROM users WHERE user_id = $1",
                user_id
            ) or "غير متوفر"
        except:
            referral_code = "غير متوفر"
    
    profile_text = (
        f"👤 **الملف الشخصي**\n\n"
        f"🆔 **الآيدي:** `{user_id}`\n"
        f"👤 **الاسم:** {message.from_user.full_name}\n"
        f"📅 **اليوزر:** @{message.from_user.username or 'غير متوفر'}\n"
        f"💰 **الرصيد:** {balance:,.0f} ل.س\n"
        f"⭐ **النقاط:** {points}\n\n"
        f"🔗 **كود الإحالة:**\n"
        f"`{referral_code}`"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="referral_link"),
        types.InlineKeyboardButton(text="📋 سجل النقاط", callback_data="points_history")
    )
    
    await message.answer(
        profile_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
@router.callback_query(F.data == "points_history")
async def show_points_history(callback: types.CallbackQuery, db_pool):
    """عرض سجل النقاط مع توقيت دمشق"""
    async with db_pool.acquire() as conn:
        # ضبط المنطقة الزمنية للاتصال
        await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
        
        # جلب سجل النقاط مع تحويل التوقيت
        history = await conn.fetch('''
            SELECT points, action, description, 
                   (created_at AT TIME ZONE 'Asia/Damascus') as created_at_local
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
        return await callback.answer("❌ لا يوجد سجل نقاط حالياً", show_alert=True)
    
    total_earned = stats['total_earned'] if stats else 0
    total_spent = stats['total_spent'] if stats else 0
    
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
            'points_spent': 'خصم نقاط'
        }
        
        action_text = action_names.get(item['action'], item['action'])
        description = item.get('description', action_text)
        
        text += f"{i}. {symbol} **{points_abs} نقطة**\n"
        text += f"   📝 {description}\n"
        text += f"   🕐 {date}\n\n"
    
    text += "📊 **الإحصائيات:**\n"
    text += f"• إجمالي المكتسب: {total_earned} نقطة\n"
    text += f"• إجمالي المستخدم: {total_spent} نقطة\n"
    text += f"• الرصيد الحالي: {total_earned - total_spent} نقطة"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("back_to_profile"),
        parse_mode="Markdown"
    )

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
    
    text = (
        f"🔗 **رابط الإحالة الخاص بك**\n\n"
        f"`{link}`\n\n"
        f"**📊 إحصائيات الإحالة:**\n"
        f"• عدد المحالين: {referrals_count}\n"
        f"• النقاط المكتسبة: {points_from_referrals}\n\n"
        f"**🎁 مميزات الإحالة:**\n"
        f"• 5 نقاط لكل مشترك جديد\n"
        f"• النقاط قابلة للاستبدال برصيد\n"
        f"• كل 500 نقطة = 5$ ({500 * USD_TO_SYP:,.0f} ل.س)\n\n"
        f"شارك الرابط مع أصدقائك!"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown")

@router.callback_query(F.data == "redeem_points")
async def start_redeem_points(callback: types.CallbackQuery, db_pool):
    """بدء عملية استرداد النقاط"""
    from database import get_user_points, get_redemption_rate, get_exchange_rate, calculate_points_value
    
    user_id = callback.from_user.id
    points = await get_user_points(db_pool, user_id)
    
    # جلب الإعدادات
    redemption_rate = await get_redemption_rate(db_pool)
    exchange_rate = await get_exchange_rate(db_pool)
    
    if points < redemption_rate:
        return await callback.answer(
            f"تحتاج {redemption_rate} نقطة على الأقل للاسترداد.\nلديك {points} نقطة فقط.", 
            show_alert=True
        )
    
    # حساب المبالغ الممكنة
    possible_redemptions = []
    max_redemptions = min(points // redemption_rate, 5)  # حد أقصى 5 عمليات
    
    for i in range(1, max_redemptions + 1):
        points_needed = i * redemption_rate
        usd_amount = i * 5
        syp_amount = usd_amount * exchange_rate  # استخدام سعر الصرف الحالي
        possible_redemptions.append((points_needed, usd_amount, syp_amount))
    
    builder = InlineKeyboardBuilder()
    for points_needed, usd_amount, syp_amount in possible_redemptions:
        builder.row(types.InlineKeyboardButton(
            text=f"{usd_amount}$ ({syp_amount:,.0f} ل.س) - {points_needed} نقطة",
            callback_data=f"redeem_{points_needed}_{syp_amount}_{exchange_rate}"
        ))
    
    # ✅ استخدام الدالة المستوردة لزر الرجوع
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع", 
        callback_data="back_to_profile"
    ))
    
    text = (
        f"🎁 **استرداد النقاط**\n\n"
        f"لديك {points} نقطة\n"
        f"كل {redemption_rate} نقطة = 5$ ({redemption_rate * exchange_rate:,.0f} ل.س)\n"
        f"💰 **سعر الصرف الحالي:** {exchange_rate:,.0f} ل.س = 1$\n\n"
        f"اختر المبلغ الذي تريد استرداده:"
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
@router.callback_query(F.data.startswith("redeem_"))
async def process_redeem(callback: types.CallbackQuery, db_pool):
    """معالجة طلب الاسترداد"""
    try:
        parts = callback.data.split("_")
        points = int(parts[1])
        amount_syp = float(parts[2])
        exchange_rate = float(parts[3]) if len(parts) > 3 else None
        
        amount_usd = amount_syp / exchange_rate if exchange_rate else points / 500 * 5
        
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
                reply_markup=get_back_inline_keyboard("back_to_profile")  # 👈 مستوردة
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
                
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data == "my_stats")
async def show_detailed_stats(callback: types.CallbackQuery, db_pool):
    """عرض إحصائيات مفصلة"""
    from database import get_user_full_stats
    
    stats = await get_user_full_stats(db_pool, callback.from_user.id)
    
    if not stats:
        return await callback.answer("لا توجد إحصائيات كافية بعد", show_alert=True)
    
    text = (
        "📊 **إحصائياتك التفصيلية**\n\n"
        
        "💰 **الإيداعات:**\n"
        f"• إجمالي الإيداعات: {stats['deposits'].get('total_count', 0)} عملية\n"
        f"• إجمالي المبالغ: {stats['deposits'].get('total_amount', 0):,.0f} ل.س\n"
        f"• الإيداعات المقبولة: {stats['deposits'].get('approved_count', 0)} عملية\n"
        f"• قيمة المقبولة: {stats['deposits'].get('approved_amount', 0):,.0f} ل.س\n\n"
        
        "🛒 **الطلبات:**\n"
        f"• إجمالي الطلبات: {stats['orders'].get('total_count', 0)} طلب\n"
        f"• إجمالي المبالغ: {stats['orders'].get('total_amount', 0):,.0f} ل.س\n"
        f"• الطلبات المكتملة: {stats['orders'].get('completed_count', 0)} طلب\n"
        f"• قيمة المكتملة: {stats['orders'].get('completed_amount', 0):,.0f} ل.س\n"
        f"• نقاط من الطلبات: {stats['orders'].get('total_points_earned', 0)} نقطة\n\n"
        
        "👥 **الإحالات:**\n"
        f"• عدد المحالين: {stats['referrals'].get('total_referrals', 0)}\n"
        f"• إيداعات المحالين: {stats['referrals'].get('referrals_deposits', 0):,.0f} ل.س\n"
        f"• طلبات المحالين: {stats['referrals'].get('referrals_orders', 0)}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_inline_keyboard("back_to_profile"),  # 👈 مستوردة
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "recent_orders")
async def show_recent_orders(callback: types.CallbackQuery, db_pool):
    """عرض آخر 5 طلبات"""
    from database import get_user_full_stats
    
    stats = await get_user_full_stats(db_pool, callback.from_user.id)
    
    if not stats or not stats.get('recent_orders'):
        return await callback.answer("لا توجد طلبات حديثة", show_alert=True)
    
    text = "📋 **آخر 5 طلبات**\n\n"
    
    for order in stats['recent_orders']:
        date = order['created_at'].strftime("%Y-%m-%d %H:%M") if order['created_at'] else "تاريخ غير معروف"
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
        reply_markup=get_back_inline_keyboard("back_to_profile"),  # 👈 مستوردة
        parse_mode="Markdown"
    )
@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: types.CallbackQuery, db_pool):
    """العودة إلى الملف الشخصي"""
    # إنشاء رسالة جديدة بدلاً من تعديل القديمة
    await callback.message.delete()
    await show_profile(callback.message, db_pool)
