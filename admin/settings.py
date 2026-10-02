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

# ✅ استيراد الدوال مباشرة من database.core
from database.core import (
    get_exchange_rate,
    set_exchange_rate,
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
    waiting_wallet_value = State()

# ✅ دوال مساعدة بدون كاش - تجلب من قاعدة البيانات مباشرة
async def get_db_exchange_rate(db_pool) -> float:
    """جلب سعر الصرف من قاعدة البيانات مباشرة"""
    return await get_exchange_rate(db_pool)

async def get_db_syriatel_numbers(db_pool) -> List[str]:
    """جلب أرقام سيرياتل من قاعدة البيانات مباشرة"""
    return await get_syriatel_numbers(db_pool)

async def get_db_maintenance_message(db_pool) -> str:
    """جلب رسالة الصيانة من قاعدة البيانات مباشرة"""
    return await get_maintenance_message(db_pool)

async def get_db_bot_status(db_pool) -> bool:
    """جلب حالة البوت من قاعدة البيانات مباشرة"""
    return await get_bot_status(db_pool)

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
    
    # ✅ جلب القيمة الحقيقية من قاعدة البيانات مباشرة
    async with db_pool.acquire() as conn:
        db_status = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = 'bot_status'"
        )
        current_status = (db_status == 'running')
    
    new_status = not current_status
    
    logger.info(f"🔄 تغيير حالة البوت: {current_status} ({'🟢' if current_status else '🔴'}) -> {new_status}")
    
    # ✅ تحديث قاعدة البيانات
    await set_bot_status(db_pool, new_status)
    
    # ✅ تحديث كاش الميدل وير (لازم نشيله بعدين)
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
    
    await callback.answer()
    
    # ✅ عرض الرسالة الحالية من قاعدة البيانات مباشرة
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
# ============= إدارة محافظ وبنوك الدفع =============
@router.callback_query(F.data == "edit_wallets_menu")
async def edit_wallets_menu(callback: types.CallbackQuery, db_pool):
    """لوحة التحكم بالمحافظ"""
    if not is_admin(callback.from_user.id): return
    await callback.answer()
    
    # جلب العناوين الحالية (أو استخدام القيم الموجودة بالكونفج كاحتياط)
    import config
    async with db_pool.acquire() as conn:
        syr = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'syriatel_nums'")
        sham = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'sham_cash_num'")
        sham_usd = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'sham_cash_usd'")
        usdt = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'usdt_wallet'")
        
    syr_display = syr if syr else ", ".join(config.SYRIATEL_NUMS) if config.SYRIATEL_NUMS else "غير محدد"
    
    text = (
        "💳 <b>إدارة محافظ الدفع وأرقام التحويل</b>\n\n"
        f"📞 <b>سيرياتل كاش:</b>\n<code>{syr_display}</code>\n\n"
        f"🇸🇾 <b>شام كاش (ليرة):</b>\n<code>{sham or config.SHAM_CASH_NUM or 'غير محدد'}</code>\n\n"
        f"💵 <b>شام كاش (دولار):</b>\n<code>{sham_usd or config.SHAM_CASH_NUM_USD or 'غير محدد'}</code>\n\n"
        f"💎 <b>محفظة USDT:</b>\n<code>{usdt or config.USDT_BEP20_WALLET or 'غير محدد'}</code>\n\n"
        "🔸 <b>اختر المحفظة التي تريد تعديلها:</b>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📞 سيرياتل كاش", callback_data="edit_wallet_syriatel_nums"))
    builder.row(types.InlineKeyboardButton(text="🇸🇾 شام كاش (ل.س)", callback_data="edit_wallet_sham_cash_num"))
    builder.row(types.InlineKeyboardButton(text="💵 شام كاش ($)", callback_data="edit_wallet_sham_cash_usd"))
    builder.row(types.InlineKeyboardButton(text="💎 محفظة USDT", callback_data="edit_wallet_usdt_wallet"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_settings_menu"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("edit_wallet_"))
async def edit_wallet_start(callback: types.CallbackQuery, state: FSMContext):
    wallet_key = callback.data.replace("edit_wallet_", "")
    
    names = {
        "syriatel_nums": "أرقام سيرياتل كاش (ضع فاصلة إذا كان أكثر من رقم)",
        "sham_cash_num": "رقم شام كاش (ليرة سورية)",
        "sham_cash_usd": "رقم شام كاش (دولار)",
        "usdt_wallet": "عنوان محفظة USDT (BEP20)"
    }
    
    await state.update_data(wallet_key=wallet_key)
    await state.set_state(SettingsStates.waiting_wallet_value)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="❌ إلغاء", callback_data="edit_wallets_menu"))
    
    await callback.message.edit_text(
        f"✏️ <b>تعديل {names.get(wallet_key)}</b>\n\n"
        f"أرسل الرقم أو العنوان الجديد الآن في رسالة:\n",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )

@router.message(SettingsStates.waiting_wallet_value)
async def save_wallet_value(message: types.Message, state: FSMContext, db_pool):
    if message.text in ["/cancel", "❌ إلغاء", "🔙 رجوع للقائمة"]:
        await state.clear()
        return await message.answer("✅ تم الإلغاء.")
        
    data = await state.get_data()
    wallet_key = data.get('wallet_key')
    new_value = message.text.strip()
    
    # تحديث في قاعدة البيانات
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO bot_settings (key, value) 
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = $2
        ''', wallet_key, new_value)
        
    # تحديث الكونفج الحية لكي تظهر للزبائن في قائمة الإيداع فوراً بدون إعادة تشغيل
    import config
    if wallet_key == "syriatel_nums":
        config.SYRIATEL_NUMS = [x.strip() for x in new_value.split(',')]
    elif wallet_key == "sham_cash_num":
        config.SHAM_CASH_NUM = new_value
    elif wallet_key == "sham_cash_usd":
        config.SHAM_CASH_NUM_USD = new_value
    elif wallet_key == "usdt_wallet":
        config.USDT_BEP20_WALLET = new_value
        
    await state.clear()
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 العودة للمحافظ", callback_data="edit_wallets_menu"))
    
    await message.answer(
        f"✅ <b>تم تحديث المحفظة بنجاح!</b>\n\n"
        f"القيمة الجديدة: <code>{new_value}</code>\n"
        f"ستظهر هذه القيمة للزبائن فوراً في قسم الإيداع.",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )

# سعر الصرف
@router.callback_query(F.data == "edit_rate")
async def start_edit_rate(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل سعر الصرف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    # ✅ استخدام قاعدة البيانات مباشرة
    current_rate = await get_db_exchange_rate(db_pool)
    
    await callback.message.answer(
        f"💵 **تعديل سعر الصرف**\n\n"
        f"السعر الحالي: {current_rate:,.0f} ل.س\n"
        f"🕐 آخر تحديث: {get_formatted_damascus_time()}\n\n"
        f"📝 **أدخل السعر الجديد:**\n\n"
        f" أرسل /cancel للإلغاء",
        parse_mode="Markdown",
        
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
            
        )

@router.callback_query(F.data.startswith("confirm_high_rate_"))
async def confirm_high_rate(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """تأكيد سعر الصرف المرتفع"""
    await callback.answer()
    
    new_rate = float(callback.data.replace("confirm_high_rate_", ""))
    await update_exchange_rate(callback.message, state, db_pool, new_rate)

@router.callback_query(F.data == "cancel_rate_edit")
async def cancel_rate_edit(callback: types.CallbackQuery, state: FSMContext):
    """إلغاء تعديل سعر الصرف"""
    await callback.answer()
    
    await state.clear()
    await safe_edit_message(callback.message, "✅ تم إلغاء تعديل سعر الصرف.")

async def update_exchange_rate(message: types.Message, state: FSMContext, db_pool, new_rate: float):
    """تحديث سعر الصرف في قاعدة البيانات"""
    start_time = time.time()
    
    await set_exchange_rate(db_pool, new_rate)
    
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
    
    await callback.answer()
    
    # جلب جميع الإعدادات من قاعدة البيانات مباشرة
    rate = await get_db_exchange_rate(db_pool)
    syriatel = await get_db_syriatel_numbers(db_pool)
    maintenance = await get_db_maintenance_message(db_pool)
    bot_status = await get_db_bot_status(db_pool)
    
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
    
    if not is_owner(callback.from_user.id):
        return await callback.answer("⚠️ فقط المالك يمكنه إعادة تعيين الإعدادات", show_alert=True)
    
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
    await callback.answer()
    
    await safe_edit_message(callback.message, "✅ تم إلغاء العملية.")
