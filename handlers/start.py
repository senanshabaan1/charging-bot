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
from handlers.keyboards import get_main_menu_keyboard, get_back_keyboard
from utils import is_admin
from .profile_handlers import router as profile_router
from database.points import get_redemption_rate, create_redemption_request
from database.core import get_exchange_rate
from database.vip import get_next_vip_level
from database.referrals import generate_referral_code
from database.users import is_admin_user 
from aiogram.fsm.state import State, StatesGroup
class ReferralStates(StatesGroup):
    waiting_subscription = State()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()
router.include_router(profile_router)

async def notify_admins(bot, message_text, db_pool=None):
    """إرسال إشعار لجميع المشرفين"""
    from config import ADMIN_ID, MODERATORS
    
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
    
    logger.info(f"✅ تم إرسال إشعار لـ {sent_count} مشرف")
    return sent_count

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
        damascus_tz = pytz.timezone('Asia/Damascus')
        current_time = datetime.now(damascus_tz).strftime('%H:%M:%S')
        
        current_state = await state.get_state()
        logger.info(f"حالة FSM الحالية: {current_state}")
        
        await state.clear()
        
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
    
    # ✅ تجاهل البوت نفسه
    BOT_ID = 8384048684
    if message.from_user.id == BOT_ID:
        return
    
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    
    args = message.text.split()
    referral_code = args[1] if len(args) > 1 else None
    
    # ✅ تعريف المتغيرات في البداية
    balance = 0
    is_banned = False
    total_points = 0
    is_new_user = False
    
    # التحقق من اشتراك القناة أولاً
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
    
    # المستخدم مشترك في القناة، نكمل إنشاء الحساب
    async with db_pool.acquire() as conn:
        try:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        except Exception as e:
            logger.error(f"خطأ في جلب المستخدم: {e}")
            user = None
        
        # ===== إذا كان المستخدم غير موجود =====
        if not user:
            # إنشاء كود إحالة فريد للمستخدم الجديد
            new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            while True:
                check = await conn.fetchval(
                    "SELECT user_id FROM users WHERE referral_code = $1",
                    new_code
                )
                if not check:
                    break
                new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            # إنشاء المستخدم في قاعدة البيانات
            try:
                await conn.execute('''
                    INSERT INTO users 
                    (user_id, username, first_name, last_name, balance, referral_code, created_at, is_banned)
                    VALUES ($1, $2, $3, $4, 0, $5, CURRENT_TIMESTAMP, FALSE)
                ''', user_id, username, first_name, last_name, new_code)
                logger.info(f"✅ تم إنشاء مستخدم جديد: {user_id} بكود إحالة {new_code}")
            except Exception as e:
                logger.error(f"خطأ في إنشاء مستخدم: {e}")
            
            welcome_text = (
                "🎉 أهلاً بك في LINK 🔗 BOT لخدمات الشحن!\n\n"
                "🌟 تم إنشاء حسابك بنجاح\n\n"
                "🔸 ماذا يمكنك أن تفعل؟\n"
                "• 💰 شحن رصيد المحفظة\n"
                "• 📱 شراء خدمات وتطبيقات\n"
                "• ⭐ كسب نقاط من عملياتك\n"
                "• 🔗 دعوة أصدقائك وكسب نقاط إضافية\n\n"
            )
            
            # ========== معالجة الإحالة ==========
            if referral_code:
                logging.info(f"🔍 تم استلام كود إحالة: {referral_code}")
                logger.info(f"🔍 محاولة معالجة إحالة بكود: {referral_code}")
                
                try:
                    referrer = await conn.fetchrow(
                        "SELECT user_id, username, total_points FROM users WHERE referral_code = $1",
                        referral_code
                    )
                    
                    if referrer:
                        logger.info(f"✅ تم العثور على المُحيل: {referrer['user_id']}")
                        
                        if referrer['user_id'] == user_id:
                            logger.warning("⚠️ المستخدم يحاول إحالة نفسه!")
                        else:
                            # 1. تسجيل من أحال المستخدم الجديد
                            await conn.execute(
                                "UPDATE users SET referred_by = $1 WHERE user_id = $2",
                                referrer['user_id'], user_id
                            )
                            logger.info(f"✅ تم تسجيل referred_by للمستخدم الجديد")
                            
                            # 2. جلب عدد النقاط من الإعدادات
                            points = await conn.fetchval(
                                "SELECT value::integer FROM bot_settings WHERE key = 'points_per_referral'"
                            ) or 1
                            
                            # 3. تحديث بيانات المُحيل (نقاط + عدد الإحالات)
                            await conn.execute('''
                                UPDATE users 
                                SET referral_count = referral_count + 1,
                                    total_points = total_points + $1,
                                    referral_earnings = referral_earnings + $1
                                WHERE user_id = $2
                            ''', points, referrer['user_id'])
                            
                            logger.info(f"✅ تم إضافة {points} نقاط للمُحيل")
                            
                            # 4. تسجيل في سجل النقاط
                            try:
                                await conn.execute('''
                                    INSERT INTO points_history (user_id, points, action, description, created_at)
                                    VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                                ''', referrer['user_id'], points, 'referral', f'إحالة المستخدم {user_id}')
                                logger.info(f"✅ تم تسجيل النقاط في سجل النقاط")
                            except Exception as e:
                                logger.error(f"⚠️ فشل تسجيل النقاط في السجل: {e}")
                            
                            # 5. إرسال إشعار للمُحيل
                            try:
                                new_points = await conn.fetchval(
                                    "SELECT total_points FROM users WHERE user_id = $1",
                                    referrer['user_id']
                                )
                                await message.bot.send_message(
                                    referrer['user_id'],
                                    f"🎉 **مبروك! لديك إحالة جديدة**\n\n"
                                    f"👤 المستخدم: @{username or first_name or 'مستخدم جديد'}\n"
                                    f"⭐ نقاط مكتسبة: +{points}\n"
                                    f"💰 رصيد النقاط الحالي: {new_points}",
                                    parse_mode="Markdown"
                                )
                                logger.info(f"✅ تم إرسال إشعار للمُحيل: {referrer['user_id']}")
                            except Exception as e:
                                logger.error(f"⚠️ فشل إرسال إشعار للمحيل: {e}")
                            
                            # 6. تحديث نص الترحيب للمستخدم الجديد
                            welcome_text += f"\n\n🎁 تم تسجيل دخولك عن طريق رابط إحالة! صديقك حصل على {points} نقاط إضافية."
                    
                    else:
                        logger.warning(f"⚠️ لم يتم العثور على مُحيل للكود: {referral_code}")
                        
                except Exception as e:
                    logger.error(f"❌ خطأ في معالجة الإحالة: {e}")
                    import traceback
                    traceback.print_exc()
            
            # إكمال نص الترحيب
            welcome_text += "🔹 لبدء الاستخدام، اختر من القائمة أدناه."
        
        # ===== إذا كان المستخدم موجوداً مسبقاً =====
        else:
            # تحديث المعلومات
            try:
                await conn.execute('''
                    UPDATE users 
                    SET username = $1, last_activity = CURRENT_TIMESTAMP
                    WHERE user_id = $2
                ''', username, user_id)
            except Exception as e:
                logger.error(f"خطأ في تحديث المستخدم: {e}")
            
            try:
                await conn.execute(
                    "UPDATE users SET first_name = $1, last_name = $2 WHERE user_id = $3",
                    first_name, last_name, user_id
                )
            except Exception as e:
                logger.error(f"خطأ في تحديث الاسم: {e}")
            
            try:
                balance_row = await conn.fetchrow(
                    "SELECT balance, is_banned FROM users WHERE user_id = $1",
                    user_id
                )
                if balance_row:
                    balance = balance_row['balance'] or 0
                    is_banned = balance_row['is_banned'] or False
                logger.info(f"📊 المستخدم {user_id}: الرصيد={balance}, محظور={is_banned}")
            except Exception as e:
                logger.error(f"خطأ في جلب الرصيد: {e}")
                balance = 0
                is_banned = False
            
            try:
                total_points = await conn.fetchval(
                    "SELECT total_points FROM users WHERE user_id = $1",
                    user_id
                ) or 0
            except Exception as e:
                logger.error(f"خطأ في جلب النقاط: {e}")
                total_points = 0
            
            # التحقق إذا كان المستخدم له referred_by (أي جاء عبر إحالة سابقة)
            referred_by = user.get('referred_by')
            welcome_text = f"👋 أهلاً بعودتك {first_name or ''}!\n\n"
            
            if referred_by and not user.get('welcome_shown'):
                # إذا كان المستخدم جاء عبر إحالة ولم تظهر له رسالة التأكيد بعد
                welcome_text += f"🎁 تم تسجيل دخولك عن طريق رابط إحالة!\n\n"
                # تحديث حقل لمنع ظهور الرسالة مرة أخرى (إذا أضفت هذا الحقل)
            
            welcome_text += (
                f"📊 ملخص حسابك:\n"
                f"💰 الرصيد: {balance:,.0f} ل.س\n"
                f"⭐ النقاط: {total_points}\n\n"
                "🔸 اختر ما تريد من القائمة."
            )
    
    # التحقق من الحظر
    if is_banned:
        logger.warning(f"🚫 محاولة دخول من مستخدم محظور: {user_id}")
        return await message.answer(
            "🚫 عذراً، حسابك محظور من استخدام البوت.\n\n"
            "📞 للتواصل مع الدعم: @support"
        )
    
    # إرسال رسالة الترحيب
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(is_admin(user_id))
    )

# ========== التحقق من اشتراك القناة ==========
@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """التحقق من اشتراك المستخدم بعد الانضمام للقناة"""
    user_id = callback.from_user.id
    channel_username = "@LINKcharger22"
    
    try:
        member = await callback.bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        is_member = member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"⚠️ خطأ في التحقق من القناة: {e}")
        is_member = False
    
    if is_member:
        await callback.message.delete()
        
        # ✅ استرجاع كود الإحالة من state
        data = await state.get_data()
        referral_code = data.get('referral_code')
        
        # إنشاء رسالة جديدة بنفس كود الإحالة
        new_message = callback.message
        new_message.text = f"/start {referral_code}" if referral_code else "/start"
        
        # مسح الحالة
        await state.clear()
        
        # استدعاء cmd_start مع الرسالة المعدلة
        await cmd_start(new_message, state, db_pool)
    else:
        await callback.answer("❌ لم تشترك في القناة بعد! اشترك ثم حاول مرة أخرى.", show_alert=True)

# ========== العودة للقائمة الرئيسية ==========
@router.message(F.text == "🔙 رجوع للقائمة")
async def back_to_main_menu(message: types.Message, db_pool):
    """معالجة زر الرجوع للقائمة الرئيسية"""
    await cmd_start(message, db_pool)

# ========== لوحة تحكم المشرفين ==========
@router.message(F.text == "🛠 لوحة التحكم")
async def admin_control_panel(message: types.Message, db_pool):
    """لوحة تحكم المشرفين"""
    if not is_admin(message.from_user.id):
        return await message.answer("⚠️ هذا الزر مخصص للمشرفين فقط.")
    
    from admin import router as admin_router
    from admin.main import admin_panel
    await admin_panel(message, db_pool)

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
        "• VIP 0: 0% خصم\n"
        "• VIP 1: 1% خصم (3500 ل.س)\n"
        "• VIP 2: 2% خصم (6500 ل.س)\n"
        "• VIP 3: 3% خصم (12000 ل.س)\n"
            
        "**📞 للدعم:**\n"
        "• @Charger444\n\n"
        
        "🔹 **لتحديث القائمة: أرسل /start**"
    )
    
    await message.answer(help_text, parse_mode="Markdown")
