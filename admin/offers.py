# admin/offers.py
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from datetime import datetime, timedelta
import pytz

from database.users import is_admin_user
from database.offers import (
    get_active_global_offer, get_active_deposit_bonus,
    create_global_offer, create_deposit_bonus,
    get_all_offers, deactivate_offer,
    get_offer_usage_stats
)
from handlers.keyboards import get_back_inline_keyboard
from handlers.time_utils import get_damascus_time_now, format_damascus_time

logger = logging.getLogger(__name__)
router = Router()
DAMASCUS_TZ = pytz.timezone('Asia/Damascus')


class OfferStates(StatesGroup):
    waiting_offer_name = State()
    waiting_discount_percent = State()
    waiting_start_date = State()
    waiting_end_date = State()
    waiting_description = State()
    waiting_bonus_percent = State()
    waiting_min_deposit = State()
    waiting_max_bonus = State()


# ============= القائمة الرئيسية =============
@router.callback_query(F.data == "offers_menu")
async def offers_menu(callback: types.CallbackQuery, db_pool):
    """قائمة العروض والمكافآت"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    # جلب العرض النشط الحالي
    active_offer = await get_active_global_offer(db_pool)
    active_bonus = await get_active_deposit_bonus(db_pool)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🎁 عرض عام جديد", callback_data="new_global_offer"),
        types.InlineKeyboardButton(text="💰 مكافأة إيداع جديدة", callback_data="new_deposit_bonus")
    )
    builder.row(
        types.InlineKeyboardButton(text="📋 قائمة العروض", callback_data="list_global_offers"),
        types.InlineKeyboardButton(text="📋 قائمة المكافآت", callback_data="list_deposit_bonuses")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin")
    )
    
    status_text = ""
    if active_offer:
        end_date = active_offer['end_date'].strftime('%Y-%m-%d %H:%M')
        status_text += f"\n🎁 **عرض نشط:** {active_offer['discount_percent']}% خصم\n   حتى {end_date}\n"
    else:
        status_text += "\n🎁 **لا يوجد عرض نشط حالياً**\n"
    
    if active_bonus:
        end_date = active_bonus['end_date'].strftime('%Y-%m-%d %H:%M')
        min_deposit = active_bonus.get('min_deposit_amount', 0)
        status_text += f"💰 **مكافأة نشطة:** {active_bonus['bonus_percent']}% على الإيداع"
        if min_deposit:
            status_text += f" (حد أدنى {min_deposit:,.0f} ل.س)"
        status_text += f"\n   حتى {end_date}\n"
    else:
        status_text += "💰 **لا توجد مكافأة إيداع نشطة حالياً**\n"
    
    await callback.message.edit_text(
        f"🎁 **نظام العروض والمكافآت**\n\n"
        f"📊 **الحالة الحالية:**{status_text}\n\n"
        f"🔹 **العرض العام:** خصم على جميع المنتجات والخيارات\n"
        f"🔹 **مكافأة الإيداع:** نسبة إضافية على المبلغ المودع\n\n"
        f"اختر الإجراء المطلوب:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= إنشاء عرض عام =============
@router.callback_query(F.data == "new_global_offer")
async def new_global_offer_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إنشاء عرض عام جديد"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state(OfferStates.waiting_offer_name)
    
    await callback.message.edit_text(
        "🎁 **إنشاء عرض عام جديد**\n\n"
        "📝 **أدخل اسم العرض:**\n"
        "(مثال: عرض الربيع 20%)\n\n"
        "❌ للإلغاء أرسل /cancel",
        reply_markup=get_back_inline_keyboard("offers_menu"),
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_offer_name)
async def get_offer_name(message: types.Message, state: FSMContext, db_pool):
    """استلام اسم العرض"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    name = message.text.strip()
    if len(name) < 3:
        await message.answer("⚠️ الاسم قصير جداً (3 أحرف على الأقل). حاول مرة أخرى:")
        return
    
    await state.update_data(offer_name=name)
    await state.set_state(OfferStates.waiting_discount_percent)
    
    await message.answer(
        "📊 **أدخل نسبة الخصم:**\n"
        "(مثال: 20 يعني 20% خصم)\n\n"
        "🔹 **ملاحظة:** الخصم يطبق على جميع المنتجات والخيارات",
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_discount_percent)
async def get_offer_discount(message: types.Message, state: FSMContext, db_pool):
    """استلام نسبة الخصم"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    try:
        discount = int(message.text.strip().replace('%', ''))
        if discount < 1 or discount > 100:
            raise ValueError
    except:
        await message.answer("⚠️ نسبة غير صحيحة. أدخل رقماً بين 1 و 100:")
        return
    
    await state.update_data(discount_percent=discount)
    await state.set_state(OfferStates.waiting_start_date)
    
    now = get_damascus_time_now()
    default_start = now.strftime('%Y-%m-%d %H:%M')
    default_end = (now + timedelta(days=7)).strftime('%Y-%m-%d %H:%M')
    
    await message.answer(
        f"📅 **أدخل تاريخ بدء العرض:**\n"
        f"(صيغة: YYYY-MM-DD HH:MM)\n\n"
        f"⏰ **الوقت الحالي:** {now.strftime('%Y-%m-%d %H:%M')}\n"
        f"📌 **مثال:** {default_start}\n\n"
        f"💡 اضغط /skip لاستخدام {default_start}",
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_start_date)
async def get_offer_start_date(message: types.Message, state: FSMContext, db_pool):
    """استلام تاريخ البداية"""
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
    await state.set_state(OfferStates.waiting_end_date)
    
    default_end = (start_date + timedelta(days=7)).strftime('%Y-%m-%d %H:%M')
    
    await message.answer(
        f"📅 **أدخل تاريخ انتهاء العرض:**\n"
        f"(صيغة: YYYY-MM-DD HH:MM)\n\n"
        f"📌 **مثال:** {default_end}\n"
        f"💡 اضغط /skip لاستخدام {default_end}",
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_end_date)
async def get_offer_end_date(message: types.Message, state: FSMContext, db_pool):
    """استلام تاريخ النهاية"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    data = await state.get_data()
    
    if message.text.lower() == '/skip':
        end_date = data['start_date'] + timedelta(days=7)
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
    await state.set_state(OfferStates.waiting_description)
    
    await message.answer(
        "📝 **أدخل وصف للعرض (اختياري):**\n"
        "(يمكنك تركها فارغة بالضغط /skip)",
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_description)
async def get_offer_description(message: types.Message, state: FSMContext, db_pool):
    """استلام الوصف وإنشاء العرض"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    data = await state.get_data()
    
    description = None if message.text.lower() == '/skip' else message.text.strip()
    
    offer_id = await create_global_offer(
        pool=db_pool,
        name=data['offer_name'],
        discount_percent=data['discount_percent'],
        start_date=data['start_date'],
        end_date=data['end_date'],
        description=description,
        created_by=message.from_user.id
    )
    
    await state.clear()
    
    if offer_id:
        await message.answer(
            f"✅ **تم إنشاء العرض العام بنجاح!**\n\n"
            f"🎁 **الاسم:** {data['offer_name']}\n"
            f"📊 **الخصم:** {data['discount_percent']}%\n"
            f"📅 **من:** {data['start_date'].strftime('%Y-%m-%d %H:%M')}\n"
            f"📅 **إلى:** {data['end_date'].strftime('%Y-%m-%d %H:%M')}\n"
            f"📝 **الوصف:** {description or 'لا يوجد'}\n\n"
            f"🔹 **الآن جميع المنتجات والخيارات تحصل على خصم {data['discount_percent']}%**",
            reply_markup=get_back_inline_keyboard("offers_menu"),
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ فشل إنشاء العرض", reply_markup=get_back_inline_keyboard("offers_menu"))


# ============= إنشاء مكافأة إيداع =============
@router.callback_query(F.data == "new_deposit_bonus")
async def new_deposit_bonus_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إنشاء مكافأة إيداع جديدة"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    await state.set_state(OfferStates.waiting_offer_name)
    
    await callback.message.edit_text(
        "💰 **إنشاء مكافأة إيداع جديدة**\n\n"
        "📝 **أدخل اسم المكافأة:**\n"
        "(مثال: مكافأة الودائع 10%)\n\n"
        "❌ للإلغاء أرسل /cancel",
        reply_markup=get_back_inline_keyboard("offers_menu"),
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_offer_name)
async def get_bonus_name(message: types.Message, state: FSMContext, db_pool):
    """استلام اسم المكافأة"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    await state.update_data(bonus_name=message.text.strip())
    await state.set_state(OfferStates.waiting_bonus_percent)
    
    await message.answer(
        "📊 **أدخل نسبة المكافأة:**\n"
        "(مثال: 10 يعني 10% من قيمة الإيداع)\n\n"
        "🔹 **ملاحظة:** تضاف تلقائياً عند الموافقة على طلب الإيداع",
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_bonus_percent)
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
    await state.set_state(OfferStates.waiting_min_deposit)
    
    await message.answer(
        "💰 **أدخل الحد الأدنى للإيداع (اختياري):**\n"
        "(مثال: 5000 يعني أقل إيداع للحصول على المكافأة)\n"
        "💡 اضغط /skip للتخطي (لا يوجد حد أدنى)",
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_min_deposit)
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
    await state.set_state(OfferStates.waiting_max_bonus)
    
    await message.answer(
        "💰 **أدخل الحد الأقصى للمكافأة (اختياري):**\n"
        "(مثال: 10000 يعني أقصى مكافأة 10,000 ل.س)\n"
        "💡 اضغط /skip للتخطي (لا يوجد حد أقصى)",
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_max_bonus)
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
    await state.set_state(OfferStates.waiting_start_date)
    
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


@router.message(OfferStates.waiting_start_date)
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
    await state.set_state(OfferStates.waiting_end_date)
    
    default_end = (start_date + timedelta(days=30)).strftime('%Y-%m-%d %H:%M')
    
    await message.answer(
        f"📅 **أدخل تاريخ انتهاء المكافأة:**\n"
        f"(صيغة: YYYY-MM-DD HH:MM)\n\n"
        f"📌 **مثال:** {default_end}\n"
        f"💡 اضغط /skip لاستخدام {default_end}",
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_end_date)
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
    await state.set_state(OfferStates.waiting_description)
    
    await message.answer(
        "📝 **أدخل وصف للمكافأة (اختياري):**\n"
        "(يمكنك تركها فارغة بالضغط /skip)",
        parse_mode="Markdown"
    )


@router.message(OfferStates.waiting_description)
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
        text += f"🔹 **الآن كل إيداع مؤهل يحصل على {data['bonus_percent']}% إضافية!**"
        
        await message.answer(text, reply_markup=get_back_inline_keyboard("offers_menu"), parse_mode="Markdown")
    else:
        await message.answer("❌ فشل إنشاء المكافأة", reply_markup=get_back_inline_keyboard("offers_menu"))


# ============= قائمة العروض والمكافآت =============
@router.callback_query(F.data == "list_global_offers")
async def list_global_offers(callback: types.CallbackQuery, db_pool):
    """عرض قائمة العروض العامة"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    offers = await get_all_offers(db_pool, 'global')
    
    if not offers:
        await callback.message.edit_text(
            "📋 **لا توجد عروض عامة سابقة**\n\n"
            "يمكنك إنشاء عرض جديد من القائمة الرئيسية.",
            reply_markup=get_back_inline_keyboard("offers_menu"),
            parse_mode="Markdown"
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    for offer in offers[:10]:
        status = "🟢" if offer['is_active'] else "🔴"
        end_date = offer['end_date'].strftime('%Y-%m-%d')
        builder.row(types.InlineKeyboardButton(
            text=f"{status} {offer['name']} - {offer['discount_percent']}% (حتى {end_date})",
            callback_data=f"view_offer_{offer['id']}_global"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="offers_menu"
    ))
    
    await callback.message.edit_text(
        f"📋 **قائمة العروض العامة**\n\n"
        f"🟢 نشط | 🔴 منتهي\n\n"
        f"🔹 اضغط على أي عرض لعرض تفاصيله أو إلغائه:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "list_deposit_bonuses")
async def list_deposit_bonuses(callback: types.CallbackQuery, db_pool):
    """عرض قائمة مكافآت الإيداع"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    bonuses = await get_all_offers(db_pool, 'deposit')
    
    if not bonuses:
        await callback.message.edit_text(
            "📋 **لا توجد مكافآت إيداع سابقة**\n\n"
            "يمكنك إنشاء مكافأة جديدة من القائمة الرئيسية.",
            reply_markup=get_back_inline_keyboard("offers_menu"),
            parse_mode="Markdown"
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    for bonus in bonuses[:10]:
        status = "🟢" if bonus['is_active'] else "🔴"
        end_date = bonus['end_date'].strftime('%Y-%m-%d')
        builder.row(types.InlineKeyboardButton(
            text=f"{status} {bonus['name']} - {bonus['bonus_percent']}% (حتى {end_date})",
            callback_data=f"view_offer_{bonus['id']}_deposit"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="offers_menu"
    ))
    
    await callback.message.edit_text(
        f"📋 **قائمة مكافآت الإيداع**\n\n"
        f"🟢 نشط | 🔴 منتهي\n\n"
        f"🔹 اضغط على أي مكافأة لعرض تفاصيلها أو إلغائها:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= عرض تفاصيل العرض/المكافأة =============
@router.callback_query(F.data.startswith("view_offer_"))
async def view_offer_details(callback: types.CallbackQuery, db_pool):
    """عرض تفاصيل عرض/مكافأة"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    parts = callback.data.split("_")
    offer_id = int(parts[2])
    offer_type = parts[3]
    
    async with db_pool.acquire() as conn:
        table = 'global_offers' if offer_type == 'global' else 'deposit_bonuses'
        offer = await conn.fetchrow(f"SELECT * FROM {table} WHERE id = $1", offer_id)
    
    if not offer:
        await callback.answer("العرض غير موجود", show_alert=True)
        return
    
    # جلب إحصائيات الاستخدام
    stats = await get_offer_usage_stats(db_pool, offer_id, offer_type)
    
    builder = InlineKeyboardBuilder()
    
    if offer['is_active']:
        builder.row(types.InlineKeyboardButton(
            text="❌ إلغاء تنشيط العرض",
            callback_data=f"deactivate_offer_{offer_id}_{offer_type}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data=f"list_{offer_type}_offers" if offer_type == 'global' else "list_deposit_bonuses"
    ))
    
    text = f"📋 **تفاصيل {'العرض' if offer_type == 'global' else 'المكافأة'}**\n\n"
    text += f"🔹 **الاسم:** {offer['name']}\n"
    
    if offer_type == 'global':
        text += f"📊 **الخصم:** {offer['discount_percent']}%\n"
    else:
        text += f"📊 **النسبة:** {offer['bonus_percent']}%\n"
        if offer.get('min_deposit_amount'):
            text += f"💰 **الحد الأدنى للإيداع:** {offer['min_deposit_amount']:,.0f} ل.س\n"
        if offer.get('max_bonus_amount'):
            text += f"💰 **الحد الأقصى للمكافأة:** {offer['max_bonus_amount']:,.0f} ل.س\n"
    
    text += f"📅 **من:** {offer['start_date'].strftime('%Y-%m-%d %H:%M')}\n"
    text += f"📅 **إلى:** {offer['end_date'].strftime('%Y-%m-%d %H:%M')}\n"
    text += f"📊 **الحالة:** {'🟢 نشط' if offer['is_active'] else '🔴 منتهي'}\n"
    text += f"📈 **إحصائيات الاستخدام:**\n"
    text += f"   • عدد المستخدمين: {stats.get('unique_users', 0)}\n"
    text += f"   • إجمالي الاستخدامات: {stats.get('total_uses', 0)}\n"
    if offer.get('description'):
        text += f"📝 **الوصف:** {offer['description']}\n"
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


# ============= إلغاء تنشيط العرض/المكافأة =============
@router.callback_query(F.data.startswith("deactivate_offer_"))
async def deactivate_offer(callback: types.CallbackQuery, db_pool):
    """إلغاء تنشيط عرض/مكافأة"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    parts = callback.data.split("_")
    offer_id = int(parts[2])
    offer_type = parts[3]
    
    success = await deactivate_offer(db_pool, offer_id, offer_type)
    
    if success:
        await callback.answer("✅ تم إلغاء التنشيط", show_alert=True)
        await callback.message.edit_text(
            f"✅ **تم إلغاء تنشيط {'العرض' if offer_type == 'global' else 'المكافأة'} بنجاح**\n\n"
            f"🔹 لن يتم تطبيقه على الطلبات الجديدة.",
            reply_markup=get_back_inline_keyboard(f"list_{offer_type}_offers" if offer_type == 'global' else "list_deposit_bonuses"),
            parse_mode="Markdown"
        )
    else:
        await callback.answer("❌ فشل إلغاء التنشيط", show_alert=True)
