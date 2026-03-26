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
from handlers.keyboards import get_confirmation_keyboard
from utils import is_admin, is_owner, safe_edit_message, format_amount, get_formatted_damascus_time

# ✅ استيراد الدوال من database.core
from database.core import (
    get_exchange_rate,
    set_exchange_rate,
    get_all_exchange_rates,
    update_exchange_rate,
    get_syriatel_numbers,
    set_syriatel_numbers,
    get_maintenance_message,
    get_bot_status,
    set_bot_status
)
from handlers.middleware import refresh_bot_status_cache

logger = logging.getLogger(__name__)
router = Router(name="admin_settings")

class SettingsStates(StatesGroup):
    waiting_new_rate = State()
    waiting_maintenance_msg = State()
    waiting_new_syriatel_numbers = State()
    waiting_purchase_rate = State()   # ✅ جديد
    waiting_deposit_rate = State()    # ✅ جديد
    waiting_points_rate = State()     # ✅ جديد


# ============= دوال مساعدة =============
async def get_db_exchange_rate(db_pool) -> float:
    """جلب سعر الصرف من قاعدة البيانات مباشرة (للتوافق)"""
    return await get_exchange_rate(db_pool, 'deposit')

async def get_db_syriatel_numbers(db_pool) -> List[str]:
    """جلب أرقام سيرياتل من قاعدة البيانات مباشرة"""
    return await get_syriatel_numbers(db_pool)

async def get_db_maintenance_message(db_pool) -> str:
    """جلب رسالة الصيانة من قاعدة البيانات مباشرة"""
    return await get_maintenance_message(db_pool)

async def get_db_bot_status(db_pool) -> bool:
    """جلب حالة البوت من قاعدة البيانات مباشرة"""
    return await get_bot_status(db_pool)


# ============= قائمة إدارة أسعار الصرف (جديدة) =============
@router.callback_query(F.data == "exchange_rates_menu")
async def exchange_rates_menu(callback: types.CallbackQuery, state: FSMContext):
    """عرض قائمة إدارة أسعار الصرف المنفصلة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    # ✅ جلب جميع الأسعار
    rates = await get_all_exchange_rates(callback.bot.db_pool)
    
    purchase_rate = rates.get('purchase', 118)
    deposit_rate = rates.get('deposit', 118)
    points_rate = rates.get('points', 118)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text=f"🔒 سعر الشراء (مخفي): {purchase_rate:,.0f} ل.س",
            callback_data="edit_purchase_rate"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text=f"💳 سعر الإيداع (ظاهر): {deposit_rate:,.0f} ل.س",
            callback_data="edit_deposit_rate"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text=f"⭐ سعر النقاط: {points_rate:,.0f} ل.س",
            callback_data="edit_points_rate"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🔙 رجوع",
            callback_data="back_to_admin"
        )
    )
    
    await safe_edit_message(
        callback.message,
        f"💰 **إدارة أسعار الصرف المنفصلة**\n\n"
        f"🔹 **سعر الشراء (مخفي):** يستخدم لحساب أسعار الخدمات - لا يظهر للمستخدم\n"
        f"🔹 **سعر الإيداع (ظاهر):** يظهر للمستخدم عند الشحن واستبدال النقاط\n"
        f"🔹 **سعر النقاط:** يستخدم لحساب قيمة النقاط عند الاسترداد\n\n"
        f"📊 **الأسعار الحالية:**\n"
        f"• شراء: {purchase_rate:,.0f} ل.س = 1$\n"
        f"• إيداع: {deposit_rate:,.0f} ل.س = 1$\n"
        f"• نقاط: {points_rate:,.0f} ل.س = 1$\n\n"
        f"🔽 **اختر السعر الذي تريد تعديله:**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= تعديل سعر الشراء (مخفي) =============
@router.callback_query(F.data == "edit_purchase_rate")
async def edit_purchase_rate_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل سعر الشراء (مخفي)"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state(SettingsStates.waiting_purchase_rate)
    
    current_rate = await get_exchange_rate(db_pool, 'purchase')
    
    await callback.message.answer(
        f"🔒 **تعديل سعر الشراء (مخفي)**\n\n"
        f"⚠️ **هذا السعر لا يظهر للمستخدمين!**\n"
        f"يستخدم لحساب أسعار الخدمات داخلياً.\n\n"
        f"💰 **السعر الحالي:** {current_rate:,.0f} ل.س = 1$\n\n"
        f"📝 **أدخل السعر الجديد:**\n"
        f"(مثال: 125)\n\n"
        f"❌ للإلغاء أرسل /cancel",
        parse_mode="Markdown"
    )


# ============= تعديل سعر الإيداع (ظاهر) =============
@router.callback_query(F.data == "edit_deposit_rate")
async def edit_deposit_rate_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل سعر الإيداع (ظاهر للمستخدم)"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state(SettingsStates.waiting_deposit_rate)
    
    current_rate = await get_exchange_rate(db_pool, 'deposit')
    
    await callback.message.answer(
        f"💳 **تعديل سعر الإيداع (ظاهر للمستخدم)**\n\n"
        f"💰 **السعر الحالي:** {current_rate:,.0f} ل.س = 1$\n\n"
        f"📝 **أدخل السعر الجديد:**\n"
        f"(مثال: 125)\n\n"
        f"⚠️ **ملاحظة:** هذا السعر سيظهر للمستخدمين عند الشحن\n\n"
        f"❌ للإلغاء أرسل /cancel",
        parse_mode="Markdown"
    )


# ============= تعديل سعر النقاط =============
@router.callback_query(F.data == "edit_points_rate")
async def edit_points_rate_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل سعر النقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state(SettingsStates.waiting_points_rate)
    
    current_rate = await get_exchange_rate(db_pool, 'points')
    
    await callback.message.answer(
        f"⭐ **تعديل سعر النقاط**\n\n"
        f"💰 **السعر الحالي:** {current_rate:,.0f} ل.س = 1$\n\n"
        f"📝 **أدخل السعر الجديد:**\n"
        f"(مثال: 120)\n\n"
        f"⚠️ **ملاحظة:** هذا السعر يستخدم لحساب قيمة النقاط عند الاسترداد\n\n"
        f"❌ للإلغاء أرسل /cancel",
        parse_mode="Markdown"
    )


# ============= حفظ الأسعار الجديدة =============
@router.message(SettingsStates.waiting_purchase_rate)
async def save_purchase_rate(message: types.Message, state: FSMContext, db_pool):
    """حفظ سعر الشراء الجديد"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_rate = float(message.text.replace(',', '').strip())
        if new_rate <= 0:
            raise ValueError
    except:
        await message.answer(
            "❌ **خطأ:** الرجاء إدخال رقم صحيح أكبر من 0.\n"
            "مثال: 125",
            parse_mode="Markdown"
        )
        return
    
    start_time = time.time()
    
    success = await update_exchange_rate(db_pool, 'purchase', new_rate, message.from_user.id)
    
    if success:
        elapsed_time = time.time() - start_time
        
        await message.answer(
            f"✅ **تم تحديث سعر الشراء بنجاح!**\n\n"
            f"💰 **السعر الجديد:** {new_rate:,.0f} ل.س = 1$\n\n"
            f"🔒 هذا السعر **مخفي** عن المستخدمين ويستخدم لحساب أسعار الخدمات.\n"
            f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية",
            parse_mode="Markdown"
        )
        
        # إشعار للمشرفين
        for mod_id in MODERATORS:
            if mod_id and mod_id != message.from_user.id:
                try:
                    await message.bot.send_message(
                        mod_id,
                        f"ℹ️ **تم تغيير سعر الشراء (مخفي)**\n"
                        f"💰 السعر الجديد: {new_rate:,.0f} ل.س = 1$\n"
                        f"👤 بواسطة: @{message.from_user.username or 'مشرف'}\n"
                        f"🕐 {get_formatted_damascus_time()}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
    else:
        await message.answer("❌ **فشل تحديث السعر**", parse_mode="Markdown")
    
    await state.clear()


@router.message(SettingsStates.waiting_deposit_rate)
async def save_deposit_rate(message: types.Message, state: FSMContext, db_pool):
    """حفظ سعر الإيداع الجديد"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_rate = float(message.text.replace(',', '').strip())
        if new_rate <= 0:
            raise ValueError
    except:
        await message.answer(
            "❌ **خطأ:** الرجاء إدخال رقم صحيح أكبر من 0.\n"
            "مثال: 125",
            parse_mode="Markdown"
        )
        return
    
    start_time = time.time()
    
    success = await update_exchange_rate(db_pool, 'deposit', new_rate, message.from_user.id)
    
    if success:
        elapsed_time = time.time() - start_time
        
        await message.answer(
            f"✅ **تم تحديث سعر الإيداع بنجاح!**\n\n"
            f"💰 **السعر الجديد:** {new_rate:,.0f} ل.س = 1$\n\n"
            f"👁️ هذا السعر **سيظهر للمستخدمين** عند الشحن واستبدال النقاط.\n"
            f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية",
            parse_mode="Markdown"
        )
        
        for mod_id in MODERATORS:
            if mod_id and mod_id != message.from_user.id:
                try:
                    await message.bot.send_message(
                        mod_id,
                        f"ℹ️ **تم تغيير سعر الإيداع (ظاهر)**\n"
                        f"💰 السعر الجديد: {new_rate:,.0f} ل.س = 1$\n"
                        f"👤 بواسطة: @{message.from_user.username or 'مشرف'}\n"
                        f"🕐 {get_formatted_damascus_time()}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
    else:
        await message.answer("❌ **فشل تحديث السعر**", parse_mode="Markdown")
    
    await state.clear()


@router.message(SettingsStates.waiting_points_rate)
async def save_points_rate(message: types.Message, state: FSMContext, db_pool):
    """حفظ سعر النقاط الجديد"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_rate = float(message.text.replace(',', '').strip())
        if new_rate <= 0:
            raise ValueError
    except:
        await message.answer(
            "❌ **خطأ:** الرجاء إدخال رقم صحيح أكبر من 0.\n"
            "مثال: 120",
            parse_mode="Markdown"
        )
        return
    
    start_time = time.time()
    
    success = await update_exchange_rate(db_pool, 'points', new_rate, message.from_user.id)
    
    if success:
        elapsed_time = time.time() - start_time
        
        await message.answer(
            f"✅ **تم تحديث سعر النقاط بنجاح!**\n\n"
            f"💰 **السعر الجديد:** {new_rate:,.0f} ل.س = 1$\n\n"
            f"⭐ هذا السعر يستخدم لحساب قيمة النقاط عند الاسترداد.\n"
            f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية",
            parse_mode="Markdown"
        )
        
        for mod_id in MODERATORS:
            if mod_id and mod_id != message.from_user.id:
                try:
                    await message.bot.send_message(
                        mod_id,
                        f"ℹ️ **تم تغيير سعر النقاط**\n"
                        f"💰 السعر الجديد: {new_rate:,.0f} ل.س = 1$\n"
                        f"👤 بواسطة: @{message.from_user.username or 'مشرف'}\n"
                        f"🕐 {get_formatted_damascus_time()}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
    else:
        await message.answer("❌ **فشل تحديث السعر**", parse_mode="Markdown")
    
    await state.clear()


# ============= دوال قديمة محفوظة للتوافق =============

# تشغيل/إيقاف البوت
@router.callback_query(F.data == "toggle_bot")
async def toggle_bot(callback: types.CallbackQuery, db_pool):
    """تشغيل أو إيقاف البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    if not is_owner(callback.from_user.id):
        return await callback.answer("⚠️ فقط المالك يمكنه تشغيل/إيقاف البوت", show_alert=True)
    
    await callback.answer()
    start_time = time.time()
    
    async with db_pool.acquire() as conn:
        db_status = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = 'bot_status'"
        )
        current_status = (db_status == 'running')
    
    new_status = not current_status
    
    logger.info(f"🔄 تغيير حالة البوت: {current_status} -> {new_status}")
    
    await set_bot_status(db_pool, new_status)
    await refresh_bot_status_cache(db_pool)
    
    status_text = "🟢 يعمل" if new_status else "🔴 متوقف"
    action_text = "تشغيل" if new_status else "إيقاف"
    
    elapsed_time = time.time() - start_time
    
    await safe_edit_message(
        callback.message,
        f"✅ تم {action_text} البوت بنجاح\n\n"
        f"الحالة الآن: {status_text}\n"
        f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
    )
    
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
    
    await callback.answer()
    
    current_msg = await get_db_maintenance_message(db_pool)
    
    await callback.message.answer(
        f"📝 **تعديل رسالة الصيانة**\n\n"
        f"الرسالة الحالية:\n`{current_msg}`\n\n"
        f"أرسل رسالة الصيانة الجديدة:\n\n"
        f"(هذه الرسالة ستظهر للمستخدمين عند إيقاف البوت)\n\n"
        f" أرسل /cancel للإلغاء",
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
    
    await callback.answer()
    
    current_nums = await get_db_syriatel_numbers(db_pool)
    
    nums_text = "\n".join([f"{i+1}. `{num}`" for i, num in enumerate(current_nums)])
    
    text = (
        f"📞 **أرقام سيرياتل كاش الحالية:**\n\n"
        f"{nums_text}\n\n"
        f"**أدخل الأرقام الجديدة** (كل رقم في سطر منفصل):\n"
        f"مثال:\n74091109\n63826779\n\n"
        f" أرسل /cancel للإلغاء"
    )
    
    await callback.message.answer(text, parse_mode="Markdown")
    await state.set_state(SettingsStates.waiting_new_syriatel_numbers)


@router.message(SettingsStates.waiting_new_syriatel_numbers)
async def save_syriatel_numbers(message: types.Message, state: FSMContext, db_pool):
    """حفظ أرقام سيرياتل الجديدة"""
    if not is_admin(message.from_user.id):
        return
    
    numbers = [line.strip() for line in message.text.split('\n') if line.strip()]
    
    valid_numbers = []
    invalid_numbers = []
    
    for num in numbers:
        clean_num = num.replace(' ', '').replace('-', '').replace('+', '')
        if clean_num.isdigit() and len(clean_num) >= 8:
            valid_numbers.append(clean_num)
        else:
            invalid_numbers.append(num)
    
    if invalid_numbers:
        return await message.answer(
            f"❌ الأرقام التالية غير صحيحة:\n{', '.join(invalid_numbers)}\n\n"
            f"يرجى إدخال أرقام صحيحة (8 أرقام على الأقل).",
        )
    
    success = await set_syriatel_numbers(db_pool, valid_numbers)
    
    if success:
        import config
        config.SYRIATEL_NUMS = valid_numbers
        
        text = "✅ **تم تحديث أرقام سيرياتل كاش بنجاح!**\n\nالأرقام الجديدة:\n"
        for i, num in enumerate(valid_numbers, 1):
            text += f"{i}. `{num}`\n"
    else:
        text = "❌ **فشل تحديث الأرقام**"
    
    await message.answer(text, parse_mode="Markdown")
    await state.clear()


# سعر الصرف القديم (للتوافق)
@router.callback_query(F.data == "edit_rate")
async def start_edit_rate(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل سعر الصرف (يعدل سعر الإيداع فقط)"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    current_rate = await get_exchange_rate(db_pool, 'deposit')
    
    await callback.message.answer(
        f"💵 **تعديل سعر الإيداع**\n\n"
        f"السعر الحالي: {current_rate:,.0f} ل.س\n"
        f"🕐 آخر تحديث: {get_formatted_damascus_time()}\n\n"
        f"📝 **أدخل السعر الجديد:**\n\n"
        f" أرسل /cancel للإلغاء",
        parse_mode="Markdown",
    )
    await state.set_state(SettingsStates.waiting_new_rate)


@router.message(SettingsStates.waiting_new_rate)
async def save_new_rate(message: types.Message, state: FSMContext, db_pool):
    """حفظ سعر الصرف الجديد (يعدل سعر الإيداع)"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        clean_text = message.text.replace(',', '').replace(' ', '')
        new_rate = float(clean_text)
        
        if new_rate <= 0:
            return await message.answer(
                "⚠️ سعر الصرف يجب أن يكون أكبر من 0:",
            )
        
        await update_exchange_rate(db_pool, 'deposit', new_rate, message.from_user.id)
        
        elapsed_time = time.time() - start_time
        
        await message.answer(
            f"✅ **تم تحديث سعر الإيداع بنجاح**\n\n"
            f"💰 السعر الجديد: {new_rate:,.0f} ل.س\n"
            f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
        )
        
        for mod_id in MODERATORS:
            if mod_id and mod_id != message.from_user.id:
                try:
                    await message.bot.send_message(
                        mod_id,
                        f"ℹ️ تم تغيير سعر الإيداع إلى {new_rate:,.0f} ل.س\n"
                        f"👤 بواسطة: @{message.from_user.username or 'مشرف'}\n"
                        f"🕐 {get_formatted_damascus_time()}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
        
        await state.clear()
        
    except ValueError:
        await message.answer(
            "⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 118):",
        )


# عرض الإعدادات الحالية
@router.callback_query(F.data == "view_settings")
async def view_settings(callback: types.CallbackQuery, db_pool):
    """عرض جميع الإعدادات الحالية"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    rates = await get_all_exchange_rates(db_pool)
    syriatel = await get_db_syriatel_numbers(db_pool)
    maintenance = await get_db_maintenance_message(db_pool)
    bot_status = await get_db_bot_status(db_pool)
    
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"
    
    syriatel_text = "\n".join([f"  {i+1}. `{num}`" for i, num in enumerate(syriatel)])
    
    text = (
        f"⚙️ **الإعدادات الحالية**\n\n"
        f"🤖 حالة البوت: {status_text}\n"
        f"💰 **أسعار الصرف:**\n"
        f"  • شراء (مخفي): {rates.get('purchase', 118):,.0f} ل.س\n"
        f"  • إيداع (ظاهر): {rates.get('deposit', 118):,.0f} ل.س\n"
        f"  • نقاط: {rates.get('points', 118):,.0f} ل.س\n"
        f"📞 أرقام سيرياتل:\n{syriatel_text}\n"
        f"📝 رسالة الصيانة:\n`{maintenance}`\n\n"
        f"🕐 {get_formatted_damascus_time()}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="💰 تعديل أسعار الصرف", callback_data="exchange_rates_menu"),
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
    
    if not is_owner(callback.from_user.id):
        return await callback.answer("⚠️ فقط المالك يمكنه إعادة تعيين الإعدادات", show_alert=True)
    
    await callback.answer()
    
    builder = get_confirmation_keyboard("confirm_reset_settings", "cancel_reset_settings")
    
    await safe_edit_message(
        callback.message,
        "⚠️ **إعادة تعيين الإعدادات الافتراضية**\n\n"
        "سيتم إعادة تعيين:\n"
        "• أسعار الصرف إلى 118 ل.س\n"
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
    
    await callback.answer()
    
    start_time = time.time()
    
    default_syriatel = ["74091109", "63826779"]
    default_rate = 118.0
    
    async with db_pool.acquire() as conn:
        # إعادة تعيين أسعار الصرف
        await conn.execute('''
            UPDATE exchange_rates SET rate_value = $1 WHERE rate_type = 'purchase'
        ''', default_rate)
        await conn.execute('''
            UPDATE exchange_rates SET rate_value = $1 WHERE rate_type = 'deposit'
        ''', default_rate)
        await conn.execute('''
            UPDATE exchange_rates SET rate_value = $1 WHERE rate_type = 'points'
        ''', default_rate)
        
        # إعادة تعيين أرقام سيرياتل
        await conn.execute('''
            UPDATE bot_settings SET value = $1 WHERE key = 'syriatel_nums'
        ''', ','.join(default_syriatel))
        
        # إعادة تعيين رسالة الصيانة
        await conn.execute('''
            UPDATE bot_settings SET value = $1 WHERE key = 'maintenance_message'
        ''', 'البوت قيد الصيانة حالياً، يرجى المحاولة لاحقاً')
    
    elapsed_time = time.time() - start_time
    
    await safe_edit_message(
        callback.message,
        f"✅ **تم إعادة تعيين الإعدادات بنجاح!**\n\n"
        f"💰 أسعار الصرف: 118 ل.س\n"
        f"📞 أرقام سيرياتل: {', '.join(default_syriatel)}\n"
        f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
    )


@router.callback_query(F.data == "cancel_reset_settings")
async def cancel_reset_settings(callback: types.CallbackQuery):
    """إلغاء إعادة تعيين الإعدادات"""
    await callback.answer()
    
    await safe_edit_message(callback.message, "✅ تم إلغاء العملية.")
