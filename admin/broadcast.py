# admin/broadcast.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import asyncio
import logging
import time
from datetime import datetime
from utils import is_admin, is_owner, safe_edit_message, format_datetime
from handlers.keyboards import get_confirmation_keyboard
from cache import cached, clear_cache  # ✅ استيراد الكاش

logger = logging.getLogger(__name__)
router = Router(name="admin_broadcast")

class BroadcastStates(StatesGroup):
    waiting_broadcast_msg = State()
    waiting_custom_message_user = State()
    waiting_custom_message_text = State()

# ✅ ثوابت للإرسال
BROADCAST_BATCH_SIZE = 20  # إرسال 20 رسالة في كل دفعة
BROADCAST_DELAY = 0.03     # تأخير 30ms بين الرسائل

# ✅ كاش لعدد المستخدمين
@cached(ttl=60, key_prefix="users_count")
async def get_cached_users_count(db_pool):
    """جلب عدد المستخدمين مع كاش دقيقة"""
    async with db_pool.acquire() as conn:
        active_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE NOT is_banned")
        banned_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned")
        return {
            'active': active_users or 0,
            'banned': banned_users or 0,
            'total': (active_users or 0) + (banned_users or 0)
        }

# إرسال رسالة للكل
@router.callback_query(F.data == "broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إرسال رسالة للجميع"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ التحقق من أن المستخدم هو المالك أو مشرف كبير
    if not is_owner(callback.from_user.id):
        return await callback.answer("⚠️ فقط المالك يمكنه إرسال رسائل جماعية", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ جلب إحصائيات المستخدمين
    users_stats = await get_cached_users_count(db_pool)
    
    await callback.message.answer(
        f"📢 <b>إرسال رسالة للجميع</b>\n\n"
        f"📊 <b>إحصائيات المستخدمين:</b>\n"
        f"• 👥 المستخدمين النشطين: {users_stats['active']}\n"
        f"• 🚫 المحظورين: {users_stats['banned']}\n"
        f"• 📈 الإجمالي: {users_stats['total']}\n\n"
        f"أدخل الرسالة التي تريد إرسالها لجميع المستخدمين:\n\n"
        f"✏️ يمكنك استخدام Markdown للتنسيق:\n"
        f"• **نص عريض**\n"
        f"• *نص مائل*\n"
        f"• `كود`\n\n"
        f"أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_broadcast_msg)

@router.message(BroadcastStates.waiting_broadcast_msg)
async def send_broadcast(message: types.Message, state: FSMContext, db_pool, bot: Bot):
    """معاينة رسالة جماعية"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء الإرسال.")
        return
    
    broadcast_text = message.text
    
    # ✅ جلب إحصائيات المستخدمين
    users_stats = await get_cached_users_count(db_pool)
    
    if users_stats['active'] == 0:
        await message.answer("⚠️ لا يوجد مستخدمين نشطين في قاعدة البيانات")
        await state.clear()
        return
    
    try:
        # ✅ معاينة الرسالة
        await bot.send_message(
            message.from_user.id,
            f"📢 <b>معاينة الرسالة:</b>\n\n{broadcast_text}",
            parse_mode=ParseMode.HTML
        )
        
        # ✅ أزرار التأكيد
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ تأكيد الإرسال", callback_data="confirm_broadcast"),
            types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_broadcast")
        )
        builder.row(types.InlineKeyboardButton(text="📝 تعديل الرسالة", callback_data="edit_broadcast"))
        
        await message.answer(
            f"📊 <b>معلومات الإرسال</b>\n\n"
            f"👥 عدد المستلمين: {users_stats['active']} مستخدم نشط\n"
            f"🚫 المحظورين: {users_stats['banned']} (لن يستلموا)\n"
            f"⏱️ الوقت المتوقع: ~{users_stats['active'] * BROADCAST_DELAY:.1f} ثانية\n\n"
            f"هل أنت متأكد من إرسال الرسالة؟",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
        await state.update_data(
            broadcast_text=broadcast_text,
            total_users=users_stats['active']
        )
    except Exception as e:
        await message.answer(
            f"❌ <b>خطأ في تنسيق HTML</b>\n\n"
            f"الخطأ: {str(e)}\n\n"
            f"تأكد من إغلاق جميع الرموز بشكل صحيح:\n"
            f"• &lt;b&gt;نص عريض&lt;/b&gt;\n"
            f"• &lt;i&gt;نص مائل&lt;/i&gt;\n"
            f"• &lt;code&gt;كود&lt;/code&gt;",
            parse_mode="HTML"
        )

@router.callback_query(F.data == "edit_broadcast")
async def edit_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """تعديل رسالة البث"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await safe_edit_message(
        callback.message,
        "📝 **أدخل الرسالة الجديدة:**\n\n"
        "✏️ يمكنك استخدام Markdown للتنسيق:\n"
        "• **نص عريض**\n"
        "• *نص مائل*\n"
        "• `كود`\n\n"
        "أو أرسل /cancel للإلغاء"
    )

@router.callback_query(F.data == "confirm_broadcast")
async def confirm_broadcast(callback: types.CallbackQuery, state: FSMContext, bot: Bot, db_pool):
    """تأكيد إرسال البث"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    data = await state.get_data()
    broadcast_text = data.get('broadcast_text')
    total_users = data.get('total_users', 0)
    
    if not broadcast_text:
        await callback.answer("❌ لا توجد رسالة للإرسال", show_alert=True)
        await state.clear()
        return
    
    # ✅ تحديث الرسالة
    start_time = time.time()
    await safe_edit_message(
        callback.message,
        f"⏳ <b>جاري الإرسال...</b>\n\n"
        f"📊 0/{total_users} مستخدم\n"
        f"✅ 0 نجح | ❌ 0 فشل",
        parse_mode="HTML"
    )
    
    # ✅ جلب المستخدمين النشطين فقط
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users WHERE NOT is_banned")
    
    success_count = 0
    failed_count = 0
    failed_users = []
    
    # ✅ إرسال على دفعات
    for i in range(0, len(users), BROADCAST_BATCH_SIZE):
        batch = users[i:i + BROADCAST_BATCH_SIZE]
        
        # ✅ إرسال الدفعة بشكل متوازي
        tasks = []
        for user in batch:
            user_id = user['user_id']
            
            if user_id == callback.from_user.id:
                continue
            
            tasks.append(send_single_message(bot, user_id, broadcast_text))
        
        # ✅ انتظار انتهاء الدفعة
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # ✅ تحديث الإحصائيات
        for result in results:
            if isinstance(result, Exception):
                failed_count += 1
            elif result is True:
                success_count += 1
            elif result is False:
                failed_count += 1
                # نضيف المستخدم للقائمة الفاشلة (سيكون None)
        
        # ✅ تحديث进度 كل دفعة
        processed = min(i + BROADCAST_BATCH_SIZE, len(users))
        await safe_edit_message(
            callback.message,
            f"⏳ <b>جاري الإرسال...</b>\n\n"
            f"📊 {processed}/{total_users} مستخدم\n"
            f"✅ {success_count} نجح | ❌ {failed_count} فشل",
            parse_mode="HTML"
        )
        
        # ✅ تأخير بسيط بين الدفعات
        await asyncio.sleep(BROADCAST_DELAY)
    
    # ✅ حساب الوقت المستغرق
    elapsed_time = time.time() - start_time
    
    # ✅ إعداد النتيجة النهائية
    result_text = (
        f"✅ <b>تم إرسال الرسالة</b>\n\n"
        f"📊 <b>نتيجة الإرسال:</b>\n"
        f"• ✅ نجح: {success_count}\n"
        f"• ❌ فشل: {failed_count}\n"
        f"• 👥 الإجمالي: {total_users}\n"
        f"• ⏱️ الوقت: {elapsed_time:.1f} ثانية\n\n"
    )
    
    # ✅ إضافة زر إعادة الإرسال للمستخدمين الفاشلين
    builder = InlineKeyboardBuilder()
    if failed_count > 0:
        result_text += f"⚠️ فشل الإرسال لـ {failed_count} مستخدم"
        builder.row(types.InlineKeyboardButton(
            text="🔄 إعادة للمستخدمين الفاشلين", 
            callback_data="retry_failed_broadcast"
        ))
    
    await safe_edit_message(
        callback.message,
        result_text,
        reply_markup=builder.as_markup() if failed_count > 0 else None,
        parse_mode="HTML"
    )
    
    # ✅ تسجيل في السجل
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO logs (user_id, action, details, created_at)
            VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
        ''', callback.from_user.id, 'broadcast', 
           f'إرسال رسالة جماعية - نجح: {success_count}, فشل: {failed_count}, وقت: {elapsed_time:.1f}ث')
    
    await state.clear()


async def send_single_message(bot: Bot, user_id: int, text: str) -> bool:
    """إرسال رسالة لمستخدم واحد"""
    try:
        await bot.send_message(
            user_id,
            f"📢 <b>رسالة من الإدارة:</b>\n\n{text}",
            parse_mode=ParseMode.HTML
        )
        return True
    except Exception:
        try:
            # ✅ محاولة إرسال كنص عادي
            await bot.send_message(
                user_id,
                f"📢 رسالة من الإدارة:\n\n{text}"
            )
            return True
        except Exception:
            return False


@router.callback_query(F.data == "retry_failed_broadcast")
async def retry_failed_broadcast(callback: types.CallbackQuery, state: FSMContext, bot: Bot, db_pool):
    """إعادة إرسال للمستخدمين الفاشلين"""
    # ✅ هذه دالة مستقبلية يمكن تطويرها
    await callback.answer("هذه الميزة قيد التطوير", show_alert=True)


@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    """إلغاء البث"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await state.clear()
    await safe_edit_message(callback.message, "✅ تم إلغاء الإرسال.")


# إرسال رسالة لمستخدم محدد
@router.callback_query(F.data == "send_custom_message")
async def send_custom_message_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء إرسال رسالة لمستخدم محدد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await callback.message.answer(
        "✉️ <b>إرسال رسالة لمستخدم محدد</b>\n\n"
        "أدخل آيدي المستخدم (ID) أو اليوزر نيم:\n"
        "مثال: <code>123456789</code> أو @username\n\n"
        "أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_custom_message_user)


@router.message(BroadcastStates.waiting_custom_message_user)
async def get_custom_message_user(message: types.Message, state: FSMContext, db_pool):
    """استقبال آيدي المستخدم"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    search_term = message.text.strip()
    user = None
    
    async with db_pool.acquire() as conn:
        try:
            # ✅ محاولة البحث بالآيدي
            user_id = int(search_term)
            user = await conn.fetchrow(
                "SELECT user_id, username, first_name, is_banned FROM users WHERE user_id = $1",
                user_id
            )
        except ValueError:
            # ✅ البحث باليوزر نيم
            username = search_term.replace('@', '')
            user = await conn.fetchrow(
                "SELECT user_id, username, first_name, is_banned FROM users WHERE username = $1",
                username
            )
    
    if not user:
        await message.answer(
            "❌ <b>المستخدم غير موجود</b>\n\n"
            "تأكد من الآيدي أو اليوزر نيم وحاول مرة أخرى.\n"
            "أو أرسل /cancel للإلغاء",
            reply_markup=get_cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # ✅ تحذير إذا كان المستخدم محظوراً
    ban_warning = "\n⚠️ <b>هذا المستخدم محظور!</b>" if user['is_banned'] else ""
    
    await state.update_data(
        target_user=user['user_id'],
        target_username=user['username'] or user['first_name'] or str(user['user_id']),
        is_banned=user['is_banned']
    )
    
    await message.answer(
        f"👤 <b>المستخدم المستهدف:</b> @{user['username'] or 'غير معروف'}\n"
        f"🆔 <b>الآيدي:</b> <code>{user['user_id']}</code>"
        f"{ban_warning}\n\n"
        f"📝 <b>أدخل الرسالة التي تريد إرسالها:</b>\n\n"
        f"✏️ يمكنك استخدام HTML للتنسيق:\n"
        f"• &lt;b&gt;نص عريض&lt;/b&gt;\n"
        f"• &lt;i&gt;نص مائل&lt;/i&gt;\n"
        f"• &lt;code&gt;كود&lt;/code&gt;\n\n"
        f"أو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_custom_message_text)


@router.message(BroadcastStates.waiting_custom_message_text)
async def send_custom_message_text(message: types.Message, state: FSMContext, bot: Bot, db_pool):
    """إرسال الرسالة للمستخدم المحدد"""
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
    is_banned = data.get('is_banned', False)
    
    # ✅ محاولة إرسال الرسالة
    success = False
    error_msg = ""
    
    try:
        # ✅ محاولة إرسال مع HTML
        await bot.send_message(
            target_user,
            f"✉️ <b>رسالة خاصة من الإدارة</b>\n\n{custom_text}",
            parse_mode=ParseMode.HTML
        )
        success = True
    except Exception as e:
        error_msg = str(e)
        try:
            # ✅ محاولة إرسال كنص عادي
            await bot.send_message(
                target_user,
                f"✉️ رسالة خاصة من الإدارة:\n\n{custom_text}"
            )
            success = True
        except Exception as e2:
            error_msg = str(e2)
    
    if success:
        await message.answer(
            f"✅ <b>تم إرسال الرسالة بنجاح!</b>\n\n"
            f"👤 إلى: @{target_username}\n"
            f"🆔 الآيدي: <code>{target_user}</code>\n"
            f"{'⚠️ المستخدم محظور ولكن الرسالة وصلت' if is_banned else ''}\n\n"
            f"📝 نص الرسالة:\n{custom_text}",
            parse_mode="HTML"
        )
        
        # ✅ تسجيل في السجل
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO logs (user_id, action, details, created_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
            ''', message.from_user.id, 'custom_message', 
               f'إرسال رسالة خاصة إلى {target_user} (@{target_username})')
    else:
        await message.answer(
            f"❌ <b>فشل إرسال الرسالة</b>\n\n"
            f"الخطأ: {error_msg}\n\n"
            f"تأكد من أن المستخدم لم يحظر البوت أو أن الآيدي صحيح.",
            parse_mode="HTML"
        )
    
    await state.clear()


# ============= معالج المدخلات الخاطئة =============

@router.message(BroadcastStates.waiting_broadcast_msg)
@router.message(BroadcastStates.waiting_custom_message_user)
@router.message(BroadcastStates.waiting_custom_message_text)
async def wrong_input_handler(message: types.Message, state: FSMContext):
    """معالج المدخلات الخاطئة"""
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم الإلغاء", reply_markup=get_cancel_keyboard())
        return
    
    await message.answer(
        "❌ إدخال غير صحيح\nأو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
