import logging
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID
import database as db
import keyboards as kb

logger = logging.getLogger(__name__)

# هذا هو السطر الذي كان مفقوداً وسبب المشكلة
router = Router()

# ================== حالات الإدارة (FSM) ==================
class AdminStates(StatesGroup):
    waiting_rate = State()
    waiting_provider_info = State()  # name|url|token
    waiting_category_name = State()
    waiting_product_info = State()   # cat_id|prov_id|remote_id|name|price_usd

# ================== أوامر المستخدم ==================

@router.message(CommandStart())
@router.message(F.text.in_(["/cancel", "إلغاء", "رجوع"]))
async def cmd_start(message: types.Message, state: FSMContext, db_pool):
    await state.clear()
    user = await db.get_or_create_user(db_pool, message.from_user.id)
    rate = await db.get_exchange_rate(db_pool)
    
    is_admin = (message.from_user.id == ADMIN_ID)
    
    # استخدام balance حصراً
    raw_balance = user['balance'] if user and 'balance' in user else 0.0
    balance_display = raw_balance if user['currency'] == 'USD' else raw_balance * rate
    curr_sym = "$" if user['currency'] == 'USD' else "ل.س"

    text = (
        f"أهلاً بك في بوت الخدمات 🤖\n\n"
        f"رقم حسابك: <code>{message.from_user.id}</code>\n"
        f"رصيدك الحالي: {balance_display:,.2f} {curr_sym}\n\n"
        f"اختر من القائمة أدناه 👇"
    )
    
    await message.answer(text, reply_markup=kb.main_menu(is_admin, user['currency']), parse_mode="HTML")

@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext, db_pool):
    await callback.answer()
    await cmd_start(callback.message, state, db_pool)

@router.callback_query(F.data == "change_currency")
async def change_currency(callback: types.CallbackQuery, db_pool):
    await callback.answer()
    user = await db.get_or_create_user(db_pool, callback.from_user.id)
    rate = await db.get_exchange_rate(db_pool)
    balance_display = user['balance_usd'] if user['currency'] == 'USD' else user['balance_usd'] * rate
    curr_sym = "$" if user['currency'] == 'USD' else "ل.س"

    text = (
        f"**عملة الحساب 💱**\n\n"
        f"رصيدك: **{balance_display:,.2f} {curr_sym}**\n\n"
        "اختر العملة المفضلة لعرض الأسعار:"
    )
    await callback.message.edit_text(text, reply_markup=kb.currency_menu(user['currency']), parse_mode="Markdown")

@router.callback_query(F.data.startswith("set_curr_"))
async def set_currency(callback: types.CallbackQuery, db_pool):
    new_curr = callback.data.split("_")[2]
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET currency = $1 WHERE user_id = $2", new_curr, callback.from_user.id)
    
    await callback.answer("✅ تم تغيير العملة بنجاح")
    try:
        await callback.message.edit_reply_markup(reply_markup=kb.currency_menu(new_curr))
    except:
        pass

# ================== أوامر الإدارة ==================

@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.answer()
    await callback.message.edit_text("🛠 **لوحة تحكم الإدارة**", reply_markup=kb.admin_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "admin_set_rate")
async def ask_rate(callback: types.CallbackQuery, state: FSMContext, db_pool):
    if callback.from_user.id != ADMIN_ID: return
    await callback.answer()
    rate = await db.get_exchange_rate(db_pool)
    await callback.message.answer(f"سعر الصرف الحالي: {rate}\nأرسل السعر الجديد الآن:")
    await state.set_state(AdminStates.waiting_rate)

@router.message(AdminStates.waiting_rate)
async def set_rate(message: types.Message, state: FSMContext, db_pool):
    if message.from_user.id != ADMIN_ID: return
    try:
        new_rate = float(message.text)
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE settings SET value = $1 WHERE key = 'exchange_rate'", str(new_rate))
        await message.answer(f"✅ تم تحديث سعر الصرف إلى {new_rate}")
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إرسال رقم صحيح.")

@router.callback_query(F.data == "admin_add_provider")
async def ask_provider(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await callback.answer()
    await callback.message.answer("أرسل بيانات موقع الـ API بالصيغة التالية:\n`الاسم|الرابط|التوكن`\n\nمثال:\n`VIP Game|https://vipgame.com|12345token`", parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_provider_info)

@router.message(AdminStates.waiting_provider_info)
async def save_provider(message: types.Message, state: FSMContext, db_pool):
    if message.from_user.id != ADMIN_ID: return
    parts = message.text.split('|')
    if len(parts) != 3:
        return await message.answer("❌ صيغة خاطئة.")
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO api_providers (name, base_url, api_token) VALUES ($1, $2, $3)",
            parts[0].strip(), parts[1].strip(), parts[2].strip()
        )
    await message.answer(f"✅ تم إضافة المزود {parts[0]} بنجاح.")
    await state.clear()
