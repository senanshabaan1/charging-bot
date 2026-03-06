# admin/settings.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import logging
from config import ADMIN_ID, MODERATORS
from handlers.keyboards import get_cancel_keyboard
from .utils import is_admin, format_message_text, safe_edit_message, format_amount
logger = logging.getLogger(__name__)
router = Router(name="admin_settings")

class SettingsStates(StatesGroup):
    waiting_new_rate = State()
    waiting_maintenance_msg = State()
    waiting_new_syriatel_numbers = State()

# تشغيل/إيقاف البوت
@router.callback_query(F.data == "toggle_bot")
async def toggle_bot(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_bot_status, set_bot_status
    from handlers.middleware import refresh_bot_status_cache
    
    current_status = await get_bot_status(db_pool)
    new_status = not current_status
    await set_bot_status(db_pool, new_status)
    await refresh_bot_status_cache(db_pool)
    
    status_text = "🟢 يعمل" if new_status else "🔴 متوقف"
    action_text = "تشغيل" if new_status else "إيقاف"
    
    await callback.message.edit_text(f"✅ تم {action_text} البوت بنجاح\n\nالحالة الآن: {status_text}")
    
    # إشعار المشرفين
    admin_ids = [ADMIN_ID] + MODERATORS
    for admin_id in admin_ids:
        if admin_id and admin_id != callback.from_user.id:
            try:
                await callback.bot.send_message(
                    admin_id,
                    f"ℹ️ تم {action_text} البوت بواسطة @{callback.from_user.username or 'مشرف'}"
                )
            except:
                pass

# رسالة الصيانة
@router.callback_query(F.data == "edit_maintenance")
async def edit_maintenance_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.answer(
        "📝 أرسل رسالة الصيانة الجديدة:\n\n"
        "(هذه الرسالة ستظهر للمستخدمين عند إيقاف البوت)\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(SettingsStates.waiting_maintenance_msg)

@router.message(SettingsStates.waiting_maintenance_msg)
async def save_maintenance_message(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE bot_settings SET value = $1, updated_at = CURRENT_TIMESTAMP WHERE key = 'maintenance_message'",
            message.text
        )
    
    await message.answer("✅ تم تحديث رسالة الصيانة بنجاح")
    await state.clear()

# أرقام سيرياتل
@router.callback_query(F.data == "edit_syriatel")
async def edit_syriatel_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from config import SYRIATEL_NUMS
    current_nums = "\n".join([f"{i+1}. `{num}`" for i, num in enumerate(SYRIATEL_NUMS)])
    
    text = (
        f"📞 **أرقام سيرياتل كاش الحالية:**\n\n"
        f"{current_nums}\n\n"
        f"**أدخل الأرقام الجديدة** (كل رقم في سطر منفصل):\n"
        f"مثال:\n74091109\n63826779\n\n"
        f"أو أرسل /cancel للإلغاء"
    )
    
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=get_cancel_keyboard())
    await state.set_state(SettingsStates.waiting_new_syriatel_numbers)

@router.message(SettingsStates.waiting_new_syriatel_numbers)
async def save_syriatel_numbers(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    numbers = [line.strip() for line in message.text.split('\n') if line.strip()]
    from database import set_syriatel_numbers
    success = await set_syriatel_numbers(db_pool, numbers)
    
    if success:
        import config
        config.SYRIATEL_NUMS = numbers
        text = "✅ **تم تحديث أرقام سيرياتل كاش بنجاح!**\n\nالأرقام الجديدة:\n"
        for i, num in enumerate(numbers, 1):
            text += f"{i}. `{num}`\n"
    else:
        text = "❌ **فشل تحديث الأرقام**"
    
    await message.answer(text, parse_mode="Markdown")
    await state.clear()

# سعر الصرف
@router.callback_query(F.data == "edit_rate")
async def start_edit_rate(callback: types.CallbackQuery, state: FSMContext, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_exchange_rate
    current_rate = await get_exchange_rate(db_pool)
    
    await callback.message.answer(
        f"💵 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س\n\n"
        f"📝 **أدخل السعر الجديد:**\n\n"
        f"أو أرسل /cancel للإلغاء",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(SettingsStates.waiting_new_rate)

@router.message(SettingsStates.waiting_new_rate)
async def save_new_rate(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_rate = float(message.text)
        if new_rate <= 0:
            return await message.answer("⚠️ يرجى إدخال رقم موجب:", reply_markup=get_cancel_keyboard())
        
        from database import set_exchange_rate
        await set_exchange_rate(db_pool, new_rate)
        
        import config
        config.USD_TO_SYP = new_rate
        
        await message.answer(f"✅ تم تحديث سعر الصرف إلى {new_rate}")
        
        for mod_id in MODERATORS:
            if mod_id and mod_id != message.from_user.id:
                try:
                    await message.bot.send_message(mod_id, f"ℹ️ تم تغيير السعر إلى {new_rate}")
                except:
                    pass
        
        await state.clear()
        
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 118):", reply_markup=get_cancel_keyboard())