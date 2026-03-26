# admin/reset.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from utils import is_admin
from database.core import get_bot_status, set_bot_status, update_exchange_rate
from utils import get_formatted_damascus_time

logger = logging.getLogger(__name__)
router = Router(name="admin_reset")

class ResetStates(StatesGroup):
    waiting_purchase_rate = State()   # سعر الشراء (مخفي)
    waiting_deposit_rate = State()    # سعر الإيداع (ظاهر)
    waiting_points_rate = State()     # سعر النقاط
    confirm_reset = State()


# تصفير البوت
@router.callback_query(F.data == "reset_bot")
async def reset_bot_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="⚠️ نعم، تصفير البوت", callback_data="confirm_reset_start"),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_reset")
    )
    
    await callback.message.edit_text(
        "⚠️ **تحذير: تصفير البوت** ⚠️\n\n"
        "هذا الإجراء سيقوم بحذف:\n"
        "• جميع المستخدمين (عدا المشرفين)\n"
        "• جميع طلبات الشحن\n"
        "• جميع طلبات التطبيقات\n"
        "• جميع النقاط وسجل النقاط\n"
        "• جميع الإحالات\n\n"
        "**سيتم الاحتفاظ بـ:**\n"
        "• المشرفين\n"
        "• المنتجات والأقسام\n"
        "• خيارات المنتجات\n"
        "• أسعار الصرف (سيطلب منك إدخالها)\n\n"
        "هل أنت متأكد؟",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "confirm_reset_start")
async def reset_bot_ask_purchase_rate(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 1: طلب سعر الشراء (مخفي)"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await callback.message.edit_text(
        "🔒 **الخطوة 1/3: سعر الشراء (مخفي)**\n\n"
        "⚠️ **هذا السعر لا يظهر للمستخدمين!**\n"
        "يستخدم لحساب أسعار الخدمات داخلياً.\n\n"
        "💰 **أدخل سعر الشراء الجديد:**\n"
        "مثال: 118\n\n"
        "أو أرسل /cancel للإلغاء",
        parse_mode="Markdown"
    )
    await state.set_state(ResetStates.waiting_purchase_rate)


@router.message(ResetStates.waiting_purchase_rate)
async def get_purchase_rate(message: types.Message, state: FSMContext):
    """استلام سعر الشراء"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        purchase_rate = float(message.text.strip().replace(',', ''))
        if purchase_rate <= 0:
            raise ValueError
    except:
        return await message.answer(
            "⚠️ خطأ! يرجى إدخال رقم صحيح أكبر من 0 (مثال: 118):",
            parse_mode="Markdown"
        )
    
    await state.update_data(purchase_rate=purchase_rate)
    
    await message.answer(
        "💳 **الخطوة 2/3: سعر الإيداع (ظاهر للمستخدم)**\n\n"
        "💰 **أدخل سعر الإيداع الجديد:**\n"
        "(هذا السعر سيظهر للمستخدمين عند الشحن)\n"
        "مثال: 125\n\n"
        "أو أرسل /cancel للإلغاء",
        parse_mode="Markdown"
    )
    await state.set_state(ResetStates.waiting_deposit_rate)


@router.message(ResetStates.waiting_deposit_rate)
async def get_deposit_rate(message: types.Message, state: FSMContext):
    """استلام سعر الإيداع"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        deposit_rate = float(message.text.strip().replace(',', ''))
        if deposit_rate <= 0:
            raise ValueError
    except:
        return await message.answer(
            "⚠️ خطأ! يرجى إدخال رقم صحيح أكبر من 0 (مثال: 125):",
            parse_mode="Markdown"
        )
    
    await state.update_data(deposit_rate=deposit_rate)
    
    await message.answer(
        "⭐ **الخطوة 3/3: سعر النقاط**\n\n"
        "💰 **أدخل سعر النقاط الجديد:**\n"
        "(هذا السعر يستخدم لحساب قيمة النقاط عند الاسترداد)\n"
        "مثال: 120\n\n"
        "أو أرسل /cancel للإلغاء",
        parse_mode="Markdown"
    )
    await state.set_state(ResetStates.waiting_points_rate)


@router.message(ResetStates.waiting_points_rate)
async def get_points_rate(message: types.Message, state: FSMContext):
    """استلام سعر النقاط وتأكيد التصفير"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        points_rate = float(message.text.strip().replace(',', ''))
        if points_rate <= 0:
            raise ValueError
    except:
        return await message.answer(
            "⚠️ خطأ! يرجى إدخال رقم صحيح أكبر من 0 (مثال: 120):",
            parse_mode="Markdown"
        )
    
    await state.update_data(points_rate=points_rate)
    
    data = await state.get_data()
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم، تصفير البوت", callback_data="confirm_reset_final"),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_reset")
    )
    
    await message.answer(
        f"⚠️ **تأكيد تصفير البوت**\n\n"
        f"**الأسعار الجديدة:**\n"
        f"🔒 سعر الشراء (مخفي): {data['purchase_rate']:,.0f} ل.س\n"
        f"💳 سعر الإيداع (ظاهر): {data['deposit_rate']:,.0f} ل.س\n"
        f"⭐ سعر النقاط: {data['points_rate']:,.0f} ل.س\n\n"
        f"**سيتم حذف:**\n"
        f"• جميع المستخدمين (عدا المشرفين)\n"
        f"• جميع الطلبات والإيداعات\n"
        f"• جميع النقاط والسجلات\n\n"
        f"هل أنت متأكد من التصفير؟",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(ResetStates.confirm_reset)


@router.callback_query(F.data == "confirm_reset_final")
async def execute_reset_bot(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """تنفيذ تصفير البوت مع الأسعار الجديدة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer("⏳ جاري تصفير البوت...")
    
    data = await state.get_data()
    purchase_rate = data.get('purchase_rate', 118)
    deposit_rate = data.get('deposit_rate', 118)
    points_rate = data.get('points_rate', 118)
    
    from config import ADMIN_ID, MODERATORS
    admin_ids = [ADMIN_ID] + MODERATORS
    admin_ids_str = ','.join([str(id) for id in admin_ids if id])
    
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # ✅ حذف بيانات المستخدمين والطلبات فقط
            await conn.execute("DELETE FROM points_history")
            await conn.execute("DELETE FROM redemption_requests")
            await conn.execute("DELETE FROM deposit_requests")
            await conn.execute("DELETE FROM orders")
            await conn.execute("DELETE FROM offer_usage")  # ✅ حذف سجل العروض
            
            # ✅ إعادة ضبط sequences
            sequences = [
                "orders_id_seq",
                "deposit_requests_id_seq", 
                "redemption_requests_id_seq",
                "points_history_id_seq",
                "offer_usage_id_seq"
            ]
            
            for seq in sequences:
                try:
                    await conn.execute(f"ALTER SEQUENCE {seq} RESTART WITH 1")
                    logger.info(f"✅ تم تصفير {seq}")
                except Exception as e:
                    logger.warning(f"⚠️ لم يتم تصفير {seq}: {e}")
            
            # ✅ حذف المستخدمين مع الاحتفاظ بالمشرفين
            if admin_ids_str:
                await conn.execute(f"DELETE FROM users WHERE user_id NOT IN ({admin_ids_str})")
                
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
                await conn.execute("DELETE FROM users")
            
            # ✅ تحديث أسعار الصرف الثلاثة
            await update_exchange_rate(db_pool, 'purchase', purchase_rate, callback.from_user.id)
            await update_exchange_rate(db_pool, 'deposit', deposit_rate, callback.from_user.id)
            await update_exchange_rate(db_pool, 'points', points_rate, callback.from_user.id)
            
            # ✅ تحديث إعدادات النقاط
            await conn.execute("UPDATE bot_settings SET value = '1' WHERE key = 'points_per_order'")
            await conn.execute("UPDATE bot_settings SET value = '1' WHERE key = 'points_per_referral'")
            await conn.execute("UPDATE bot_settings SET value = '100' WHERE key = 'redemption_rate'")
            
            # ✅ إعادة ضبط مستويات VIP
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
            
            # ✅ إعادة ضبط العروض (تعطيل جميع العروض النشطة)
            await conn.execute("UPDATE global_offers SET is_active = FALSE")
            await conn.execute("UPDATE deposit_bonuses SET is_active = FALSE")
    
    await state.clear()
    
    await callback.message.edit_text(
        f"✅ **تم تصفير البوت بنجاح!**\n\n"
        f"💰 **أسعار الصرف الجديدة:**\n"
        f"🔒 سعر الشراء (مخفي): {purchase_rate:,.0f} ل.س\n"
        f"💳 سعر الإيداع (ظاهر): {deposit_rate:,.0f} ل.س\n"
        f"⭐ سعر النقاط: {points_rate:,.0f} ل.س\n\n"
        f"⭐ **إعدادات النقاط:**\n"
        f"• نقاط لكل طلب: 1\n"
        f"• نقاط لكل إحالة: 1\n"
        f"• {100} نقطة = 1 دولار\n\n"
        f"👑 **نظام VIP الجديد:**\n"
        f"• VIP 1: 3500 ل.س - خصم 1%\n"
        f"• VIP 2: 6500 ل.س - خصم 2%\n"
        f"• VIP 3: 12000 ل.س - خصم 3%\n\n"
        f"✅ **المنتجات والخيارات والأقسام لم يتم حذفها**\n"
        f"✅ **تم تعطيل جميع العروض النشطة**\n\n"
        f"البوت الآن جاهز للبدء من جديد!",
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "cancel_reset")
async def cancel_reset(callback: types.CallbackQuery, state: FSMContext):
    """إلغاء عملية التصفير"""
    await callback.answer()
    await state.clear()
    
    from admin.main import back_to_admin_panel
    await back_to_admin_panel(callback, callback.bot.db_pool)
