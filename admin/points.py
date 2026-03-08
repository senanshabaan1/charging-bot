# admin/points.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from utils import is_admin, format_amount
from handlers.keyboards import get_cancel_keyboard

logger = logging.getLogger(__name__)
router = Router(name="admin_points")

class PointsStates(StatesGroup):
    waiting_points_settings = State()

# إدارة النقاط
@router.callback_query(F.data == "manage_points")
async def manage_points(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        points_per_order = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_per_order'")
        points_per_referral = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_per_referral'")
        points_to_usd = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_to_usd'")
        pending_redemptions = await conn.fetch("SELECT * FROM redemption_requests WHERE status = 'pending' ORDER BY created_at")
    
    kb = [
        [types.InlineKeyboardButton(text="⚙️ تعديل إعدادات النقاط", callback_data="edit_points_settings")],
        [types.InlineKeyboardButton(text="📋 طلبات الاسترداد", callback_data="view_redemptions")],
        [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin")]
    ]
    
    text = (
        "⭐ **إدارة النقاط**\n\n"
        f"**الإعدادات الحالية:**\n"
        f"• نقاط لكل طلب: {points_per_order or 5}\n"
        f"• نقاط لكل إحالة: {points_per_referral or 5}\n"
        f"• {points_to_usd or 100} نقطة = 1 دولار\n\n"
        f"**طلبات الاسترداد المعلقة:** {len(pending_redemptions)}"
    )
    
    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

# تعديل إعدادات النقاط
@router.callback_query(F.data == "edit_points_settings")
async def edit_points_settings(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.answer(
        "⚙️ **تعديل إعدادات النقاط**\n\n"
        "أدخل القيم الجديدة بالصيغة التالية:\n"
        "`نقاط_الطلب نقاط_الإحالة نقاط_الدولار`\n\n"
        "مثال: `1 1 100`\n\n"
        "أو أرسل /cancel للإلغاء",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(PointsStates.waiting_points_settings)

@router.message(PointsStates.waiting_points_settings)
async def save_points_settings(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            return await message.answer("❌ صيغة غير صحيحة. استخدم: `نقاط_الطلب نقاط_الإحالة نقاط_الدولار`")
        
        points_order, points_referral, points_usd = parts
        
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'points_per_order'", points_order)
            await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'points_per_referral'", points_referral)
            await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'points_to_usd'", points_usd)
        
        await message.answer("✅ **تم تحديث إعدادات النقاط بنجاح**")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ **حدث خطأ:** {str(e)}")
        await state.clear()

# طلبات الاسترداد
@router.callback_query(F.data == "view_redemptions")
async def view_redemptions(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        redemptions = await conn.fetch("SELECT * FROM redemption_requests WHERE status = 'pending' ORDER BY created_at")
    
    if not redemptions:
        await callback.answer("لا توجد طلبات استرداد معلقة", show_alert=True)
        return
    
    for r in redemptions:
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ موافقة", callback_data=f"appr_red_{r['id']}"),
            types.InlineKeyboardButton(text="❌ رفض", callback_data=f"reje_red_{r['id']}")
        )
        
        await callback.message.answer(
            f"🆔 **طلب استرداد #{r['id']}**\n\n"
            f"👤 **المستخدم:** @{r['username'] or 'غير معروف'}\n"
            f"🆔 **الآيدي:** `{r['user_id']}`\n"
            f"⭐ **النقاط:** {r['points']}\n"
            f"💰 **المبلغ:** {r['amount_usd']}$ ({r['amount_syp']:,.0f} ل.س)\n"
            f"📅 **التاريخ:** {r['created_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
            f"**الإجراء:**",
            reply_markup=builder.as_markup()
        )

@router.callback_query(F.data.startswith("appr_red_"))
async def approve_redemption(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    try:
        req_id = int(callback.data.split("_")[2])
        
        from database.points import approve_redemption, reject_redemption
        from database.core import get_exchange_rate
        current_rate = await get_exchange_rate(db_pool)
        success, error = await approve_redemption(db_pool, req_id, callback.from_user.id)
        
        if success:
            async with db_pool.acquire() as conn:
                req = await conn.fetchrow("SELECT * FROM redemption_requests WHERE id = $1", req_id)
            
            await callback.answer("✅ تمت الموافقة على الطلب")
            await callback.message.edit_text(
                callback.message.text + f"\n\n✅ **تمت الموافقة على الطلب**\n💰 بسعر صرف: {current_rate:,.0f} ل.س",
                reply_markup=None
            )
            
            try:
                await bot.send_message(
                    req['user_id'],
                    f"✅ **تمت الموافقة على طلب استرداد النقاط!**\n\n"
                    f"⭐ النقاط: {req['points']}\n"
                    f"💰 المبلغ: {req['amount_syp']:,.0f} ل.س\n"
                    f"💵 بسعر صرف: {current_rate:,.0f} ل.س\n\n"
                    f"تم إضافة المبلغ إلى رصيدك."
                )
            except:
                pass
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
    except Exception as e:
        logger.error(f"❌ خطأ في الموافقة على الاسترداد: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reje_red_"))
async def reject_redemption(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    try:
        req_id = int(callback.data.split("_")[2])
        
        from database import reject_redemption
        success, error = await reject_redemption(db_pool, req_id, callback.from_user.id, "رفض من قبل الإدارة")
        
        if success:
            await callback.answer("❌ تم رفض الطلب")
            await callback.message.edit_text(
                callback.message.text + "\n\n❌ **تم رفض الطلب**",
                reply_markup=None
            )
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الاسترداد: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)