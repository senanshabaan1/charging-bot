# admin/users.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from .utils import is_admin, format_message_text, safe_edit_message
from handlers.keyboards import get_cancel_keyboard

logger = logging.getLogger(__name__)
router = Router(name="admin_users")

class UserStates(StatesGroup):
    waiting_user_info = State()
    waiting_balance_amount = State()
    waiting_points_amount = State()

# معلومات المستخدم
@router.callback_query(F.data == "user_info")
async def user_info_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "👤 **أدخل آيدي المستخدم للحصول على معلوماته:**\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(UserStates.waiting_user_info)

@router.message(UserStates.waiting_user_info)
async def user_info_show(message: types.Message, state: FSMContext, db_pool):
    try:
        user_id = int(message.text)
        
        from database import get_user_profile
        profile = await get_user_profile(db_pool, user_id)
        
        if not profile:
            await message.answer("⚠️ **المستخدم غير موجود**")
            await state.clear()
            return
        
        user = profile['user']
        deposits = profile['deposits']
        orders = profile['orders']
        
        join_date = user['created_at'].strftime("%Y-%m-%d %H:%M") if user.get('created_at') else "غير معروف"
        last_active = user['last_activity'].strftime("%Y-%m-%d %H:%M") if user.get('last_activity') else "غير معروف"
        manual_status = " (يدوي)" if user.get('manual_vip') else ""
        
        info_text = (
            f"👤 **معلومات المستخدم**\n\n"
            f"🆔 **الآيدي:** `{user['user_id']}`\n"
            f"👤 **اليوزر:** @{user['username'] or 'غير موجود'}\n"
            f"📝 **الاسم:** {user.get('first_name', '')} {user.get('last_name', '')}\n"
            f"💰 **الرصيد:** {user.get('balance', 0):,.0f} ل.س\n"
            f"⭐ **النقاط:** {user.get('total_points', 0)}\n"
            f"👑 **مستوى VIP:** {user.get('vip_level', 0)}{manual_status}\n"
            f"💰 **إجمالي الإنفاق:** {user.get('total_spent', 0):,.0f} ل.س\n"
            f"🔒 **الحالة:** {'🚫 محظور' if user.get('is_banned') else '✅ نشط'}\n"
            f"📅 **تاريخ التسجيل:** {join_date}\n"
            f"⏰ **آخر نشاط:** {last_active}\n"
            f"🔗 **كود الإحالة:** `{user.get('referral_code', 'لا يوجد')}`\n"
            f"👥 **تمت إحالته بواسطة:** {user.get('referred_by', 'لا يوجد')}\n\n"
            
            f"📊 **إحصائيات الإيداعات:**\n"
            f"• إجمالي الإيداعات: {deposits.get('total_count', 0)} عملية\n"
            f"• إجمالي المبالغ: {deposits.get('total_amount', 0):,.0f} ل.س\n"
            f"• الإيداعات المقبولة: {deposits.get('approved_count', 0)} عملية\n"
            f"• قيمة المقبولة: {deposits.get('approved_amount', 0):,.0f} ل.س\n\n"
            
            f"📊 **إحصائيات الطلبات:**\n"
            f"• إجمالي الطلبات: {orders.get('total_count', 0)} طلب\n"
            f"• إجمالي المبالغ: {orders.get('total_amount', 0):,.0f} ل.س\n"
            f"• الطلبات المكتملة: {orders.get('completed_count', 0)} طلب\n"
            f"• قيمة المكتملة: {orders.get('completed_amount', 0):,.0f} ل.س\n"
            f"• نقاط مكتسبة من الطلبات: {orders.get('total_points_earned', 0)}\n"
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="🔓 فك الحظر" if user.get('is_banned') else "🔒 حظر",
                                       callback_data=f"toggle_ban_{user['user_id']}"),
            types.InlineKeyboardButton(text="💰 تعديل الرصيد", callback_data=f"edit_bal_{user['user_id']}")
        )
        builder.row(
            types.InlineKeyboardButton(text="⭐ إضافة نقاط", callback_data=f"add_points_{user['user_id']}"),
            types.InlineKeyboardButton(text="👑 رفع مستوى VIP", callback_data=f"upgrade_vip_{user['user_id']}")
        )
        builder.row(types.InlineKeyboardButton(text="⬇️ خفض مستوى VIP", callback_data=f"downgrade_vip_{user['user_id']}"))
        
        await message.answer(info_text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await message.answer("⚠️ **الرجاء إدخال آيدي صحيح (أرقام فقط)**")
        await state.clear()
    except Exception as e:
        logger.error(f"خطأ في معلومات المستخدم: {e}")
        await message.answer(f"❌ **حدث خطأ:** {str(e)}")
        await state.clear()

# إضافة نقاط
@router.callback_query(F.data.startswith("add_points_"))
async def add_points_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        user_id = int(callback.data.split("_")[2])
        await state.update_data(target_user=user_id)
        await callback.message.answer(
            f"⭐ **أدخل عدد النقاط لإضافتها للمستخدم {user_id}:**\n\nأو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(UserStates.waiting_points_amount)
    except Exception as e:
        logger.error(f"خطأ في بدء إضافة نقاط: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.message(UserStates.waiting_points_amount)
async def add_points_finalize(message: types.Message, state: FSMContext, db_pool):
    try:
        points = int(message.text)
        if points <= 0:
            return await message.answer("⚠️ يرجى إدخال رقم موجب:", reply_markup=get_cancel_keyboard())
        
        data = await state.get_data()
        user_id = data['target_user']
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT username, total_points FROM users WHERE user_id = $1", user_id)
            if not user:
                return await message.answer("❌ المستخدم غير موجود")
            
            await conn.execute("UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2", points, user_id)
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ''', user_id, points, 'admin_add', f'إضافة نقاط من الأدمن: {points}')
            
            new_total = await conn.fetchval("SELECT total_points FROM users WHERE user_id = $1", user_id)
        
        await message.answer(f"✅ تم إضافة {points} نقطة للمستخدم @{user['username']}\n⭐ الرصيد الجديد: {new_total}")
        
        try:
            await message.bot.send_message(user_id, f"✅ تم إضافة {points} نقطة إلى رصيدك!\n⭐ رصيدك الحالي: {new_total}")
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمستخدم {user_id}: {e}")
        
        await state.clear()
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 100):", reply_markup=get_cancel_keyboard())
    except Exception as e:
        logger.error(f"خطأ في إضافة نقاط: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# تعديل الرصيد
@router.callback_query(F.data.startswith("edit_bal_"))
async def edit_balance_from_info(callback: types.CallbackQuery, state: FSMContext):
    try:
        user_id = int(callback.data.split("_")[2])
        await state.update_data(target_user=user_id)
        await callback.message.answer(
            f"💰 **أدخل الرصيد الجديد للمستخدم {user_id}:**\n\nأو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(UserStates.waiting_balance_amount)
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.message(UserStates.waiting_balance_amount)
async def finalize_add_balance(message: types.Message, state: FSMContext, db_pool):
    try:
        amount = float(message.text)
    except ValueError:
        return await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 5000):", reply_markup=get_cancel_keyboard())
    
    data = await state.get_data()
    user_id = data['target_user']
    
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1, total_deposits = total_deposits + $1 WHERE user_id = $2", amount, user_id)
        user = await conn.fetchrow("SELECT username, balance, total_points FROM users WHERE user_id = $1", user_id)
    
    await message.answer(
        f"✅ **تمت إضافة الرصيد بنجاح**\n\n"
        f"👤 **المستخدم:** {user['username'] or 'بدون اسم'}\n"
        f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
        f"💳 **الرصيد الجديد:** {user['balance']:,.0f} ل.س\n"
        f"⭐ **النقاط:** {user['total_points']}",
        parse_mode="Markdown"
    )
    
    try:
        await message.bot.send_message(
            user_id,
            f"✅ **تم إضافة رصيد إلى حسابك!**\n\n"
            f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
            f"💳 **الرصيد الحالي:** {user['balance']:,.0f} ل.س",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"فشل إرسال إشعار للمستخدم {user_id}: {e}")
    
    await state.clear()

# تبديل حالة الحظر
@router.callback_query(F.data.startswith("toggle_ban_"))
async def toggle_ban_from_info(callback: types.CallbackQuery, db_pool):
    try:
        user_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT is_banned FROM users WHERE user_id = $1", user_id)
            
            if user:
                new_status = not user['is_banned']
                await conn.execute("UPDATE users SET is_banned = $1 WHERE user_id = $2", new_status, user_id)
                
                status_text = "محظور" if new_status else "نشط"
                await callback.message.answer(f"✅ تم تغيير حالة المستخدم إلى: {status_text}")
                
                try:
                    await callback.bot.send_message(
                        user_id,
                        f"⚠️ **تم تغيير حالة حسابك**\n\n"
                        f"الحالة الجديدة: {'🚫 محظور' if new_status else '✅ نشط'}"
                    )
                except:
                    pass
            else:
                await callback.answer("المستخدم غير موجود", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)