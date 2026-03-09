# admin/broadcast.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import asyncio
import logging
from utils import is_admin
from handlers.keyboards import get_cancel_keyboard

logger = logging.getLogger(__name__)
router = Router(name="admin_broadcast")

class BroadcastStates(StatesGroup):
    waiting_broadcast_msg = State()
    waiting_custom_message_user = State()
    waiting_custom_message_text = State()

# إرسال رسالة للكل
@router.callback_query(F.data == "broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.answer(
        "📢 **إرسال رسالة للجميع**\n\n"
        "أدخل الرسالة التي تريد إرسالها لجميع المستخدمين:\n\n"
        "✏️ يمكنك استخدام Markdown للتنسيق:\n"
        "• **نص عريض**\n"
        "• *نص مائل*\n"
        "• `كود`\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BroadcastStates.waiting_broadcast_msg)

@router.message(BroadcastStates.waiting_broadcast_msg)
async def send_broadcast(message: types.Message, state: FSMContext, db_pool, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء الإرسال.")
        return
    
    broadcast_text = message.text
    
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users WHERE NOT is_banned")
        total_users = len(users)
        banned_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned")
    
    if total_users == 0:
        await message.answer("⚠️ لا يوجد مستخدمين في قاعدة البيانات")
        await state.clear()
        return
    
    try:
        await bot.send_message(
            message.from_user.id,
            f"📢 **معاينة الرسالة:**\n\n{broadcast_text}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ تأكيد الإرسال", callback_data="confirm_broadcast"),
            types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_broadcast")
        )
        builder.row(types.InlineKeyboardButton(text="📝 تعديل الرسالة", callback_data="edit_broadcast"))
        
        await message.answer(
            f"📊 **معلومات الإرسال**\n\n"
            f"👥 عدد المستلمين: {total_users} مستخدم\n"
            f"🚫 المحظورين: {banned_count} (لن يستلموا)\n\n"
            f"هل أنت متأكد من إرسال الرسالة؟",
            reply_markup=builder.as_markup()
        )
        
        await state.update_data(broadcast_text=broadcast_text, total_users=total_users)
    except Exception as e:
        await message.answer(
            f"❌ **خطأ في تنسيق Markdown**\n\n"
            f"الخطأ: {str(e)}\n\n"
            f"تأكد من إغلاق جميع الرموز بشكل صحيح:\n"
            f"• `**نص**` للنص العريض\n"
            f"• `*نص*` للنص المائل\n"
            f"• `` `نص` `` للكود"
        )

@router.callback_query(F.data == "edit_broadcast")
async def edit_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 **أدخل الرسالة الجديدة:**\n\n"
        "✏️ يمكنك استخدام Markdown للتنسيق:\n"
        "• **نص عريض**\n"
        "• *نص مائل*\n"
        "• `كود`\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_broadcast")
async def confirm_broadcast(callback: types.CallbackQuery, state: FSMContext, bot: Bot, db_pool):
    data = await state.get_data()
    broadcast_text = data.get('broadcast_text')
    total_users = data.get('total_users', 0)
    
    if not broadcast_text:
        await callback.answer("❌ لا توجد رسالة للإرسال", show_alert=True)
        await state.clear()
        return
    
    await callback.message.edit_text("⏳ **جاري الإرسال...**\nقد يستغرق هذا بعض الوقت.")
    
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users WHERE NOT is_banned")
    
    success_count = 0
    failed_count = 0
    failed_users = []
    
    for i, user in enumerate(users):
        user_id = user['user_id']
        
        if user_id == callback.from_user.id:
            continue
        
        try:
            await bot.send_message(
                user_id,
                f"📢 **رسالة من الإدارة:**\n\n{broadcast_text}",
                parse_mode=ParseMode.MARKDOWN
            )
            success_count += 1
        except Exception:
            try:
                await bot.send_message(
                    user_id,
                    f"📢 رسالة من الإدارة:\n\n{broadcast_text}"
                )
                success_count += 1
            except Exception:
                failed_count += 1
                failed_users.append(str(user_id))
        
        if (i + 1) % 10 == 0:
            await callback.message.edit_text(
                f"⏳ **جاري الإرسال...**\n"
                f"✅ تم: {success_count}\n"
                f"❌ فشل: {failed_count}\n"
                f"📊 المتبقي: {total_users - (i + 1)}"
            )
        
        await asyncio.sleep(0.05)
    
    result_text = (
        f"✅ **تم إرسال الرسالة**\n\n"
        f"📊 **نتيجة الإرسال:**\n"
        f"• ✅ نجح: {success_count}\n"
        f"• ❌ فشل: {failed_count}\n"
        f"• 👥 الإجمالي: {total_users}\n\n"
    )
    
    if failed_users:
        failed_sample = failed_users[:10]
        result_text += f"⚠️ أمثلة على المستخدمين الذين فشل الإرسال لهم:\n"
        result_text += f"`{', '.join(failed_sample)}`\n"
        if len(failed_users) > 10:
            result_text += f"... و{len(failed_users) - 10} آخرين\n"
    
    await callback.message.edit_text(result_text)
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO logs (user_id, action, details, created_at)
            VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
        ''', callback.from_user.id, 'broadcast', 
           f'إرسال رسالة جماعية - نجح: {success_count}, فشل: {failed_count}')
    
    await state.clear()

@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("✅ تم إلغاء الإرسال.")

# إرسال رسالة لمستخدم محدد
@router.callback_query(F.data == "send_custom_message")
async def send_custom_message_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.answer(
        "✉️ **إرسال رسالة لمستخدم محدد**\n\n"
        "أدخل آيدي المستخدم (ID) أو اليوزر نيم:\n"
        "مثال: `123456789` أو `@username`\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BroadcastStates.waiting_custom_message_user)

@router.message(BroadcastStates.waiting_custom_message_user)
async def get_custom_message_user(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    search_term = message.text.strip()
    
    async with db_pool.acquire() as conn:
        try:
            user_id = int(search_term)
            user = await conn.fetchrow(
                "SELECT user_id, username, first_name FROM users WHERE user_id = $1",
                user_id
            )
        except ValueError:
            username = search_term.replace('@', '')
            user = await conn.fetchrow(
                "SELECT user_id, username, first_name FROM users WHERE username = $1",
                username
            )
    
    if not user:
        await message.answer(
            "❌ **المستخدم غير موجود**\n\n"
            "تأكد من الآيدي أو اليوزر نيم وحاول مرة أخرى.\n"
            "أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(
        target_user=user['user_id'],
        target_username=user['username'] or user['first_name'] or str(user['user_id'])
    )
    
    await message.answer(
        f"👤 **المستخدم المستهدف:** @{user['username'] or 'غير معروف'}\n"
        f"🆔 **الآيدي:** `{user['user_id']}`\n\n"
        f"📝 **أدخل الرسالة التي تريد إرسالها:**\n\n"
        f"✏️ يمكنك استخدام Markdown للتنسيق:\n"
        f"• **نص عريض**\n"
        f"• *نص مائل*\n"
        f"• `كود`\n\n"
        f"أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(BroadcastStates.waiting_custom_message_text)

@router.message(BroadcastStates.waiting_custom_message_text)
async def send_custom_message_text(message: types.Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    custom_text = message.text
    data = await state.get_data()
    target_user = data['target_user']
    target_username = data['target_username']
    
    try:
        await bot.send_message(
            target_user,
            f"✉️ **رسالة خاصة من الإدارة**\n\n{custom_text}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await message.answer(
            f"✅ **تم إرسال الرسالة بنجاح!**\n\n"
            f"👤 إلى: @{target_username}\n"
            f"🆔 الآيدي: `{target_user}`\n\n"
            f"📝 نص الرسالة:\n{custom_text}"
        )
    except Exception as e:
        try:
            await bot.send_message(
                target_user,
                f"✉️ رسالة خاصة من الإدارة:\n\n{custom_text}"
            )
            
            await message.answer(
                f"✅ **تم إرسال الرسالة (كنص عادي) بنجاح!**\n\n"
                f"👤 إلى: @{target_username}\n"
                f"🆔 الآيدي: `{target_user}`\n\n"
                f"📝 نص الرسالة:\n{custom_text}"
            )
        except Exception as e2:
            await message.answer(
                f"❌ **فشل إرسال الرسالة**\n\n"
                f"الخطأ: {str(e2)}\n\n"
                f"تأكد من أن المستخدم لم يحظر البوت."
            )
    
    await state.clear()