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
    waiting_purchase_rate = State()
    waiting_deposit_rate = State()
    waiting_points_rate = State()


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
async def exchange_rates_menu(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض قائمة إدارة أسعار الصرف المنفصلة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    # ✅ استخدام db_pool من المعاملات
    rates = await get_all_exchange_rates(db_pool)
    
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


# ============= باقي الدوال (كما هي) =============
# ... (التشغيل/الإيقاف، رسالة الصيانة، أرقام سيرياتل، سعر الصرف القديم، عرض الإعدادات، إعادة التعيين)
# تبقى كما هي دون تغيير
