# handlers/start.py
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ADMIN_ID, MODERATORS
import logging
from datetime import datetime
import pytz
import random
import string
from handlers.time_utils import format_damascus_time, get_damascus_time_now
from handlers.keyboards import get_main_menu_keyboard, get_back_inline_keyboard, get_currency_keyboard, get_back_to_main_keyboard
from utils import is_admin
from .profile_handlers import router as profile_router
from database.points import get_redemption_rate, create_redemption_request
from database.core import get_exchange_rate
from database.vip import get_next_vip_level, get_user_vip
from database.referrals import generate_referral_code
from database.users import is_admin_user 
from aiogram.fsm.state import State, StatesGroup
from cache import cached, clear_cache

class ReferralStates(StatesGroup):
    waiting_subscription = State()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()
router.include_router(profile_router)

# ✅ كاش للمستخدمين
@cached(ttl=30, key_prefix="user")
async def get_cached_user(db_pool, user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

# ✅ كاش لحالة الحظر
@cached(ttl=15, key_prefix="user_ban")
async def get_cached_user_ban_status(db_pool, user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT is_banned FROM users WHERE user_id = $1", user_id)

async def notify_admins(bot, message_text, db_pool=None):
    """إرسال إشعار لجميع المشرفين"""
    admin_ids = set()
    admin_ids.add(ADMIN_ID)
    for mod_id in MODERATORS:
        if mod_id:
            admin_ids.add(mod_id)
    
    sent_count = 0
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, message_text, parse_mode="Markdown")
            sent_count += 1
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمشرف {admin_id}: {e}")
    return sent_count

# ========== دوال الإلغاء ==========
@router.message(Command("cancel"))
@router.message(Command("الغاء"))
@router.message(Command("رجوع"))
@router.message(F.text == "/cancel")
@router.message(F.text == "/الغاء")
@router.message(F.text == "/رجوع")
async def cmd_cancel(message: types.Message, state: FSMContext, db_pool):
    await state.clear()
    
    # جلب الرصيد لتحضير رسالة الواجهة
    async with db_pool.acquire() as conn:
        balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", message.from_user.id) or 0
    current_rate = await get_exchange_rate(db_pool)
    balance_usd = balance / current_rate if current_rate > 0 else 0
    
    welcome_text = (
        f"أهلاً بك في بوت الخدمات 🤖\n\n"
        f"رقم حسابك: <code>{message.from_user.id}</code>\n"
        f"رصيدك الحالي: {balance_usd:,.2f} $\n\n"
        f"اختر من القائمة أدناه 👇"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id), "USD"),
        parse_mode="HTML"
    )

# ========== أمر البدء الرئيسي ==========
@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext, db_pool):
    # تجاهل البوت نفسه
    BOT_ID = 8384048684
    if message.from_user.id == BOT_ID:
        return
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    
    args = message.text.split()
    referral_code = args[1] if len(args) > 1 else None
    
    if not referral_code:
        data = await state.get_data()
        referral_code = data.get('referral_code')
    
    balance = 0
    is_banned = False
    
    # التحقق من اشتراك القناة
    channel_username = "@LINKcharger22"
    try:
        member = await message.bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        is_member = member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.warning(f"⚠️ خطأ في التحقق من القناة: {e}")
        is_member = False
    
    if not is_member:
        if referral_code:
            await state.update_data(referral_code=referral_code)
            await state.set_state(ReferralStates.waiting_subscription)
        
        join_button = InlineKeyboardBuilder()
        join_button.row(types.InlineKeyboardButton(text="📢 انضم إلى القناة", url="https://t.me/LINKcharger22"))
        join_button.row(types.InlineKeyboardButton(text="✅ تحقق من الاشتراك", callback_data="check_subscription"))
        
        await message.answer(
            "❌ **عذراً، يجب الاشتراك في قناتنا أولاً لاستخدام البوت.**\n\n"
            "📢 **قناة البوت:** @LINKcharger22\n\n"
            "🔹 بعد الاشتراك، اضغط على زر 'تحقق من الاشتراك'.",
            reply_markup=join_button.as_markup(),
            parse_mode="Markdown"
        )
        return
    
    current_rate = await get_exchange_rate(db_pool)
    
    async with db_pool.acquire() as conn:
        user = await get_cached_user(db_pool, user_id)
        
        # ===== مستخدم جديد =====
        if not user:
            new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            while True:
                check = await conn.fetchval("SELECT user_id FROM users WHERE referral_code = $1", new_code)
                if not check: break
                new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            try:
                await conn.execute('''
                    INSERT INTO users 
                    (user_id, username, first_name, last_name, balance, referral_code, created_at, is_banned)
                    VALUES ($1, $2, $3, $4, 0, $5, CURRENT_TIMESTAMP, FALSE)
                ''', user_id, username, first_name, last_name, new_code)
                clear_cache(f"user:{user_id}")
                clear_cache(f"user_ban:{user_id}")
            except Exception as e:
                logger.error(f"خطأ في إنشاء مستخدم: {e}")
            
            # معالجة الإحالة
            if referral_code:
                try:
                    referrer = await conn.fetchrow("SELECT user_id, username, total_points FROM users WHERE referral_code = $1", referral_code)
                    if referrer and referrer['user_id'] != user_id:
                        from database.referrals import check_existing_referral
                        exists, msg = await check_existing_referral(db_pool, referrer['user_id'], user_id)
                        if not exists:
                            await conn.execute("UPDATE users SET referred_by = $1 WHERE user_id = $2", referrer['user_id'], user_id)
                            points = await conn.fetchval("SELECT value::integer FROM bot_settings WHERE key = 'points_per_referral'") or 1
                            await conn.execute('''
                                UPDATE users SET referral_count = referral_count + 1, total_points = total_points + $1, referral_earnings = referral_earnings + $1
                                WHERE user_id = $2
                            ''', points, referrer['user_id'])
                            clear_cache(f"user:{referrer['user_id']}")
                            clear_cache(f"user_points:{referrer['user_id']}")
                            await conn.execute("INSERT INTO points_history (user_id, points, action, description, created_at) VALUES ($1, $2, 'referral', $3, CURRENT_TIMESTAMP)", referrer['user_id'], points, f'إحالة المستخدم {user_id}')
                            try:
                                await message.bot.send_message(referrer['user_id'], f"🎉 **مبروك! لديك إحالة جديدة**\n👤 المستخدم: @{username or 'جديد'}\n⭐ كسبت: +{points} نقاط", parse_mode="Markdown")
                            except: pass
                except Exception as e:
                    logger.error(f"❌ خطأ إحالة: {e}")
            balance = 0
            
        # ===== مستخدم قديم =====
        else:
            try:
                await conn.execute("UPDATE users SET username = $1, first_name = $2, last_name = $3, last_activity = CURRENT_TIMESTAMP WHERE user_id = $4", username, first_name, last_name, user_id)
                clear_cache(f"user:{user_id}")
                is_banned = await get_cached_user_ban_status(db_pool, user_id) or False
                balance_row = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
                balance = balance_row['balance'] or 0 if balance_row else 0
            except Exception as e:
                logger.error(f"خطأ تحديث مستخدم قديم: {e}")
                balance = 0
    
    if is_banned:
        return await message.answer("🚫 عذراً، حسابك محظور من استخدام البوت.\n📞 للتواصل مع الدعم: @Charger444")
    
    # رسالة الترحيب والواجهة الجديدة (التقاط.PNG)
    balance_usd = balance / current_rate if current_rate > 0 else 0
    user_currency = "USD" # القيمة الافتراضية للعملة
    
    welcome_text = (
        f"أهلاً بك في بوت الخدمات 🤖\n\n"
        f"رقم حسابك: <code>{user_id}</code>\n"
        f"رصيدك الحالي: {balance_usd:,.2f} $\n\n"
        f"اختر من القائمة أدناه 👇"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(is_admin(user_id), user_currency),
        parse_mode="HTML"
    )

# ========== التحقق من اشتراك القناة ==========
@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: types.CallbackQuery, state: FSMContext, db_pool):
    await callback.answer()
    
    user_id = callback.from_user.id
    channel_username = "@LINKcharger22"
    
    try:
        member = await callback.bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        is_member = member.status in ["member", "administrator", "creator"]
    except:
        is_member = False
    
    if is_member:
        await callback.message.delete()
        
        # نفس منطق بناء المستخدم الموجود في cmd_start
        async with db_pool.acquire() as conn:
            balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", user_id) or 0
        
        current_rate = await get_exchange_rate(db_pool)
        balance_usd = balance / current_rate if current_rate > 0 else 0
        
        welcome_text = (
            f"أهلاً بك في بوت الخدمات 🤖\n\n"
            f"رقم حسابك: <code>{user_id}</code>\n"
            f"رصيدك الحالي: {balance_usd:,.2f} $\n\n"
            f"اختر من القائمة أدناه 👇"
        )
        
        await callback.message.answer(
            welcome_text,
            reply_markup=get_main_menu_keyboard(is_admin(user_id), "USD"),
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await callback.answer("❌ لم تشترك في القناة بعد! اشترك ثم حاول مرة أخرى.", show_alert=True)

# ================= واجهات النظام الجديد (العملة والـ VIP) =================

@router.callback_query(F.data == "change_currency")
async def change_currency_menu(callback: types.CallbackQuery, db_pool):
    """عرض قائمة تغيير العملة (مطابق لصورة 10.PNG)"""
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", callback.from_user.id) or 0
    current_rate = await get_exchange_rate(db_pool)
    balance_usd = balance / current_rate if current_rate > 0 else 0
    
    # افتراضياً العملة دولار
    current_currency = "USD"
    
    text = (
        "**عملة الحساب 💱**\n\n"
        f"العملة الحالية: **دولار ($)**\n"
        f"رصيدك: **{balance_usd:,.2f} $**\n\n"
        "ℹ️ كل الأسعار ورصيدك تظهر بالعملة المختارة حسب صرف وسيلة الإيداع المرتبطة بها.\n\n"
        "اختر العملة 👇:"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_currency_keyboard(current_currency),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.in_(["set_curr_USD", "set_curr_SYP"]))
async def set_currency(callback: types.CallbackQuery):
    """حفظ العملة (حالياً تحديث واجهة فقط)"""
    new_curr = callback.data.split("_")[2]
    await callback.answer("✅ تم تحديث عملة العرض", show_alert=False)
    
    # تحديث الكيبورد ليظهر الصح على العملة الجديدة
    await callback.message.edit_reply_markup(
        reply_markup=get_currency_keyboard(new_curr)
    )

@router.callback_query(F.data == "vip_system")
async def show_vip_system(callback: types.CallbackQuery, db_pool):
    """عرض نظام الخصومات والـ VIP (مطابق لصورة 114.PNG)"""
    await callback.answer()
    
    user_id = callback.from_user.id
    current_rate = await get_exchange_rate(db_pool)
    
    # جلب تفاصيل الـ VIP الحقيقية للمستخدم
    vip_data = await get_user_vip(db_pool, user_id)
    total_spent_syp = vip_data.get('total_spent', 0)
    current_vip_level = vip_data.get('vip_level', 0)
    
    total_spent_usd = total_spent_syp / current_rate if current_rate > 0 else 0
    
    # جلب متطلبات المستوى التالي
    next_level_info = get_next_vip_level(total_spent_syp)
    
    if next_level_info['remaining'] > 0:
        req_spent_syp = total_spent_syp + next_level_info['remaining']
        req_spent_usd = req_spent_syp / current_rate if current_rate > 0 else 0
        remaining_usd = next_level_info['remaining'] / current_rate if current_rate > 0 else 0
        next_discount = next_level_info.get('next_discount', 0)
        next_level_num = next_level_info.get('next_level', 1)
        
        progress_msg = (
            f"▫️ VIP 0 — المستوى الافتراضي لجميع المستخدمين (بدون خصم)\n"
            f"🔒 VIP {next_level_num} — VIP {next_level_num}\n\n"
            f"🏷 الخصم: **{next_discount:.2f}%**\n"
            f"💰 المصروف المطلوب: **{req_spent_usd:,.2f} $**\n\n"
            f"🚀 باقي لك **{remaining_usd:,.2f} $** للوصول إلى VIP {next_level_num} — VIP {next_level_num}"
        )
    else:
        progress_msg = "✨ لقد وصلت إلى أعلى مستوى VIP متاح حالياً!"
    
    text = (
        "**نظام الخصومات 💎**\n"
        "━━━━━━━━━━━━━━━\n"
        "كلما زادت مصروفاتك في البوت ترتقي تلقائياً لمستوى أعلى وتنخفض أسعار جميع المنتجات لك.\n\n"
        f"👤 مستواك الحالي: **VIP {current_vip_level}**\n"
        f"💸 إجمالي مصروفك: **{total_spent_usd:,.2f} $**\n\n"
        f"{progress_msg}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_main_keyboard(),
        parse_mode="Markdown"
    )

# ========== لوحة تحكم المشرفين ==========
@router.message(F.text == "🛠 لوحة التحكم")
async def admin_control_panel(message: types.Message, db_pool):
    if not is_admin(message.from_user.id):
        return await message.answer("⚠️ هذا الزر مخصص للمشرفين فقط.")
    from admin.main import admin_panel
    await admin_panel(message, db_pool)

# ========== المساعدة والدعم ==========
@router.callback_query(F.data == "show_help")
async def show_help_callback(callback: types.CallbackQuery):
    await callback.answer()
    help_text = (
        "**📞 للمساعدة يرجى التواصل مع الادمن:**\n"
        "🔰المعرف :  @Charger444\n\n"
        "🔹 **لتحديث القائمة: أرسل /start**"
    )
    await callback.message.edit_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=get_back_to_main_keyboard()
    )
