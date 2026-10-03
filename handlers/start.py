# handlers/start.py
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
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

@cached(ttl=30, key_prefix="user")
async def get_cached_user(db_pool, user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

@cached(ttl=15, key_prefix="user_ban")
async def get_cached_user_ban_status(db_pool, user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT is_banned FROM users WHERE user_id = $1", user_id)

@router.message(Command("format_store"))
async def format_store_cmd(message: types.Message, db_pool):
    if not is_admin(message.from_user.id): return
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM product_options")
        await conn.execute("DELETE FROM applications")
        await conn.execute("DELETE FROM categories")
    clear_cache()
    await message.answer("✅ **تم مسح جميع الأقسام والتطبيقات بنجاح!**\nالمتجر الآن فارغ تماماً، يمكنك إضافة تطبيقاتك وربطها يدوياً.")

@router.message(Command("cancel"))
@router.message(Command("الغاء"))
@router.message(Command("رجوع"))
@router.message(F.text == "/cancel")
@router.message(F.text == "/الغاء")
@router.message(F.text == "/رجوع")
async def cmd_cancel(message: types.Message, state: FSMContext, db_pool):
    await state.clear()
    async with db_pool.acquire() as conn:
        user_data = await conn.fetchrow("SELECT balance, currency FROM users WHERE user_id = $1", message.from_user.id)
        balance = user_data['balance'] or 0 if user_data else 0
        currency = user_data['currency'] or 'USD' if user_data else 'USD'
    current_rate = await get_exchange_rate(db_pool)
    balance_usd = balance / current_rate if current_rate > 0 else 0
    
    welcome_text = (f"أهلاً بك في بوت الخدمات 🤖\n\nرقم حسابك: <code>{message.from_user.id}</code>\nرصيدك الحالي: {balance_usd:,.2f} $\n\nاختر من القائمة أدناه 👇")
    await message.answer(welcome_text, reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id), currency), parse_mode="HTML")

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext, db_pool):
    if message.from_user.id == 8384048684: return
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
    currency = 'USD'
    
    channel_username = "@LINKcharger22"
    try:
        member = await message.bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        is_member = member.status in ["member", "administrator", "creator"]
    except: is_member = False
    
    if not is_member:
        if referral_code:
            await state.update_data(referral_code=referral_code)
            await state.set_state(ReferralStates.waiting_subscription)
        join_button = InlineKeyboardBuilder()
        join_button.row(types.InlineKeyboardButton(text="📢 انضم إلى القناة", url="https://t.me/LINKcharger22"))
        join_button.row(types.InlineKeyboardButton(text="✅ تحقق من الاشتراك", callback_data="check_subscription"))
        await message.answer("❌ **عذراً، يجب الاشتراك في قناتنا أولاً.**\n📢 **قناة البوت:** @LINKcharger22", reply_markup=join_button.as_markup(), parse_mode="Markdown")
        return
    
    current_rate = await get_exchange_rate(db_pool)
    async with db_pool.acquire() as conn:
        user = await get_cached_user(db_pool, user_id)
        if not user:
            new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            await conn.execute('''INSERT INTO users (user_id, username, first_name, last_name, balance, referral_code, created_at, is_banned, currency) VALUES ($1, $2, $3, $4, 0, $5, CURRENT_TIMESTAMP, FALSE, 'USD')''', user_id, username, first_name, last_name, new_code)
            clear_cache(f"user:{user_id}")
            clear_cache(f"user_ban:{user_id}")
            if referral_code:
                try:
                    referrer = await conn.fetchrow("SELECT user_id, username, total_points FROM users WHERE referral_code = $1", referral_code)
                    if referrer and referrer['user_id'] != user_id:
                        await conn.execute("UPDATE users SET referred_by = $1 WHERE user_id = $2", referrer['user_id'], user_id)
                        await conn.execute('''UPDATE users SET referral_count = referral_count + 1, total_points = total_points + 1, referral_earnings = referral_earnings + 1 WHERE user_id = $1''', referrer['user_id'])
                        clear_cache(f"user:{referrer['user_id']}")
                except: pass
        else:
            await conn.execute("UPDATE users SET username = $1, first_name = $2, last_name = $3, last_activity = CURRENT_TIMESTAMP WHERE user_id = $4", username, first_name, last_name, user_id)
            clear_cache(f"user:{user_id}")
            is_banned = await get_cached_user_ban_status(db_pool, user_id) or False
            user_data = await conn.fetchrow("SELECT balance, currency FROM users WHERE user_id = $1", user_id)
            balance = user_data['balance'] or 0 if user_data else 0
            currency = user_data['currency'] or 'USD' if user_data else 'USD'
            
    if is_banned: return await message.answer("🚫 عذراً، حسابك محظور.\n📞 للتواصل مع الدعم: @Charger444")
    
    balance_usd = balance / current_rate if current_rate > 0 else 0
    await message.answer(f"أهلاً بك في بوت الخدمات 🤖\n\nرقم حسابك: <code>{user_id}</code>\nرصيدك الحالي: {balance_usd:,.2f} $\n\nاختر من القائمة أدناه 👇", reply_markup=get_main_menu_keyboard(is_admin(user_id), currency), parse_mode="HTML")

@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: types.CallbackQuery, state: FSMContext, db_pool):
    await callback.answer()
    try:
        member = await callback.bot.get_chat_member(chat_id="@LINKcharger22", user_id=callback.from_user.id)
        is_member = member.status in ["member", "administrator", "creator"]
    except: is_member = False
    
    if is_member:
        await callback.message.delete()
        await cmd_start(callback.message, state, db_pool)
    else:
        await callback.answer("❌ لم تشترك في القناة بعد!", show_alert=True)

@router.callback_query(F.data == "change_currency")
async def change_currency_menu(callback: types.CallbackQuery, db_pool):
    await callback.answer()
    async with db_pool.acquire() as conn:
        user_data = await conn.fetchrow("SELECT balance, currency FROM users WHERE user_id = $1", callback.from_user.id)
        balance = user_data['balance'] or 0
        current_currency = user_data['currency'] or 'USD'
        
    current_rate = await get_exchange_rate(db_pool)
    balance_usd = balance / current_rate if current_rate > 0 else 0
    
    text = (f"**عملة الحساب 💱**\n\nالعملة الحالية: **{'دولار ($)' if current_currency == 'USD' else 'ليرة (ل.س)'}**\nرصيدك: **{balance_usd:,.2f} $**\n\nℹ كل الأسعار ورصيدك تظهر بالعملة المختارة حسب صرف وسيلة الإيداع المرتبطة بها.\n\nاختر العملة 👇:")
    await callback.message.edit_text(text, reply_markup=get_currency_keyboard(current_currency), parse_mode="Markdown")

@router.callback_query(F.data.in_(["set_curr_USD", "set_curr_SYP"]))
async def set_currency(callback: types.CallbackQuery, db_pool):
    new_curr = callback.data.split("_")[2]
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET currency = $1 WHERE user_id = $2", new_curr, callback.from_user.id)
    clear_cache(f"user:{callback.from_user.id}")
    await callback.answer(f"✅ تم تغيير العملة إلى {'دولار' if new_curr == 'USD' else 'ليرة'}", show_alert=False)
    try:
        await callback.message.edit_reply_markup(reply_markup=get_currency_keyboard(new_curr))
    except TelegramBadRequest: pass

@router.callback_query(F.data == "vip_system")
async def show_vip_system(callback: types.CallbackQuery, db_pool):
    await callback.answer()
    current_rate = await get_exchange_rate(db_pool)
    vip_data = await get_user_vip(db_pool, callback.from_user.id)
    total_spent_usd = vip_data.get('total_spent', 0) / current_rate if current_rate > 0 else 0
    next_level_info = get_next_vip_level(vip_data.get('total_spent', 0))
    
    if next_level_info['remaining'] > 0:
        req_spent_usd = (vip_data.get('total_spent', 0) + next_level_info['remaining']) / current_rate
        remaining_usd = next_level_info['remaining'] / current_rate
        progress_msg = (f"▫️ VIP 0 — المستوى الافتراضي (بدون خصم)\n🔒 VIP {next_level_info['next_level']} — VIP {next_level_info['next_level']}\n\n🏷 الخصم: **{next_level_info['next_discount']:.2f}%**\n💰 المصروف المطلوب: **{req_spent_usd:,.2f} $**\n\n🚀 باقي لك **{remaining_usd:,.2f} $** للوصول إلى VIP {next_level_info['next_level']}")
    else: progress_msg = "✨ لقد وصلت إلى أعلى مستوى VIP!"
    
    text = (f"**نظام الخصومات 💎**\n━━━━━━━━━━━━━━━\nكلما زادت مصروفاتك في البوت ترتقي تلقائياً لمستوى أعلى وتنخفض أسعار جميع المنتجات لك.\n\n👤 مستواك الحالي: **VIP {vip_data.get('vip_level', 0)}**\n💸 إجمالي مصروفك: **{total_spent_usd:,.2f} $**\n\n{progress_msg}")
    await callback.message.edit_text(text, reply_markup=get_back_to_main_keyboard(), parse_mode="Markdown")

@router.message(F.text == "🛠 لوحة التحكم")
async def admin_control_panel(message: types.Message, db_pool):
    if not is_admin(message.from_user.id): return await message.answer("⚠️ هذا الزر مخصص للمشرفين فقط.")
    from admin.main import admin_panel
    await admin_panel(message, db_pool)

@router.callback_query(F.data == "show_help")
async def show_help_callback(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("**📞 للمساعدة يرجى التواصل مع الادمن:**\n🔰المعرف :  @Charger444\n\n🔹 **لتحديث القائمة: أرسل /start**", parse_mode="Markdown", reply_markup=get_back_to_main_keyboard())

@router.message(F.text.in_(["🔙 رجوع للقائمة", "/رجوع", "/cancel", "🏠 القائمة الرئيسية", "❌ إلغاء"]))
async def global_back_handler(message: types.Message, state: FSMContext, db_pool):
    await state.clear()
    async with db_pool.acquire() as conn:
        user_data = await conn.fetchrow("SELECT currency FROM users WHERE user_id = $1", message.from_user.id)
    await message.answer("👋 أهلاً بك في القائمة الرئيسية", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id), user_data['currency'] if user_data else 'USD'))
