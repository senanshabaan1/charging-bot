
# admin/group_handlers.py
from aiogram import Router, F, types, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
import asyncio
from handlers.time_utils import get_damascus_time_now
from utils import get_formatted_damascus_time, format_amount
from database.cache_utils import invalidate_user_cache
from database.points import get_points_per_order
from database.vip import update_user_vip
from database.core import get_active_deposit_bonus, record_offer_usage  # ✅ فقط مكافآت الإيداع

logger = logging.getLogger(__name__)
router = Router(name="admin_group")

# ✅ كاش للطلبات قيد المعالجة (لمنع التكرار)
processing_orders = set()
processing_deposits = set()


# ============= معالجة طلبات الشحن من المجموعة =============

@router.callback_query(F.data.startswith("appr_dep_"))
async def approve_deposit_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """موافقة على طلب شحن من المجموعة - مع مكافأة الإيداع"""
    
    # استخراج البيانات
    try:
        parts = callback.data.split("_")
        if len(parts) >= 4:
            _, _, uid, amt = parts
            user_id = int(uid)
            amount = float(amt)
        else:
            await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
            return
    except:
        await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
        return
    
    # ✅ منع المعالجة المزدوجة
    dep_key = f"{user_id}_{amount}"
    if dep_key in processing_deposits:
        await callback.answer("⚠️ الطلب قيد المعالجة بالفعل", show_alert=True)
        return
    
    processing_deposits.add(dep_key)
    
    try:
        await callback.answer("✅ جاري معالجة الطلب...", show_alert=False)
        
        # ✅ تحديث الرسالة فوراً
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text + "\n\n⏳ **جاري المعالجة...**"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None)
        except:
            pass
        
        asyncio.create_task(process_deposit_approval(
            user_id, amount, callback, db_pool, bot
        ))
        
    except Exception as e:
        logger.error(f"❌ خطأ في موافقة الشحن: {e}")
        processing_deposits.discard(dep_key)


async def process_deposit_approval(user_id: int, amount: float, callback: types.CallbackQuery, db_pool, bot: Bot):
    """معالجة موافقة الشحن في الخلفية - مع مكافأة الإيداع"""
    try:
        async with db_pool.acquire() as conn:
            # جلب المستخدم
            user = await conn.fetchrow("SELECT username, balance FROM users WHERE user_id = $1", user_id)
            
            if not user:
                await conn.execute(
                    "INSERT INTO users (user_id, balance, created_at) VALUES ($1, 0, CURRENT_TIMESTAMP)", 
                    user_id
                )
                user = {'username': None, 'balance': 0}
            
            # ✅ جلب مكافأة الإيداع النشطة
            active_bonus = await get_active_deposit_bonus(db_pool, amount)
            bonus_amount = 0
            bonus_id = None
            bonus_percent = 0
            
            if active_bonus:
                bonus_percent = active_bonus['bonus_percent']
                bonus_amount = amount * (bonus_percent / 100)
                
                # تطبيق الحد الأقصى للمكافأة إن وجد
                max_bonus = active_bonus.get('max_bonus_amount')
                if max_bonus and bonus_amount > max_bonus:
                    bonus_amount = max_bonus
                
                bonus_id = active_bonus['id']
                logger.info(f"🎁 تم تطبيق مكافأة إيداع {bonus_percent}%: +{bonus_amount:,.0f} ل.س")
            
            # تحديث الرصيد (مع المكافأة)
            new_balance = user['balance'] + amount + bonus_amount
            
            await conn.execute(
                "UPDATE users SET balance = $1, total_deposits = total_deposits + $2, last_activity = CURRENT_TIMESTAMP WHERE user_id = $3",
                new_balance, amount, user_id
            )
            
            # تحديث طلب الشحن مع إضافة المكافأة
            await conn.execute('''
                UPDATE deposit_requests 
                SET status = 'approved', updated_at = CURRENT_TIMESTAMP, 
                    bonus_amount = $1, bonus_id = $2
                WHERE id = (
                    SELECT id FROM deposit_requests 
                    WHERE user_id = $3 AND status = 'pending' AND amount_syp = $4
                    ORDER BY created_at DESC 
                    LIMIT 1
                )
            ''', bonus_amount, bonus_id, user_id, amount)
            
            # ✅ تسجيل استخدام المكافأة
            if bonus_id:
                await record_offer_usage(
                    pool=db_pool,
                    user_id=user_id,
                    offer_id=bonus_id,
                    offer_type='deposit',
                    deposit_id=None
                )
            
            # ✅ مسح كاش المستخدم
            await invalidate_user_cache(user_id)
        
        damascus_time = get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')
        
        # ✅ إرسال إشعار للمستخدم مع تفاصيل المكافأة
        asyncio.create_task(notify_user_deposit_approved(
            bot, user_id, amount, bonus_percent, bonus_amount, new_balance, damascus_time
        ))
        
        # تحديث رسالة المجموعة
        try:
            current_text = callback.message.text or callback.message.caption or ""
            bonus_text = f"\n🎁 **مكافأة إيداع:** +{bonus_amount:,.0f} ل.س ({bonus_percent}%)" if bonus_amount > 0 else ""
            new_text = current_text.replace("⏳ **جاري المعالجة...**", "") + f"\n\n✅ **تمت الموافقة على الطلب**{bonus_text}\n📅 **بتاريخ:** {damascus_time}"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None)
        except Exception as e:
            logger.error(f"❌ فشل تحديث رسالة المجموعة: {e}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة موافقة الشحن: {e}")
    finally:
        processing_deposits.discard(f"{user_id}_{amount}")


async def notify_user_deposit_approved(bot: Bot, user_id: int, amount: float, bonus_percent: int, bonus_amount: float, new_balance: float, timestamp: str):
    """إرسال إشعار للمستخدم بموافقة الشحن مع المكافأة"""
    try:
        text = f"✅ **تم تأكيد عملية الشحن بنجاح!**\n\n"
        text += f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
        
        if bonus_amount > 0:
            text += f"🎁 **مكافأة إيداع {bonus_percent}%:** +{bonus_amount:,.0f} ل.س\n"
        
        text += f"💳 **الرصيد الحالي:** {new_balance:,.0f} ل.س\n"
        text += f"📅 **التاريخ:** {timestamp}\n\n"
        text += f"🔸 **شكراً لاستخدامك خدماتنا**"
        
        await bot.send_message(user_id, text, parse_mode="Markdown")
        logger.info(f"✅ تم إرسال إشعار موافقة للمستخدم {user_id} (مكافأة: {bonus_amount:,.0f})")
    except Exception as e:
        logger.error(f"❌ فشل إرسال رسالة للمستخدم {user_id}: {e}")


@router.callback_query(F.data.startswith("reje_dep_"))
async def reject_deposit_from_group(callback: types.CallbackQuery, bot: Bot, db_pool):
    """رفض طلب شحن من المجموعة"""
    try:
        logger.info(f"📩 استقبال رفض شحن: {callback.data}")
        user_id = int(callback.data.split("_")[2])
        
        await callback.answer("❌ جاري رفض الطلب...", show_alert=False)
        
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text + "\n\n⏳ **جاري الرفض...**"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None)
        except:
            pass
        
        asyncio.create_task(process_deposit_rejection(user_id, callback, db_pool, bot))
        
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الشحن: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)


async def process_deposit_rejection(user_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    """معالجة رفض الشحن في الخلفية"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE deposit_requests 
                SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM deposit_requests 
                    WHERE user_id = $1 AND status = 'pending'
                    ORDER BY created_at DESC 
                    LIMIT 1
                )
            ''', user_id)
        
        damascus_time = get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')
        
        asyncio.create_task(notify_user_deposit_rejected(bot, user_id, damascus_time))
        
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text.replace("⏳ **جاري الرفض...**", "") + f"\n\n❌ **تم رفض الطلب**\n📅 **بتاريخ:** {damascus_time}"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None)
        except Exception as e:
            logger.error(f"❌ فشل تحديث رسالة المجموعة: {e}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة رفض الشحن: {e}")


async def notify_user_deposit_rejected(bot: Bot, user_id: int, timestamp: str):
    """إرسال إشعار للمستخدم برفض الشحن"""
    try:
        await bot.send_message(
            user_id,
            f"❌ نعتذر، تم رفض طلب الشحن الخاص بك.\n\n"
            f"📅 **تاريخ الرفض:** {timestamp}\n"
            f"🔸 **الأسباب المحتملة:**\n"
            f"• بيانات التحويل غير صحيحة\n"
            f"• لم يتم العثور على التحويل\n"
            f"• المشكلة فنية\n\n"
            f"📞 **للمساعدة تواصل مع الدعم.**",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ فشل إرسال رسالة الرفض للمستخدم {user_id}: {e}")


# ============= معالجة طلبات التطبيقات من المجموعة =============
# ✅ تم إزالة العروض العامة من طلبات التطبيقات

@router.callback_query(F.data.startswith("appr_order_"))
async def approve_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """موافقة على طلب تطبيق من المجموعة"""
    
    order_id = int(callback.data.split("_")[2])
    
    if order_id in processing_orders:
        await callback.answer("⚠️ الطلب قيد المعالجة بالفعل", show_alert=True)
        return
    
    processing_orders.add(order_id)
    
    try:
        await callback.answer("✅ جاري معالجة الطلب...", show_alert=False)
        
        try:
            new_text = callback.message.text + "\n\n⏳ **جاري المعالجة...**"
            await callback.message.edit_text(new_text, reply_markup=None)
        except:
            pass
        
        asyncio.create_task(process_order_approval(order_id, callback, db_pool, bot))
        
    except Exception as e:
        logger.error(f"❌ خطأ في موافقة الطلب: {e}")
        processing_orders.discard(order_id)


async def process_order_approval(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    """معالجة الموافقة في الخلفية"""
    try:
        async with db_pool.acquire() as conn:
            # جلب معلومات الطلب
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.id = $1
            ''', order_id)
            
            if not order:
                await callback.message.answer("❌ الطلب غير موجود")
                processing_orders.discard(order_id)
                return
            
            # ✅ تحديث حالة الطلب (بدون خصم عرض)
            await conn.execute(
                "UPDATE orders SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = $1", 
                order_id
            )
            
            # ✅ مسح كاش المستخدم
            await invalidate_user_cache(order['user_id'])
        
        # إرسال إشعار للمستخدم
        asyncio.create_task(notify_user_order_approved(bot, order))
        
        # إنشاء أزرار جديدة
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ تم التنفيذ", callback_data=f"compl_order_{order_id}"),
            types.InlineKeyboardButton(text="❌ تعذر التنفيذ", callback_data=f"fail_order_{order_id}"),
            width=2
        )
        
        # تحديث رسالة المجموعة
        await callback.message.edit_text(
            callback.message.text.replace("⏳ **جاري المعالجة...**", "") + "\n\n🔄 **جاري التنفيذ...**",
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة الطلب: {e}")
    finally:
        processing_orders.discard(order_id)


async def notify_user_order_approved(bot, order):
    """إرسال إشعار للمستخدم بموافقة الطلب"""
    try:
        points = order['points_earned'] or 0
        text = f"✅ تمت الموافقة على طلبك #{order['id']}\n\n"
        text += f"📱 التطبيق: {order['app_name']}\n"
        text += f"📦 الكمية: {order['quantity']}\n"
        text += f"🎯 المستهدف: {order['target_id']}\n"
        text += f"💰 المبلغ: {order['total_amount_syp']:,.0f} ل.س\n"
        text += f"⭐ نقاط مكتسبة: +{points}\n\n"
        text += f"⏳ جاري تنفيذ طلبك عبر النظام..."
        
        await bot.send_message(order['user_id'], text, parse_mode="Markdown")
        logger.info(f"✅ تم إرسال إشعار موافقة للمستخدم {order['user_id']}")
    except Exception as e:
        logger.error(f"❌ فشل إرسال إشعار للمستخدم {order['user_id']}: {e}")

 =============
# ... (reje_order_, compl_order_, fail_order_ تبقى كما هي)
@router.callback_query(F.data.startswith("reje_dep_"))
async def reject_deposit_from_group(callback: types.CallbackQuery, bot: Bot, db_pool):
    """رفض طلب شحن من المجموعة"""
    try:
        logger.info(f"📩 استقبال رفض شحن: {callback.data}")
        user_id = int(callback.data.split("_")[2])
        
        await callback.answer("❌ جاري رفض الطلب...", show_alert=False)
        
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text + "\n\n⏳ **جاري الرفض...**"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None)
        except:
            pass
        
        asyncio.create_task(process_deposit_rejection(user_id, callback, db_pool, bot))
        
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الشحن: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)


async def process_deposit_rejection(user_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    """معالجة رفض الشحن في الخلفية"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE deposit_requests 
                SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM deposit_requests 
                    WHERE user_id = $1 AND status = 'pending'
                    ORDER BY created_at DESC 
                    LIMIT 1
                )
            ''', user_id)
        
        damascus_time = get_damascus_time_now().strftime('%Y-%m-%d %H:%M:%S')
        
        asyncio.create_task(notify_user_deposit_rejected(bot, user_id, damascus_time))
        
        try:
            current_text = callback.message.text or callback.message.caption or ""
            new_text = current_text.replace("⏳ **جاري الرفض...**", "") + f"\n\n❌ **تم رفض الطلب**\n📅 **بتاريخ:** {damascus_time}"
            
            if callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None)
        except Exception as e:
            logger.error(f"❌ فشل تحديث رسالة المجموعة: {e}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة رفض الشحن: {e}")


async def notify_user_deposit_rejected(bot: Bot, user_id: int, timestamp: str):
    """إرسال إشعار للمستخدم برفض الشحن"""
    try:
        await bot.send_message(
            user_id,
            f"❌ نعتذر، تم رفض طلب الشحن الخاص بك.\n\n"
            f"📅 **تاريخ الرفض:** {timestamp}\n"
            f"🔸 **الأسباب المحتملة:**\n"
            f"• بيانات التحويل غير صحيحة\n"
            f"• لم يتم العثور على التحويل\n"
            f"• المشكلة فنية\n\n"
            f"📞 **للمساعدة تواصل مع الدعم.**",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ فشل إرسال رسالة الرفض للمستخدم {user_id}: {e}")


# ============= معالجة طلبات التطبيقات من المجموعة =============

@router.callback_query(F.data.startswith("appr_order_"))
async def approve_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """موافقة على طلب تطبيق من المجموعة - مع تطبيق خصم العرض العام"""
    
    order_id = int(callback.data.split("_")[2])
    
    if order_id in processing_orders:
        await callback.answer("⚠️ الطلب قيد المعالجة بالفعل", show_alert=True)
        return
    
    processing_orders.add(order_id)
    
    try:
        await callback.answer("✅ جاري معالجة الطلب...", show_alert=False)
        
        try:
            new_text = callback.message.text + "\n\n⏳ **جاري المعالجة...**"
            await callback.message.edit_text(new_text, reply_markup=None)
        except:
            pass
        
        asyncio.create_task(process_order_approval(order_id, callback, db_pool, bot))
        
    except Exception as e:
        logger.error(f"❌ خطأ في موافقة الطلب: {e}")
        processing_orders.discard(order_id)


async def process_order_approval(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    """معالجة الموافقة في الخلفية - مع تطبيق خصم العرض العام"""
    try:
        async with db_pool.acquire() as conn:
            # جلب معلومات الطلب
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.id = $1
            ''', order_id)
            
            if not order:
                await callback.message.answer("❌ الطلب غير موجود")
                processing_orders.discard(order_id)
                return
            
            # ✅ جلب العرض العام النشط
            active_offer = await get_active_global_offer(db_pool)
            offer_discount = active_offer['discount_percent'] if active_offer else 0
            offer_id = active_offer['id'] if active_offer else None
            
            # ✅ تطبيق خصم العرض على المبلغ
            total_amount = order['total_amount_syp']
            discounted_amount = total_amount * (1 - offer_discount / 100) if offer_discount > 0 else total_amount
            
            # تحديث الطلب مع خصم العرض
            await conn.execute('''
                UPDATE orders 
                SET status = 'processing', 
                    updated_at = CURRENT_TIMESTAMP,
                    offer_discount = $1,
                    offer_id = $2,
                    total_amount_syp = $3
                WHERE id = $4
            ''', offer_discount, offer_id, discounted_amount, order_id)
            
            # ✅ تسجيل استخدام العرض
            if offer_id:
                await record_offer_usage(
                    pool=db_pool,
                    user_id=order['user_id'],
                    offer_id=offer_id,
                    offer_type='global',
                    order_id=order_id
                )
            
            # ✅ مسح كاش المستخدم
            await invalidate_user_cache(order['user_id'])
        
        # إرسال إشعار للمستخدم مع تفاصيل الخصم
        asyncio.create_task(notify_user_order_approved(bot, order, offer_discount, discounted_amount))
        
        # إنشاء أزرار جديدة
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ تم التنفيذ", callback_data=f"compl_order_{order_id}"),
            types.InlineKeyboardButton(text="❌ تعذر التنفيذ", callback_data=f"fail_order_{order_id}"),
            width=2
        )
        
        # تحديث رسالة المجموعة مع تفاصيل الخصم
        discount_text = f"\n🎁 **خصم عرض:** {offer_discount}%" if offer_discount > 0 else ""
        await callback.message.edit_text(
            callback.message.text.replace("⏳ **جاري المعالجة...**", "") + f"\n\n🔄 **جاري التنفيذ...**{discount_text}",
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة الطلب: {e}")
    finally:
        processing_orders.discard(order_id)


async def notify_user_order_approved(bot, order, offer_discount: int = 0, discounted_amount: float = None):
    """إرسال إشعار للمستخدم بموافقة الطلب مع تفاصيل الخصم"""
    try:
        points = order['points_earned'] or 0
        text = f"✅ تمت الموافقة على طلبك #{order['id']}\n\n"
        text += f"📱 التطبيق: {order['app_name']}\n"
        text += f"📦 الكمية: {order['quantity']}\n"
        text += f"🎯 المستهدف: {order['target_id']}\n"
        
        if offer_discount > 0 and discounted_amount:
            text += f"💰 المبلغ الأصلي: {order['total_amount_syp']:,.0f} ل.س\n"
            text += f"🎁 خصم العرض: {offer_discount}%\n"
            text += f"💰 المبلغ بعد الخصم: {discounted_amount:,.0f} ل.س\n"
        else:
            text += f"💰 المبلغ: {order['total_amount_syp']:,.0f} ل.س\n"
        
        text += f"⭐ نقاط مكتسبة: +{points}\n\n"
        text += f"⏳ جاري تنفيذ طلبك عبر النظام..."
        
        await bot.send_message(order['user_id'], text, parse_mode="Markdown")
        logger.info(f"✅ تم إرسال إشعار موافقة للمستخدم {order['user_id']}")
    except Exception as e:
        logger.error(f"❌ فشل إرسال إشعار للمستخدم {order['user_id']}: {e}")


@router.callback_query(F.data.startswith("reje_order_"))
async def reject_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """رفض طلب تطبيق من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        await callback.answer("❌ جاري رفض الطلب...", show_alert=False)
        
        try:
            await callback.message.edit_text(
                callback.message.text + "\n\n⏳ **جاري الرفض...**",
                reply_markup=None
            )
        except:
            pass
        
        asyncio.create_task(process_order_rejection(order_id, callback, db_pool, bot))
        
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الطلب: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)


async def process_order_rejection(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    """معالجة رفض الطلب في الخلفية"""
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT id, user_id, total_amount_syp FROM orders WHERE id = $1", order_id)
            
            if order:
                logger.info(f"📝 جاري رفض الطلب #{order_id} للمستخدم {order['user_id']}")
                
                # إعادة الرصيد
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2", 
                    order['total_amount_syp'], order['user_id']
                )
                
                # تحديث حالة الطلب
                await conn.execute(
                    "UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", 
                    order_id
                )
                
                await invalidate_user_cache(order['user_id'])
                await notify_user_order_rejected(bot, order)
        
        await callback.message.edit_text(
            callback.message.text.replace("⏳ **جاري الرفض...**", "") + "\n\n❌ **تم رفض الطلب وإعادة الرصيد**",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة رفض الطلب: {e}")
        await callback.message.answer(f"❌ حدث خطأ: {str(e)}")


async def notify_user_order_rejected(bot, order):
    """إرسال إشعار للمستخدم برفض الطلب"""
    try:
        order_id = order.get('id') or order.get('order_id')
        if not order_id:
            logger.error(f"❌ لا يوجد معرف للطلب في البيانات: {dict(order)}")
            return
        
        text = (
            f"❌ تم رفض طلبك #{order_id}\n\n"
            f"💰 **تم إعادة:** {order['total_amount_syp']:,.0f} ل.س لرصيدك\n\n"
            f"🔸 **الأسباب المحتملة:**\n"
            "• مشكلة في معلومات الحساب المستهدف\n"
            "• الخدمة غير متوفرة حالياً\n"
            "• مشكلة فنية في النظام\n\n"
            f"📞 **للمساعدة تواصل مع الدعم.**"
        )
        
        await bot.send_message(order['user_id'], text, parse_mode="Markdown")
        logger.info(f"✅ تم إرسال إشعار رفض للمستخدم {order['user_id']}")
        
    except Exception as e:
        logger.error(f"❌ فشل إرسال إشعار للمستخدم {order.get('user_id', 'unknown')}: {e}")


@router.callback_query(F.data.startswith("compl_order_"))
async def complete_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """تأكيد تنفيذ الطلب من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        await callback.answer("✅ جاري تأكيد التنفيذ...", show_alert=False)
        asyncio.create_task(process_order_completion(order_id, callback, db_pool, bot))
        
    except Exception as e:
        logger.error(f"❌ خطأ في تأكيد التنفيذ: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)


async def process_order_completion(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    """معالجة تأكيد تنفيذ الطلب في الخلفية"""
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.id = $1
            ''', order_id)
            
            if not order:
                await callback.message.answer("❌ الطلب غير موجود")
                return
            
            points = await get_points_per_order(db_pool)
            
            await conn.execute(
                "UPDATE orders SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", 
                order_id
            )
            
            await conn.execute(
                "UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2",
                points, order['user_id']
            )
            
            await conn.execute(
                "UPDATE orders SET points_earned = $1 WHERE id = $2", 
                points, order_id
            )
            
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ''', order['user_id'], points, 'order_completed', f'نقاط من طلب مكتمل #{order_id}')
            
            vip_info = await update_user_vip(db_pool, order['user_id'])
            
            if vip_info:
                vip_discount = vip_info.get('discount', 0)
                vip_level = vip_info.get('level', 0)
            else:
                vip_discount = 0
                vip_level = 0
                
            vip_icons = ["⚪", "🔵", "🟣", "🟡"]
            vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "⚪"
            
            user_points = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1", 
                order['user_id']
            ) or 0
            
            await invalidate_user_cache(order['user_id'])
        
        asyncio.create_task(notify_user_order_completed(
            bot, order, points, user_points, vip_icon, vip_level, vip_discount
        ))
        
        await callback.message.edit_text(
            callback.message.text.replace("🔄 **جاري التنفيذ...**", "") + "\n\n✅ **تم التنفيذ بنجاح**",
            reply_markup=None
        )
        
        await callback.answer("✅ تم تأكيد التنفيذ")
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة تأكيد التنفيذ: {e}")
        await callback.message.answer(f"❌ حدث خطأ: {str(e)}")


async def notify_user_order_completed(bot, order, points, user_points, vip_icon, vip_level, vip_discount):
    """إرسال إشعار للمستخدم بإتمام الطلب"""
    try:
        await bot.send_message(
            order['user_id'],
            f"✅ تم تنفيذ طلبك #{order['id']} بنجاح!\n\n"
            f"📱 التطبيق: {order['app_name']}\n"
            f"⭐ نقاط مكتسبة: +{points}\n"
            f"💰 رصيد النقاط الجديد: {user_points}\n"
            f"👑 مستواك: {vip_icon} VIP {vip_level} (خصم {vip_discount}%)\n\n"
            f"شكراً لاستخدامك خدماتنا"
        )
    except Exception as e:
        logger.error(f"❌ فشل إرسال رسالة للمستخدم: {e}")


@router.callback_query(F.data.startswith("fail_order_"))
async def fail_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """تعذر تنفيذ الطلب من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        logger.info(f"📩 استقبال فشل تنفيذ للطلب #{order_id}")
        
        await callback.answer("❌ جاري معالجة الفشل...", show_alert=False)
        
        try:
            await callback.message.edit_text(
                callback.message.text.replace("🔄 **جاري التنفيذ...**", "") + "\n\n⏳ **جاري معالجة الفشل...**",
                reply_markup=None
            )
        except:
            pass
        
        asyncio.create_task(process_order_failure(order_id, callback, db_pool, bot))
        
    except Exception as e:
        logger.error(f"❌ خطأ في تعذر التنفيذ: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)


async def process_order_failure(order_id: int, callback: types.CallbackQuery, db_pool, bot: Bot):
    """معالجة فشل الطلب في الخلفية"""
    try:
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow("SELECT id, user_id, total_amount_syp FROM orders WHERE id = $1", order_id)
            
            if order:
                logger.info(f"📝 جاري معالجة فشل الطلب #{order_id} للمستخدم {order['user_id']}")
                
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2", 
                    order['total_amount_syp'], order['user_id']
                )
                
                await conn.execute(
                    "UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1", 
                    order_id
                )
                
                await invalidate_user_cache(order['user_id'])
                await notify_user_order_failed(bot, order)
        
        await callback.message.edit_text(
            callback.message.text.replace("🔄 **جاري التنفيذ...**", "") + "\n\n❌ **تعذر التنفيذ وتم إعادة الرصيد**",
            reply_markup=None
        )
        
        await callback.answer("❌ تم تحديث حالة الطلب")
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة فشل الطلب: {e}")
        await callback.message.answer(f"❌ حدث خطأ: {str(e)}")


async def notify_user_order_failed(bot, order):
    """إرسال إشعار للمستخدم بفشل الطلب"""
    try:
        order_id = order.get('id') or order.get('order_id')
        if not order_id:
            logger.error(f"❌ لا يوجد معرف للطلب في البيانات: {dict(order)}")
            return
        
        text = (
            f"❌ تعذر تنفيذ طلبك #{order_id}\n\n"
            f"💰 **تم إعادة المبلغ إلى رصيدك:** {order['total_amount_syp']:,.0f} ل.س\n"
            f"⭐ لم تتم إضافة نقاط لهذا الطلب\n\n"
            f"🔸 **الأسباب المحتملة:**\n"
            "• مشكلة في معلومات الحساب المستهدف\n"
            "• الخدمة غير متوفرة حالياً\n"
            "• مشكلة فنية في النظام\n\n"
            f"🔄 يمكنك المحاولة مرة أخرى.\n"
            f"📞 **للمساعدة تواصل مع الدعم.**"
        )
        
        await bot.send_message(order['user_id'], text, parse_mode="Markdown")
        logger.info(f"✅ تم إرسال إشعار فشل للمستخدم {order['user_id']}")
        
    except Exception as e:
        logger.error(f"❌ فشل إرسال إشعار للمستخدم {order.get('user_id', 'unknown')}: {e}")
