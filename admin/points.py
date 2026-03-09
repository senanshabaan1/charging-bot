# admin/points.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import time
from typing import Optional, Dict, Any
from utils import is_admin, format_amount, safe_edit_message, get_formatted_damascus_time
from handlers.keyboards import get_cancel_keyboard, get_confirmation_keyboard
from cache import cached, clear_cache  # ✅ استيراد الكاش

logger = logging.getLogger(__name__)
router = Router(name="admin_points")

class PointsStates(StatesGroup):
    waiting_points_settings = State()

# ✅ ثوابت للأداء
CACHE_TTL_SETTINGS = 60  # 60 ثانية
CACHE_TTL_REDEMPTIONS = 30  # 30 ثانية

# ✅ كاش لإعدادات النقاط
@cached(ttl=CACHE_TTL_SETTINGS, key_prefix="points_settings")
async def get_cached_points_settings(db_pool) -> Dict[str, Any]:
    """جلب إعدادات النقاط مع كاش دقيقة"""
    async with db_pool.acquire() as conn:
        points_per_order = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_per_order'")
        points_per_referral = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_per_referral'")
        points_to_usd = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_to_usd'")
        redemption_rate = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'redemption_rate'")
        
        return {
            'points_per_order': int(points_per_order) if points_per_order else 1,
            'points_per_referral': int(points_per_referral) if points_per_referral else 1,
            'points_to_usd': int(points_to_usd) if points_to_usd else 100,
            'redemption_rate': int(redemption_rate) if redemption_rate else 100
        }

# ✅ كاش لطلبات الاسترداد المعلقة
@cached(ttl=CACHE_TTL_REDEMPTIONS, key_prefix="pending_redemptions")
async def get_cached_pending_redemptions(db_pool):
    """جلب طلبات الاسترداد المعلقة مع كاش 30 ثانية"""
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM redemption_requests WHERE status = 'pending' ORDER BY created_at")

# ✅ كاش لعدد طلبات الاسترداد المعلقة
@cached(ttl=CACHE_TTL_REDEMPTIONS, key_prefix="pending_count")
async def get_cached_pending_count(db_pool) -> int:
    """جلب عدد طلبات الاسترداد المعلقة مع كاش 30 ثانية"""
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM redemption_requests WHERE status = 'pending'") or 0

# إدارة النقاط
@router.callback_query(F.data == "manage_points")
async def manage_points(callback: types.CallbackQuery, db_pool):
    """عرض لوحة إدارة النقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    settings = await get_cached_points_settings(db_pool)
    pending_count = await get_cached_pending_count(db_pool)
    
    text = (
        "⭐ **إدارة النقاط**\n\n"
        f"**الإعدادات الحالية:**\n"
        f"• نقاط لكل طلب: {settings['points_per_order']}\n"
        f"• نقاط لكل إحالة: {settings['points_per_referral']}\n"
        f"• {settings['points_to_usd']} نقطة = 1 دولار\n"
        f"• {settings['redemption_rate']} نقطة للاسترداد\n\n"
        f"**طلبات الاسترداد المعلقة:** {pending_count}\n"
        f"🕐 {get_formatted_damascus_time()}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⚙️ تعديل الإعدادات", callback_data="edit_points_settings"))
    builder.row(types.InlineKeyboardButton(text="📋 طلبات الاسترداد", callback_data="view_redemptions"))
    builder.row(types.InlineKeyboardButton(text="📊 إحصائيات النقاط", callback_data="points_statistics"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

# إحصائيات النقاط
@router.callback_query(F.data == "points_statistics")
async def points_statistics(callback: types.CallbackQuery, db_pool):
    """عرض إحصائيات النقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        stats = await conn.fetchrow('''
            SELECT 
                COALESCE(SUM(total_points), 0) as total_points,
                COALESCE(SUM(total_points_earned), 0) as total_earned,
                COALESCE(SUM(total_points_redeemed), 0) as total_redeemed,
                COUNT(DISTINCT user_id) as users_with_points,
                COALESCE(AVG(total_points), 0) as avg_points
            FROM users
            WHERE total_points > 0
        ''')
        
        today_stats = await conn.fetchrow('''
            SELECT 
                COALESCE(SUM(CASE WHEN points > 0 THEN points ELSE 0 END), 0) as points_given_today,
                COALESCE(SUM(CASE WHEN points < 0 THEN ABS(points) ELSE 0 END), 0) as points_redeemed_today
            FROM points_history
            WHERE DATE(created_at) = CURRENT_DATE
        ''')
    
    text = (
        f"📊 **إحصائيات النقاط**\n\n"
        f"**إجمالي النقاط:** {stats['total_points']:,.0f}\n"
        f"**نقاط مكتسبة:** {stats['total_earned']:,.0f}\n"
        f"**نقاط مستردة:** {stats['total_redeemed']:,.0f}\n"
        f"**مستخدمين لديهم نقاط:** {stats['users_with_points']}\n"
        f"**متوسط النقاط:** {stats['avg_points']:.1f}\n\n"
        f"**إحصائيات اليوم:**\n"
        f"• نقاط ممنوحة: {today_stats['points_given_today']:,.0f}\n"
        f"• نقاط مستردة: {today_stats['points_redeemed_today']:,.0f}\n"
        f"🕐 {get_formatted_damascus_time()}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 تحديث", callback_data="points_statistics"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_points"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

# تعديل إعدادات النقاط
@router.callback_query(F.data == "edit_points_settings")
async def edit_points_settings(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل إعدادات النقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ عرض الإعدادات الحالية
    settings = await get_cached_points_settings(db_pool)
    
    await callback.message.answer(
        f"⚙️ **تعديل إعدادات النقاط**\n\n"
        f"الإعدادات الحالية:\n"
        f"• نقاط لكل طلب: {settings['points_per_order']}\n"
        f"• نقاط لكل إحالة: {settings['points_per_referral']}\n"
        f"• {settings['points_to_usd']} نقطة = 1 دولار\n"
        f"• {settings['redemption_rate']} نقطة للاسترداد\n\n"
        f"أدخل القيم الجديدة بالصيغة التالية:\n"
        f"`نقاط_الطلب نقاط_الإحالة نقاط_الدولار معدل_الاسترداد`\n\n"
        f"مثال: `1 1 100 100`\n\n"
        f"أو أرسل /cancel للإلغاء",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(PointsStates.waiting_points_settings)

@router.message(PointsStates.waiting_points_settings)
async def save_points_settings(message: types.Message, state: FSMContext, db_pool):
    """حفظ إعدادات النقاط الجديدة"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 4:
            return await message.answer(
                "❌ صيغة غير صحيحة. استخدم: `نقاط_الطلب نقاط_الإحالة نقاط_الدولار معدل_الاسترداد`\n"
                "مثال: `1 1 100 100`"
            )
        
        points_order, points_referral, points_usd, redemption_rate = parts
        
        # التحقق من صحة الأرقام
        try:
            int(points_order)
            int(points_referral)
            int(points_usd)
            int(redemption_rate)
        except ValueError:
            return await message.answer("❌ جميع القيم يجب أن تكون أرقاماً صحيحة")
        
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'points_per_order'", points_order)
            await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'points_per_referral'", points_referral)
            await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'points_to_usd'", points_usd)
            await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'redemption_rate'", redemption_rate)
        
        # ✅ مسح الكاش
        clear_cache("points_settings")
        
        await message.answer(
            f"✅ **تم تحديث إعدادات النقاط بنجاح**\n\n"
            f"القيم الجديدة:\n"
            f"• نقاط لكل طلب: {points_order}\n"
            f"• نقاط لكل إحالة: {points_referral}\n"
            f"• {points_usd} نقطة = 1 دولار\n"
            f"• {redemption_rate} نقطة للاسترداد"
        )
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ **حدث خطأ:** {str(e)}")
        await state.clear()

# طلبات الاسترداد
@router.callback_query(F.data == "view_redemptions")
async def view_redemptions(callback: types.CallbackQuery, db_pool):
    """عرض طلبات الاسترداد المعلقة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    redemptions = await get_cached_pending_redemptions(db_pool)
    
    if not redemptions:
        await callback.answer("📭 لا توجد طلبات استرداد معلقة", show_alert=True)
        return
    
    # ✅ حذف الرسالة الحالية وإرسال الطلبات
    await callback.message.delete()
    
    for r in redemptions:
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ موافقة", callback_data=f"appr_red_{r['id']}"),
            types.InlineKeyboardButton(text="❌ رفض", callback_data=f"reje_red_{r['id']}")
        )
        
        created_at = r['created_at'].strftime('%Y-%m-%d %H:%M') if r['created_at'] else "غير معروف"
        
        await callback.message.answer(
            f"🆔 **طلب استرداد #{r['id']}**\n\n"
            f"👤 **المستخدم:** @{r['username'] or 'غير معروف'}\n"
            f"🆔 **الآيدي:** `{r['user_id']}`\n"
            f"⭐ **النقاط:** {r['points']}\n"
            f"💰 **المبلغ:** ${r['amount_usd']:.2f} ({r['amount_syp']:,.0f} ل.س)\n"
            f"📅 **التاريخ:** {created_at}\n\n"
            f"**الإجراء:**",
            reply_markup=builder.as_markup()
        )

@router.callback_query(F.data.startswith("appr_red_"))
async def approve_redemption(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    """الموافقة على طلب استرداد نقاط"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    start_time = time.time()
    
    try:
        req_id = int(callback.data.split("_")[2])
        
        from database.points import approve_redemption
        from database.core import get_exchange_rate
        
        current_rate = await get_exchange_rate(db_pool)
        success, error = await approve_redemption(db_pool, req_id, callback.from_user.id)
        
        if success:
            async with db_pool.acquire() as conn:
                req = await conn.fetchrow("SELECT * FROM redemption_requests WHERE id = $1", req_id)
            
            # ✅ مسح الكاش
            clear_cache("pending_redemptions")
            clear_cache("pending_count")
            clear_cache("points_settings")
            
            elapsed_time = time.time() - start_time
            
            await safe_edit_message(
                callback.message,
                callback.message.text + f"\n\n✅ **تمت الموافقة على الطلب**\n"
                f"💰 بسعر صرف: {current_rate:,.0f} ل.س\n"
                f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية",
                reply_markup=None
            )
            
            try:
                await bot.send_message(
                    req['user_id'],
                    f"✅ **تمت الموافقة على طلب استرداد النقاط!**\n\n"
                    f"⭐ النقاط: {req['points']}\n"
                    f"💰 المبلغ: {req['amount_syp']:,.0f} ل.س\n"
                    f"💵 بسعر صرف: {current_rate:,.0f} ل.س\n\n"
                    f"تم إضافة المبلغ إلى رصيدك.",
                    parse_mode="Markdown"
                )
                logger.info(f"✅ تم إرسال إشعار موافقة للمستخدم {req['user_id']}")
            except Exception as e:
                logger.error(f"❌ فشل إرسال إشعار للمستخدم {req['user_id']}: {e}")
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
    except Exception as e:
        logger.error(f"❌ خطأ في الموافقة على الاسترداد: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reje_red_"))
async def reject_redemption(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    """رفض طلب استرداد نقاط"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    try:
        req_id = int(callback.data.split("_")[2])
        
        from database.points import reject_redemption
        success, error = await reject_redemption(db_pool, req_id, callback.from_user.id, "رفض من قبل الإدارة")
        
        if success:
            async with db_pool.acquire() as conn:
                req = await conn.fetchrow("SELECT user_id, points FROM redemption_requests WHERE id = $1", req_id)
            
            # ✅ مسح الكاش
            clear_cache("pending_redemptions")
            clear_cache("pending_count")
            
            await safe_edit_message(
                callback.message,
                callback.message.text + "\n\n❌ **تم رفض الطلب**",
                reply_markup=None
            )
            
            try:
                await bot.send_message(
                    req['user_id'],
                    f"❌ **نعتذر، تم رفض طلب استرداد النقاط الخاص بك.**\n\n"
                    f"⭐ النقاط: {req['points']}\n"
                    f"🔸 الأسباب المحتملة:\n"
                    f"• مشكلة في بيانات الطلب\n"
                    f"• رصيد النقاط غير كافي\n"
                    f"• مشكلة فنية\n\n"
                    f"📞 للاستفسار، تواصل مع الدعم.",
                    parse_mode="Markdown"
                )
                logger.info(f"✅ تم إرسال إشعار رفض للمستخدم {req['user_id']}")
            except Exception as e:
                logger.error(f"❌ فشل إرسال إشعار للمستخدم {req['user_id']}: {e}")
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الاسترداد: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# تحديث قائمة الطلبات
@router.callback_query(F.data == "refresh_redemptions")
async def refresh_redemptions(callback: types.CallbackQuery, db_pool):
    """تحديث قائمة طلبات الاسترداد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer("🔄 جاري التحديث...")
    
    # ✅ مسح الكاش
    clear_cache("pending_redemptions")
    clear_cache("pending_count")
    
    # ✅ العودة لعرض الطلبات
    await view_redemptions(callback, db_pool)

# تصدير تقرير النقاط
@router.callback_query(F.data == "export_points_report")
async def export_points_report(callback: types.CallbackQuery, db_pool, bot: Bot):
    """تصدير تقرير النقاط كملف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer("📊 جاري إنشاء التقرير...")
    
    try:
        async with db_pool.acquire() as conn:
            # جلب جميع المستخدمين الذين لديهم نقاط
            users = await conn.fetch('''
                SELECT user_id, username, first_name, total_points, 
                       total_points_earned, total_points_redeemed,
                       vip_level
                FROM users
                WHERE total_points > 0 OR total_points_earned > 0
                ORDER BY total_points DESC
                LIMIT 100
            ''')
            
            # جلب آخر 50 عملية نقاط
            history = await conn.fetch('''
                SELECT ph.*, u.username 
                FROM points_history ph
                JOIN users u ON ph.user_id = u.user_id
                ORDER BY ph.created_at DESC
                LIMIT 50
            ''')
        
        # إنشاء نص التقرير
        report = "📊 **تقرير النقاط التفصيلي**\n\n"
        report += f"تاريخ التقرير: {get_formatted_damascus_time()}\n"
        report += "=" * 50 + "\n\n"
        
        report += "**أكثر المستخدمين نقاطاً:**\n"
        for i, user in enumerate(users[:10], 1):
            username = user['username'] or user['first_name'] or f"ID:{user['user_id']}"
            report += f"{i}. {username} - {user['total_points']} نقطة (VIP {user['vip_level']})\n"
        
        report += "\n**آخر عمليات النقاط:**\n"
        for h in history[:10]:
            action = {
                'order_completed': '✅ شراء',
                'referral': '👥 إحالة',
                'admin_add': '➕ إدارة',
                'redemption': '💰 استرداد'
            }.get(h['action'], h['action'])
            
            username = h['username'] or f"ID:{h['user_id']}"
            date = h['created_at'].strftime('%Y-%m-%d %H:%M')
            report += f"• {username}: {h['points']:+d} نقطة ({action}) - {date}\n"
        
        # إرسال الملف
        from io import BytesIO
        file = BytesIO()
        file.write(report.encode('utf-8'))
        file.seek(0)
        
        filename = f"points_report_{get_formatted_damascus_time().replace(':', '-')}.txt"
        
        await callback.message.answer_document(
            types.BufferedInputFile(file=file.getvalue(), filename=filename),
            caption="✅ تم إنشاء تقرير النقاط"
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في تصدير تقرير النقاط: {e}")
        await callback.answer("❌ فشل إنشاء التقرير", show_alert=True)