# admin/reset.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from utils import is_admin
from handlers.keyboards import get_cancel_keyboard
from database.core import get_bot_status, set_bot_status
logger = logging.getLogger(__name__)
router = Router(name="admin_reset")

class ResetStates(StatesGroup):
    waiting_reset_rate = State()

# تصفير البوت
@router.callback_query(F.data == "reset_bot")
async def reset_bot_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="⚠️ نعم، تصفير البوت", callback_data="confirm_reset"),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_del")
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
        "• خيارات المنتجات\n\n"
        "هل أنت متأكد؟",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "confirm_reset")
async def reset_bot_ask_rate(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💰 **أدخل سعر الصرف الجديد**\n"
        "مثال: 118\n\n"
        "سيتم استخدام هذا السعر بعد تصفير البوت.\n\n"
        "أو أرسل /cancel للإلغاء",
        parse_mode="Markdown"
    )
    await state.set_state(ResetStates.waiting_reset_rate)

@router.message(ResetStates.waiting_reset_rate)
async def execute_reset_bot(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_rate = float(message.text)
    except ValueError:
        return await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 118):", reply_markup=get_cancel_keyboard())
    
    from config import ADMIN_ID, MODERATORS
    admin_ids = [ADMIN_ID] + MODERATORS
    admin_ids_str = ','.join([str(id) for id in admin_ids if id])
    
    async with db_pool.acquire() as conn:
        # ✅ حذف بيانات المستخدمين والطلبات فقط
        await conn.execute("DELETE FROM points_history")
        await conn.execute("DELETE FROM redemption_requests")
        await conn.execute("DELETE FROM deposit_requests")
        await conn.execute("DELETE FROM orders")
        
        # ✅ لا نحذف product_options ولا applications
        # await conn.execute("DELETE FROM product_options")  # ❌ محذوف
        # await conn.execute("DELETE FROM applications")     # ❌ محذوف
        
        # ✅ إعادة ضبط sequences للجداول التي تم حذفها فقط
        sequences = [
            "orders_id_seq",
            "deposit_requests_id_seq", 
            "redemption_requests_id_seq",
            "points_history_id_seq"
            # "product_options_id_seq",  # ❌ محذوف
            # "applications_id_seq",      # ❌ محذوف
            # "categories_id_seq"         # ❌ محذوف (الأقسام تبقى)
        ]
        
        for seq in sequences:
            try:
                await conn.execute(f"ALTER SEQUENCE {seq} RESTART WITH 1")
                logger.info(f"✅ تم تصفير {seq}")
            except Exception as e:
                logger.warning(f"⚠️ لم يتم تصفير {seq}: {e}")
        
        # حذف المستخدمين مع الاحتفاظ بالمشرفين
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
    
    await message.answer(
        f"✅ **تم تصفير البوت بنجاح!**\n\n"
        f"💰 سعر الصرف الجديد: {new_rate} ل.س\n"
        f"⭐ نقاط لكل طلب: 1\n"
        f"🔗 نقاط لكل إحالة: 1\n"
        f"🎁 100 نقطة = 1 دولار\n"
        f"👑 **نظام VIP الجديد:**\n"
        f"• VIP 1: 3500 ل.س - خصم 1%\n"
        f"• VIP 2: 6500 ل.س - خصم 2%\n"
        f"• VIP 3: 12000 ل.س - خصم 3%\n\n"
        f"✅ **المنتجات والخيارات والأقسام لم يتم حذفها**\n\n"
        f"البوت الآن جاهز للبدء من جديد!",
        parse_mode="Markdown"
    )
    await state.clear()

@router.callback_query(F.data == "cancel_del")
async def cancel_action(callback: types.CallbackQuery):
    await callback.message.edit_text("✅ تم الإلغاء.")
