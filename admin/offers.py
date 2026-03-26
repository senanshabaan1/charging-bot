# admin/offers.py - مكافآت الإيداع فقط
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from datetime import datetime, timedelta
import pytz

from database.users import is_admin_user
from handlers.keyboards import get_back_inline_keyboard, get_confirmation_keyboard
from handlers.time_utils import get_damascus_time_now

from database.core import (
    get_active_deposit_bonus,
    create_deposit_bonus,
    get_all_deposit_bonuses,
    deactivate_deposit_bonus,
    get_offer_usage_stats
)

logger = logging.getLogger(__name__)
router = Router()
DAMASCUS_TZ = pytz.timezone('Asia/Damascus')


class BonusStates(StatesGroup):
    waiting_bonus_name = State()
    waiting_bonus_percent = State()
    waiting_min_deposit = State()
    waiting_max_bonus = State()
    waiting_start_date = State()
    waiting_end_date = State()
    waiting_description = State()


# ============= القائمة الرئيسية =============
@router.callback_query(F.data == "offers_menu")
async def offers_menu(callback: types.CallbackQuery, db_pool):
    """قائمة مكافآت الإيداع"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    active_bonus = await get_active_deposit_bonus(db_pool)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="💰 مكافأة إيداع جديدة", callback_data="new_deposit_bonus")
    )
    builder.row(
        types.InlineKeyboardButton(text="📋 قائمة المكافآت", callback_data="list_deposit_bonuses")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin")
    )
    
    status_text = ""
    if active_bonus:
        end_date = active_bonus['end_date'].strftime('%Y-%m-%d %H:%M')
        min_deposit = active_bonus.get('min_deposit_amount', 0)
        max_bonus = active_bonus.get('max_bonus_amount', 0)
        status_text += f"💰 **مكافأة نشطة:** {active_bonus['bonus_percent']}% على الإيداع"
        if min_deposit:
            status_text += f"\n   📌 الحد الأدنى: {min_deposit:,.0f} ل.س"
        if max_bonus:
            status_text += f"\n   📌 الحد الأقصى للمكافأة: {max_bonus:,.0f} ل.س"
        status_text += f"\n   🕐 تنتهي في: {end_date}\n"
    else:
        status_text += "💰 **لا توجد مكافأة إيداع نشطة حالياً**\n"
    
    await callback.message.edit_text(
        f"💰 **نظام مكافآت الإيداع**\n\n"
        f"📊 **الحالة الحالية:**{status_text}\n\n"
        f"🔹 **مكافأة الإيداع:** نسبة إضافية على المبلغ المودع\n"
        f"🔹 يتم تطبيقها تلقائياً عند الموافقة على طلب الإيداع\n"
        f"🔹 تنطبق على جميع طرق الدفع (سيرياتل، شام كاش، USDT)\n\n"
        f"اختر الإجراء المطلوب:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= إنشاء مكافأة إيداع جديدة =============
@router.callback_query(F.data == "new_deposit_bonus")
async def new_deposit_bonus_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إنشاء مكافأة إيداع جديدة"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state(BonusStates.waiting_bonus_name)
    
    await callback.message.edit_text(
        "💰 **إنشاء مكافأة إيداع جديدة**\n\n"
        "📝 **أدخل اسم المكافأة:**\n"
        "(مثال: مكافأة الودائع 10%)\n"
        "🔹 هذا الاسم يظهر للمشرفين فقط للإدارة\n\n"
        "❌ للإلغاء أرسل /cancel",
        reply_markup=get_back_inline_keyboard("offers_menu"),
        parse_mode="Markdown"
    )


@router.message(BonusStates.waiting_bonus_name)
async def get_bonus_name(message: types.Message, state: FSMContext, db_pool):
    """استلام اسم المكافأة"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    name = message.text.strip()
    if len(name) < 3:
        await message.answer("⚠️ الاسم قصير جداً (3 أحرف على الأقل). حاول مرة أخرى:")
        return
    
    await state.update_data(bonus_name=name)
    await state.set_state(BonusStates.waiting_bonus_percent)
    
    await message.answer(
        "📊 **أدخل نسبة المكافأة:**\n"
        "(مثال: 10 يعني 10% من قيمة الإيداع)\n\n"
        "🔹 **ملاحظة:** تضاف تلقائياً عند الموافقة على طلب الإيداع\n"
        "🔹 تحسب كالتالي: المبلغ المودع × (النسبة / 100)",
        parse_mode="Markdown"
    )


@router.message(BonusStates.waiting_bonus_percent)
async def get_bonus_percent(message: types.Message, state: FSMContext, db_pool):
    """استلام نسبة المكافأة"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    try:
        percent = int(message.text.strip().replace('%', ''))
        if percent < 1 or percent > 100:
            raise ValueError
    except:
        await message.answer("⚠️ نسبة غير صحيحة. أدخل رقماً بين 1 و 100:")
        return
    
    await state.update_data(bonus_percent=percent)
    await state.set_state(BonusStates.waiting_min_deposit)
    
    await message.answer(
        "💰 **أدخل الحد الأدنى للإيداع (اختياري):**\n"
        "(مثال: 5000 يعني أقل إيداع للحصول على المكافأة)\n"
        "🔹 إذا كان المبلغ أقل من هذا الحد، لا يحصل المستخدم على مكافأة\n"
        "💡 اضغط /skip للتخطي (لا يوجد حد أدنى)",
        parse_mode="Markdown"
    )


@router.message(BonusStates.waiting_min_deposit)
async def get_min_deposit(message: types.Message, state: FSMContext, db_pool):
    """استلام الحد الأدنى للإيداع"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    if message.text.lower() == '/skip':
        min_deposit = None
    else:
        try:
            min_deposit = float(message.text.strip().replace(',', ''))
            if min_deposit <= 0:
                raise ValueError
        except:
            await message.answer("⚠️ قيمة غير صحيحة. أدخل رقماً موجباً أو /skip:")
            return
    
    await state.update_data(min_deposit=min_deposit)
    await state.set_state(BonusStates.waiting_max_bonus)
    
    await message.answer(
        "💰 **أدخل الحد الأقصى للمكافأة (اختياري):**\n"
        "(مثال: 10000 يعني أقصى مكافأة 10,000 ل.س)\n"
        "🔹 إذا تجاوزت المكافأة هذا الحد، يتم تطبيق الحد الأقصى فقط\n"
        "💡 اضغط /skip للتخطي (لا يوجد حد أقصى)",
        parse_mode="Markdown"
    )


@router.message(BonusStates.waiting_max_bonus)
async def get_max_bonus(message: types.Message, state: FSMContext, db_pool):
    """استلام الحد الأقصى للمكافأة"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    if message.text.lower() == '/skip':
        max_bonus = None
    else:
        try:
            max_bonus = float(message.text.strip().replace(',', ''))
            if max_bonus <= 0:
                raise ValueError
        except:
            await message.answer("⚠️ قيمة غير صحيحة. أدخل رقماً موجباً أو /skip:")
            return
    
    await state.update_data(max_bonus=max_bonus)
    await state.set_state(BonusStates.waiting_start_date)
    
    now = get_damascus_time_now()
    default_start = now.strftime('%Y-%m-%d %H:%M')
    default_end = (now + timedelta(days=30)).strftime('%Y-%m-%d %H:%M')
    
    await message.answer(
        f"📅 **أدخل تاريخ بدء المكافأة:**\n"
        f"(صيغة: YYYY-MM-DD HH:MM)\n\n"
        f"⏰ **الوقت الحالي:** {now.strftime('%Y-%m-%d %H:%M')}\n"
        f"📌 **مثال:** {default_start}\n\n"
        f"💡 اضغط /skip لاستخدام {default_start}",
        parse_mode="Markdown"
    )


@router.message(BonusStates.waiting_start_date)
async def get_bonus_start_date(message: types.Message, state: FSMContext, db_pool):
    """استلام تاريخ البداية للمكافأة"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    if message.text.lower() == '/skip':
        start_date = get_damascus_time_now()
    else:
        try:
            start_date = datetime.strptime(message.text.strip(), '%Y-%m-%d %H:%M')
            start_date = DAMASCUS_TZ.localize(start_date)
        except:
            await message.answer("⚠️ صيغة غير صحيحة. استخدم: YYYY-MM-DD HH:MM\nأو /skip للاستخدام التلقائي:")
            return
    
    await state.update_data(start_date=start_date)
    await state.set_state(BonusStates.waiting_end_date)
    
    default_end = (start_date + timedelta(days=30)).strftime('%Y-%m-%d %H:%M')
    
    await message.answer(
        f"📅 **أدخل تاريخ انتهاء المكافأة:**\n"
        f"(صيغة: YYYY-MM-DD HH:MM)\n\n"
        f"📌 **مثال:** {default_end}\n"
        f"💡 اضغط /skip لاستخدام {default_end}",
        parse_mode="Markdown"
    )


@router.message(BonusStates.waiting_end_date)
async def get_bonus_end_date(message: types.Message, state: FSMContext, db_pool):
    """استلام تاريخ النهاية وإنشاء المكافأة"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    data = await state.get_data()
    
    if message.text.lower() == '/skip':
        end_date = data['start_date'] + timedelta(days=30)
    else:
        try:
            end_date = datetime.strptime(message.text.strip(), '%Y-%m-%d %H:%M')
            end_date = DAMASCUS_TZ.localize(end_date)
        except:
            await message.answer("⚠️ صيغة غير صحيحة. استخدم: YYYY-MM-DD HH:MM\nأو /skip للاستخدام التلقائي:")
            return
    
    if end_date <= data['start_date']:
        await message.answer("⚠️ تاريخ النهاية يجب أن يكون بعد تاريخ البداية!")
        return
    
    await state.update_data(end_date=end_date)
    await state.set_state(BonusStates.waiting_description)
    
    await message.answer(
        "📝 **أدخل وصف للمكافأة (اختياري):**\n"
        "(يمكنك تركها فارغة بالضغط /skip)\n"
        "🔹 هذا الوصف يظهر للمشرفين فقط عند عرض التفاصيل",
        parse_mode="Markdown"
    )


@router.message(BonusStates.waiting_description)
async def get_bonus_description(message: types.Message, state: FSMContext, db_pool):
    """استلام الوصف وإنشاء المكافأة"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    data = await state.get_data()
    
    description = None if message.text.lower() == '/skip' else message.text.strip()
    
    bonus_id = await create_deposit_bonus(
        pool=db_pool,
        name=data['bonus_name'],
        bonus_percent=data['bonus_percent'],
        start_date=data['start_date'],
        end_date=data['end_date'],
        min_deposit_amount=data.get('min_deposit'),
        max_bonus_amount=data.get('max_bonus'),
        description=description,
        created_by=message.from_user.id
    )
    
    await state.clear()
    
    if bonus_id:
        text = f"✅ **تم إنشاء مكافأة الإيداع بنجاح!**\n\n"
        text += f"💰 **الاسم:** {data['bonus_name']}\n"
        text += f"📊 **النسبة:** {data['bonus_percent']}%\n"
        if data.get('min_deposit'):
            text += f"💰 **الحد الأدنى للإيداع:** {data['min_deposit']:,.0f} ل.س\n"
        if data.get('max_bonus'):
            text += f"💰 **الحد الأقصى للمكافأة:** {data['max_bonus']:,.0f} ل.س\n"
        text += f"📅 **من:** {data['start_date'].strftime('%Y-%m-%d %H:%M')}\n"
        text += f"📅 **إلى:** {data['end_date'].strftime('%Y-%m-%d %H:%M')}\n"
        text += f"📝 **الوصف:** {description or 'لا يوجد'}\n\n"
        text += f"🔹 **الآن كل إيداع مؤهل يحصل على {data['bonus_percent']}% إضافية!**\n"
        text += f"🔹 تنطبق على جميع طرق الدفع (سيرياتل، شام كاش، USDT)"
        
        await message.answer(text, reply_markup=get_back_inline_keyboard("offers_menu"), parse_mode="Markdown")
    else:
        await message.answer("❌ فشل إنشاء المكافأة", reply_markup=get_back_inline_keyboard("offers_menu"))


# ============= قائمة المكافآت =============
@router.callback_query(F.data == "list_deposit_bonuses")
async def list_deposit_bonuses(callback: types.CallbackQuery, db_pool):
    """عرض قائمة مكافآت الإيداع"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    bonuses = await get_all_deposit_bonuses(db_pool)
    
    if not bonuses:
        await callback.message.edit_text(
            "📋 **لا توجد مكافآت إيداع سابقة**\n\n"
            "يمكنك إنشاء مكافأة جديدة من القائمة الرئيسية.",
            reply_markup=get_back_inline_keyboard("offers_menu"),
            parse_mode="Markdown"
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    for bonus in bonuses:
        status = "🟢" if bonus['is_active'] else "🔴"
        end_date = bonus['end_date'].strftime('%Y-%m-%d')
        builder.row(types.InlineKeyboardButton(
            text=f"{status} {bonus['name']} - {bonus['bonus_percent']}% (حتى {end_date})",
            callback_data=f"view_bonus_{bonus['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="offers_menu"
    ))
    
    await callback.message.edit_text(
        f"📋 **قائمة مكافآت الإيداع**\n\n"
        f"🟢 نشطة | 🔴 منتهية\n\n"
        f"🔹 اضغط على أي مكافأة لعرض تفاصيلها أو إلغائها أو حذفها:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= عرض تفاصيل المكافأة =============
@router.callback_query(F.data.startswith("view_bonus_"))
async def view_bonus_details(callback: types.CallbackQuery, db_pool):
    """عرض تفاصيل مكافأة إيداع"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    bonus_id = int(callback.data.split("_")[2])
    
    async with db_pool.acquire() as conn:
        bonus = await conn.fetchrow("SELECT * FROM deposit_bonuses WHERE id = $1", bonus_id)
    
    if not bonus:
        await callback.answer("المكافأة غير موجودة", show_alert=True)
        return
    
    stats = await get_offer_usage_stats(db_pool, bonus_id, 'deposit')
    
    builder = InlineKeyboardBuilder()
    
    if bonus['is_active']:
        builder.row(types.InlineKeyboardButton(
            text="❌ إلغاء تنشيط المكافأة",
            callback_data=f"deactivate_bonus_{bonus_id}"
        ))
    else:
        builder.row(types.InlineKeyboardButton(
            text="🗑️ حذف المكافأة نهائياً",
            callback_data=f"delete_bonus_{bonus_id}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="list_deposit_bonuses"
    ))
    
    text = f"📋 **تفاصيل مكافأة الإيداع**\n\n"
    text += f"🔹 **الاسم:** {bonus['name']}\n"
    text += f"📊 **النسبة:** {bonus['bonus_percent']}%\n"
    if bonus.get('min_deposit_amount'):
        text += f"💰 **الحد الأدنى للإيداع:** {bonus['min_deposit_amount']:,.0f} ل.س\n"
    if bonus.get('max_bonus_amount'):
        text += f"💰 **الحد الأقصى للمكافأة:** {bonus['max_bonus_amount']:,.0f} ل.س\n"
    text += f"📅 **من:** {bonus['start_date'].strftime('%Y-%m-%d %H:%M')}\n"
    text += f"📅 **إلى:** {bonus['end_date'].strftime('%Y-%m-%d %H:%M')}\n"
    text += f"📊 **الحالة:** {'🟢 نشطة' if bonus['is_active'] else '🔴 منتهية'}\n"
    text += f"📈 **إحصائيات الاستخدام:**\n"
    text += f"   • عدد المستخدمين: {stats.get('unique_users', 0)}\n"
    text += f"   • إجمالي الاستخدامات: {stats.get('total_uses', 0)}\n"
    if bonus.get('description'):
        text += f"📝 **الوصف:** {bonus['description']}\n"
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


# ============= إلغاء تنشيط المكافأة =============
@router.callback_query(F.data.startswith("deactivate_bonus_"))
async def deactivate_bonus(callback: types.CallbackQuery, db_pool):
    """إلغاء تنشيط مكافأة إيداع"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    bonus_id = int(callback.data.split("_")[2])
    
    success = await deactivate_deposit_bonus(db_pool, bonus_id)
    
    if success:
        await callback.answer("✅ تم إلغاء التنشيط", show_alert=True)
        await callback.message.edit_text(
            f"✅ **تم إلغاء تنشيط المكافأة بنجاح**\n\n"
            f"🔹 لن يتم تطبيقها على الإيداعات الجديدة.\n"
            f"🔹 يمكنك حذفها نهائياً من خلال تفاصيل المكافأة.",
            reply_markup=get_back_inline_keyboard("list_deposit_bonuses"),
            parse_mode="Markdown"
        )
    else:
        await callback.answer("❌ فشل إلغاء التنشيط", show_alert=True)


# ============= حذف المكافأة نهائياً =============
@router.callback_query(F.data.startswith("delete_bonus_"))
async def delete_bonus(callback: types.CallbackQuery, db_pool):
    """بدء عملية حذف مكافأة إيداع"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    bonus_id = int(callback.data.split("_")[2])
    
    async with db_pool.acquire() as conn:
        bonus = await conn.fetchrow("SELECT * FROM deposit_bonuses WHERE id = $1", bonus_id)
    
    if not bonus:
        await callback.answer("المكافأة غير موجودة", show_alert=True)
        return
    
    stats = await get_offer_usage_stats(db_pool, bonus_id, 'deposit')
    
    builder = get_confirmation_keyboard(f"confirm_delete_bonus_{bonus_id}", f"view_bonus_{bonus_id}")
    
    text = f"⚠️ **تأكيد حذف مكافأة الإيداع نهائياً**\n\n"
    text += f"🔹 **الاسم:** {bonus['name']}\n"
    text += f"📊 **النسبة:** {bonus['bonus_percent']}%\n"
    text += f"📅 **الفترة:** {bonus['start_date'].strftime('%Y-%m-%d')} → {bonus['end_date'].strftime('%Y-%m-%d')}\n"
    text += f"📈 **إحصائيات الاستخدام:**\n"
    text += f"   • عدد المستخدمين الذين استفادوا: {stats.get('unique_users', 0)}\n"
    text += f"   • إجمالي مرات الاستخدام: {stats.get('total_uses', 0)}\n\n"
    text += f"⚠️ **هذا الإجراء لا يمكن التراجع عنه!**\n"
    text += f"سيتم حذف جميع سجلات استخدام هذه المكافأة نهائياً."
    
    await callback.message.edit_text(text, reply_markup=builder, parse_mode="Markdown")


@router.callback_query(F.data.startswith("confirm_delete_bonus_"))
async def confirm_delete_bonus(callback: types.CallbackQuery, db_pool):
    """تأكيد حذف المكافأة نهائياً"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    bonus_id = int(callback.data.split("_")[3])
    
    try:
        async with db_pool.acquire() as conn:
            # حذف سجلات الاستخدام أولاً
            await conn.execute(
                "DELETE FROM offer_usage WHERE offer_id = $1 AND offer_type = 'deposit'",
                bonus_id
            )
            # حذف المكافأة
            await conn.execute("DELETE FROM deposit_bonuses WHERE id = $1", bonus_id)
        
        await callback.answer("✅ تم الحذف بنجاح", show_alert=True)
        await callback.message.edit_text(
            f"✅ **تم حذف المكافأة نهائياً!**\n\n"
            f"🔹 تم حذف جميع سجلات الاستخدام المرتبطة بها.\n"
            f"🔹 لن تظهر في القائمة بعد الآن.",
            reply_markup=get_back_inline_keyboard("list_deposit_bonuses"),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ خطأ في حذف المكافأة: {e}")
        await callback.answer(f"❌ فشل الحذف: {str(e)}", show_alert=True)
