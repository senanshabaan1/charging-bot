# admin/settings.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import logging
import time
from typing import Optional, List
from config import ADMIN_ID, MODERATORS
from handlers.keyboards import get_confirmation_keyboard, get_cancel_keyboard
from utils import is_admin, is_owner, safe_edit_message, format_amount, get_formatted_damascus_time
from cache import cached, clear_cache  # ✅ استيراد الكاش

# ✅ استيراد دوال قاعدة البيانات من core.py (التعديل هنا)
from database.core import (
    get_exchange_rate, 
    set_exchange_rate,
    get_bot_status, 
    set_bot_status, 
    get_syriatel_numbers, 
    set_syriatel_numbers,
    get_maintenance_message
)
from handlers.middleware import refresh_bot_status_cache

logger = logging.getLogger(__name__)
router = Router(name="admin_settings")

class SettingsStates(StatesGroup):
    waiting_new_rate = State()
    waiting_maintenance_msg = State()
    waiting_new_syriatel_numbers = State()

# ✅ ثوابت للأداء
CACHE_TTL_RATE = 30  # 30 ثانية
CACHE_TTL_SYRIATEL = 120  # دقيقتين
CACHE_TTL_MAINTENANCE = 60  # دقيقة

# ✅ كاش لسعر الصرف
@cached(ttl=CACHE_TTL_RATE, key_prefix="exchange_rate")
async def get_cached_exchange_rate(db_pool) -> float:
    """جلب سعر الصرف مع كاش 30 ثانية"""
    return await get_exchange_rate(db_pool)

# ✅ كاش لأرقام سيرياتل
@cached(ttl=CACHE_TTL_SYRIATEL, key_prefix="syriatel_numbers")
async def get_cached_syriatel_numbers(db_pool) -> List[str]:
    """جلب أرقام سيرياتل مع كاش دقيقتين"""
    return await get_syriatel_numbers(db_pool)

# ✅ كاش لرسالة الصيانة
@cached(ttl=CACHE_TTL_MAINTENANCE, key_prefix="maintenance_message")
async def get_cached_maintenance_message(db_pool) -> str:
    """جلب رسالة الصيانة مع كاش دقيقة"""
    return await get_maintenance_message(db_pool)

# ✅ كاش لحالة البوت
@cached(ttl=30, key_prefix="bot_status")
async def get_cached_bot_status(db_pool) -> bool:
    """جلب حالة البوت مع كاش 30 ثانية"""
    return await get_bot_status(db_pool)

# تشغيل/إيقاف البوت
@router.callback_query(F.data == "toggle_bot")
async def toggle_bot(callback: types.CallbackQuery, db_pool):
    """تشغيل أو إيقاف البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ التحقق من أن المستخدم هو المالك
    if not is_owner(callback.from_user.id):
        return await callback.answer("⚠️ فقط المالك يمكنه تشغيل/إيقاف البوت", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    start_time = time.time()
    
    from database import get_bot_status, set_bot_status
    from handlers.middleware import refresh_bot_status_cache
    
    current_status = await get_cached_bot_status(db_pool)
    new_status = not current_status
    
    await set_bot_status(db_pool, new_status)
    await refresh_bot_status_cache(db_pool)
    
    # ✅ مسح الكاش
    clear_cache("bot_status")
    
    status_text = "🟢 يعمل" if new_status else "🔴 متوقف"
    action_text = "تشغيل" if new_status else "إيقاف"
    
    elapsed_time = time.time() - start_time
    
    await safe_edit_message(
        callback.message,
        f"✅ تم {action_text} البوت بنجاح\n\n"
        f"الحالة الآن: {status_text}\n"
        f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
    )
    
    # إشعار المشرفين
    admin_ids = [ADMIN_ID] + MODERATORS
    for admin_id in admin_ids:
        if admin_id and admin_id != callback.from_user.id:
            try:
                await callback.bot.send_message(
                    admin_id,
                    f"ℹ️ تم {action_text} البوت بواسطة @{callback.from_user.username or 'مشرف'}\n"
                    f"🕐 {get_formatted_damascus_time()}",
                    parse_mode="Markdown"
                )
            except:
                pass

# رسالة الصيانة
@router.callback_query(F.data == "edit_maintenance")
async def edit_maintenance_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل رسالة الصيانة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ عرض الرسالة الحالية
    current_msg = await get_cached_maintenance_message(db_pool)
    
    await callback.message.answer(
        f"📝 **تعديل رسالة الصيانة**\n\n"
        f"الرسالة الحالية:\n`{current_msg}`\n\n"
        f"أرسل رسالة الصيانة الجديدة:\n\n"
        f"(هذه الرسالة ستظهر للمستخدمين عند إيقاف البوت)\n\n"
        f"أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(SettingsStates.waiting_maintenance_msg)

@router.message(SettingsStates.waiting_maintenance_msg)
async def save_maintenance_message(message: types.Message, state: FSMContext, db_pool):
    """حفظ رسالة الصيانة الجديدة"""
    if not is_admin(message.from_user.id):
        return
    
    start_time = time.time()
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE bot_settings SET value = $1, updated_at = CURRENT_TIMESTAMP WHERE key = 'maintenance_message'",
            message.text
        )
    
    # ✅ مسح الكاش
    clear_cache("maintenance_message")
    
    elapsed_time = time.time() - start_time
    
    await message.answer(
        f"✅ تم تحديث رسالة الصيانة بنجاح\n"
        f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
    )
    await state.clear()

# أرقام سيرياتل
@router.callback_query(F.data == "edit_syriatel")
async def edit_syriatel_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل أرقام سيرياتل كاش"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    current_nums = await get_cached_syriatel_numbers(db_pool)
    
    nums_text = "\n".join([f"{i+1}. `{num}`" for i, num in enumerate(current_nums)])
    
    text = (
        f"📞 **أرقام سيرياتل كاش الحالية:**\n\n"
        f"{nums_text}\n\n"
        f"**أدخل الأرقام الجديدة** (كل رقم في سطر منفصل):\n"
        f"مثال:\n74091109\n63826779\n\n"
        f"أو أرسل /cancel للإلغاء"
    )
    
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=get_cancel_keyboard())
    await state.set_state(SettingsStates.waiting_new_syriatel_numbers)

@router.message(SettingsStates.waiting_new_syriatel_numbers)
async def save_syriatel_numbers(message: types.Message, state: FSMContext, db_pool):
    """حفظ أرقام سيرياتل الجديدة"""
    if not is_admin(message.from_user.id):
        return
    
    numbers = [line.strip() for line in message.text.split('\n') if line.strip()]
    
    # ✅ التحقق من صحة الأرقام
    valid_numbers = []
    invalid_numbers = []
    
    for num in numbers:
        # إزالة أي مسافات أو شرطات
        clean_num = num.replace(' ', '').replace('-', '').replace('+', '')
        if clean_num.isdigit() and len(clean_num) >= 8:
            valid_numbers.append(clean_num)
        else:
            invalid_numbers.append(num)
    
    if invalid_numbers:
        return await message.answer(
            f"❌ الأرقام التالية غير صحيحة:\n{', '.join(invalid_numbers)}\n\n"
            f"يرجى إدخال أرقام صحيحة (8 أرقام على الأقل).",
            reply_markup=get_cancel_keyboard()
        )
    
    from database import set_syriatel_numbers
    success = await set_syriatel_numbers(db_pool, valid_numbers)
    
    if success:
        import config
        config.SYRIATEL_NUMS = valid_numbers
        
        # ✅ مسح الكاش
        clear_cache("syriatel_numbers")
        
        text = "✅ **تم تحديث أرقام سيرياتل كاش بنجاح!**\n\nالأرقام الجديدة:\n"
        for i, num in enumerate(valid_numbers, 1):
            text += f"{i}. `{num}`\n"
    else:
        text = "❌ **فشل تحديث الأرقام**"
    
    await message.answer(text, parse_mode="Markdown")
    await state.clear()

# سعر الصرف
@router.callback_query(F.data == "edit_rate")
async def start_edit_rate(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل سعر الصرف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    current_rate = await get_cached_exchange_rate(db_pool)
    
    await callback.message.answer(
        f"💵 **تعديل سعر الصرف**\n\n"
        f"السعر الحالي: {current_rate:,.0f} ل.س\n"
        f"🕐 آخر تحديث: {get_formatted_damascus_time()}\n\n"
        f"📝 **أدخل السعر الجديد:**\n\n"
        f"أو أرسل /cancel للإلغاء",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(SettingsStates.waiting_new_rate)

@router.message(SettingsStates.waiting_new_rate)
async def save_new_rate(message: types.Message, state: FSMContext, db_pool):
    """حفظ سعر الصرف الجديد"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        # تنظيف النص من الفواصل
        clean_text = message.text.replace(',', '').replace(' ', '')
        new_rate = float(clean_text)
        
        if new_rate <= 0:
            return await message.answer(
                "⚠️ سعر الصرف يجب أن يكون أكبر من 0:",
                reply_markup=get_cancel_keyboard()
            )
        
        if new_rate > 10000:
            # تأكيد إذا كان السعر مرتفع جداً
            builder = InlineKeyboardBuilder()
            builder.row(
                types.InlineKeyboardButton(text="✅ نعم، متابعة", callback_data=f"confirm_high_rate_{new_rate}"),
                types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_rate_edit")
            )
            
            await message.answer(
                f"⚠️ **تحذير: سعر صرف مرتفع جداً**\n\n"
                f"السعر الجديد: {new_rate:,.0f} ل.س\n"
                f"هل أنت متأكد من متابعة التحديث؟",
                reply_markup=builder.as_markup()
            )
            await state.update_data(temp_rate=new_rate)
            return
        
        await update_exchange_rate(message, state, db_pool, new_rate)
        
    except ValueError:
        await message.answer(
            "⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 118):",
            reply_markup=get_cancel_keyboard()
        )

@router.callback_query(F.data.startswith("confirm_high_rate_"))
async def confirm_high_rate(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """تأكيد سعر الصرف المرتفع"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    new_rate = float(callback.data.replace("confirm_high_rate_", ""))
    await update_exchange_rate(callback.message, state, db_pool, new_rate)

@router.callback_query(F.data == "cancel_rate_edit")
async def cancel_rate_edit(callback: types.CallbackQuery, state: FSMContext):
    """إلغاء تعديل سعر الصرف"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await state.clear()
    await safe_edit_message(callback.message, "✅ تم إلغاء تعديل سعر الصرف.")

async def update_exchange_rate(message: types.Message, state: FSMContext, db_pool, new_rate: float):
    """تحديث سعر الصرف في قاعدة البيانات"""
    start_time = time.time()
    
    from database import set_exchange_rate
    await set_exchange_rate(db_pool, new_rate)
    
    # ✅ مسح الكاش
    clear_cache("exchange_rate")
    
    import config
    config.USD_TO_SYP = new_rate
    
    elapsed_time = time.time() - start_time
    
    await message.answer(
        f"✅ **تم تحديث سعر الصرف بنجاح**\n\n"
        f"💰 السعر الجديد: {new_rate:,.0f} ل.س\n"
        f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
    )
    
    # إشعار المشرفين
    for mod_id in MODERATORS:
        if mod_id and mod_id != message.from_user.id:
            try:
                await message.bot.send_message(
                    mod_id,
                    f"ℹ️ تم تغيير سعر الصرف إلى {new_rate:,.0f} ل.س\n"
                    f"👤 بواسطة: @{message.from_user.username or 'مشرف'}\n"
                    f"🕐 {get_formatted_damascus_time()}",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    await state.clear()

# عرض الإعدادات الحالية
@router.callback_query(F.data == "view_settings")
async def view_settings(callback: types.CallbackQuery, db_pool):
    """عرض جميع الإعدادات الحالية"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # جلب جميع الإعدادات
    rate = await get_cached_exchange_rate(db_pool)
    syriatel = await get_cached_syriatel_numbers(db_pool)
    maintenance = await get_cached_maintenance_message(db_pool)
    bot_status = await get_cached_bot_status(db_pool)
    
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"
    
    syriatel_text = "\n".join([f"  {i+1}. `{num}`" for i, num in enumerate(syriatel)])
    
    text = (
        f"⚙️ **الإعدادات الحالية**\n\n"
        f"🤖 حالة البوت: {status_text}\n"
        f"💰 سعر الصرف: {rate:,.0f} ل.س\n"
        f"📞 أرقام سيرياتل:\n{syriatel_text}\n"
        f"📝 رسالة الصيانة:\n`{maintenance}`\n\n"
        f"🕐 {get_formatted_damascus_time()}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📈 تعديل السعر", callback_data="edit_rate"),
        types.InlineKeyboardButton(text="📞 تعديل الأرقام", callback_data="edit_syriatel")
    )
    builder.row(
        types.InlineKeyboardButton(text="📝 تعديل الصيانة", callback_data="edit_maintenance"),
        types.InlineKeyboardButton(text="🔄 تشغيل/إيقاف", callback_data="toggle_bot")
    )
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

# إعادة تعيين الإعدادات الافتراضية
@router.callback_query(F.data == "reset_settings")
async def reset_settings(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """إعادة تعيين الإعدادات الافتراضية"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ التحقق من أن المستخدم هو المالك
    if not is_owner(callback.from_user.id):
        return await callback.answer("⚠️ فقط المالك يمكنه إعادة تعيين الإعدادات", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    builder = get_confirmation_keyboard("confirm_reset_settings", "cancel_reset_settings")
    
    await safe_edit_message(
        callback.message,
        "⚠️ **إعادة تعيين الإعدادات الافتراضية**\n\n"
        "سيتم إعادة تعيين:\n"
        "• سعر الصرف إلى 118 ل.س\n"
        "• أرقام سيرياتل إلى الأرقام الافتراضية\n"
        "• رسالة الصيانة إلى الرسالة الافتراضية\n\n"
        "هل أنت متأكد؟",
        reply_markup=builder
    )

@router.callback_query(F.data == "confirm_reset_settings")
async def confirm_reset_settings(callback: types.CallbackQuery, db_pool):
    """تأكيد إعادة تعيين الإعدادات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    start_time = time.time()
    
    default_syriatel = ["74091109", "63826779"]
    
    async with db_pool.acquire() as conn:
        # إعادة تعيين سعر الصرف
        await conn.execute('''
            UPDATE bot_settings SET value = '118' WHERE key = 'usd_to_syp'
        ''')
        
        # إعادة تعيين أرقام سيرياتل
        await conn.execute('''
            UPDATE bot_settings SET value = $1 WHERE key = 'syriatel_nums'
        ''', ','.join(default_syriatel))
        
        # إعادة تعيين رسالة الصيانة
        await conn.execute('''
            UPDATE bot_settings SET value = $1 WHERE key = 'maintenance_message'
        ''', 'البوت قيد الصيانة حالياً، يرجى المحاولة لاحقاً')
    
    # ✅ مسح الكاش
    clear_cache("exchange_rate")
    clear_cache("syriatel_numbers")
    clear_cache("maintenance_message")
    
    elapsed_time = time.time() - start_time
    
    await safe_edit_message(
        callback.message,
        f"✅ **تم إعادة تعيين الإعدادات بنجاح!**\n\n"
        f"💰 سعر الصرف: 118 ل.س\n"
        f"📞 أرقام سيرياتل: {', '.join(default_syriatel)}\n"
        f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
    )

@router.callback_query(F.data == "cancel_reset_settings")
async def cancel_reset_settings(callback: types.CallbackQuery):
    """إلغاء إعادة تعيين الإعدادات"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await safe_edit_message(callback.message, "✅ تم إلغاء العملية.")
