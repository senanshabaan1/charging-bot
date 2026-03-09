# admin/vip.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import time
from typing import Optional, Dict, Any
from utils import is_admin, format_amount, safe_edit_message, get_formatted_damascus_time
from handlers.keyboards import get_confirmation_keyboard, get_cancel_keyboard
from database.vip import get_user_vip, update_user_vip, get_vip_levels
from cache import cached, clear_cache  # ✅ استيراد الكاش

logger = logging.getLogger(__name__)
router = Router(name="admin_vip")

class VIPStates(StatesGroup):
    waiting_vip_discount = State()
    waiting_vip_downgrade_reason = State()
    waiting_vip_custom_level = State()

# ✅ ثوابت للأداء
VIP_ICONS = ["⚪", "🔵", "🟣", "🟡", "💎", "👑"]
VIP_LEVELS = [
    {"level": 0, "name": "VIP 0", "icon": "⚪", "discount": 0},
    {"level": 1, "name": "VIP 1", "icon": "🔵", "discount": 1},
    {"level": 2, "name": "VIP 2", "icon": "🟣", "discount": 2},
    {"level": 3, "name": "VIP 3", "icon": "🟡", "discount": 3},
]

# ✅ كاش لمعلومات المستخدم
@cached(ttl=30, key_prefix="user_vip_info")
async def get_cached_user_vip_info(db_pool, user_id: int) -> Optional[Dict[str, Any]]:
    """جلب معلومات VIP للمستخدم مع كاش 30 ثانية"""
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT username, first_name, vip_level, discount_percent, total_spent, manual_vip FROM users WHERE user_id = $1",
            user_id
        )

# ✅ كاش لقائمة مستويات VIP
@cached(ttl=300, key_prefix="vip_levels_list")
async def get_cached_vip_levels(db_pool):
    """جلب قائمة مستويات VIP مع كاش 5 دقائق"""
    return await get_vip_levels(db_pool)

# رفع مستوى VIP
@router.callback_query(F.data.startswith("upgrade_vip_"))
async def upgrade_vip_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء رفع مستوى VIP لمستخدم"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user=user_id)
    
    # ✅ استخدام الكاش
    user = await get_cached_user_vip_info(db_pool, user_id)
    
    if not user:
        return await callback.answer("المستخدم غير موجود", show_alert=True)
    
    username = user['username'] or user['first_name'] or str(user_id)
    current_vip = user['vip_level']
    current_discount = user['discount_percent']
    total_spent = user['total_spent']
    manual_status = " (يدوي)" if user['manual_vip'] else ""
    
    text = (
        f"👑 **رفع مستوى VIP للمستخدم**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"📊 المستوى الحالي: VIP {current_vip}{manual_status} (خصم {current_discount}%)\n"
        f"💰 إجمالي المشتريات: {total_spent:,.0f} ل.س\n\n"
        f"اختر المستوى الجديد:"
    )
    
    builder = InlineKeyboardBuilder()
    
    for level in VIP_LEVELS:
        if level['level'] != current_vip:
            btn_text = f"{level['icon']} {level['name']} ({level['discount']}%)"
            builder.row(types.InlineKeyboardButton(
                text=btn_text,
                callback_data=f"set_vip_{user_id}_{level['level']}_{level['discount']}"
            ))
    
    builder.row(types.InlineKeyboardButton(text="🎯 خصم مخصص", callback_data=f"custom_discount_{user_id}"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"user_info_cancel"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("set_vip_"))
async def set_vip_level(callback: types.CallbackQuery, db_pool):
    """تحديد مستوى VIP للمستخدم - يدوي"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    parts = callback.data.split("_")
    user_id = int(parts[2])
    level = int(parts[3])
    discount = int(parts[4])
    
    start_time = time.time()
    
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('''
                UPDATE users 
                SET vip_level = $1, discount_percent = $2, manual_vip = TRUE
                WHERE user_id = $3
            ''', level, discount, user_id)
            
            user = await conn.fetchrow("SELECT username, first_name FROM users WHERE user_id = $1", user_id)
    
    # ✅ مسح الكاش
    clear_cache(f"user_vip_info:{user_id}")
    clear_cache("vip_stats")
    
    username = user['username'] or user['first_name'] or str(user_id)
    elapsed_time = time.time() - start_time
    icon = VIP_ICONS[level] if level < len(VIP_ICONS) else "⭐"
    
    await safe_edit_message(
        callback.message,
        f"✅ **تم رفع المستوى يدوياً!**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"👑 المستوى الجديد: {icon} VIP {level}\n"
        f"💰 نسبة الخصم: {discount}%\n"
        f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية\n\n"
        f"⚠️ هذا المستوى يدوي ولن يتغير تلقائياً."
    )
    
    try:
        await callback.bot.send_message(
            user_id,
            f"🎉 **تم ترقية مستواك في البوت يدوياً!**\n\n"
            f"{icon} مستواك الجديد: VIP {level}\n"
            f"💰 نسبة الخصم: {discount}%\n\n"
            f"✨ هذا المستوى خاص ولن يتغير تلقائياً.",
            parse_mode="Markdown"
        )
        logger.info(f"✅ تم إرسال إشعار ترقية للمستخدم {user_id}")
    except Exception as e:
        logger.error(f"❌ فشل إرسال إشعار للمستخدم {user_id}: {e}")

# خصم مخصص
@router.callback_query(F.data.startswith("custom_discount_"))
async def custom_discount_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إعطاء خصم مخصص"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user=user_id)
    
    # ✅ عرض معلومات المستخدم الحالية
    user = await get_cached_user_vip_info(db_pool, user_id)
    username = user['username'] or user['first_name'] or str(user_id) if user else str(user_id)
    current_discount = user['discount_percent'] if user else 0
    
    await safe_edit_message(
        callback.message,
        f"🎯 **إعطاء خصم مخصص**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"💰 الخصم الحالي: {current_discount}%\n\n"
        f"أدخل نسبة الخصم المطلوبة (0-100):\n"
        f"مثال: `15` تعني 15% خصم\n\n"
        f"❌ للإلغاء أرسل /cancel"
    )
    await state.set_state(VIPStates.waiting_vip_discount)

@router.message(VIPStates.waiting_vip_discount)
async def set_custom_discount(message: types.Message, state: FSMContext, db_pool):
    """تحديد خصم مخصص لمستخدم"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "/رجوع", "🔙 رجوع للقائمة"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    try:
        discount = float(message.text.strip())
        if discount < 0 or discount > 100:
            return await message.answer(
                "❌ نسبة الخصم يجب أن تكون بين 0 و 100:",
                reply_markup=get_cancel_keyboard()
            )
        
        data = await state.get_data()
        user_id = data['target_user']
        
        start_time = time.time()
        
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute('''
                    UPDATE users 
                    SET discount_percent = $1, manual_vip = TRUE 
                    WHERE user_id = $2
                ''', discount, user_id)
                
                user = await conn.fetchrow(
                    "SELECT username, first_name, vip_level FROM users WHERE user_id = $1",
                    user_id
                )
        
        # ✅ مسح الكاش
        clear_cache(f"user_vip_info:{user_id}")
        clear_cache("vip_stats")
        
        username = user['username'] or user['first_name'] or str(user_id)
        vip_level = user['vip_level']
        elapsed_time = time.time() - start_time
        icon = VIP_ICONS[vip_level] if vip_level < len(VIP_ICONS) else "⭐"
        
        await message.answer(
            f"✅ **تم تحديث الخصم بنجاح**\n\n"
            f"👤 المستخدم: @{username}\n"
            f"🆔 الآيدي: `{user_id}`\n"
            f"👑 مستوى VIP: {icon} VIP {vip_level}\n"
            f"💰 نسبة الخصم الجديدة: {discount}%\n"
            f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية"
        )
        
        try:
            await message.bot.send_message(
                user_id,
                f"🎁 **تم تعديل نسبة الخصم في حسابك!**\n\n"
                f"💰 نسبة الخصم الجديدة: {discount}%\n"
                f"👑 مستواك الحالي: {icon} VIP {vip_level}\n\n"
                f"شكراً لاستخدامك خدماتنا!",
                parse_mode="Markdown"
            )
            logger.info(f"✅ تم إرسال إشعار خصم للمستخدم {user_id}")
        except Exception as e:
            logger.error(f"❌ فشل إرسال إشعار للمستخدم {user_id}: {e}")
        
        await state.clear()
        
    except ValueError:
        await message.answer(
            "❌ يرجى إدخال رقم صحيح:",
            reply_markup=get_cancel_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ خطأ في تعيين الخصم: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# خفض مستوى VIP
@router.callback_query(F.data.startswith("downgrade_vip_"))
async def downgrade_vip_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء خفض مستوى VIP لمستخدم"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user=user_id)
    
    # ✅ استخدام الكاش
    user = await get_cached_user_vip_info(db_pool, user_id)
    
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
    
    for level in VIP_LEVELS:
        if level['level'] < current_vip:
            btn_text = f"{level['icon']} {level['name']} ({level['discount']}%)"
            builder.row(types.InlineKeyboardButton(
                text=btn_text,
                callback_data=f"downgrade_to_{user_id}_{level['level']}_{level['discount']}"
            ))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data=f"user_info_cancel"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("downgrade_to_"))
async def downgrade_vip_ask_reason(callback: types.CallbackQuery, state: FSMContext):
    """طلب سبب خفض المستوى"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    parts = callback.data.split("_")
    user_id = int(parts[2])
    new_level = int(parts[3])
    new_discount = int(parts[4])
    
    await state.update_data(target_user=user_id, new_level=new_level, new_discount=new_discount)
    
    await safe_edit_message(
        callback.message,
        f"⚠️ **خفض مستوى VIP**\n\n"
        f"المستوى الجديد: VIP {new_level} (خصم {new_discount}%)\n\n"
        f"📝 **أدخل سبب خفض المستوى** (سيتم إرساله للمستخدم):\n"
        f"مثال: عدم الالتزام بشروط الاستخدام\n\n"
        f"أو أرسل /skip لتخطي إرسال سبب"
    )
    await state.set_state(VIPStates.waiting_vip_downgrade_reason)

@router.message(VIPStates.waiting_vip_downgrade_reason)
async def downgrade_vip_execute(message: types.Message, state: FSMContext, db_pool, bot: Bot):
    """تنفيذ خفض مستوى VIP مع إرسال تحذير"""
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    user_id = data['target_user']
    new_level = data['new_level']
    new_discount = data['new_discount']
    
    reason = None
    if message.text and message.text != "/skip":
        reason = message.text.strip()
    
    start_time = time.time()
    
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('''
                UPDATE users 
                SET vip_level = $1, discount_percent = $2, manual_vip = TRUE
                WHERE user_id = $3
            ''', new_level, new_discount, user_id)
            
            user = await conn.fetchrow("SELECT username, first_name FROM users WHERE user_id = $1", user_id)
    
    # ✅ مسح الكاش
    clear_cache(f"user_vip_info:{user_id}")
    clear_cache("vip_stats")
    
    username = user['username'] or user['first_name'] or str(user_id)
    elapsed_time = time.time() - start_time
    icon = VIP_ICONS[new_level] if new_level < len(VIP_ICONS) else "⭐"
    
    admin_text = (
        f"✅ **تم خفض مستوى VIP بنجاح**\n\n"
        f"👤 المستخدم: @{username}\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"👑 المستوى الجديد: {icon} VIP {new_level}\n"
        f"💰 نسبة الخصم: {new_discount}%\n"
        f"⚡ وقت المعالجة: {elapsed_time:.2f} ثانية\n"
    )
    
    if reason:
        admin_text += f"📝 السبب: {reason}\n"
    
    admin_text += f"\n⚠️ تم إرسال إشعار للمستخدم."
    
    await message.answer(admin_text)
    
    try:
        user_message = (
            f"⚠️ **تم تعديل مستواك في البوت**\n\n"
            f"👑 مستواك الجديد: {icon} VIP {new_level}\n"
            f"💰 نسبة الخصم: {new_discount}%\n\n"
        )
        
        if reason:
            user_message += f"📝 **السبب:** {reason}\n\n"
        
        user_message += (
            f"🔸 هذا التعديل نهائي ولن يتغير تلقائياً.\n"
            f"📞 للاستفسار، تواصل مع الدعم."
        )
        
        await bot.send_message(user_id, user_message, parse_mode="Markdown")
        logger.info(f"✅ تم إرسال إشعار خفض للمستخدم {user_id}")
        
    except Exception as e:
        logger.error(f"❌ فشل إرسال إشعار للمستخدم {user_id}: {e}")
        await message.answer(f"❌ فشل إرسال إشعار للمستخدم: {e}")
    
    await state.clear()

@router.callback_query(F.data == "user_info_cancel")
async def user_info_cancel(callback: types.CallbackQuery):
    """إلغاء والعودة لمعلومات المستخدم"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await safe_edit_message(callback.message, "✅ تم الإلغاء")

# عرض إحصائيات VIP
@router.callback_query(F.data == "vip_statistics")
async def vip_statistics(callback: types.CallbackQuery, db_pool):
    """عرض إحصائيات VIP"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    async with db_pool.acquire() as conn:
        # إحصائيات عدد المستخدمين في كل مستوى
        stats = await conn.fetch('''
            SELECT vip_level, COUNT(*) as count, COALESCE(SUM(total_spent), 0) as total_spent
            FROM users
            GROUP BY vip_level
            ORDER BY vip_level
        ''')
        
        # إجمالي الخصومات الممنوحة
        total_discounts = await conn.fetchval('''
            SELECT COALESCE(SUM(
                CASE 
                    WHEN o.status = 'completed' 
                    THEN o.total_amount_syp * (u.discount_percent / 100.0)
                    ELSE 0 
                END
            ), 0)
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            WHERE o.status = 'completed'
        ''')
        
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
    
    text = "👑 **إحصائيات VIP**\n\n"
    
    stats_dict = {row['vip_level']: {'count': row['count'], 'spent': row['total_spent']} for row in stats}
    
    for level in VIP_LEVELS:
        count = stats_dict.get(level['level'], {}).get('count', 0)
        spent = stats_dict.get(level['level'], {}).get('spent', 0)
        percentage = (count / total_users * 100) if total_users > 0 else 0
        
        text += f"{level['icon']} **{level['name']}**\n"
        text += f"   👥 {count} مستخدم ({percentage:.1f}%)\n"
        text += f"   💰 إنفاق: {spent:,.0f} ل.س\n\n"
    
    text += f"💰 إجمالي الخصومات الممنوحة: {total_discounts:,.0f} ل.س\n"
    text += f"🕐 {get_formatted_damascus_time()}"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 تحديث", callback_data="vip_statistics"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())
