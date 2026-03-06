# admin/vip.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from utils import is_admin
from handlers.keyboards import get_cancel_keyboard

logger = logging.getLogger(__name__)
router = Router(name="admin_vip")

class VIPStates(StatesGroup):
    waiting_vip_discount = State()
    waiting_vip_downgrade_reason = State()

# رفع مستوى VIP
@router.callback_query(F.data.startswith("upgrade_vip_"))
async def upgrade_vip_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user=user_id)
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT username, first_name, vip_level, discount_percent, total_spent FROM users WHERE user_id = $1",
            user_id
        )
    
    if not user:
        return await callback.answer("المستخدم غير موجود", show_alert=True)
    
    username = user['username'] or user['first_name'] or str(user_id)
    current_vip = user['vip_level']
    current_discount = user['discount_percent']
    total_spent = user['total_spent']
    
    text = (
        f"👑 **رفع مستوى VIP للمستخدم**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"📊 المستوى الحالي: VIP {current_vip} (خصم {current_discount}%)\n"
        f"💰 إجمالي المشتريات: {total_spent:,.0f} ل.س\n\n"
        f"اختر المستوى الجديد:"
    )
    
    builder = InlineKeyboardBuilder()
    levels = [
        ("⚪ VIP 0 (0%)", 0, 0), ("🔵 VIP 1 (1%)", 1, 1), ("🟣 VIP 2 (2%)", 2, 2),
        ("🟡 VIP 3 (3%)", 3, 3),
    ]
    
    for btn_text, level, discount in levels:
        if level != current_vip:
            builder.row(types.InlineKeyboardButton(text=btn_text, callback_data=f"set_vip_{user_id}_{level}_{discount}"))
    
    builder.row(types.InlineKeyboardButton(text="🎯 خصم مخصص", callback_data=f"custom_discount_{user_id}"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"user_info_cancel"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("set_vip_"))
async def set_vip_level(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    level = int(parts[3])
    discount = int(parts[4])
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            UPDATE users 
            SET vip_level = $1, discount_percent = $2, manual_vip = TRUE
            WHERE user_id = $3
        ''', level, discount, user_id)
        
        user = await conn.fetchrow("SELECT username, first_name FROM users WHERE user_id = $1", user_id)
    
    username = user['username'] or user['first_name'] or str(user_id)
    
    await callback.message.edit_text(
        f"✅ **تم رفع المستوى يدوياً!**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"👑 المستوى الجديد: VIP {level}\n"
        f"💰 نسبة الخصم: {discount}%\n\n"
        f"⚠️ هذا المستوى يدوي ولن يتغير تلقائياً."
    )
    
    try:
        vip_icons = ["⚪", "🔵", "🟣", "🟡"]
        icon = vip_icons[level] if level < len(vip_icons) else "⭐"
        await callback.bot.send_message(
            user_id,
            f"🎉 **تم ترقية مستواك في البوت يدوياً!**\n\n"
            f"{icon} مستواك الجديد: VIP {level}\n"
            f"💰 نسبة الخصم: {discount}%\n\n"
            f"✨ هذا المستوى خاص ولن يتغير تلقائياً."
        )
    except:
        pass

# خصم مخصص
@router.callback_query(F.data.startswith("custom_discount_"))
async def custom_discount_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user=user_id)
    
    await callback.message.edit_text(
        f"🎯 **إعطاء خصم مخصص**\n\n"
        f"أدخل نسبة الخصم المطلوبة (0-100):\n"
        f"مثال: `15` تعني 15% خصم\n\n"
        f"❌ للإلغاء أرسل /cancel"
    )
    await state.set_state(VIPStates.waiting_vip_discount)

@router.message(VIPStates.waiting_vip_discount)
async def set_custom_discount(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "/رجوع", "🔙 رجوع للقائمة"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    try:
        discount = float(message.text.strip())
        if discount < 0 or discount > 100:
            return await message.answer("❌ نسبة الخصم يجب أن تكون بين 0 و 100:", reply_markup=get_cancel_keyboard())
        
        data = await state.get_data()
        user_id = data['target_user']
        
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE users 
                SET discount_percent = $1, manual_vip = TRUE 
                WHERE user_id = $2
            ''', discount, user_id)
            
            user = await conn.fetchrow("SELECT username, first_name, vip_level FROM users WHERE user_id = $1", user_id)
        
        username = user['username'] or user['first_name'] or str(user_id)
        vip_level = user['vip_level']
        
        await message.answer(
            f"✅ **تم تحديث الخصم بنجاح**\n\n"
            f"👤 المستخدم: @{username}\n"
            f"🆔 الآيدي: `{user_id}`\n"
            f"👑 مستوى VIP: {vip_level}\n"
            f"💰 نسبة الخصم الجديدة: {discount}%"
        )
        
        try:
            await message.bot.send_message(
                user_id,
                f"🎁 **تم تعديل نسبة الخصم في حسابك!**\n\n"
                f"💰 نسبة الخصم الجديدة: {discount}%\n"
                f"👑 مستواك الحالي: VIP {vip_level}\n\n"
                f"شكراً لاستخدامك خدماتنا!"
            )
        except:
            pass
        
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إدخال رقم صحيح:", reply_markup=get_cancel_keyboard())

# خفض مستوى VIP
@router.callback_query(F.data.startswith("downgrade_vip_"))
async def downgrade_vip_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user=user_id)
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT username, first_name, vip_level, discount_percent, manual_vip FROM users WHERE user_id = $1",
            user_id
        )
    
    if not user:
        return await callback.answer("المستخدم غير موجود", show_alert=True)
    
    username = user['username'] or user['first_name'] or str(user_id)
    current_vip = user['vip_level']
    current_discount = user['discount_percent']
    manual_status = " (يدوي)" if user['manual_vip'] else ""
    
    text = (
        f"⚠️ **خفض مستوى VIP للمستخدم**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"📊 المستوى الحالي: VIP {current_vip}{manual_status} (خصم {current_discount}%)\n\n"
        f"اختر المستوى الجديد:"
    )
    
    builder = InlineKeyboardBuilder()
    for level in range(0, current_vip):
        if level == 0:
            discount = 0; btn_text = f"⚪ VIP 0 (0%)"
        elif level == 1:
            discount = 1; btn_text = f"🔵 VIP 1 (1%)"
        elif level == 2:
            discount = 2; btn_text = f"🟣 VIP 2 (2%)"
        elif level == 3:
            discount = 3; btn_text = f"🟡 VIP 3 (3%)"
            continue
        
        builder.row(types.InlineKeyboardButton(text=btn_text, callback_data=f"downgrade_to_{user_id}_{level}_{discount}"))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"user_info_cancel"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("downgrade_to_"))
async def downgrade_vip_ask_reason(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    new_level = int(parts[3])
    new_discount = int(parts[4])
    
    await state.update_data(target_user=user_id, new_level=new_level, new_discount=new_discount)
    
    await callback.message.edit_text(
        f"⚠️ **خفض مستوى VIP**\n\n"
        f"المستوى الجديد: VIP {new_level} (خصم {new_discount}%)\n\n"
        f"📝 **أدخل سبب خفض المستوى** (سيتم إرساله للمستخدم):\n"
        f"مثال: عدم الالتزام بشروط الاستخدام\n\n"
        f"أو أرسل /skip لتخطي إرسال سبب"
    )
    await state.set_state(VIPStates.waiting_vip_downgrade_reason)

@router.message(VIPStates.waiting_vip_downgrade_reason)
async def downgrade_vip_execute(message: types.Message, state: FSMContext, db_pool, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    user_id = data['target_user']
    new_level = data['new_level']
    new_discount = data['new_discount']
    
    reason = None
    if message.text and message.text != "/skip":
        reason = message.text.strip()
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            UPDATE users 
            SET vip_level = $1, discount_percent = $2, manual_vip = TRUE
            WHERE user_id = $3
        ''', new_level, new_discount, user_id)
        
        user = await conn.fetchrow("SELECT username, first_name FROM users WHERE user_id = $1", user_id)
    
    username = user['username'] or user['first_name'] or str(user_id)
    
    admin_text = (
        f"✅ **تم خفض مستوى VIP بنجاح**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"👑 المستوى الجديد: VIP {new_level}\n"
        f"💰 نسبة الخصم: {new_discount}%\n"
    )
    
    if reason:
        admin_text += f"📝 السبب: {reason}\n"
    
    admin_text += f"\n⚠️ تم إرسال تحذير للمستخدم."
    
    await message.answer(admin_text)
    
    try:
        user_message = (
            f"⚠️ **تم تعديل مستواك في البوت**\n\n"
            f"👑 مستواك الجديد: VIP {new_level}\n"
            f"💰 نسبة الخصم: {new_discount}%\n\n"
        )
        
        if reason:
            user_message += f"📝 **السبب:** {reason}\n\n"
        
        user_message += (
            f"🔸 هذا التعديل نهائي ولن يتغير تلقائياً.\n"
            f"📞 للاستفسار، تواصل مع الدعم."
        )
        
        await bot.send_message(user_id, user_message)
    except Exception as e:
        await message.answer(f"❌ فشل إرسال إشعار للمستخدم: {e}")
    
    await state.clear()

@router.callback_query(F.data == "user_info_cancel")
async def user_info_cancel(callback: types.CallbackQuery):
    await callback.message.edit_text("✅ تم الإلغاء")