# admin/option_profits.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging

from database.users import is_admin_user
from database.products import (
    get_product_options, get_product_option,
    update_option_profit, update_option_original_price
)
from handlers.keyboards import get_back_inline_keyboard
from database.core import get_exchange_rate

logger = logging.getLogger(__name__)
router = Router()


class OptionProfitStates(StatesGroup):
    waiting_profit = State()
    waiting_original_price = State()


# ============= القائمة الرئيسية =============
@router.callback_query(F.data == "manage_option_profits")
async def manage_option_profits_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إدارة نسب الربح للخيارات"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.answer()
    
    # جلب جميع التطبيقات التي لها خيارات
    async with db_pool.acquire() as conn:
        apps = await conn.fetch('''
            SELECT DISTINCT a.id, a.name, a.profit_percentage as app_profit
            FROM applications a
            JOIN product_options po ON a.id = po.product_id
            ORDER BY a.name
        ''')
    
    if not apps:
        await callback.message.edit_text(
            "⚠️ لا توجد خيارات في النظام. قم بإضافة خيارات للتطبيقات أولاً.",
            reply_markup=get_back_inline_keyboard("back_to_admin")
        )
        return
    
    builder = InlineKeyboardBuilder()
    for app in apps:
        builder.row(types.InlineKeyboardButton(
            text=f"📱 {app['name']} (نسبة ربح التطبيق: {app['app_profit']}%)",
            callback_data=f"show_app_options_{app['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="back_to_admin"
    ))
    
    await callback.message.edit_text(
        "📊 **إدارة نسب الربح للخيارات**\n\n"
        "🔹 **ما هذا؟**\n"
        "يمكنك تحديد نسبة ربح مختلفة لكل خيار (مثل: متابعين عادي، متابعين جودة عالية)\n\n"
        "🔹 **كيف يعمل؟**\n"
        "• نسبة الربح المحددة للخيار تضاف على سعر المورد\n"
        "• إذا لم تحدد نسبة، تستخدم نسبة التطبيق الأساسية\n\n"
        "🔽 **اختر التطبيق:**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= عرض خيارات التطبيق =============
@router.callback_query(F.data.startswith("show_app_options_"))
async def show_app_options(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض خيارات التطبيق مع نسب الربح الحالية"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    app_id = int(callback.data.split("_")[3])
    
    async with db_pool.acquire() as conn:
        app = await conn.fetchrow(
            "SELECT id, name, profit_percentage FROM applications WHERE id = $1",
            app_id
        )
        
        options = await conn.fetch('''
            SELECT po.*, a.profit_percentage as app_profit
            FROM product_options po
            JOIN applications a ON po.product_id = a.id
            WHERE po.product_id = $1
            ORDER BY po.sort_order, po.price_usd
        ''', app_id)
    
    if not options:
        await callback.message.edit_text(
            f"⚠️ لا توجد خيارات للتطبيق {app['name']}",
            reply_markup=get_back_inline_keyboard("manage_option_profits")
        )
        return
    
    builder = InlineKeyboardBuilder()
    
    purchase_rate = await get_exchange_rate(db_pool, 'purchase')
    
    for opt in options:
        opt_profit = opt.get('profit_percentage', 0)
        app_profit = opt.get('app_profit', 0)
        opt_price = float(opt['price_usd'])
        
        if opt_profit:
            final_price = opt_price * (1 + opt_profit / 100)
            status = f"🔹 {opt_profit}% (خاص)"
        else:
            final_price = opt_price * (1 + app_profit / 100)
            status = f"🔸 {app_profit}% (من التطبيق)"
        
        final_price_syp = final_price * purchase_rate
        
        builder.row(types.InlineKeyboardButton(
            text=f"{opt['name']} - {status} - {final_price_syp:,.0f} ل.س",
            callback_data=f"edit_option_profit_{opt['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data="manage_option_profits"
    ))
    
    await callback.message.edit_text(
        f"📱 **التطبيق: {app['name']}**\n"
        f"📊 **نسبة ربح التطبيق الأساسية:** {app['profit_percentage']}%\n"
        f"💰 **سعر الشراء الحالي:** {purchase_rate:,.0f} ل.س = 1$\n\n"
        f"🔹 **الخيارات:**\n"
        f"• 🔹 خاص: نسبة ربح مخصصة لهذا الخيار\n"
        f"• 🔸 من التطبيق: يستخدم نسبة التطبيق الأساسية\n\n"
        f"🔽 **اختر الخيار لتعديل نسبة ربحه أو سعر المورد:**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= تعديل نسبة ربح الخيار =============
@router.callback_query(F.data.startswith("edit_option_profit_"))
async def edit_option_profit(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """تعديل نسبة ربح خيار معين"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    option_id = int(callback.data.split("_")[3])
    
    option = await get_product_option(db_pool, option_id)
    
    if not option:
        await callback.answer("الخيار غير موجود", show_alert=True)
        return
    
    await state.update_data(option_id=option_id, option_name=option['name'], product_id=option['product_id'])
    await state.set_state(OptionProfitStates.waiting_profit)
    
    current_profit = option.get('profit_percentage', 0)
    app_profit = option.get('app_profit_percentage', 0)
    current_price = option.get('price_usd', 0)
    original_price = option.get('original_price_usd', current_price)
    
    # حساب السعر الحالي
    if current_profit:
        final_price = original_price * (1 + current_profit / 100)
    else:
        final_price = original_price * (1 + app_profit / 100)
    
    purchase_rate = await get_exchange_rate(db_pool, 'purchase')
    final_price_syp = final_price * purchase_rate
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="💰 تعديل سعر المورد الأصلي",
        callback_data=f"edit_original_price_{option_id}"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🗑️ حذف النسبة الخاصة (استخدام نسبة التطبيق)",
        callback_data=f"clear_option_profit_{option_id}"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع",
        callback_data=f"show_app_options_{option['product_id']}"
    ))
    
    await callback.message.edit_text(
        f"📦 **الخيار:** {option['name']}\n"
        f"💰 **سعر المورد الأصلي:** ${original_price:.2f}\n"
        f"📊 **نسبة ربح التطبيق:** {app_profit}%\n"
        f"🔹 **نسبة الربح الحالية للخيار:** {current_profit if current_profit else 'غير محددة (يستخدم نسبة التطبيق)'}\n\n"
        f"💰 **السعر النهائي الحالي:** ${final_price:.2f} ({final_price_syp:,.0f} ل.س)\n\n"
        f"✏️ **أدخل نسبة الربح الجديدة لهذا الخيار (0-100):**\n"
        f"(مثال: 15 يعني 15% ربح)\n\n"
        f"💡 **ملاحظة:** إذا أدخلت 0، سيتم استخدام نسبة التطبيق\n\n"
        f"❌ للإلغاء أرسل /cancel",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


@router.message(OptionProfitStates.waiting_profit)
async def save_option_profit(message: types.Message, state: FSMContext, db_pool):
    """حفظ نسبة الربح الجديدة للخيار"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    try:
        profit = float(message.text.replace('%', '').strip())
        if profit < 0 or profit > 100:
            raise ValueError
    except:
        await message.answer(
            "❌ **خطأ:** الرجاء إدخال نسبة صحيحة بين 0 و 100.\n"
            "مثال: 15 (يعني 15% ربح)\n\n"
            "أو أرسل 0 لاستخدام نسبة التطبيق",
            parse_mode="Markdown"
        )
        return
    
    data = await state.get_data()
    option_id = data.get('option_id')
    option_name = data.get('option_name')
    product_id = data.get('product_id')
    
    if profit == 0:
        await update_option_profit(db_pool, option_id, None)
        profit_text = "سيتم استخدام نسبة ربح التطبيق الأساسية"
    else:
        await update_option_profit(db_pool, option_id, profit)
        profit_text = f"{profit}% (خاص بالخيار)"
    
    await state.clear()
    
    # جلب معلومات محدثة
    option = await get_product_option(db_pool, option_id)
    app_profit = option.get('app_profit_percentage', 0)
    original_price = option.get('original_price_usd', option.get('price_usd', 0))
    
    if profit > 0:
        final_price = original_price * (1 + profit / 100)
    else:
        final_price = original_price * (1 + app_profit / 100)
    
    purchase_rate = await get_exchange_rate(db_pool, 'purchase')
    final_price_syp = final_price * purchase_rate
    
    await message.answer(
        f"✅ **تم تحديث نسبة الربح للخيار بنجاح!**\n\n"
        f"📦 **الخيار:** {option_name}\n"
        f"💰 **سعر المورد:** ${original_price:.2f}\n"
        f"📊 **نسبة الربح الجديدة:** {profit_text}\n"
        f"💰 **السعر النهائي:** ${final_price:.2f} ({final_price_syp:,.0f} ل.س)\n\n"
        f"🔹 يمكنك تعديل أي خيار آخر من القائمة.",
        reply_markup=get_back_inline_keyboard(f"show_app_options_{product_id}"),
        parse_mode="Markdown"
    )


# ============= حذف النسبة الخاصة =============
@router.callback_query(F.data.startswith("clear_option_profit_"))
async def clear_option_profit(callback: types.CallbackQuery, db_pool):
    """حذف نسبة الربح الخاصة واستخدام نسبة التطبيق"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    option_id = int(callback.data.split("_")[3])
    
    await update_option_profit(db_pool, option_id, None)
    
    option = await get_product_option(db_pool, option_id)
    app_profit = option.get('app_profit_percentage', 0)
    original_price = option.get('original_price_usd', option.get('price_usd', 0))
    final_price = original_price * (1 + app_profit / 100)
    
    purchase_rate = await get_exchange_rate(db_pool, 'purchase')
    final_price_syp = final_price * purchase_rate
    
    await callback.answer("✅ تم حذف النسبة الخاصة، سيتم استخدام نسبة التطبيق")
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔙 رجوع للخيارات",
        callback_data=f"show_app_options_{option['product_id']}"
    ))
    
    await callback.message.edit_text(
        f"✅ **تم حذف نسبة الربح الخاصة للخيار**\n\n"
        f"📦 **الخيار:** {option['name']}\n"
        f"📊 **سيتم الآن استخدام نسبة ربح التطبيق:** {app_profit}%\n"
        f"💰 **السعر النهائي:** ${final_price:.2f} ({final_price_syp:,.0f} ل.س)",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )


# ============= تعديل سعر المورد الأصلي =============
@router.callback_query(F.data.startswith("edit_original_price_"))
async def edit_original_price(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """تعديل سعر المورد الأصلي للخيار"""
    if not await is_admin_user(db_pool, callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    option_id = int(callback.data.split("_")[3])
    
    option = await get_product_option(db_pool, option_id)
    
    if not option:
        await callback.answer("الخيار غير موجود", show_alert=True)
        return
    
    await state.update_data(option_id=option_id, option_name=option['name'], product_id=option['product_id'])
    await state.set_state(OptionProfitStates.waiting_original_price)
    
    current_original = option.get('original_price_usd', option.get('price_usd', 0))
    
    await callback.message.edit_text(
        f"💰 **تعديل سعر المورد الأصلي للخيار**\n\n"
        f"📦 **الخيار:** {option['name']}\n"
        f"💰 **السعر الحالي للمورد:** ${current_original:.2f}\n\n"
        f"✏️ **أدخل السعر الجديد للمورد (بالدولار):**\n"
        f"(مثال: 5.50)\n\n"
        f"⚠️ **ملاحظة:** هذا هو السعر الذي تشتري به الخدمة من المورد\n"
        f"❌ للإلغاء أرسل /cancel",
        parse_mode="Markdown"
    )


@router.message(OptionProfitStates.waiting_original_price)
async def save_original_price(message: types.Message, state: FSMContext, db_pool):
    """حفظ سعر المورد الأصلي الجديد"""
    if not await is_admin_user(db_pool, message.from_user.id):
        return
    
    try:
        new_price = float(message.text.strip().replace(',', ''))
        if new_price <= 0:
            raise ValueError
    except:
        await message.answer(
            "❌ **خطأ:** الرجاء إدخال سعر صحيح أكبر من 0.\n"
            "مثال: 5.50",
            parse_mode="Markdown"
        )
        return
    
    data = await state.get_data()
    option_id = data.get('option_id')
    option_name = data.get('option_name')
    product_id = data.get('product_id')
    
    await update_option_original_price(db_pool, option_id, new_price)
    
    await state.clear()
    
    # جلب معلومات محدثة
    option = await get_product_option(db_pool, option_id)
    profit = option.get('profit_percentage', 0)
    app_profit = option.get('app_profit_percentage', 0)
    
    if profit:
        final_price = new_price * (1 + profit / 100)
    else:
        final_price = new_price * (1 + app_profit / 100)
    
    purchase_rate = await get_exchange_rate(db_pool, 'purchase')
    final_price_syp = final_price * purchase_rate
    
    await message.answer(
        f"✅ **تم تحديث سعر المورد للخيار بنجاح!**\n\n"
        f"📦 **الخيار:** {option_name}\n"
        f"💰 **سعر المورد الجديد:** ${new_price:.2f}\n"
        f"💰 **السعر النهائي:** ${final_price:.2f} ({final_price_syp:,.0f} ل.س)\n\n"
        f"🔹 يمكنك تعديل أي خيار آخر من القائمة.",
        reply_markup=get_back_inline_keyboard(f"show_app_options_{product_id}"),
        parse_mode="Markdown"
                          )
