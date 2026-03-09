# admin/reset.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import time
import asyncio
from datetime import datetime
from utils import is_admin, is_owner, safe_edit_message, get_formatted_damascus_time
from handlers.keyboards import get_cancel_keyboard, get_confirmation_keyboard
from database.core import get_bot_status, set_bot_status
from cache import clear_cache  # ✅ استيراد الكاش

logger = logging.getLogger(__name__)
router = Router(name="admin_reset")

class ResetStates(StatesGroup):
    waiting_reset_rate = State()
    waiting_confirmation_code = State()  # ✅ خطوة إضافية للأمان

# ✅ كود تأكيد عشوائي للتصفير (يتغير كل مرة)
import random
import string

def generate_confirmation_code() -> str:
    """توليد كود تأكيد عشوائي من 6 أرقام"""
    return ''.join(random.choices(string.digits, k=6))

# تصفير البوت
@router.callback_query(F.data == "reset_bot")
async def reset_bot_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء عملية تصفير البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ التحقق من أن المستخدم هو المالك
    if not is_owner(callback.from_user.id):
        return await callback.answer("⚠️ فقط المالك يمكنه تصفير البوت", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ توليد كود تأكيد عشوائي
    confirm_code = generate_confirmation_code()
    await state.update_data(confirm_code=confirm_code)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="⚠️ نعم، متابعة", callback_data="confirm_reset_step1"),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_del")
    )
    
    await safe_edit_message(
        callback.message,
        f"⚠️ **تحذير: تصفير البوت** ⚠️\n\n"
        f"هذا الإجراء سيقوم بحذف:\n"
        f"• جميع المستخدمين (عدا المشرفين)\n"
        f"• جميع طلبات الشحن\n"
        f"• جميع طلبات التطبيقات\n"
        f"• جميع النقاط وسجل النقاط\n"
        f"• جميع الإحالات\n\n"
        f"**سيتم الاحتفاظ بـ:**\n"
        f"• المشرفين\n"
        f"• المنتجات والأقسام\n"
        f"• خيارات المنتجات\n\n"
        f"**📋 كود التأكيد:** `{confirm_code}`\n"
        f"احتفظ بهذا الكود للخطوة التالية.\n\n"
        f"هل أنت متأكد من متابعة عملية التصفير؟",
        reply_markup=builder.as_markup()
    )
    await state.set_state(ResetStates.waiting_confirmation_code)

@router.callback_query(F.data == "confirm_reset_step1")
async def reset_bot_ask_confirmation(callback: types.CallbackQuery, state: FSMContext):
    """طلب إدخال كود التأكيد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    data = await state.get_data()
    confirm_code = data.get('confirm_code', 'XXXXXX')
    
    await safe_edit_message(
        callback.message,
        f"🔐 **تأكيد تصفير البوت**\n\n"
        f"أدخل كود التأكيد الذي ظهر في الرسالة السابقة:\n"
        f"`{confirm_code}`\n\n"
        f"📝 أرسل الكود الآن:\n\n"
        f"أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )

@router.message(ResetStates.waiting_confirmation_code)
async def verify_confirmation_code(message: types.Message, state: FSMContext):
    """التحقق من كود التأكيد"""
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    correct_code = data.get('confirm_code')
    
    if message.text.strip() != correct_code:
        return await message.answer(
            "❌ كود التأكيد غير صحيح!\n"
            "أعد المحاولة أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
    
    # ✅ كود صحيح - ننتقل لطلب سعر الصرف
    await message.answer(
        "✅ **تم التحقق من الكود بنجاح!**\n\n"
        "💰 **أدخل سعر الصرف الجديد**\n"
        "مثال: 118\n\n"
        "سيتم استخدام هذا السعر بعد تصفير البوت.\n\n"
        "أو أرسل /cancel للإلغاء",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ResetStates.waiting_reset_rate)

@router.message(ResetStates.waiting_reset_rate)
async def execute_reset_bot(message: types.Message, state: FSMContext, db_pool):
    """تنفيذ تصفير البوت بعد التحقق"""
    if not is_admin(message.from_user.id):
        return
    
    # ✅ التحقق من صحة سعر الصرف
    try:
        new_rate = float(message.text.strip())
        if new_rate <= 0:
            return await message.answer(
                "⚠️ سعر الصرف يجب أن يكون أكبر من 0:",
                reply_markup=get_cancel_keyboard()
            )
    except ValueError:
        return await message.answer(
            "⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 118):",
            reply_markup=get_cancel_keyboard()
        )
    
    start_time = time.time()
    
    # ✅ إرسال رسالة تأكيد بدء العملية
    status_msg = await message.answer("⏳ **جاري تصفير البوت...**\nقد تستغرق هذه العملية بضع ثوانٍ.")
    
    from config import ADMIN_ID, MODERATORS
    admin_ids = [ADMIN_ID] + MODERATORS
    admin_ids_str = ','.join([str(id) for id in admin_ids if id])
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():  # ✅ استخدام transaction لضمان التكامل
                
                # 1. حذف بيانات المستخدمين والطلبات
                logger.warning(f"⚠️ بدء تصفير البوت بواسطة {message.from_user.id}")
                
                deleted_counts = {}
                
                # حذف سجل النقاط
                deleted_counts['points_history'] = await conn.fetchval("DELETE FROM points_history RETURNING COUNT(*)") or 0
                
                # حذف طلبات الاسترداد
                deleted_counts['redemption_requests'] = await conn.fetchval("DELETE FROM redemption_requests RETURNING COUNT(*)") or 0
                
                # حذف طلبات الشحن
                deleted_counts['deposit_requests'] = await conn.fetchval("DELETE FROM deposit_requests RETURNING COUNT(*)") or 0
                
                # حذف الطلبات
                deleted_counts['orders'] = await conn.fetchval("DELETE FROM orders RETURNING COUNT(*)") or 0
                
                # ✅ إعادة ضبط sequences للجداول التي تم حذفها فقط
                sequences = [
                    "orders_id_seq",
                    "deposit_requests_id_seq", 
                    "redemption_requests_id_seq",
                    "points_history_id_seq"
                ]
                
                for seq in sequences:
                    try:
                        await conn.execute(f"ALTER SEQUENCE {seq} RESTART WITH 1")
                        logger.info(f"✅ تم تصفير {seq}")
                    except Exception as e:
                        logger.warning(f"⚠️ لم يتم تصفير {seq}: {e}")
                
                # حذف المستخدمين مع الاحتفاظ بالمشرفين
                if admin_ids_str:
                    # حذف المستخدمين العاديين
                    deleted_counts['users'] = await conn.fetchval(
                        f"DELETE FROM users WHERE user_id NOT IN ({admin_ids_str}) RETURNING COUNT(*)"
                    ) or 0
                    
                    # تصفير بيانات المشرفين
                    for admin_id in admin_ids:
                        if admin_id:
                            await conn.execute('''
                                UPDATE users 
                                SET balance = 0, total_points = 0, total_deposits = 0, total_orders = 0,
                                    referral_count = 0, referral_earnings = 0, total_points_earned = 0,
                                    total_points_redeemed = 0, vip_level = 0, total_spent = 0,
                                    discount_percent = 0, manual_vip = FALSE, last_activity = CURRENT_TIMESTAMP
                                WHERE user_id = $1
                            ''', admin_id)
                else:
                    deleted_counts['users'] = await conn.fetchval("DELETE FROM users RETURNING COUNT(*)") or 0
                
                # تحديث الإعدادات
                await conn.execute('''
                    INSERT INTO bot_settings (key, value, description) 
                    VALUES ('usd_to_syp', $1, 'سعر صرف الدولار مقابل الليرة')
                    ON CONFLICT (key) DO UPDATE SET value = $1
                ''', str(new_rate))
                
                await conn.execute("UPDATE bot_settings SET value = '1' WHERE key IN ('points_per_order', 'points_per_referral')")
                await conn.execute("UPDATE bot_settings SET value = '100' WHERE key = 'redemption_rate'")
                
                # إعادة ضبط مستويات VIP (تبقى نفسها)
                await conn.execute('''
                    INSERT INTO vip_levels (level, name, min_spent, discount_percent, icon) 
                    VALUES 
                        (0, 'VIP 0', 0, 0, '⚪'),
                        (1, 'VIP 1', 3500, 1, '🔵'),
                        (2, 'VIP 2', 6500, 2, '🟣'),
                        (3, 'VIP 3', 12000, 3, '🟡')
                    ON CONFLICT (level) DO UPDATE SET 
                        min_spent = EXCLUDED.min_spent,
                        discount_percent = EXCLUDED.discount_percent,
                        icon = EXCLUDED.icon;
                ''')
        
        # ✅ مسح كل الكاش بعد التصفير
        clear_cache()
        
        elapsed_time = time.time() - start_time
        
        # ✅ حذف رسالة "جاري التصفير"
        await status_msg.delete()
        
        # ✅ إرسال نتيجة التصفير
        await message.answer(
            f"✅ **تم تصفير البوت بنجاح!**\n\n"
            f"📊 **إحصائيات الحذف:**\n"
            f"• 👥 المستخدمين: {deleted_counts.get('users', 0)}\n"
            f"• 💰 طلبات الشحن: {deleted_counts.get('deposit_requests', 0)}\n"
            f"• 📦 الطلبات: {deleted_counts.get('orders', 0)}\n"
            f"• ⭐ سجل النقاط: {deleted_counts.get('points_history', 0)}\n"
            f"• 🎁 طلبات الاسترداد: {deleted_counts.get('redemption_requests', 0)}\n\n"
            f"💰 **سعر الصرف الجديد:** {new_rate} ل.س\n"
            f"⭐ نقاط لكل طلب: 1\n"
            f"🔗 نقاط لكل إحالة: 1\n"
            f"🎁 100 نقطة = 1 دولار\n"
            f"👑 **نظام VIP:**\n"
            f"• VIP 1: 3500 ل.س - خصم 1%\n"
            f"• VIP 2: 6500 ل.س - خصم 2%\n"
            f"• VIP 3: 12000 ل.س - خصم 3%\n\n"
            f"✅ **المنتجات والأقسام والخيارات لم يتم حذفها**\n"
            f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية\n\n"
            f"البوت الآن جاهز للبدء من جديد!",
            parse_mode="Markdown"
        )
        
        # ✅ تسجيل العملية في ملف logs
        logger.warning(
            f"✅ تم تصفير البوت بواسطة {message.from_user.id} "
            f"(حذف {deleted_counts.get('users', 0)} مستخدم، {deleted_counts.get('orders', 0)} طلب) "
            f"في {elapsed_time:.2f} ثانية"
        )
        
        # ✅ إشعار المشرفين الآخرين
        from config import MODERATORS
        for admin_id in MODERATORS:
            if admin_id and admin_id != message.from_user.id:
                try:
                    await message.bot.send_message(
                        admin_id,
                        f"⚠️ **تم تصفير البوت**\n\n"
                        f"👤 تم التنفيذ بواسطة: @{message.from_user.username or 'مشرف'}\n"
                        f"💰 سعر الصرف الجديد: {new_rate} ل.س\n"
                        f"🕐 وقت التنفيذ: {get_formatted_damascus_time()}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"❌ خطأ في تصفير البوت: {e}")
        await message.answer(
            f"❌ **حدث خطأ أثناء تصفير البوت**\n\n"
            f"الخطأ: {str(e)}\n\n"
            f"يرجى المحاولة مرة أخرى أو التواصل مع المطور.",
            parse_mode="Markdown"
        )
        await state.clear()

@router.callback_query(F.data == "cancel_del")
async def cancel_action(callback: types.CallbackQuery, state: FSMContext):
    """إلغاء عملية التصفير"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await state.clear()
    await safe_edit_message(callback.message, "✅ تم إلغاء عملية التصفير.")


