# admin/users.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import time
from typing import Optional, Dict, Any
from utils import is_admin, format_amount, format_datetime, safe_edit_message, get_formatted_damascus_time
from handlers.keyboards import get_confirmation_keyboard
from database.users import get_user_profile, get_user_by_id
from database.cache_utils import invalidate_user_cache
from database.core import get_exchange_rate
from database.points import get_redemption_rate, get_user_points_summary
from database.vip import get_next_vip_level
from cache import cached, clear_cache

logger = logging.getLogger(__name__)
router = Router(name="admin_users")

class UserStates(StatesGroup):
    waiting_user_info = State()
    waiting_balance_amount = State()
    waiting_points_amount = State()
    waiting_search_query = State()

# ✅ ثوابت للأداء
CACHE_TTL_USER_PROFILE = 60

# ✅ كاش لملف المستخدم
@cached(ttl=CACHE_TTL_USER_PROFILE, key_prefix="user_profile")
async def get_cached_user_profile(db_pool, user_id: int) -> Optional[Dict[str, Any]]:
    """جلب ملف المستخدم مع كاش دقيقة"""
    return await get_user_profile(db_pool, user_id)

# ✅ كاش للبحث عن المستخدمين
@cached(ttl=30, key_prefix="user_search")
async def search_users(db_pool, query: str, limit: int = 10):
    """البحث عن المستخدمين بالآيدي أو اليوزرنيم"""
    async with db_pool.acquire() as conn:
        # البحث بالآيدي
        try:
            user_id = int(query)
            users = await conn.fetch('''
                SELECT user_id, username, first_name, balance, is_banned 
                FROM users WHERE user_id = $1
                LIMIT $2
            ''', user_id, limit)
            if users:
                return users
        except ValueError:
            pass
        
        # البحث باليوزرنيم
        users = await conn.fetch('''
            SELECT user_id, username, first_name, balance, is_banned 
            FROM users 
            WHERE username ILIKE $1 OR first_name ILIKE $1
            ORDER BY 
                CASE 
                    WHEN username ILIKE $2 THEN 1
                    WHEN username ILIKE $3 THEN 2
                    ELSE 3
                END,
                balance DESC
            LIMIT $4
        ''', f'%{query}%', f'{query}%', f'%{query}', limit)
        
        return users


# ============= معلومات المستخدم =============
@router.callback_query(F.data == "user_info")
async def user_info_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء البحث عن معلومات مستخدم"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    await callback.message.answer(
        "👤 <b>البحث عن مستخدم</b>\n\n"
        "أدخل آيدي المستخدم (ID) أو اليوزر نيم للبحث:\n"
        "مثال: <code>123456789</code> أو @username\n\n"
        " أرسل /cancel للإلغاء",
        parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_user_info)


@router.message(UserStates.waiting_user_info)
async def user_info_search(message: types.Message, state: FSMContext, db_pool):
    """البحث عن المستخدم وعرض النتائج"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء البحث")
        return
    
    query = message.text.strip().replace('@', '')
    
    users = await search_users(db_pool, query)
    
    if not users:
        await message.answer(
            "❌ لم يتم العثور على مستخدمين\n"
            "تأكد من الآيدي أو اليوزر نيم وحاول مرة أخرى.",
        )
        return
    
    if len(users) == 1:
        await show_user_details(message, state, db_pool, users[0]['user_id'])
    else:
        await show_user_search_results(message, state, users)


async def show_user_search_results(message: types.Message, state: FSMContext, users):
    """عرض نتائج البحث المتعددة"""
    text = "🔍 <b>نتائج البحث:</b>\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for user in users:
        username = f"@{user['username']}" if user['username'] else "لا يوجد"
        name = user['first_name'] or "غير معروف"
        status = "🔒" if user['is_banned'] else "✅"
        
        text += f"{status} <b>{name}</b>\n"
        text += f"   🆔 <code>{user['user_id']}</code> | {username}\n"
        text += f"   💰 {user['balance']:,.0f} ل.س\n\n"
        
        builder.row(types.InlineKeyboardButton(
            text=f"اختر {user['user_id']}",
            callback_data=f"select_user_{user['user_id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_user_search"))
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UserStates.waiting_user_info)


@router.callback_query(F.data.startswith("select_user_"))
async def select_user_from_search(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """اختيار مستخدم من نتائج البحث"""
    await callback.answer()
    
    user_id = int(callback.data.split("_")[2])
    await show_user_details(callback.message, state, db_pool, user_id)


@router.callback_query(F.data == "cancel_user_search")
async def cancel_user_search(callback: types.CallbackQuery, state: FSMContext):
    """إلغاء البحث عن المستخدم"""
    await callback.answer()
    await state.clear()
    await safe_edit_message(callback.message, "✅ تم إلغاء البحث.")


async def show_user_details(message: types.Message, state: FSMContext, db_pool, user_id: int):
    """عرض تفاصيل المستخدم - باستخدام HTML"""
    start_time = time.time()
    
    profile = await get_cached_user_profile(db_pool, user_id)
    
    if not profile:
        await message.answer("⚠️ <b>المستخدم غير موجود</b>", parse_mode="HTML")
        await state.clear()
        return
    
    user = profile['user']
    deposits = profile['deposits']
    orders = profile['orders']
    
    join_date = format_datetime(user.get('created_at'), '%Y-%m-%d %H:%M')
    last_active = format_datetime(user.get('last_activity'), '%Y-%m-%d %H:%M')
    
    manual_status = " (يدوي)" if user.get('manual_vip') else ""
    
    next_level = get_next_vip_level(user.get('total_spent', 0))
    progress_text = ""
    if next_level and next_level.get('remaining', 0) > 0:
        progress_text = f"\n📊 متبقي {next_level['remaining']:,.0f} ل.س للمستوى {next_level['next_level_name']}"
    
    points_earned = orders.get('total_points_earned', 0) if orders else 0
    processing_count = orders.get('processing_count', 0) if orders else 0
    failed_count = orders.get('failed_count', 0) if orders else 0
    
    avg_order = 0
    if orders.get('completed_count', 0) > 0:
        avg_order = orders.get('completed_amount', 0) / orders.get('completed_count', 0)
    
    elapsed_time = time.time() - start_time
    
    # ✅ استخدام HTML بدلاً من Markdown
    info_text = (
        f"👤 <b>معلومات المستخدم</b>\n\n"
        f"🆔 <b>الآيدي:</b> <code>{user['user_id']}</code>\n"
        f"👤 <b>اليوزر:</b> @{user['username'] or 'غير موجود'}\n"
        f"📝 <b>الاسم:</b> {user.get('first_name', '')} {user.get('last_name', '')}\n"
        f"💰 <b>الرصيد:</b> {format_amount(user.get('balance', 0))}\n"
        f"⭐ <b>النقاط:</b> {user.get('total_points', 0)}\n"
        f"👑 <b>مستوى VIP:</b> {user.get('vip_level', 0)}{manual_status} (خصم {user.get('discount_percent', 0)}%){progress_text}\n"
        f"💰 <b>إجمالي الإنفاق:</b> {format_amount(user.get('total_spent', 0))}\n"
        f"🔒 <b>الحالة:</b> {'🚫 محظور' if user.get('is_banned') else '✅ نشط'}\n"
        f"📅 <b>تاريخ التسجيل:</b> {join_date}\n"
        f"⏰ <b>آخر نشاط:</b> {last_active}\n"
        f"🔗 <b>كود الإحالة:</b> <code>{user.get('referral_code', 'لا يوجد')}</code>\n"
        f"👥 <b>تمت إحالته بواسطة:</b> {user.get('referred_by', 'لا يوجد')}\n\n"
        
        f"📊 <b>إحصائيات الإيداعات:</b>\n"
        f"• إجمالي الإيداعات: {deposits.get('total_count', 0)} عملية\n"
        f"• إجمالي المبالغ: {format_amount(deposits.get('total_amount', 0))}\n"
        f"• الإيداعات المقبولة: {deposits.get('approved_count', 0)} عملية\n"
        f"• قيمة المقبولة: {format_amount(deposits.get('approved_amount', 0))}\n\n"
        
        f"📊 <b>إحصائيات الطلبات:</b>\n"
        f"• إجمالي الطلبات: {orders.get('total_count', 0)} طلب\n"
        f"• إجمالي المبالغ: {format_amount(orders.get('total_amount', 0))}\n"
        f"• الطلبات قيد التنفيذ: {processing_count} طلب\n"
        f"• الطلبات المكتملة: {orders.get('completed_count', 0)} طلب\n"
        f"• الطلبات الفاشلة: {failed_count} طلب\n"
        f"• قيمة المكتملة: {format_amount(orders.get('completed_amount', 0))}\n"
        f"• متوسط قيمة الطلب: {format_amount(avg_order)}\n"
        f"• نقاط مكتسبة من الطلبات: {points_earned}\n\n"
        
        f"⚡ وقت التحميل: {elapsed_time:.2f} ثانية"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="🔓 فك الحظر" if user.get('is_banned') else "🔒 حظر",
            callback_data=f"toggle_ban_{user['user_id']}"
        ),
        types.InlineKeyboardButton(
            text="💰 تعديل الرصيد",
            callback_data=f"edit_bal_{user['user_id']}"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="⭐ إضافة نقاط",
            callback_data=f"add_points_{user['user_id']}"
        ),
        types.InlineKeyboardButton(
            text="👑 رفع مستوى VIP",
            callback_data=f"upgrade_vip_{user['user_id']}"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="⬇️ خفض مستوى VIP",
            callback_data=f"downgrade_vip_{user['user_id']}"
        ),
        types.InlineKeyboardButton(
            text="📋 سجل النقاط",
            callback_data=f"user_points_history_{user['user_id']}"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🔄 تحديث",
            callback_data=f"refresh_user_{user['user_id']}"
        ),
        types.InlineKeyboardButton(
            text="🔍 بحث جديد",
            callback_data="user_info"
        )
    )
    
    # ✅ استخدام parse_mode="HTML"
    await message.answer(info_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data.startswith("refresh_user_"))
async def refresh_user(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """تحديث معلومات المستخدم"""
    await callback.answer("🔄 جاري التحديث...")
    
    user_id = int(callback.data.split("_")[2])
    clear_cache(f"user_profile:{user_id}")
    await show_user_details(callback.message, state, db_pool, user_id)


@router.callback_query(F.data.startswith("user_points_history_"))
async def user_points_history(callback: types.CallbackQuery, db_pool):
    """عرض سجل نقاط المستخدم"""
    await callback.answer()
    
    user_id = int(callback.data.split("_")[3])
    
    async with db_pool.acquire() as conn:
        history = await conn.fetch('''
            SELECT points, action, description, created_at
            FROM points_history
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 20
        ''', user_id)
        
        user = await conn.fetchrow("SELECT username FROM users WHERE user_id = $1", user_id)
    
    if not history:
        await callback.answer("لا يوجد سجل نقاط لهذا المستخدم", show_alert=True)
        return
    
    username = user['username'] if user else f"ID:{user_id}"
    
    text = f"📋 <b>سجل نقاط المستخدم</b> @{username}\n\n"
    
    for h in history:
        symbol = "➕" if h['points'] > 0 else "➖"
        date = format_datetime(h['created_at'], '%Y-%m-%d %H:%M')
        
        action_names = {
            'order_completed': 'شراء',
            'referral': 'إحالة',
            'admin_add': 'إضافة',
            'redemption': 'استرداد'
        }
        action = action_names.get(h['action'], h['action'])
        
        text += f"{symbol} <b>{abs(h['points'])} نقطة</b> - {action}\n"
        text += f"   📝 {h['description']}\n"
        text += f"   🕐 {date}\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data=f"select_user_{user_id}"
    ))
    
    await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# ============= إضافة نقاط =============
@router.callback_query(F.data.startswith("add_points_"))
async def add_points_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء إضافة نقاط لمستخدم"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    try:
        user_id = int(callback.data.split("_")[2])
        await state.update_data(target_user=user_id)
        await callback.message.answer(
            f"⭐ <b>إضافة نقاط للمستخدم {user_id}</b>\n\n"
            f"أدخل عدد النقاط (رقم موجب):\n\n"
            f" أرسل /cancel للإلغاء",
            parse_mode="HTML"
        )
        await state.set_state(UserStates.waiting_points_amount)
    except Exception as e:
        logger.error(f"خطأ في بدء إضافة نقاط: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)


@router.message(UserStates.waiting_points_amount)
async def add_points_finalize(message: types.Message, state: FSMContext, db_pool):
    """إضافة النقاط للمستخدم"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        points = int(message.text.strip())
        if points <= 0:
            return await message.answer(
                "⚠️ يرجى إدخال رقم موجب:",
            )
        
        data = await state.get_data()
        user_id = data['target_user']
        
        start_time = time.time()
        
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                user = await conn.fetchrow("SELECT username, total_points FROM users WHERE user_id = $1", user_id)
                if not user:
                    return await message.answer("❌ المستخدم غير موجود")
                
                await conn.execute(
                    "UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2",
                    points, user_id
                )
                await conn.execute('''
                    INSERT INTO points_history (user_id, points, action, description, created_at)
                    VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                ''', user_id, points, 'admin_add', f'إضافة نقاط من الأدمن: {points}')
                
                new_total = await conn.fetchval("SELECT total_points FROM users WHERE user_id = $1", user_id)
        
        await invalidate_user_cache(user_id)
        clear_cache(f"user_profile:{user_id}")
        
        elapsed_time = time.time() - start_time
        
        await message.answer(
            f"✅ <b>تم إضافة النقاط بنجاح!</b>\n\n"
            f"👤 المستخدم: @{user['username'] or 'غير معروف'}\n"
            f"⭐ النقاط المضافة: +{points}\n"
            f"💰 الرصيد الجديد: {new_total}\n"
            f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية",
            parse_mode="HTML"
        )
        
        try:
            await message.bot.send_message(
                user_id,
                f"✅ <b>تم إضافة نقاط إلى حسابك!</b>\n\n"
                f"⭐ النقاط المضافة: +{points}\n"
                f"💰 رصيدك الحالي: {new_total}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمستخدم {user_id}: {e}")
        
        await state.clear()
        
    except ValueError:
        await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 100):")
    except Exception as e:
        logger.error(f"خطأ في إضافة نقاط: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()


# ============= تعديل الرصيد =============
@router.callback_query(F.data.startswith("edit_bal_"))
async def edit_balance_from_info(callback: types.CallbackQuery, state: FSMContext):
    """بدء تعديل الرصيد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    try:
        user_id = int(callback.data.split("_")[2])
        await state.update_data(target_user=user_id)
        await callback.message.answer(
            f"💰 <b>تعديل رصيد المستخدم {user_id}</b>\n\n"
            f"أدخل المبلغ المراد إضافته (يمكن أن يكون سالباً للخصم):\n"
            f"مثال: <code>5000</code> للإضافة، <code>-1000</code> للخصم\n\n"
            f" أرسل /cancel للإلغاء",
            parse_mode="HTML"
        )
        await state.set_state(UserStates.waiting_balance_amount)
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)


@router.message(UserStates.waiting_balance_amount)
async def finalize_add_balance(message: types.Message, state: FSMContext, db_pool):
    """تعديل رصيد المستخدم"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        amount = float(message.text.strip())
        
        data = await state.get_data()
        user_id = data['target_user']
        
        start_time = time.time()
        
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                user = await conn.fetchrow(
                    "SELECT username, balance, total_points FROM users WHERE user_id = $1",
                    user_id
                )
                
                if not user:
                    return await message.answer("❌ المستخدم غير موجود")
                
                new_balance = user['balance'] + amount
                if new_balance < 0:
                    return await message.answer(
                        f"⚠️ لا يمكن خصم {abs(amount):.0f} ل.س لأن الرصيد الحالي {user['balance']:,.0f} ل.س"
                    )
                
                await conn.execute(
                    "UPDATE users SET balance = balance + $1, total_deposits = total_deposits + $1 WHERE user_id = $2",
                    amount, user_id
                )
        
        await invalidate_user_cache(user_id)
        clear_cache(f"user_profile:{user_id}")
        
        elapsed_time = time.time() - start_time
        action = "إضافة" if amount > 0 else "خصم"
        
        await message.answer(
            f"✅ <b>تم {action} الرصيد بنجاح</b>\n\n"
            f"👤 <b>المستخدم:</b> @{user['username'] or 'بدون اسم'}\n"
            f"💰 <b>المبلغ:</b> {abs(amount):,.0f} ل.س ({action})\n"
            f"💳 <b>الرصيد الجديد:</b> {new_balance:,.0f} ل.س\n"
            f"⭐ <b>النقاط:</b> {user['total_points']}\n"
            f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية",
            parse_mode="HTML"
        )
        
        try:
            action_text = "إضافة" if amount > 0 else "خصم"
            await message.bot.send_message(
                user_id,
                f"💰 <b>تم {action_text} رصيد من الإدارة</b>\n\n"
                f"💰 <b>المبلغ:</b> {abs(amount):,.0f} ل.س ({action_text})\n"
                f"💳 <b>الرصيد الحالي:</b> {new_balance:,.0f} ل.س",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمستخدم {user_id}: {e}")
        
        await state.clear()
        
    except ValueError:
        return await message.answer("⚠️ خطأ! يرجى إدخال رقم صحيح (مثال: 5000 أو -1000):")
    except Exception as e:
        logger.error(f"خطأ في تعديل الرصيد: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()


# ============= تبديل حالة الحظر =============
@router.callback_query(F.data.startswith("toggle_ban_"))
async def toggle_ban_from_info(callback: types.CallbackQuery, db_pool):
    """تبديل حالة الحظر"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    try:
        user_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT is_banned, username FROM users WHERE user_id = $1", user_id)
            
            if user:
                new_status = not user['is_banned']
                await conn.execute("UPDATE users SET is_banned = $1 WHERE user_id = $2", new_status, user_id)
                
                await invalidate_user_cache(user_id)
                clear_cache(f"user_profile:{user_id}")
                
                status_text = "محظور" if new_status else "نشط"
                await callback.message.answer(
                    f"✅ تم تغيير حالة المستخدم إلى: {status_text}\n"
                    f"👤 المستخدم: @{user['username'] or 'غير معروف'}"
                )
                
                try:
                    await callback.bot.send_message(
                        user_id,
                        f"⚠️ <b>تم تغيير حالة حسابك</b>\n\n"
                        f"الحالة الجديدة: {'🚫 محظور' if new_status else '✅ نشط'}\n"
                        f"📞 للاستفسار، تواصل مع الدعم.",
                        parse_mode="HTML"
                    )
                except:
                    pass
            else:
                await callback.answer("المستخدم غير موجود", show_alert=True)
                
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)


# ============= قائمة المستخدمين =============
@router.callback_query(F.data == "list_users")
async def list_users(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المستخدمين"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        active_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE NOT is_banned")
        banned_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned")
        
        recent_users = await conn.fetch('''
            SELECT user_id, username, first_name, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT 10
        ''')
    
    text = (
        f"👥 <b>قائمة المستخدمين</b>\n\n"
        f"📊 <b>إحصائيات:</b>\n"
        f"• إجمالي المستخدمين: {total_users}\n"
        f"• المستخدمين النشطين: {active_users}\n"
        f"• المحظورين: {banned_users}\n\n"
        f"🆕 <b>آخر المستخدمين:</b>\n"
    )
    
    for user in recent_users:
        username = f"@{user['username']}" if user['username'] else "لا يوجد"
        name = user['first_name'] or "غير معروف"
        date = format_datetime(user['created_at'], '%Y-%m-%d')
        text += f"• {name} ({username}) - {date}\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔍 بحث", callback_data="user_info"),
        types.InlineKeyboardButton(text="🔄 تحديث", callback_data="list_users")
    )
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())
