# handlers/start.py
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from config import ADMIN_ID, MODERATORS, USD_TO_SYP
import logging
from datetime import datetime
import pytz
import random
import string
from handlers.time_utils import format_damascus_time, get_damascus_time_now
from handlers.keyboards import get_main_menu_keyboard, get_back_keyboard

logger = logging.getLogger(__name__)
router = Router()

async def notify_admins(bot, message_text, db_pool=None):
    """إرسال إشعار لجميع المشرفين - مع التأكد من عدم التكرار"""
    from config import ADMIN_ID, MODERATORS

    # جمع جميع آيدي المشرفين في set لإزالة التكرار
    admin_ids = set()
    admin_ids.add(ADMIN_ID)
    for mod_id in MODERATORS:
        if mod_id:
            admin_ids.add(mod_id)

    # إرسال الإشعار لكل مشرف
    sent_count = 0
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, message_text, parse_mode="Markdown")
            sent_count += 1
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمشرف {admin_id}: {e}")

    logger.info(f"✅ تم إرسال إشعار لـ {sent_count} مشرف")
    return sent_count

# دالة التحقق من المشرفين
def is_admin(user_id):
    return user_id == ADMIN_ID or user_id in MODERATORS

# ========== دوال الإلغاء ==========

@router.message(Command("cancel"))
@router.message(Command("الغاء"))
@router.message(Command("رجوع"))
@router.message(F.text == "/cancel")
@router.message(F.text == "/الغاء")
@router.message(F.text == "/رجوع")
async def cmd_cancel(message: types.Message, state: FSMContext, db_pool):
    """إلغاء أي عملية حالية والعودة للقائمة الرئيسية"""
    try:
        # ضبط المنطقة الزمنية لدمشق
        damascus_tz = pytz.timezone('Asia/Damascus')
        current_time = datetime.now(damascus_tz).strftime('%H:%M:%S')

        # الحصول على حالة FSM الحالية
        current_state = await state.get_state()

        # تسجيل للتصحيح
        logger.info(f"حالة FSM الحالية: {current_state}")

        # مسح حالة FSM
        await state.clear()

        # التحقق من إذا كان المستخدم مشرف
        is_admin_user = is_admin(message.from_user.id)

        if current_state:
            cancel_text = (
                f"✅ تم إلغاء العملية الحالية\n\n"
                f"🕐 {current_time}\n"
                f"🔸 يمكنك البدء من جديد."
            )
        else:
            cancel_text = (
                f"👋 أهلاً بعودتك!\n\n"
                f"🕐 {current_time}\n"
                f"🔸 اختر ما تريد من القائمة."
            )

        await message.answer(
            cancel_text,
            reply_markup=get_main_menu_keyboard(is_admin_user)
        )
    except Exception as e:
        logger.error(f"خطأ في دالة الإلغاء: {e}")
        await message.answer("حدث خطأ، حاول مرة أخرى.")

# ========== أمر البدء الرئيسي ==========

@router.message(CommandStart())
async def cmd_start(message: types.Message, db_pool):
    """معالج أمر /start مع دعم الإحالات والتحقق من اشتراك القناة"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""

    # التحقق من وجود كود إحالة
    args = message.text.split()
    referral_code = args[1] if len(args) > 1 else None

    # متغيرات افتراضية
    balance = 0
    is_banned = False
    total_points = 0
    is_new_user = False

    # ========== التحقق من اشتراك القناة ==========
    channel_username = "@LINKcharger22"
    try:
        member = await message.bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        is_member = member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"⚠️ خطأ في التحقق من القناة: {e}")
        is_member = False

    if not is_member:
        join_button = InlineKeyboardBuilder()
        join_button.row(types.InlineKeyboardButton(
            text="📢 انضم إلى القناة",
            url="https://t.me/LINKcharger22"
        ))
        join_button.row(types.InlineKeyboardButton(
            text="✅ تحقق من الاشتراك",
            callback_data="check_subscription"
        ))

        await message.answer(
            "❌ **عذراً، يجب الاشتراك في قناتنا أولاً لاستخدام البوت.**\n\n"
            "📢 **قناة البوت:** @LINKcharger22\n\n"
            "🔹 بعد الاشتراك، اضغط على زر 'تحقق من الاشتراك'.",
            reply_markup=join_button.as_markup(),
            parse_mode="Markdown"
        )
        return
    # =============================================

    async with db_pool.acquire() as conn:
        # التحقق من وجود المستخدم
        try:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        except Exception as e:
            print(f"خطأ في جلب المستخدم: {e}")
            user = None

        if not user:
            is_new_user = True

            # ===== إنشاء كود إحالة فريد =====
            new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

            # التأكد من عدم تكرار الكود
            while True:
                check = await conn.fetchval(
                    "SELECT user_id FROM users WHERE referral_code = $1",
                    new_code
                )
                if not check:
                    break
                new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            # ================================

            # مستخدم جديد - إنشاء حساب مع referral_code
            try:
                await conn.execute('''
                    INSERT INTO users 
                    (user_id, username, first_name, last_name, balance, referral_code, created_at, is_banned)
                    VALUES ($1, $2, $3, $4, 0, $5, CURRENT_TIMESTAMP, FALSE)
                ''', user_id, username, first_name, last_name, new_code)
                print(f"✅ تم إنشاء مستخدم جديد: {user_id} بكود إحالة {new_code}")
            except Exception as e:
                print(f"خطأ في إنشاء مستخدم: {e}")

            # ========== نص الترحيب للمستخدم الجديد ==========
            welcome_text = (
                "🎉 أهلاً بك في LINK 🔗 BOT لخدمات الشحن!\n\n"
                "🌟 تم إنشاء حسابك بنجاح\n\n"
                "🔸 ماذا يمكنك أن تفعل؟\n"
                "• 💰 شحن رصيد المحفظة\n"
                "• 📱 شراء خدمات وتطبيقات\n"
                "• ⭐ كسب نقاط من عملياتك\n"
                "• 🔗 دعوة أصدقائك وكسب نقاط إضافية\n\n"
                "🔹 لبدء الاستخدام، اختر من القائمة أدناه."
            )

            # ========== معالجة الإحالة للمستخدم الجديد ==========
            if referral_code:
                try:
                    print(f"🔍 محاولة معالجة إحالة بكود: {referral_code}")

                    # البحث عن المستخدم الذي قام بالإحالة
                    referrer = await conn.fetchrow(
                        "SELECT user_id FROM users WHERE referral_code = $1",
                        referral_code
                    )

                    if referrer and referrer['user_id'] != user_id:
                        print(f"✅ تم العثور على المُحيل: {referrer['user_id']}")

                        # ========== التحقق من التكرار ==========
                        # 1. التحقق مما إذا كان هذا المستخدم قد سبق له الدخول عبر إحالة
                        existing_referral = await conn.fetchval(
                            "SELECT referred_by FROM users WHERE user_id = $1",
                            user_id
                        )
            
                        # 2. التحقق مما إذا كان هذا المُحيل قد قام بإحالة هذا المستخدم سابقاً
                        already_referred = await conn.fetchval('''
                            SELECT COUNT(*) FROM points_history 
                            WHERE user_id = $1 
                              AND action = 'referral' 
                              AND description LIKE $2
                        ''', referrer['user_id'], f'%{user_id}%')
            
                        if existing_referral:
                            print(f"⚠️ المستخدم {user_id} لديه إحالة سابقة: {existing_referral}")
                            welcome_text += f"\n\n🔗 لديك إحالة مسجلة مسبقاً، لا يمكن تكرارها."
            
                        elif already_referred > 0:
                            print(f"⚠️ المُحيل {referrer['user_id']} حاول إعادة إحالة {user_id}")
                            # يمكن إرسال تحذير للمشرف أو تجاهل
                            try:
                                await message.bot.send_message(
                                    ADMIN_ID,
                                    f"⚠️ **محاولة تكرار إحالة مشبوهة**\n\n"
                                    f"👤 المُحيل: {referrer['user_id']}\n"
                                    f"👤 المستهدف: {user_id}\n"
                                    f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                                )
                            except:
                                pass
             
                        else:
                            # تسجيل من أحال المستخدم
                            await conn.execute(
                                "UPDATE users SET referred_by = $1 WHERE user_id = $2",
                                referrer['user_id'], user_id
                            )

                            # زيادة عدد المحالين
                            await conn.execute(
                                "UPDATE users SET referral_count = referral_count + 1 WHERE user_id = $1",
                                referrer['user_id']
                            )

                            # الحصول على قيمة النقاط من الإعدادات
                            points = await conn.fetchval(
                                "SELECT value FROM bot_settings WHERE key = 'points_per_referral'"
                            )
                            points = int(points) if points else 1

                            # إضافة نقاط للمستخدم الذي قام بالإحالة
                            await conn.execute(
                                "UPDATE users SET total_points = total_points + $1, referral_earnings = referral_earnings + $1 WHERE user_id = $2",
                                points, referrer['user_id']
                            )

                            # تسجيل في سجل النقاط
                            try:
                                await conn.execute('''
                                    INSERT INTO points_history (user_id, points, action, description, created_at)
                                    VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                                ''', referrer['user_id'], points, 'referral', f'نقاط إحالة للمستخدم {user_id}')
                                print(f"✅ تم تسجيل النقاط في سجل النقاط")
                            except Exception as e:
                                print(f"⚠️ فشل تسجيل النقاط في السجل: {e}")

                            welcome_text += f"\n\n🎁 تم تسجيل دخولك عن طريق رابط إحالة! صديقك حصل على {points} نقاط إضافية."

                            # إرسال إشعار للمستخدم الذي قام بالإحالة
                            try:
                                await message.bot.send_message(
                                    referrer['user_id'],
                                    f"🎉 **مبروك!**\n\n"
                                    f"@{message.from_user.username or 'مستخدم جديد'} سجل في البوت عبر رابط الإحالة الخاص بك!\n"
                                    f"⭐ لقد حصلت على {points} نقاط إضافية.\n\n"
                                    f"💰 رصيد نقاطك الحالي: {(await conn.fetchval('SELECT total_points FROM users WHERE user_id = $1', referrer['user_id'])) or 0}"
                                )
                                print(f"✅ تم إرسال إشعار للمُحيل: {referrer['user_id']}")
                            except Exception as e:
                                print(f"⚠️ فشل إرسال إشعار للمحيل: {e}")

                    else:
                        print(f"⚠️ لم يتم العثور على مُحيل للكود: {referral_code} أو هو نفس المستخدم")

                except Exception as e:
                    print(f"❌ خطأ في معالجة الإحالة: {e}")
                    import traceback
                    traceback.print_exc()
         # =================================================

        else:
            # مستخدم موجود - تحديث المعلومات
            try:
                await conn.execute('''
                    UPDATE users 
                    SET username = $1, last_activity = CURRENT_TIMESTAMP
                    WHERE user_id = $2
                ''', username, user_id)
            except Exception as e:
                print(f"خطأ في تحديث المستخدم: {e}")

            # محاولة تحديث الأسماء
            try:
                await conn.execute(
                    "UPDATE users SET first_name = $1, last_name = $2 WHERE user_id = $3",
                    first_name, last_name, user_id
                )
            except:
                pass

            # جلب الرصيد والنقاط بأمان
            try:
                balance_row = await conn.fetchrow(
                    "SELECT balance, is_banned FROM users WHERE user_id = $1",
                    user_id
                )
                if balance_row:
                    balance = balance_row['balance'] or 0
                    is_banned = balance_row['is_banned'] or False
                print(f"📊 المستخدم {user_id}: الرصيد={balance}, محظور={is_banned}")
            except Exception as e:
                print(f"خطأ في جلب الرصيد: {e}")
                balance = 0
                is_banned = False

            try:
                total_points = await conn.fetchval(
                    "SELECT total_points FROM users WHERE user_id = $1",
                    user_id
                ) or 0
            except:
                total_points = 0

            # ========== معالجة الإحالة للمستخدم الموجود ==========
            if referral_code and not user.get('referred_by'):
                try:
                    print(f"🔍 محاولة معالجة إحالة لمستخدم موجود بكود: {referral_code}")

                    # البحث عن المستخدم الذي قام بالإحالة
                    referrer = await conn.fetchrow(
                        "SELECT user_id FROM users WHERE referral_code = $1",
                        referral_code
                    )

                    if referrer and referrer['user_id'] != user_id:
                        print(f"✅ تم العثور على المُحيل: {referrer['user_id']}")

                        # تسجيل من أحال المستخدم
                        await conn.execute(
                            "UPDATE users SET referred_by = $1 WHERE user_id = $2",
                            referrer['user_id'], user_id
                        )

                        # زيادة عدد المحالين
                        await conn.execute(
                            "UPDATE users SET referral_count = referral_count + 1 WHERE user_id = $1",
                            referrer['user_id']
                        )

                        # الحصول على قيمة النقاط من الإعدادات
                        points = await conn.fetchval(
                            "SELECT value FROM bot_settings WHERE key = 'points_per_referral'"
                        )
                        points = int(points) if points else 1

                        # إضافة نقاط للمستخدم الذي قام بالإحالة
                        await conn.execute(
                            "UPDATE users SET total_points = total_points + $1, referral_earnings = referral_earnings + $1 WHERE user_id = $2",
                            points, referrer['user_id']
                        )

                        # تسجيل في سجل النقاط
                        try:
                            await conn.execute('''
                                INSERT INTO points_history (user_id, points, action, description, created_at)
                                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                            ''', referrer['user_id'], points, 'referral', f'نقاط إحالة للمستخدم {user_id}')
                            print(f"✅ تم تسجيل النقاط في سجل النقاط")
                        except Exception as e:
                            print(f"⚠️ فشل تسجيل النقاط في السجل: {e}")

                        # رسالة للمستخدم
                        welcome_text += f"\n\n🎁 تم ربط حسابك برابط الإحالة! صديقك حصل على {points} نقاط إضافية."

                        # إرسال إشعار للمستخدم الذي قام بالإحالة
                        try:
                            await message.bot.send_message(
                                referrer['user_id'],
                                f"🎉 **مبروك!**\n\n"
                                f"@{message.from_user.username or 'مستخدم قديم'} دخل عبر رابط الإحالة الخاص بك!\n"
                                f"⭐ لقد حصلت على {points} نقاط إضافية.\n\n"
                                f"💰 رصيد نقاطك الحالي: {(await conn.fetchval('SELECT total_points FROM users WHERE user_id = $1', referrer['user_id'])) or 0}"
                            )
                            print(f"✅ تم إرسال إشعار للمُحيل: {referrer['user_id']}")
                        except Exception as e:
                            print(f"⚠️ فشل إرسال إشعار للمحيل: {e}")

                except Exception as e:
                    print(f"❌ خطأ في معالجة الإحالة للمستخدم الموجود: {e}")
                    import traceback
                    traceback.print_exc()
            # ====================================================

            # ========== نص الترحيب للمستخدم العائد ==========
            if not 'welcome_text' in locals():
                welcome_text = (
                    f"👋 أهلاً بعودتك {first_name or ''}!\n\n"
                    f"📊 ملخص حسابك:\n"
                    f"💰 الرصيد: {balance:,.0f} ل.س\n"
                    f"⭐ النقاط: {total_points}\n\n"
                    "🔸 اختر ما تريد من القائمة."
                )
            # ================================================

    # التحقق من الحظر - بعد كل العمليات
    if is_banned:
        print(f"🚫 محاولة دخول من مستخدم محظور: {user_id}")
        return await message.answer(
            "🚫 عذراً، حسابك محظور من استخدام البوت.\n\n"
            "📞 للتواصل مع الدعم: @support"
        )

    # إرسال الرسالة الترحيبية
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(is_admin(user_id))
    )

# ========== التحقق من اشتراك القناة ==========

@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: types.CallbackQuery, db_pool):
    """التحقق من اشتراك المستخدم بعد الانضمام للقناة"""
    user_id = callback.from_user.id
    channel_username = "@LINKcharger22"

    try:
        member = await callback.bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        is_member = member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"⚠️ خطأ في التحقق من القناة: {e}")
        is_member = False

    if is_member:
        await callback.message.delete()
        await cmd_start(callback.message, db_pool)
    else:
        await callback.answer("❌ لم تشترك في القناة بعد! اشترك ثم حاول مرة أخرى.", show_alert=True)

# ========== العودة للقائمة الرئيسية ==========

@router.message(F.text == "🔙 رجوع للقائمة")
async def back_to_main_menu(message: types.Message, db_pool):
    """معالجة زر الرجوع للقائمة الرئيسية"""
    await cmd_start(message, db_pool)

# ========== الملف الشخصي ==========

@router.message(F.text == "👤 حسابي")
async def my_account(message: types.Message, db_pool):
    """عرض الملف الشخصي مع أزرار النقاط والإحالة وتفاصيل VIP"""
    user_id = message.from_user.id

    async with db_pool.acquire() as conn:
        try:
            user_data = await conn.fetchrow(
                "SELECT is_banned, balance, total_points, referral_code, username, first_name, vip_level, discount_percent, total_spent FROM users WHERE user_id = $1",
                user_id
            )
            if user_data and user_data['is_banned']:
                return await message.answer("🚫 حسابك محظور من استخدام البوت.")

            balance = user_data['balance'] if user_data else 0
            points = user_data['total_points'] if user_data else 0
            referral_code = user_data['referral_code'] if user_data else None
            username = user_data['username'] if user_data else None
            first_name = user_data['first_name'] if user_data else None
            vip_level = user_data['vip_level'] if user_data else 0
            vip_discount = user_data['discount_percent'] if user_data else 0
            total_spent = user_data['total_spent'] if user_data else 0
        except Exception as e:
            print(f"خطأ في التحقق من الحظر: {e}")
            balance = 0
            points = 0
            referral_code = None
            username = None
            first_name = None
            vip_level = 0
            vip_discount = 0
            total_spent = 0

    # حساب قيمة النقاط بالسعر الحالي
    from database import get_redemption_rate, get_exchange_rate, get_next_vip_level
    redemption_rate = await get_redemption_rate(db_pool)
    exchange_rate = await get_exchange_rate(db_pool)

    # قيمة 100 نقطة = 1 دولار
    points_value_usd = (points / redemption_rate) 
    points_value_syp = points_value_usd * exchange_rate

    # قيمة 100 نقطة بالليرة
    base_syp = 1 * exchange_rate

    # تحديد أيقونة VIP
    vip_icons = ["⚪", "🔵", "🟣", "🟡"]
    vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "🟢"

    # حساب التقدم للمستوى التالي
    next_level_info = get_next_vip_level(total_spent)

    if next_level_info and next_level_info.get('remaining', 0) > 0:
        remaining = next_level_info['remaining']
        next_level_name = next_level_info['next_level_name']
        progress_text = f"📊 {remaining:,.0f} ل.س للمستوى {next_level_name}"
    else:
        progress_text = "✨ وصلت لأعلى مستوى! (VIP 3)"

    # إنشاء أزرار إنلاين
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="show_referral"),
        types.InlineKeyboardButton(text="⭐ رصيد النقاط", callback_data="show_points")
    )
    builder.row(
        types.InlineKeyboardButton(text="📊 سجل النقاط", callback_data="points_history_simple"),
        types.InlineKeyboardButton(text="💰 استرداد نقاط", callback_data="redeem_points_menu")
    )

    # رسالة الملف الشخصي مع تفاصيل VIP
    profile_text = (
        f"👤 **الملف الشخصي**\n\n"
        f"🆔 **الآيدي:** `{user_id}`\n"
        f"👤 **الاسم:** {first_name or message.from_user.full_name}\n"
        f"📅 **اليوزر:** @{username or message.from_user.username or 'غير متوفر'}\n"
        f"💰 **الرصيد:** {balance:,.0f} ل.س\n"
        f"⭐ **نقاطك:** {points}\n"
        f"💵 **قيمة نقاطك:** {points_value_syp:.0f} ل.س\n\n"
        f"👑 **نظام VIP:**\n"
        f"• مستواك: {vip_icon} VIP {vip_level}\n"
        f"• خصمك الحالي: {vip_discount}%\n"
        f"• إجمالي مشترياتك: {total_spent:,.0f} ل.س\n"
        f"{progress_text}\n\n"
        f"💱 **سعر الصرف:** {exchange_rate:.0f} ل.س = 1$\n"
        f"🎁 **كل {redemption_rate} نقطة = 1$** ({base_syp:.0f} ل.س)\n\n"
        f"🔹 **اختر من الأزرار أدناه:**"
    )

    await message.answer(
        profile_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# ========== رابط الإحالة ==========

@router.callback_query(F.data == "show_referral")
async def show_referral_button(callback: types.CallbackQuery, db_pool):
    """عرض رابط الإحالة مع سعر الصرف الحالي"""
    from database import generate_referral_code, get_exchange_rate

    # جلب سعر الصرف الحالي من قاعدة البيانات
    exchange_rate = await get_exchange_rate(db_pool)

    async with db_pool.acquire() as conn:
        try:
            code = await conn.fetchval(
                "SELECT referral_code FROM users WHERE user_id = $1",
                callback.from_user.id
            )
        except:
            code = None

    if not code:
        # إنشاء كود جديد
        code = await generate_referral_code(db_pool, callback.from_user.id)

    bot_username = (await callback.bot.me()).username
    link = f"https://t.me/{bot_username}?start={code}"

    # إحصائيات الإحالة
    async with db_pool.acquire() as conn:
        referrals_count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE referred_by = $1",
            callback.from_user.id
        ) or 0

        try:
            points_from_referrals = await conn.fetchval(
                "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND action = 'referral'",
                callback.from_user.id
            ) or 0
        except:
            points_from_referrals = 0

    # حساب قيمة 1 دولار بسعر الصرف الحالي
    five_usd_value = 1 * exchange_rate

    text = (
        f"🔗 رابط الإحالة الخاص بك\n\n"
        f"{link}\n\n"
        f"📊 إحصائيات الإحالة:\n"
        f"• عدد المحالين: {referrals_count}\n"
        f"• النقاط المكتسبة: {points_from_referrals}\n\n"
        f"🎁 مميزات الإحالة:\n"
        f"• 1 نقطة لكل مشترك جديد\n"
        f"• كل 100 نقطة = 1$ ({five_usd_value:.0f} ل.س)\n"
        f"💰 **سعر الصرف الحالي:** {exchange_rate:.0f} ل.س = 1$\n\n"
        f"شارك الرابط مع أصدقائك!"
    )

    await callback.message.edit_text(text)

    # زر العودة
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للحساب", callback_data="back_to_account"))
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

# ========== معلومات النقاط ==========

@router.callback_query(F.data == "show_points")
async def show_points_info(callback: types.CallbackQuery, db_pool):
    """عرض معلومات النقاط مع توقيت دمشق"""
    async with db_pool.acquire() as conn:
        current_points = await conn.fetchval(
            "SELECT total_points FROM users WHERE user_id = $1",
            callback.from_user.id
        ) or 0

        # جلب آخر 5 حركات
        recent = await conn.fetch('''
            SELECT points, description, created_at
            FROM points_history 
            WHERE user_id = $1 
            ORDER BY created_at DESC 
            LIMIT 5
        ''', callback.from_user.id)

        # إحصائيات
        total_earned = await conn.fetchval(
            "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND points > 0",
            callback.from_user.id
        ) or 0

        total_used = await conn.fetchval(
            "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND points < 0",
            callback.from_user.id
        ) or 0

        # آخر تحديث
        last_update = await conn.fetchval('''
            SELECT created_at 
            FROM points_history 
            WHERE user_id = $1 
            ORDER BY created_at DESC 
            LIMIT 1
        ''', callback.from_user.id)

    text = f"⭐ **رصيد النقاط**\n\n"
    text += f"**نقاطك الحالية:** {current_points}\n"
    text += f"📊 **إجمالي المكتسب:** {total_earned}\n"
    text += f"📊 **إجمالي المستخدم:** {abs(total_used)}\n\n"

    if last_update:
        last_update_str = format_damascus_time(last_update)
        text += f"🕐 **آخر تحديث:** {last_update_str}\n\n"

    if recent:
        text += "**آخر الحركات (بتوقيت دمشق):**\n"
        for r in recent:
            date = format_damascus_time(r['created_at'])
            sign = "➕" if r['points'] > 0 else "➖"
            emoji = "✅" if r['points'] > 0 else "❌"
            text += f"{emoji} {sign} {abs(r['points'])} نقطة - {r['description']}\n"
            text += f"   🕐 {date}\n\n"

    await callback.message.edit_text(text, parse_mode="Markdown")

    # زر العودة
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للحساب", callback_data="back_to_account"))
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

# ========== سجل النقاط المبسط ==========

@router.callback_query(F.data == "points_history_simple")
async def points_history_simple(callback: types.CallbackQuery, db_pool):
    """عرض سجل النقاط - مع توقيت دمشق"""
    try:
        async with db_pool.acquire() as conn:
            # جلب سجل النقاط
            history = await conn.fetch('''
                SELECT points, description, created_at
                FROM points_history 
                WHERE user_id = $1 
                ORDER BY created_at DESC 
                LIMIT 20
            ''', callback.from_user.id)

            # جلب الرصيد الحالي
            current_points = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                callback.from_user.id
            ) or 0

            # جلب إجمالي المكتسب والمستخدم
            total_earned = await conn.fetchval(
                "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND points > 0",
                callback.from_user.id
            ) or 0

            total_used = await conn.fetchval(
                "SELECT COALESCE(SUM(points), 0) FROM points_history WHERE user_id = $1 AND points < 0",
                callback.from_user.id
            ) or 0

            # جلب وقت آخر تحديث
            last_update = await conn.fetchval('''
                SELECT created_at 
                FROM points_history 
                WHERE user_id = $1 
                ORDER BY created_at DESC 
                LIMIT 1
            ''', callback.from_user.id)
    except Exception as e:
        print(f"خطأ في جلب سجل النقاط: {e}")
        history = []
        current_points = 0
        total_earned = 0
        total_used = 0
        last_update = None

    if not history:
        text = (
            f"📋 **سجل النقاط**\n\n"
            f"⭐ **رصيدك الحالي:** {current_points} نقطة\n\n"
            f"لا يوجد سجل نقاط بعد.\n"
            f"قم بشراء الخدمات أو شحن الرصيد لكسب النقاط!"
        )
    else:
        text = f"📋 **سجل النقاط**\n\n"
        text += f"⭐ **رصيدك الحالي:** {current_points} نقطة\n"
        text += f"📊 **إجمالي المكتسب:** {total_earned} | **المستخدم:** {abs(total_used)}\n"

        if last_update:
            last_update_str = format_damascus_time(last_update)
            text += f"🕐 **آخر تحديث:** {last_update_str}\n\n"

        for h in history:
            date = format_damascus_time(h['created_at'])

            sign = "➕" if h['points'] > 0 else "➖"
            emoji = "✅" if h['points'] > 0 else "🔄"
            text += f"{emoji} {sign} {abs(h['points'])} نقطة\n"
            text += f"   📝 {h['description']}\n"
            text += f"   🕐 {date} (دمشق)\n\n"

    await callback.message.edit_text(text, parse_mode="Markdown")

    # زر العودة
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للحساب", callback_data="back_to_account"))
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

# ========== قائمة استرداد النقاط ==========

@router.callback_query(F.data == "redeem_points_menu")
async def redeem_points_menu(callback: types.CallbackQuery, db_pool):
    """قائمة استرداد النقاط"""
    async with db_pool.acquire() as conn:
        points = await conn.fetchval(
            "SELECT total_points FROM users WHERE user_id = $1",
            callback.from_user.id
        ) or 0

        redemption_rate = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = 'redemption_rate'"
        ) or '100'
        redemption_rate = int(redemption_rate)

        from database import get_exchange_rate
        exchange_rate = await get_exchange_rate(db_pool)

    if points < redemption_rate:
        return await callback.answer(
            f"تحتاج {redemption_rate} نقطة على الأقل للاسترداد.\nلديك {points} نقطة فقط.", 
            show_alert=True
        )

    # حساب قيمة 100 نقطة بالليرة
    base_usd = 1
    base_syp = base_usd * exchange_rate

    # حساب المبالغ الممكنة
    max_redemptions = min(points // redemption_rate, 20)

    builder = InlineKeyboardBuilder()
    for i in range(1, max_redemptions + 1):
        points_needed = i * redemption_rate
        syp_amount = i * base_syp
        usd_amount = i * base_usd

        builder.row(types.InlineKeyboardButton(
            text=f"{usd_amount}$ ({syp_amount:.0f} ل.س) - {points_needed} نقطة",
            callback_data=f"redeem_{points_needed}_{syp_amount}_{exchange_rate}"
        ))

    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للحساب", 
        callback_data="back_to_account"
    ))

    text = (
        f"🎁 **استرداد النقاط**\n\n"
        f"لديك {points} نقطة\n"
        f"💰 **سعر الصرف الحالي:** {exchange_rate:.0f} ل.س = 1$\n"
        f"🎯 **معدل الاسترداد:** كل {redemption_rate} نقطة = 1$ ({base_syp:.0f} ل.س)\n\n"
        f"اختر المبلغ الذي تريد استرداده:"
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ========== معالجة طلب الاسترداد ==========

@router.callback_query(F.data.startswith("redeem_"))
async def process_redeem_from_menu(callback: types.CallbackQuery, db_pool):
    """معالجة طلب الاسترداد - مع توقيت دمشق"""
    try:
        parts = callback.data.split("_")
        points = int(parts[1])
        amount_syp = float(parts[2])
        exchange_rate = float(parts[3]) if len(parts) > 3 else None

        amount_usd = amount_syp / exchange_rate if exchange_rate else points / 100 * 1

        from database import create_redemption_request

        request_id, error = await create_redemption_request(
            db_pool, 
            callback.from_user.id,
            callback.from_user.username,
            points,
            amount_usd,
            amount_syp
        )

        if error:
            await callback.answer(f"❌ {error}", show_alert=True)
        else:
            current_time = get_damascus_time_now().strftime("%Y-%m-%d %H:%M:%S")

            await callback.message.edit_text(
                f"✅ **تم إرسال طلب الاسترداد بنجاح!**\n\n"
                f"⭐ النقاط: {points}\n"
                f"💰 المبلغ: {amount_syp:.0f} ل.س\n"
                f"💵 سعر الصرف: {exchange_rate:.0f} ل.س = 1$\n"
                f"🕐 وقت الطلب: {current_time} (دمشق)\n\n"
                f"⏳ في انتظار موافقة الإدارة.\n"
                f"📋 رقم الطلب: #{request_id}"
            )

            # إشعار المشرفين
            await notify_admins(
                callback.bot,
                f"🆕 **طلب استرداد نقاط جديد**\n\n"
                f"👤 المستخدم: @{callback.from_user.username or 'غير معروف'}\n"
                f"🆔 الآيدي: `{callback.from_user.id}`\n"
                f"⭐ النقاط: {points}\n"
                f"💰 المبلغ: {amount_syp:.0f} ل.س\n"
                f"💵 سعر الصرف: {exchange_rate:.0f} ل.س\n"
                f"🕐 وقت الطلب: {current_time} (دمشق)\n"
                f"📋 رقم الطلب: #{request_id}"
            )

            # زر العودة
            builder = InlineKeyboardBuilder()
            builder.row(types.InlineKeyboardButton(
                text="🔙 رجوع للحساب", 
                callback_data="back_to_account"
            ))
            await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# ========== العودة للملف الشخصي ==========

@router.callback_query(F.data == "back_to_account")
async def back_to_account(callback: types.CallbackQuery, db_pool):
    """العودة إلى الملف الشخصي - مع سعر الصرف الحالي وتفاصيل VIP"""
    user_id = callback.from_user.id

    # جلب سعر الصرف الحالي من قاعدة البيانات
    from database import get_exchange_rate, get_redemption_rate, get_next_vip_level
    exchange_rate = await get_exchange_rate(db_pool)
    redemption_rate = await get_redemption_rate(db_pool)

    async with db_pool.acquire() as conn:
        try:
            user_data = await conn.fetchrow(
                "SELECT is_banned, balance, total_points, referral_code, username, first_name, vip_level, discount_percent, total_spent FROM users WHERE user_id = $1",
                user_id
            )
            balance = user_data['balance'] if user_data else 0
            points = user_data['total_points'] if user_data else 0
            username = user_data['username'] if user_data else None
            first_name = user_data['first_name'] if user_data else None
            vip_level = user_data['vip_level'] if user_data else 0
            vip_discount = user_data['discount_percent'] if user_data else 0
            total_spent = user_data['total_spent'] if user_data else 0
        except:
            balance = 0
            points = 0
            username = None
            first_name = None
            vip_level = 0
            vip_discount = 0
            total_spent = 0

    # حساب قيمة النقاط بسعر الصرف الحالي
    points_value_usd = (points / redemption_rate) 
    points_value_syp = points_value_usd * exchange_rate
    base_syp = 1 * exchange_rate

    # تحديد أيقونة VIP
    vip_icons = ["⚪", "🔵", "🟣", "🟡"]
    vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "🟢"

    # حساب التقدم للمستوى التالي
    next_level_info = get_next_vip_level(total_spent)

    if next_level_info and next_level_info.get('remaining', 0) > 0:
        remaining = next_level_info['remaining']
        next_level_name = next_level_info['next_level_name']
        progress_text = f"📊 {remaining:,.0f} ل.س للمستوى {next_level_name}"
    else:
        progress_text = "✨ وصلت لأعلى مستوى! (VIP 3)"

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔗 رابط الإحالة", callback_data="show_referral"),
        types.InlineKeyboardButton(text="⭐ رصيد النقاط", callback_data="show_points")
    )
    builder.row(
        types.InlineKeyboardButton(text="📊 سجل النقاط", callback_data="points_history_simple"),
        types.InlineKeyboardButton(text="💰 استرداد نقاط", callback_data="redeem_points_menu")
    )

    profile_text = (
        f"👤 **الملف الشخصي**\n\n"
        f"🆔 **الآيدي:** `{user_id}`\n"
        f"👤 **الاسم:** {first_name or callback.from_user.full_name}\n"
        f"📅 **اليوزر:** @{username or callback.from_user.username or 'غير متوفر'}\n"
        f"💰 **الرصيد:** {balance:,.0f} ل.س\n"
        f"⭐ **نقاطك:** {points}\n"
        f"💵 **قيمة نقاطك:** {points_value_syp:.0f} ل.س\n\n"
        f"👑 **نظام VIP:**\n"
        f"• مستواك: {vip_icon} VIP {vip_level}\n"
        f"• خصمك الحالي: {vip_discount}%\n"
        f"• إجمالي مشترياتك: {total_spent:,.0f} ل.س\n"
        f"{progress_text}\n\n"
        f"💱 **سعر الصرف:** {exchange_rate:.0f} ل.س = 1$\n"
        f"🎁 **كل {redemption_rate} نقطة = 1$** ({base_syp:.0f} ل.س)\n\n"
        f"🔹 **اختر من الأزرار أدناه:**"
    )

    await callback.message.edit_text(
        profile_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# ========== لوحة تحكم المشرفين ==========

@router.message(F.text == "🛠 لوحة التحكم")
async def admin_control_panel(message: types.Message, db_pool):
    """لوحة تحكم المشرفين"""
    if not is_admin(message.from_user.id):
        return await message.answer("⚠️ هذا الزر مخصص للمشرفين فقط.")

    # استيراد لوحة التحكم من ملف admin
    try:
        from handlers.admin import admin_panel
        await admin_panel(message, db_pool)
    except ImportError as e:
        print(f"خطأ في استيراد admin_panel: {e}")
        # بديل إذا لم يكن ملف admin متوفراً
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="📈 تعديل سعر الصرف", callback_data="edit_rate"),
            types.InlineKeyboardButton(text="💰 إدارة المستخدمين", callback_data="manage_users")
        )
        builder.row(
            types.InlineKeyboardButton(text="📱 إدارة التطبيقات", callback_data="manage_apps"),
            types.InlineKeyboardButton(text="⭐ إدارة النقاط", callback_data="manage_points")
        )

        await message.answer(
            "🛠 **لوحة تحكم الإدارة**\n\n"
            "🔸 اختر الإجراء المطلوب:",
            reply_markup=builder.as_markup()
        )

# ========== المساعدة ==========

@router.message(F.text == "❓ مساعدة")
async def show_help(message: types.Message):
    """عرض رسالة المساعدة"""
    help_text = (
        "📚 **دليل استخدام البوت**\n\n"
        "**📱 خدمات الشحن:**\n"
        "• عرض قائمة التطبيقات المتاحة\n"
        "• اختيار التطبيق والكمية\n"
        "• إدخال ID الحساب المستهدف\n"
        "• الدفع من رصيدك\n\n"
        "**💰 شحن المحفظة:**\n"
        "• اختيار طريقة الدفع المناسبة\n"
        "• تحويل المبلغ للرقم المطلوب\n"
        "• إرسال رقم العملية أو لقطة شاشة\n\n"
        "**👤 حسابي:**\n"
        "• عرض الرصيد الحالي\n"
        "• عرض النقاط وقيمتها\n"
        "• رابط الإحالة الخاص بك\n"
        "• سجل النقاط\n"
        "• استرداد النقاط\n"
        "• مستوى VIP والخصم\n\n"
        "**⭐ نظام النقاط:**\n"
        "• 1 نقاط لكل عملية شراء\n"
        "• 1 نقاط لكل إحالة ناجحة\n"
        "• استبدال 100 نقطة بـ 1$ رصيد\n\n"
        "**👑 نظام VIP:**\n"
        "• VIP 0: 0% خصم (0 ل.س)\n"
        "• VIP 1: 1% خصم (2000 ل.س)\n"
        "• VIP 2: 2% خصم (4000 ل.س)\n"
        "• VIP 3: 4% خصم (8000 ل.س)\n"
        "**📞 للدعم:**\n"
        "• @support\n\n"
        "🔹 **لتحديث القائمة: أرسل /start**"
    )

    await message.answer(help_text, parse_mode="Markdown")
