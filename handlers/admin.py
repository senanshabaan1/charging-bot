# handlers/admin.py
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_ID, MODERATORS, USD_TO_SYP, DEPOSIT_GROUP, ORDERS_GROUP
import config
from datetime import datetime
import asyncio
import logging
from aiogram.utils.keyboard import InlineKeyboardBuilder
from handlers.deposit import get_damascus_time

# إعداد logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

class AdminStates(StatesGroup):
    waiting_new_rate = State()
    waiting_broadcast_msg = State()
    waiting_user_id = State()
    waiting_balance_amount = State()
    waiting_user_info = State()
    waiting_maintenance_msg = State()
    waiting_points_settings = State()
    waiting_points_amount = State()
    waiting_redeem_action = State()
    waiting_redeem_notes = State()
    # حالات جديدة
    waiting_product_name = State()
    waiting_product_price = State()
    waiting_product_min = State()
    waiting_product_profit = State()
    waiting_product_category = State()
    waiting_product_id = State()
    waiting_new_syriatel_numbers = State()
    waiting_reset_confirm = State()
    waiting_reset_rate = State()

def is_admin(user_id):
    return user_id == ADMIN_ID or user_id in MODERATORS

@router.message(Command("admin"))
async def admin_panel(message: types.Message, db_pool):
    if not is_admin(message.from_user.id):
        return

    from database import get_bot_status
    bot_status = await get_bot_status(db_pool)
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"

    kb = [
        # الصف الأول
        [
            types.InlineKeyboardButton(text="📈 سعر الصرف", callback_data="edit_rate"),
            types.InlineKeyboardButton(text="📊 الإحصائيات", callback_data="bot_stats")
        ],
        # الصف الثاني
        [
            types.InlineKeyboardButton(text="📢 رسالة للكل", callback_data="broadcast"),
            types.InlineKeyboardButton(text="👤 معلومات مستخدم", callback_data="user_info")
        ],
        # الصف الثالث
        [
            types.InlineKeyboardButton(text="💰 إضافة رصيد", callback_data="add_balance"),
            types.InlineKeyboardButton(text="⭐ إدارة النقاط", callback_data="manage_points")
        ],
        # الصف الرابع - إحصائيات المستخدمين
        [
            types.InlineKeyboardButton(text="💳 الأكثر إيداعاً", callback_data="top_deposits"),
            types.InlineKeyboardButton(text="🛒 الأكثر طلبات", callback_data="top_orders")
        ],
        # الصف الخامس
        [
            types.InlineKeyboardButton(text="🔗 الأكثر إحالة", callback_data="top_referrals"),
            types.InlineKeyboardButton(text="⭐ الأكثر نقاط", callback_data="top_points")
        ],
        # الصف السادس
        [
            types.InlineKeyboardButton(text="👥 إحصائيات VIP", callback_data="vip_stats")
        ],
        # الصف السابع - أزرار المنتجات
        [
            types.InlineKeyboardButton(text="➕ إضافة منتج", callback_data="add_product"),
            types.InlineKeyboardButton(text="✏️ تعديل منتج", callback_data="edit_product")
        ],
        # الصف الثامن
        [
            types.InlineKeyboardButton(text="🗑️ حذف منتج", callback_data="delete_product"),
            types.InlineKeyboardButton(text="📱 عرض المنتجات", callback_data="list_products")
        ],
        # الصف التاسع - أزرار سيرياتل
        [
            types.InlineKeyboardButton(text="📞 أرقام سيرياتل", callback_data="edit_syriatel"),
            types.InlineKeyboardButton(text="🔄 تشغيل/إيقاف", callback_data="toggle_bot")
        ],
        # الصف العاشر - زر التصفير
        [
            types.InlineKeyboardButton(text="⚠️ تصفير البوت", callback_data="reset_bot")
        ],
        # الصف الحادي عشر
        [
            types.InlineKeyboardButton(text="✏️ رسالة الصيانة", callback_data="edit_maintenance")
        ],
    ]
    
    await message.answer(
        f"🛠 **لوحة تحكم الإدارة**\n\n"
        f"حالة البوت: {status_text}\n\n"
        f"🔸 **اختر الإجراء المطلوب:**",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "toggle_bot")
async def toggle_bot(callback: types.CallbackQuery, db_pool):
    """تشغيل أو إيقاف البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_bot_status, set_bot_status
    
    current_status = await get_bot_status(db_pool)
    new_status = not current_status
    
    await set_bot_status(db_pool, new_status)
    
    status_text = "🟢 يعمل" if new_status else "🔴 متوقف"
    action_text = "تشغيل" if new_status else "إيقاف"
    
    await callback.message.edit_text(
        f"✅ تم {action_text} البوت بنجاح\n\n"
        f"الحالة الآن: {status_text}\n\n"
        f"{'⚠️ البوت متوقف عن العمل للمستخدمين العاديين' if not new_status else '✅ البوت يعمل بشكل طبيعي'}"
    )
    
    # إرسال إشعار للمشرفين
    from config import ADMIN_ID, MODERATORS
    admin_ids = [ADMIN_ID] + MODERATORS
    for admin_id in admin_ids:
        if admin_id and admin_id != callback.from_user.id:
            try:
                await callback.bot.send_message(
                    admin_id,
                    f"ℹ️ تم {action_text} البوت بواسطة @{callback.from_user.username or 'مشرف'}"
                )
            except:
                pass

@router.callback_query(F.data == "edit_maintenance")
async def edit_maintenance_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تعديل رسالة الصيانة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.answer(
        "📝 أرسل رسالة الصيانة الجديدة:\n\n"
        "(هذه الرسالة ستظهر للمستخدمين عند إيقاف البوت)"
    )
    await state.set_state(AdminStates.waiting_maintenance_msg)

@router.message(AdminStates.waiting_maintenance_msg)
async def save_maintenance_message(message: types.Message, state: FSMContext, db_pool):
    """حفظ رسالة الصيانة الجديدة"""
    if not is_admin(message.from_user.id):
        return
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE bot_settings SET value = $1, updated_at = CURRENT_TIMESTAMP WHERE key = 'maintenance_message'",
            message.text
        )
    
    await message.answer("✅ تم تحديث رسالة الصيانة بنجاح")
    await state.clear()

# ============= إدارة أرقام سيرياتل =============
@router.callback_query(F.data == "edit_syriatel")
async def edit_syriatel_start(callback: types.CallbackQuery, state: FSMContext):
    """تعديل أرقام سيرياتل كاش"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from config import SYRIATEL_NUMS
    current_nums = "\n".join([f"{i+1}. `{num}`" for i, num in enumerate(SYRIATEL_NUMS)])
    
    text = (
        f"📞 **أرقام سيرياتل كاش الحالية:**\n\n"
        f"{current_nums}\n\n"
        f"**أدخل الأرقام الجديدة** (كل رقم في سطر منفصل):\n"
        f"مثال:\n"
        f"74091109\n"
        f"63826779\n"
        f"0912345678"
    )
    
    await callback.message.answer(text, parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_new_syriatel_numbers)

@router.message(AdminStates.waiting_new_syriatel_numbers)
async def save_syriatel_numbers(message: types.Message, state: FSMContext, db_pool):
    """حفظ أرقام سيرياتل الجديدة في قاعدة البيانات"""
    if not is_admin(message.from_user.id):
        return
    
    # تقسيم الأرقام (كل سطر رقم)
    numbers = [line.strip() for line in message.text.split('\n') if line.strip()]
    
    # حفظ في قاعدة البيانات
    from database import set_syriatel_numbers
    success = await set_syriatel_numbers(db_pool, numbers)
    
    if success:
        # تحديث المتغير في config مؤقتاً
        import config
        config.SYRIATEL_NUMS = numbers
        
        text = "✅ **تم تحديث أرقام سيرياتل كاش بنجاح!**\n\nالأرقام الجديدة:\n"
        for i, num in enumerate(numbers, 1):
            text += f"{i}. `{num}`\n"
    else:
        text = "❌ **فشل تحديث الأرقام**"
    
    await message.answer(text, parse_mode="Markdown")
    await state.clear()

# ============= إدارة المنتجات =============
@router.callback_query(F.data == "add_product")
async def add_product_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء إضافة منتج جديد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # جلب الأقسام
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT id, display_name FROM categories ORDER BY sort_order")
    
    if not categories:
        await callback.answer("❌ لا توجد أقسام. أضف قسماً أولاً.", show_alert=True)
        return
    
    # عرض الأقسام للاختيار
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(types.InlineKeyboardButton(
            text=cat['display_name'],
            callback_data=f"sel_cat_{cat['id']}"
        ))
    
    await callback.message.answer(
        "📱 **إضافة منتج جديد**\n\n"
        "اختر القسم أولاً:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AdminStates.waiting_product_category)

@router.callback_query(F.data.startswith("sel_cat_"))
async def select_category_for_product(callback: types.CallbackQuery, state: FSMContext):
    """اختيار القسم للمنتج"""
    cat_id = int(callback.data.split("_")[2])
    await state.update_data(category_id=cat_id)
    
    await callback.message.edit_text(
        "📝 **أدخل اسم المنتج:**"
    )
    await state.set_state(AdminStates.waiting_product_name)

@router.message(AdminStates.waiting_product_name)
async def get_product_name(message: types.Message, state: FSMContext):
    """استلام اسم المنتج"""
    await state.update_data(product_name=message.text)
    await message.answer(
        "💰 **أدخل سعر الوحدة بالدولار:**\n"
        "مثال: 0.001"
    )
    await state.set_state(AdminStates.waiting_product_price)

@router.message(AdminStates.waiting_product_price)
async def get_product_price(message: types.Message, state: FSMContext):
    """استلام سعر المنتج"""
    try:
        price = float(message.text)
        await state.update_data(product_price=price)
        await message.answer(
            "📦 **أدخل الحد الأدنى للكمية:**\n"
            "مثال: 100"
        )
        await state.set_state(AdminStates.waiting_product_min)
    except ValueError:
        await message.answer("❌ يرجى إدخال رقم صحيح")

@router.message(AdminStates.waiting_product_min)
async def get_product_min(message: types.Message, state: FSMContext):
    """استلام الحد الأدنى"""
    try:
        min_units = int(message.text)
        await state.update_data(product_min=min_units)
        await message.answer(
            "📈 **أدخل نسبة الربح (%):**\n"
            "مثال: 10"
        )
        await state.set_state(AdminStates.waiting_product_profit)
    except ValueError:
        await message.answer("❌ يرجى إدخال رقم صحيح")

@router.message(AdminStates.waiting_product_profit)
async def get_product_profit(message: types.Message, state: FSMContext, db_pool):
    """استلام نسبة الربح وحفظ المنتج"""
    try:
        profit = float(message.text)
        data = await state.get_data()
        
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, category_id, type)
                VALUES ($1, $2, $3, $4, $5, 'service')
            ''', 
            data['product_name'],
            data['product_price'],
            data['product_min'],
            profit,
            data['category_id']
            )
        
        await message.answer(
            f"✅ **تم إضافة المنتج بنجاح!**\n\n"
            f"📱 الاسم: {data['product_name']}\n"
            f"💰 السعر: ${data['product_price']}\n"
            f"📦 الحد الأدنى: {data['product_min']}\n"
            f"📈 الربح: {profit}%"
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ يرجى إدخال رقم صحيح")
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

@router.callback_query(F.data == "edit_product")
async def edit_product_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المنتجات للتعديل"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.id, a.name, c.display_name 
            FROM applications a
            LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    if not products:
        await callback.answer("❌ لا توجد منتجات", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(types.InlineKeyboardButton(
            text=f"{p['name']} ({p['display_name']})",
            callback_data=f"edit_prod_{p['id']}"
        ))
    
    await callback.message.edit_text(
        "✏️ **اختر المنتج للتعديل:**",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("edit_prod_"))
async def edit_product_form(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض نموذج تعديل المنتج"""
    prod_id = int(callback.data.split("_")[2])
    
    async with db_pool.acquire() as conn:
        product = await conn.fetchrow("SELECT * FROM applications WHERE id = $1", prod_id)
    
    if not product:
        await callback.answer("❌ المنتج غير موجود", show_alert=True)
        return
    
    await state.update_data(product_id=prod_id)
    
    text = (
        f"✏️ **تعديل المنتج:** {product['name']}\n\n"
        f"السعر الحالي: ${product['unit_price_usd']}\n"
        f"الحد الأدنى: {product['min_units']}\n"
        f"الربح: {product['profit_percentage']}%\n\n"
        f"📝 أرسل البيانات الجديدة بالصيغة:\n"
        f"`الاسم|السعر|الحد_الأدنى|الربح`\n\n"
        f"مثال: `اسم جديد|0.002|200|15`"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_product_id)

@router.message(AdminStates.waiting_product_id)
async def update_product(message: types.Message, state: FSMContext, db_pool):
    """تحديث بيانات المنتج"""
    try:
        parts = message.text.split('|')
        if len(parts) != 4:
            return await message.answer("❌ صيغة غير صحيحة. استخدم: `الاسم|السعر|الحد_الأدنى|الربح`")
        
        name, price, min_units, profit = [p.strip() for p in parts]
        
        data = await state.get_data()
        prod_id = data['product_id']
        
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE applications 
                SET name = $1, unit_price_usd = $2, min_units = $3, profit_percentage = $4
                WHERE id = $5
            ''', name, float(price), int(min_units), float(profit), prod_id)
        
        await message.answer(f"✅ **تم تحديث المنتج بنجاح!**")
        await state.clear()
        
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

@router.callback_query(F.data == "delete_product")
async def delete_product_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المنتجات للحذف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.id, a.name, c.display_name 
            FROM applications a
            LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    if not products:
        await callback.answer("❌ لا توجد منتجات", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(types.InlineKeyboardButton(
            text=f"🗑️ {p['name']} ({p['display_name']})",
            callback_data=f"del_prod_{p['id']}"
        ))
    
    await callback.message.edit_text(
        "🗑️ **اختر المنتج للحذف:**",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("del_prod_"))
async def confirm_delete_product(callback: types.CallbackQuery, db_pool):
    """تأكيد حذف المنتج"""
    prod_id = int(callback.data.split("_")[2])
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم", callback_data=f"conf_del_{prod_id}"),
        types.InlineKeyboardButton(text="❌ لا", callback_data="cancel_del")
    )
    
    await callback.message.edit_text(
        "⚠️ **هل أنت متأكد من حذف هذا المنتج؟**",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("conf_del_"))
async def execute_delete_product(callback: types.CallbackQuery, db_pool):
    """تنفيذ حذف المنتج"""
    prod_id = int(callback.data.split("_")[2])
    
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM applications WHERE id = $1", prod_id)
    
    await callback.message.edit_text("✅ **تم حذف المنتج بنجاح!**")

@router.callback_query(F.data == "list_products")
async def list_products(callback: types.CallbackQuery, db_pool):
    """عرض جميع المنتجات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        products = await conn.fetch('''
            SELECT a.*, c.display_name 
            FROM applications a
            LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.name
        ''')
    
    if not products:
        await callback.answer("❌ لا توجد منتجات", show_alert=True)
        return
    
    text = "📱 **قائمة المنتجات**\n\n"
    for p in products:
        text += (
            f"**{p['name']}**\n"
            f"• القسم: {p['display_name']}\n"
            f"• السعر: ${p['unit_price_usd']}\n"
            f"• الحد الأدنى: {p['min_units']}\n"
            f"• الربح: {p['profit_percentage']}%\n"
            f"• النوع: {p['type']}\n"
            f"• الحالة: {'✅ نشط' if p['is_active'] else '❌ غير نشط'}\n\n"
        )
    
    await callback.message.edit_text(text, parse_mode="Markdown")

# ============= تصفير البوت =============
@router.callback_query(F.data == "reset_bot")
async def reset_bot_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء عملية تصفير البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="⚠️ نعم، تصفير البوت", callback_data="confirm_reset"),
        types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_del")
    )
    
    await callback.message.edit_text(
        "⚠️ **تحذير: تصفير البوت** ⚠️\n\n"
        "هذا الإجراء سيقوم بحذف:\n"
        "• جميع المستخدمين\n"
        "• جميع طلبات الشحن\n"
        "• جميع طلبات التطبيقات\n"
        "• جميع النقاط وسجل النقاط\n"
        "• جميع الإحالات\n\n"
        "**سيتم الاحتفاظ بالمشرفين فقط.**\n\n"
        "هل أنت متأكد؟",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "confirm_reset")
async def reset_bot_ask_rate(callback: types.CallbackQuery, state: FSMContext):
    """طلب سعر الصرف الجديد بعد التصفير"""
    await callback.message.edit_text(
        "💰 **أدخل سعر الصرف الجديد**\n"
        "مثال: 118\n\n"
        "سيتم استخدام هذا السعر بعد تصفير البوت."
    )
    await state.set_state(AdminStates.waiting_reset_rate)

# في handlers/admin.py - عدل دالة execute_reset_bot

@router.message(AdminStates.waiting_reset_rate)
async def execute_reset_bot(message: types.Message, state: FSMContext, db_pool):
    """تنفيذ تصفير البوت - مع إعادة ضبط VIP"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_rate = float(message.text)
        
        from config import ADMIN_ID, MODERATORS
        admin_ids = [ADMIN_ID] + MODERATORS
        admin_ids_str = ','.join([str(id) for id in admin_ids if id])
        
        async with db_pool.acquire() as conn:
            # 1. مسح سجل النقاط
            await conn.execute("DELETE FROM points_history")
            
            # 2. مسح طلبات الاسترداد
            await conn.execute("DELETE FROM redemption_requests")
            
            # 3. مسح طلبات الشحن
            await conn.execute("DELETE FROM deposit_requests")
            
            # 4. مسح طلبات التطبيقات
            await conn.execute("DELETE FROM orders")
            
            # 5. مسح المستخدمين (مع الاحتفاظ بالمشرفين)
            if admin_ids_str:
                await conn.execute(f"DELETE FROM users WHERE user_id NOT IN ({admin_ids_str})")
                
                # إعادة ضبط المشرفين - مع إعادة تعيين VIP إلى 0
                for admin_id in admin_ids:
                    if admin_id:
                        await conn.execute('''
                            UPDATE users 
                            SET 
                                balance = 0, 
                                total_points = 0, 
                                total_deposits = 0, 
                                total_orders = 0, 
                                referral_count = 0, 
                                referral_earnings = 0,
                                total_points_earned = 0, 
                                total_points_redeemed = 0,
                                vip_level = 0,           -- إعادة ضبط مستوى VIP
                                total_spent = 0,         -- إعادة ضبط إجمالي المشتريات
                                discount_percent = 0,    -- إعادة ضبط نسبة الخصم
                                last_activity = CURRENT_TIMESTAMP
                            WHERE user_id = $1
                        ''', admin_id)
            else:
                await conn.execute("DELETE FROM users")
            
            # 6. تحديث سعر الصرف
            await conn.execute('''
                INSERT INTO bot_settings (key, value, description) 
                VALUES ('usd_to_syp', $1, 'سعر صرف الدولار مقابل الليرة')
                ON CONFLICT (key) DO UPDATE SET value = $1
            ''', str(new_rate))
            
            # 7. إعادة ضبط إعدادات النقاط
            await conn.execute('''
                UPDATE bot_settings SET value = '1' 
                WHERE key IN ('points_per_order', 'points_per_referral')
            ''')
            
            # 8. إعادة ضبط redemption_rate
            await conn.execute('''
                UPDATE bot_settings SET value = '100' 
                WHERE key = 'redemption_rate'
            ''')
            
            # 9. إعادة ضبط مستويات VIP في جدول vip_levels (إذا أردت)
            await conn.execute('''
                INSERT INTO vip_levels (level, name, min_spent, discount_percent, icon) 
                VALUES 
                    (0, 'VIP 0', 0, 0, '🟢'),
                    (1, 'VIP 1', 1000, 1, '🔵'),
                    (2, 'VIP 2', 2000, 2, '🟣'),
                    (3, 'VIP 3', 4000, 3, '🟡'),
                    (4, 'VIP 4', 8000, 5, '🔴')
                ON CONFLICT (level) DO UPDATE SET 
                    min_spent = EXCLUDED.min_spent,
                    discount_percent = EXCLUDED.discount_percent,
                    icon = EXCLUDED.icon;
            ''')
        
        await message.answer(
            f"✅ **تم تصفير البوت بنجاح!**\n\n"
            f"💰 سعر الصرف الجديد: {new_rate} ل.س\n"
            f"⭐ نقاط لكل طلب: 1\n"
            f"🔗 نقاط لكل إحالة: 1\n"
            f"🎁 100 نقطة = 1 دولار\n"
            f"👑 تم إعادة ضبط جميع مستويات VIP إلى 0\n\n"
            f"البوت الآن جاهز للبدء من جديد!"
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ يرجى إدخال رقم صحيح")
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

@router.callback_query(F.data == "cancel_del")
async def cancel_action(callback: types.CallbackQuery):
    """إلغاء أي عملية"""
    await callback.message.edit_text("✅ تم الإلغاء.")

# إدارة النقاط
@router.callback_query(F.data == "manage_points")
async def manage_points(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        points_per_order = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_per_order'")
        points_per_referral = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_per_referral'")
        points_to_usd = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'points_to_usd'")
        
        # طلبات الاسترداد المعلقة
        pending_redemptions = await conn.fetch('''
            SELECT * FROM redemption_requests WHERE status = 'pending' ORDER BY created_at
        ''')
    
    kb = [
        [types.InlineKeyboardButton(text="⚙️ تعديل إعدادات النقاط", callback_data="edit_points_settings")],
        [types.InlineKeyboardButton(text="📋 طلبات الاسترداد", callback_data="view_redemptions")],
        [types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin")]
    ]
    
    text = (
        "⭐ **إدارة النقاط**\n\n"
        f"**الإعدادات الحالية:**\n"
        f"• نقاط لكل طلب: {points_per_order or 5}\n"
        f"• نقاط لكل إحالة: {points_per_referral or 5}\n"
        f"• {points_to_usd or 100} نقطة = 1 دولار\n\n"
        f"**طلبات الاسترداد المعلقة:** {len(pending_redemptions)}"
    )
    
    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "pending_redemptions")
async def show_pending_redemptions(callback: types.CallbackQuery, db_pool):
    """عرض طلبات الاسترداد المعلقة"""
    async with db_pool.acquire() as conn:
        pending = await conn.fetch('''
            SELECT id, user_id, username, points, amount_syp, created_at
            FROM redemption_requests
            WHERE status = 'pending'
            ORDER BY created_at DESC
        ''')
    
    if not pending:
        return await callback.answer("لا توجد طلبات استرداد معلقة", show_alert=True)
    
    for req in pending:
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ موافقة", callback_data=f"appr_red_{req['id']}"),
            types.InlineKeyboardButton(text="❌ رفض", callback_data=f"reje_red_{req['id']}")
        )
        
        await callback.message.answer(
            f"📋 **طلب استرداد نقاط**\n\n"
            f"🆔 رقم الطلب: {req['id']}\n"
            f"👤 المستخدم: @{req['username'] or 'غير معروف'} (ID: `{req['user_id']}`)\n"
            f"⭐ النقاط: {req['points']}\n"
            f"💰 المبلغ: {req['amount_syp']:,.0f} ل.س\n"
            f"📅 التاريخ: {req['created_at'].strftime('%Y-%m-%d %H:%M')}",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

@router.callback_query(F.data == "edit_points_settings")
async def edit_points_settings(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.answer(
        "⚙️ **تعديل إعدادات النقاط**\n\n"
        "أدخل القيم الجديدة بالصيغة التالية:\n"
        "`نقاط_الطلب نقاط_الإحالة نقاط_الدولار`\n\n"
        "مثال: `1 1 100`",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_points_settings)

@router.message(AdminStates.waiting_points_settings)
async def save_points_settings(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            return await message.answer("❌ صيغة غير صحيحة. استخدم: `نقاط_الطلب نقاط_الإحالة نقاط_الدولار`")
        
        points_order, points_referral, points_usd = parts
        
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE bot_settings SET value = $1 WHERE key = 'points_per_order'",
                points_order
            )
            await conn.execute(
                "UPDATE bot_settings SET value = $1 WHERE key = 'points_per_referral'",
                points_referral
            )
            await conn.execute(
                "UPDATE bot_settings SET value = $1 WHERE key = 'points_to_usd'",
                points_usd
            )
        
        await message.answer("✅ **تم تحديث إعدادات النقاط بنجاح**")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ **حدث خطأ:** {str(e)}")
        await state.clear()

@router.callback_query(F.data == "view_redemptions")
async def view_redemptions(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        redemptions = await conn.fetch('''
            SELECT * FROM redemption_requests WHERE status = 'pending' ORDER BY created_at
        ''')
    
    if not redemptions:
        await callback.answer("لا توجد طلبات استرداد معلقة", show_alert=True)
        return
    
    for r in redemptions:
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ موافقة", callback_data=f"appr_red_{r['id']}"),
            types.InlineKeyboardButton(text="❌ رفض", callback_data=f"reje_red_{r['id']}")
        )
        
        await callback.message.answer(
            f"🆔 **طلب استرداد #{r['id']}**\n\n"
            f"👤 **المستخدم:** @{r['username'] or 'غير معروف'}\n"
            f"🆔 **الآيدي:** `{r['user_id']}`\n"
            f"⭐ **النقاط:** {r['points']}\n"
            f"💰 **المبلغ:** {r['amount_usd']}$ ({r['amount_syp']:,.0f} ل.س)\n"
            f"📅 **التاريخ:** {r['created_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
            f"**الإجراء:**",
            reply_markup=builder.as_markup()
        )

@router.callback_query(F.data.startswith("appr_red_"))
async def approve_redemption(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    """الموافقة على طلب استرداد نقاط"""
    try:
        req_id = int(callback.data.split("_")[2])
        
        from database import approve_redemption, get_exchange_rate
        
        # جلب سعر الصرف الحالي للتأكيد
        current_rate = await get_exchange_rate(db_pool)
        
        success, error = await approve_redemption(db_pool, req_id, callback.from_user.id)
        
        if success:
            # جلب معلومات الطلب لعرضها
            async with db_pool.acquire() as conn:
                req = await conn.fetchrow(
                    "SELECT * FROM redemption_requests WHERE id = $1",
                    req_id
                )
            
            await callback.answer("✅ تمت الموافقة على الطلب")
            await callback.message.edit_text(
                callback.message.text + f"\n\n✅ **تمت الموافقة على الطلب**\n💰 بسعر صرف: {current_rate:,.0f} ل.س",
                reply_markup=None
            )
            
            # إرسال تأكيد للمستخدم
            try:
                await bot.send_message(
                    req['user_id'],
                    f"✅ **تمت الموافقة على طلب استرداد النقاط!**\n\n"
                    f"⭐ النقاط: {req['points']}\n"
                    f"💰 المبلغ: {req['amount_syp']:,.0f} ل.س\n"
                    f"💵 بسعر صرف: {current_rate:,.0f} ل.س\n\n"
                    f"تم إضافة المبلغ إلى رصيدك."
                )
            except:
                pass
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
            
    except Exception as e:
        logger.error(f"❌ خطأ في الموافقة على الاسترداد: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reje_red_"))
async def reject_redemption(callback: types.CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    """رفض طلب استرداد نقاط"""
    try:
        req_id = int(callback.data.split("_")[2])
        
        from database import reject_redemption
        success, error = await reject_redemption(db_pool, req_id, callback.from_user.id, "رفض من قبل الإدارة")
        
        if success:
            await callback.answer("❌ تم رفض الطلب")
            await callback.message.edit_text(
                callback.message.text + "\n\n❌ **تم رفض الطلب**",
                reply_markup=None
            )
        else:
            await callback.answer(f"❌ {error}", show_alert=True)
            
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الاسترداد: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: types.CallbackQuery, db_pool):
    from database import get_bot_status
    bot_status = await get_bot_status(db_pool)
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"
    
    kb = [
        [types.InlineKeyboardButton(text="📈 تعديل سعر الصرف", callback_data="edit_rate")],
        [types.InlineKeyboardButton(text="📢 إرسال رسالة للكل", callback_data="broadcast")],
        [types.InlineKeyboardButton(text="💰 إضافة رصيد", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="📊 إحصائيات البوت", callback_data="bot_stats")],
        [types.InlineKeyboardButton(text="👤 معلومات مستخدم", callback_data="user_info")],
        [types.InlineKeyboardButton(text="⭐ إدارة النقاط", callback_data="manage_points")],
        [types.InlineKeyboardButton(
            text=f"🔄 إيقاف البوت" if bot_status else "🔄 تشغيل البوت", 
            callback_data="toggle_bot"
        )],
        [types.InlineKeyboardButton(text="✏️ تعديل رسالة الصيانة", callback_data="edit_maintenance")],
    ]
    
    await callback.message.edit_text(
        f"🛠 **لوحة تحكم الإدارة**\n\n"
        f"حالة البوت: {status_text}\n\n"
        f"🔸 **اختر الإجراء المطلوب:**",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "edit_rate")
async def start_edit_rate(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """بدء تعديل سعر الصرف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_exchange_rate
    current_rate = await get_exchange_rate(db_pool)
    
    await callback.message.answer(
        f"💵 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س\n\n"
        f"📝 **أدخل السعر الجديد:**",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_new_rate)

@router.message(AdminStates.waiting_new_rate)
async def save_new_rate(message: types.Message, state: FSMContext, db_pool):
    """حفظ سعر الصرف الجديد"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_rate = float(message.text)
        
        if new_rate <= 0:
            return await message.answer("⚠️ يرجى إدخال رقم موجب")
        
        from database import set_exchange_rate
        await set_exchange_rate(db_pool, new_rate)
        
        # تحديث المتغير العام في config
        import config
        config.USD_TO_SYP = new_rate
        
        await message.answer(
            f"✅ **تم تحديث سعر الصرف بنجاح**\n\n"
            f"💰 السعر الجديد: {new_rate:,.0f} ل.س = 1$"
        )
        
        # إرسال إشعار للمشرفين الآخرين
        from config import MODERATORS
        for mod_id in MODERATORS:
            if mod_id and mod_id != message.from_user.id:
                try:
                    await message.bot.send_message(
                        mod_id,
                        f"ℹ️ تم تغيير سعر الصرف بواسطة @{message.from_user.username}\n"
                        f"💰 السعر الجديد: {new_rate:,.0f} ل.س"
                    )
                except:
                    pass
        
        await state.clear()
        
    except ValueError:
        await message.answer("⚠️ يرجى إدخال رقم صحيح")
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# إرسال رسالة للجميع
@router.callback_query(F.data == "broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 **أدخل الرسالة التي تريد إرسالها للجميع:**")
    await state.set_state(AdminStates.waiting_broadcast_msg)

@router.message(AdminStates.waiting_broadcast_msg)
async def send_broadcast(message: types.Message, state: FSMContext, db_pool, bot: Bot):
    try:
        async with db_pool.acquire() as conn:
            users = await conn.fetch("SELECT user_id FROM users WHERE NOT is_banned")
        
        success = 0
        failed = 0
        progress_msg = await message.answer("⏳ جاري الإرسال...")
        
        for i, user in enumerate(users):
            try:
                await bot.send_message(
                    user['user_id'],
                    f"📢 **رسالة من الإدارة:**\n\n{message.text}",
                    parse_mode="Markdown"
                )
                success += 1
                
                if i % 10 == 0:
                    await progress_msg.edit_text(f"⏳ تم الإرسال: {success} / {len(users)}")
                
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"فشل إرسال للمستخدم {user['user_id']}: {e}")
                failed += 1
        
        await progress_msg.delete()
        await message.answer(
            f"✅ **تم إرسال الرسالة بنجاح**\n\n"
            f"📊 **الإحصائيات:**\n"
            f"• ✅ تم الإرسال: {success}\n"
            f"• ❌ فشل الإرسال: {failed}",
            parse_mode="Markdown"
        )
        
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ **حدث خطأ:** {str(e)}")
        await state.clear()

# إضافة رصيد يدوي
@router.callback_query(F.data == "add_balance")
async def add_balance_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("👤 **أدخل آيدي المستخدم:**")
    await state.set_state(AdminStates.waiting_user_id)

@router.message(AdminStates.waiting_user_id)
async def add_balance_amount(message: types.Message, state: FSMContext, db_pool):
    try:
        user_id = int(message.text)
        await state.update_data(target_user=user_id)
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT username, balance FROM users WHERE user_id = $1",
                user_id
            )
            
            if not user:
                await message.answer("⚠️ **المستخدم غير موجود**")
                await state.clear()
                return
            
            await message.answer(
                f"👤 **المستخدم:** {user['username'] or 'بدون اسم'}\n"
                f"💰 **الرصيد الحالي:** {user['balance']:,.0f} ل.س\n\n"
                f"**أدخل المبلغ المراد إضافته (ل.س):**",
                parse_mode="Markdown"
            )
            await state.set_state(AdminStates.waiting_balance_amount)
    except ValueError:
        await message.answer("⚠️ **آيدي غير صالح. الرجاء إدخال رقم صحيح**")
        await state.clear()

@router.message(AdminStates.waiting_balance_amount)
async def finalize_add_balance(message: types.Message, state: FSMContext, db_pool):
    try:
        amount = float(message.text)
        data = await state.get_data()
        user_id = data['target_user']
        
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET balance = balance + $1, total_deposits = total_deposits + $1 WHERE user_id = $2",
                amount, user_id
            )
            
            user = await conn.fetchrow(
                "SELECT username, balance, total_points FROM users WHERE user_id = $1",
                user_id
            )
        
        await message.answer(
            f"✅ **تمت إضافة الرصيد بنجاح**\n\n"
            f"👤 **المستخدم:** {user['username'] or 'بدون اسم'}\n"
            f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
            f"💳 **الرصيد الجديد:** {user['balance']:,.0f} ل.س\n"
            f"⭐ **النقاط:** {user['total_points']}",
            parse_mode="Markdown"
        )
        
        # إرسال إشعار للمستخدم
        try:
            await message.bot.send_message(
                user_id,
                f"✅ **تم إضافة رصيد إلى حسابك!**\n\n"
                f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
                f"💳 **الرصيد الحالي:** {user['balance']:,.0f} ل.س",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمستخدم {user_id}: {e}")
        
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ **حدث خطأ:** {str(e)}")
        await state.clear()

@router.callback_query(F.data == "bot_stats")
async def show_bot_stats(callback: types.CallbackQuery, db_pool):
    """عرض إحصائيات البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_bot_stats, get_bot_status, get_exchange_rate
    
    stats = await get_bot_stats(db_pool)
    bot_status = await get_bot_status(db_pool)
    current_rate = await get_exchange_rate(db_pool)
    
    if not stats:
        return await callback.answer("❌ خطأ في جلب الإحصائيات", show_alert=True)
    
    status_text = "🟢 يعمل" if bot_status else "🔴 متوقف"
    
    stats_text = (
        "📊 **إحصائيات البوت**\n\n"
        
        f"🤖 **حالة البوت:** {status_text}\n\n"
        
        "👥 **المستخدمين:**\n"
        f"• 📈 الإجمالي: {stats['users'].get('total_users', 0)}\n"
        f"• 💰 إجمالي الأرصدة: {stats['users'].get('total_balance', 0):,.0f} ل.س\n"
        f"• 🚫 المحظورين: {stats['users'].get('banned_users', 0)}\n"
        f"• 🆕 الجدد اليوم: {stats['users'].get('new_users_today', 0)}\n"
        f"• ⭐ إجمالي النقاط: {stats['users'].get('total_points', 0)}\n\n"
        
        "💰 **الإيداعات:**\n"
        f"• 📋 الإجمالي: {stats['deposits'].get('total_deposits', 0)}\n"
        f"• 💸 إجمالي المبالغ: {stats['deposits'].get('total_deposit_amount', 0):,.0f} ل.س\n"
        f"• ⏳ المعلقة: {stats['deposits'].get('pending_deposits', 0)}\n"
        f"• ✅ المنجزة: {stats['deposits'].get('approved_deposits', 0)}\n\n"
        
        "🛒 **الطلبات:**\n"
        f"• 📋 الإجمالي: {stats['orders'].get('total_orders', 0)}\n"
        f"• 💸 إجمالي المبالغ: {stats['orders'].get('total_order_amount', 0):,.0f} ل.س\n"
        f"• ⏳ المعلقة: {stats['orders'].get('pending_orders', 0)}\n"
        f"• ✅ المكتملة: {stats['orders'].get('completed_orders', 0)}\n"
        f"• ⭐ نقاط ممنوحة: {stats['orders'].get('total_points_given', 0)}\n\n"
        
        "🎁 **نظام النقاط:**\n"
        f"• 💰 عمليات استرداد: {stats['points'].get('total_redemptions', 0)}\n"
        f"• ⭐ نقاط مستردة: {stats['points'].get('total_points_redeemed', 0)}\n"
        f"• 💵 قيمة المستردة: {stats['points'].get('total_redemption_amount', 0):,.0f} ل.س\n\n"
        
        f"💵 **سعر الصرف الحالي:** {current_rate:,.0f} ل.س = 1$\n\n"
        f"⚙️ **إعدادات النقاط:**\n"
        f"• 📦 نقاط الطلب: {stats.get('points_per_order', 1)}\n"
        f"• 🔗 نقاط الإحالة: {stats.get('points_per_referral', 1)}"
    )
    
    await callback.message.answer(stats_text, parse_mode="Markdown")
    
@router.callback_query(F.data == "top_deposits")
async def show_top_deposits(callback: types.CallbackQuery, db_pool):
    """عرض أكثر المستخدمين إيداعاً"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_deposits
    users = await get_top_users_by_deposits(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "💳 **أكثر المستخدمين إيداعاً**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        vip_icon = ["🟢", "🔵", "🟣", "🟡", "🔴", "💎"][user['vip_level']] if user['vip_level'] <= 5 else "⭐"
        text += f"{i}. {vip_icon} {username}\n   💰 {user['total_deposits']:,.0f} ل.س\n"
    
    await callback.message.answer(text, parse_mode="Markdown")

@router.callback_query(F.data == "top_orders")
async def show_top_orders(callback: types.CallbackQuery, db_pool):
    """عرض أكثر المستخدمين طلبات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_orders
    users = await get_top_users_by_orders(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "🛒 **أكثر المستخدمين طلبات**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        vip_icon = ["🟢", "🔵", "🟣", "🟡", "🔴", "💎"][user['vip_level']] if user['vip_level'] <= 5 else "⭐"
        text += f"{i}. {vip_icon} {username}\n   📦 {user['total_orders']} طلب\n"
    
    await callback.message.answer(text, parse_mode="Markdown")

@router.callback_query(F.data == "top_referrals")
async def show_top_referrals(callback: types.CallbackQuery, db_pool):
    """عرض أكثر المستخدمين إحالة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_referrals
    users = await get_top_users_by_referrals(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "🔗 **أكثر المستخدمين إحالة**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        vip_icon = ["🟢", "🔵", "🟣", "🟡", "🔴", "💎"][user['vip_level']] if user['vip_level'] <= 5 else "⭐"
        text += f"{i}. {vip_icon} {username}\n   👥 {user['referral_count']} إحالة | 💰 {user['referral_earnings']:,.0f} ل.س\n"
    
    await callback.message.answer(text, parse_mode="Markdown")

@router.callback_query(F.data == "top_points")
async def show_top_points(callback: types.CallbackQuery, db_pool):
    """عرض أكثر المستخدمين نقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_top_users_by_points
    users = await get_top_users_by_points(db_pool, 15)
    
    if not users:
        await callback.answer("لا توجد بيانات كافية", show_alert=True)
        return
    
    text = "⭐ **أكثر المستخدمين نقاط**\n\n"
    for i, user in enumerate(users, 1):
        username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        vip_icon = ["🟢", "🔵", "🟣", "🟡", "🔴", "💎"][user['vip_level']] if user['vip_level'] <= 5 else "⭐"
        text += f"{i}. {vip_icon} {username}\n   ⭐ {user['total_points']} نقطة\n"
    
    await callback.message.answer(text, parse_mode="Markdown")

@router.callback_query(F.data == "vip_stats")
async def show_vip_stats(callback: types.CallbackQuery, db_pool):
    """عرض إحصائيات VIP"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        # عدد المستخدمين في كل مستوى
        vip_counts = await conn.fetch('''
            SELECT vip_level, COUNT(*) as count 
            FROM users 
            GROUP BY vip_level 
            ORDER BY vip_level
        ''')
        
        # إجمالي الإنفاق في كل مستوى
        vip_spent = await conn.fetch('''
            SELECT vip_level, SUM(total_spent) as total 
            FROM users 
            WHERE vip_level > 0 
            GROUP BY vip_level 
            ORDER BY vip_level
        ''')
    
    vip_names = ["VIP 0 🟢", "VIP 1 🔵", "VIP 2 🟣", "VIP 3 🟡", "VIP 4 🔴", "VIP 5 💎"]
    
    text = "👥 **إحصائيات VIP**\n\n"
    
    # عرض عدد المستخدمين
    text += "**عدد المستخدمين:**\n"
    for row in vip_counts:
        level = row['vip_level']
        if level <= 5:
            text += f"• {vip_names[level]}: {row['count']} مستخدم\n"
    
    # عرض إجمالي الإنفاق
    if vip_spent:
        text += "\n**إجمالي الإنفاق:**\n"
        for row in vip_spent:
            level = row['vip_level']
            if level <= 5:
                text += f"• {vip_names[level]}: {row['total']:,.0f} ل.س\n"
    
    await callback.message.answer(text, parse_mode="Markdown")

# معلومات مستخدم
@router.callback_query(F.data == "user_info")
async def user_info_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("👤 **أدخل آيدي المستخدم للحصول على معلوماته:**")
    await state.set_state(AdminStates.waiting_user_info)

@router.message(AdminStates.waiting_user_info)
async def user_info_show(message: types.Message, state: FSMContext, db_pool):
    """عرض معلومات المستخدم"""
    try:
        user_id = int(message.text)
        
        from database import get_user_profile
        profile = await get_user_profile(db_pool, user_id)
        
        if not profile:
            await message.answer("⚠️ **المستخدم غير موجود**")
            await state.clear()
            return
        
        user = profile['user']
        deposits = profile['deposits']
        orders = profile['orders']
        referrals = profile['referrals']
        
        # تنسيق التاريخ
        join_date = user['created_at'].strftime("%Y-%m-%d %H:%M") if user.get('created_at') else "غير معروف"
        last_active = user['last_activity'].strftime("%Y-%m-%d %H:%M") if user.get('last_activity') else "غير معروف"
        
        # بناء رسالة المعلومات
        info_text = (
            f"👤 **معلومات المستخدم**\n\n"
            f"🆔 **الآيدي:** `{user['user_id']}`\n"
            f"👤 **اليوزر:** @{user['username'] or 'غير موجود'}\n"
            f"📝 **الاسم:** {user.get('first_name', '')} {user.get('last_name', '')}\n"
            f"💰 **الرصيد:** {user.get('balance', 0):,.0f} ل.س\n"
            f"⭐ **النقاط:** {user.get('total_points', 0)}\n"
            f"👑 **مستوى VIP:** {user.get('vip_level', 0)} (خصم {user.get('discount_percent', 0)}%)\n"
            f"💰 **إجمالي الإنفاق:** {user.get('total_spent', 0):,.0f} ل.س\n"
            f"🔒 **الحالة:** {'🚫 محظور' if user.get('is_banned') else '✅ نشط'}\n"
            f"📅 **تاريخ التسجيل:** {join_date}\n"
            f"⏰ **آخر نشاط:** {last_active}\n"
            f"🔗 **كود الإحالة:** `{user.get('referral_code', 'لا يوجد')}`\n"
            f"👥 **تمت إحالته بواسطة:** {user.get('referred_by', 'لا يوجد')}\n\n"
            
            f"📊 **إحصائيات الإيداعات:**\n"
            f"• إجمالي الإيداعات: {deposits.get('total_count', 0)} عملية\n"
            f"• إجمالي المبالغ: {deposits.get('total_amount', 0):,.0f} ل.س\n"
            f"• الإيداعات المقبولة: {deposits.get('approved_count', 0)} عملية\n"
            f"• قيمة المقبولة: {deposits.get('approved_amount', 0):,.0f} ل.س\n\n"
            
            f"📊 **إحصائيات الطلبات:**\n"
            f"• إجمالي الطلبات: {orders.get('total_count', 0)} طلب\n"
            f"• إجمالي المبالغ: {orders.get('total_amount', 0):,.0f} ل.س\n"
            f"• الطلبات المكتملة: {orders.get('completed_count', 0)} طلب\n"
            f"• قيمة المكتملة: {orders.get('completed_amount', 0):,.0f} ل.س\n"
            f"• نقاط مكتسبة من الطلبات: {orders.get('total_points_earned', 0)}\n\n"
            
            f"👥 **الإحالات:**\n"
            f"• عدد المحالين: {referrals.get('total_referrals', 0)}\n"
            f"• إيداعات المحالين: {referrals.get('referrals_deposits', 0):,.0f} ل.س\n"
            f"• طلبات المحالين: {referrals.get('referrals_orders', 0)}"
        )
        
        # أزرار للإجراءات السريعة
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
            )
        )
        
        await message.answer(
            info_text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        
        await state.clear()
        
    except ValueError:
        await message.answer("⚠️ **الرجاء إدخال آيدي صحيح (أرقام فقط)**")
        await state.clear()
    except Exception as e:
        logger.error(f"خطأ في معلومات المستخدم: {e}")
        await message.answer(f"❌ **حدث خطأ:** {str(e)}")
        await state.clear()

@router.callback_query(F.data.startswith("add_points_"))
async def add_points_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء إضافة نقاط لمستخدم"""
    try:
        user_id = int(callback.data.split("_")[2])
        await state.update_data(target_user=user_id)
        await callback.message.answer(f"⭐ **أدخل عدد النقاط لإضافتها للمستخدم {user_id}:**")
        await state.set_state(AdminStates.waiting_points_amount)
    except Exception as e:
        logger.error(f"خطأ في بدء إضافة نقاط: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.message(AdminStates.waiting_points_amount)
async def add_points_finalize(message: types.Message, state: FSMContext, db_pool):
    """إضافة النقاط للمستخدم"""
    try:
        points = int(message.text)
        if points <= 0:
            return await message.answer("⚠️ يرجى إدخال رقم موجب")
        
        data = await state.get_data()
        user_id = data['target_user']
        
        async with db_pool.acquire() as conn:
            # التحقق من وجود المستخدم
            user = await conn.fetchrow(
                "SELECT username, total_points FROM users WHERE user_id = $1",
                user_id
            )
            
            if not user:
                return await message.answer("❌ المستخدم غير موجود")
            
            # إضافة النقاط للمستخدم
            await conn.execute(
                "UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2",
                points, user_id
            )
            
            # تسجيل في سجل النقاط
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ''', user_id, points, 'admin_add', f'إضافة نقاط من الأدمن: {points}')
            
            # جلب الرصيد الجديد
            new_total = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                user_id
            )
        
        await message.answer(
            f"✅ **تم إضافة {points} نقطة للمستخدم {user_id}**\n\n"
            f"👤 المستخدم: @{user['username'] or 'غير معروف'}\n"
            f"⭐ الرصيد السابق: {user['total_points']}\n"
            f"⭐ الرصيد الجديد: {new_total}"
        )
        
        # إرسال إشعار للمستخدم
        try:
            await message.bot.send_message(
                user_id,
                f"✅ **تم إضافة نقاط إلى رصيدك!**\n\n"
                f"⭐ المبلغ المضاف: +{points} نقطة\n"
                f"⭐ رصيدك الحالي: {new_total} نقطة"
            )
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمستخدم {user_id}: {e}")
        
        await state.clear()
        
    except ValueError:
        await message.answer("⚠️ يرجى إدخال رقم صحيح")
    except Exception as e:
        logger.error(f"خطأ في إضافة نقاط: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# تبديل حالة الحظر
@router.callback_query(F.data.startswith("toggle_ban_"))
async def toggle_ban_from_info(callback: types.CallbackQuery, db_pool):
    try:
        user_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT is_banned FROM users WHERE user_id = $1",
                user_id
            )
            
            if user:
                new_status = not user['is_banned']
                await conn.execute(
                    "UPDATE users SET is_banned = $1 WHERE user_id = $2",
                    new_status, user_id
                )
                
                status_text = "محظور" if new_status else "نشط"
                await callback.message.answer(f"✅ تم تغيير حالة المستخدم إلى: {status_text}")
                
                try:
                    await callback.bot.send_message(
                        user_id,
                        f"⚠️ **تم تغيير حالة حسابك**\n\n"
                        f"الحالة الجديدة: {'🚫 محظور' if new_status else '✅ نشط'}"
                    )
                except:
                    pass
            else:
                await callback.answer("المستخدم غير موجود", show_alert=True)
                
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# تعديل الرصيد
@router.callback_query(F.data.startswith("edit_bal_"))
async def edit_balance_from_info(callback: types.CallbackQuery, state: FSMContext):
    try:
        user_id = int(callback.data.split("_")[2])
        await state.update_data(target_user=user_id)
        await callback.message.answer(f"💰 **أدخل الرصيد الجديد للمستخدم {user_id}:**")
        await state.set_state(AdminStates.waiting_balance_amount)
    except Exception as e:
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# ============= معالجة طلبات الشحن من المجموعة =============

@router.callback_query(F.data.startswith("appr_dep_"))
async def approve_deposit_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """موافقة على طلب شحن من المجموعة"""
    try:
        logger.info(f"📩 استقبال موافقة شحن: {callback.data}")
        
        parts = callback.data.split("_")
        if len(parts) >= 4:
            _, _, uid, amt = parts
            user_id = int(uid)
            amount = float(amt)
        else:
            await callback.answer("❌ بيانات غير صحيحة", show_alert=True)
            return
        
        logger.info(f"✅ موافقة على شحن: user={user_id}, amount={amount}")
        
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT username, balance FROM users WHERE user_id = $1",
                user_id
            )
            
            if not user:
                await conn.execute(
                    "INSERT INTO users (user_id, balance, created_at) VALUES ($1, 0, CURRENT_TIMESTAMP)",
                    user_id
                )
                user = {'username': None, 'balance': 0}
            
            new_balance = user['balance'] + amount
            await conn.execute(
                "UPDATE users SET balance = $1, total_deposits = total_deposits + $2, last_activity = CURRENT_TIMESTAMP WHERE user_id = $3",
                new_balance, amount, user_id
            )
            
            # تحديث حالة الطلب
            await conn.execute('''
                UPDATE deposit_requests 
                SET status = 'approved', updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM deposit_requests 
                    WHERE user_id = $1 AND status = 'pending' AND amount_syp = $2
                    ORDER BY created_at DESC 
                    LIMIT 1
                )
            ''', user_id, amount)
        
        # استخدام توقيت دمشق للمستخدم
        damascus_time = get_damascus_time()
        
        # إرسال إشعار للمستخدم مع توقيت دمشق
        try:
            await bot.send_message(
                user_id,
                f"✅ **تم تأكيد عملية الشحن بنجاح!**\n\n"
                f"💰 **المبلغ المضاف:** {amount:,.0f} ل.س\n"
                f"💳 **الرصيد الحالي:** {new_balance:,.0f} ل.س\n"
                f"📅 **التاريخ:** {damascus_time}\n\n"
                f"🔸 **شكراً لاستخدامك خدماتنا**",
                parse_mode="Markdown"
            )
            logger.info(f"✅ تم إرسال رسالة النجاح للمستخدم {user_id}")
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة للمستخدم {user_id}: {e}")
        
        # تحديث رسالة المجموعة - نسخة محسنة
        try:
            # التحقق من وجود نص في الرسالة
            current_text = callback.message.text or callback.message.caption or ""
            
            # إضافة نص التأكيد مع توقيت دمشق
            new_text = current_text + f"\n\n✅ **تمت الموافقة على الطلب**\n📅 **بتاريخ:** {damascus_time}"
            
            # التحقق من نوع الرسالة (نص أو صورة)
            if callback.message.photo:
                # إذا كانت رسالة تحتوي على صورة
                await callback.message.edit_caption(
                    caption=new_text,
                    reply_markup=None
                )
            else:
                # إذا كانت رسالة نصية عادية
                await callback.message.edit_text(
                    text=new_text,
                    reply_markup=None
                )
                
            logger.info(f"✅ تم تحديث رسالة المجموعة بنجاح")
        except Exception as e:
            logger.error(f"❌ فشل تحديث رسالة المجموعة: {e}")
        
        await callback.answer("✅ تمت الموافقة بنجاح")
        
    except Exception as e:
        logger.error(f"❌ خطأ عام في موافقة الشحن: {e}")
        import traceback
        traceback.print_exc()
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reje_dep_"))
async def reject_deposit_from_group(callback: types.CallbackQuery, bot: Bot, db_pool):
    """رفض طلب شحن من المجموعة"""
    try:
        logger.info(f"📩 استقبال رفض شحن: {callback.data}")
        user_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            # تحديث حالة الطلب
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
        
        # استخدام توقيت دمشق للمستخدم
        damascus_time = get_damascus_time()
        
        # إرسال إشعار للمستخدم مع توقيت دمشق
        try:
            await bot.send_message(
                user_id,
                f"❌ **نعتذر، تم رفض طلب الشحن الخاص بك.**\n\n"
                f"📅 **تاريخ الرفض:** {damascus_time}\n"
                f"🔸 **الأسباب المحتملة:**\n"
                f"• بيانات التحويل غير صحيحة\n"
                f"• لم يتم العثور على التحويل\n"
                f"• المشكلة فنية\n\n"
                f"📞 **للمساعدة تواصل مع الدعم.**",
                parse_mode="Markdown"
            )
            logger.info(f"✅ تم إرسال رسالة الرفض للمستخدم {user_id}")
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة الرفض للمستخدم {user_id}: {e}")
        
        # تحديث رسالة المجموعة مع توقيت دمشق
        try:
            # التحقق من نوع الرسالة (صورة أو نص)
            current_text = callback.message.text or callback.message.caption or ""
            
            # إضافة نص الرفض مع التاريخ
            new_text = current_text + f"\n\n❌ **تم رفض الطلب**\n📅 **بتاريخ:** {damascus_time}"
            
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=new_text,
                    reply_markup=None
                )
            else:
                await callback.message.edit_text(
                    text=new_text,
                    reply_markup=None
                )
            logger.info(f"✅ تم تحديث رسالة المجموعة للرفض")
        except Exception as e:
            logger.error(f"❌ فشل تحديث رسالة المجموعة: {e}")
        
        await callback.answer("❌ تم رفض الطلب")
        
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الشحن: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

# معالجة طلبات التطبيقات من المجموعة
@router.callback_query(F.data.startswith("appr_order_"))
async def approve_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """موافقة على طلب تطبيق من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.id = $1
            ''', order_id)
            
            if order:
                # تحديث حالة الطلب إلى processing
                await conn.execute(
                    "UPDATE orders SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                    order_id
                )
                
                # جلب نقاط الطلب (التي أضيفت بالفعل عند إنشاء الطلب)
                points = order['points_earned'] or 0
                
                # إرسال إشعار للمستخدم (بدون إضافة نقاط جديدة)
                try:
                    message_text = (
                        f"✅ تمت الموافقة على طلبك #{order_id}\n\n"
                        f"📱 التطبيق: {order['app_name']}\n"
                        f"📦 الكمية: {order['quantity']}\n"
                        f"🎯 المستهدف: {order['target_id']}\n"
                        f"⭐ نقاط مكتسبة: +{points}\n\n"
                        f"⏳ جاري تنفيذ طلبك عبر النظام..."
                    )
                    await bot.send_message(order['user_id'], message_text)
                    logger.info(f"✅ تم إرسال رسالة الموافقة للمستخدم {order['user_id']}")
                except Exception as e:
                    logger.error(f"❌ فشل إرسال رسالة للمستخدم: {e}")
                
                # تحديث رسالة المجموعة
                builder = InlineKeyboardBuilder()
                builder.row(
                    types.InlineKeyboardButton(
                        text="✅ تم التنفيذ", 
                        callback_data=f"compl_order_{order_id}"
                    ),
                    types.InlineKeyboardButton(
                        text="❌ تعذر التنفيذ", 
                        callback_data=f"fail_order_{order_id}"
                    ),
                    width=2
                )
                
                # تعديل رسالة المجموعة
                new_text = callback.message.text + "\n\n🔄 **جاري التنفيذ...**"
                await callback.message.edit_text(new_text, reply_markup=builder.as_markup())
                
                await callback.answer("✅ تمت الموافقة على الطلب")
            else:
                await callback.answer("❌ الطلب غير موجود", show_alert=True)
                
    except Exception as e:
        logger.error(f"❌ خطأ في موافقة الطلب: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("reje_order_"))
async def reject_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """رفض طلب تطبيق من المجموعة"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow(
                "SELECT user_id, total_amount_syp FROM orders WHERE id = $1",
                order_id
            )
            
            if order:
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                    order['total_amount_syp'], order['user_id']
                )
                
                await conn.execute(
                    "UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                    order_id
                )
                
                try:
                    await bot.send_message(
                        order['user_id'],
                        f"❌ **تم رفض طلبك #{order_id}**\n\n"
                        f"💰 **تم إعادة:** {order['total_amount_syp']:,.0f} ل.س لرصيدك\n\n"
                        f"🔸 **الأسباب المحتملة:**\n"
                        "• مشكلة في معلومات الحساب المستهدف\n"
                        "• الخدمة غير متوفرة حالياً\n"
                        "• مشكلة فنية في النظام\n\n"
                        f"📞 **للمساعدة تواصل مع الدعم.**",
                        parse_mode="Markdown"
                    )
                except:
                    pass
                
                await callback.message.edit_text(
                    callback.message.text + "\n\n❌ **تم رفض الطلب وإعادة الرصيد**",
                    reply_markup=None
                )
            else:
                await callback.answer("الطلب غير موجود", show_alert=True)
                
    except Exception as e:
        logger.error(f"❌ خطأ في رفض الطلب: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("compl_order_"))
async def complete_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """تأكيد تنفيذ الطلب من المجموعة - مع إضافة النقاط"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow('''
                SELECT o.*, u.user_id, u.username
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.id = $1
            ''', order_id)
            
            if not order:
                await callback.answer("❌ الطلب غير موجود", show_alert=True)
                return
            
            # جلب عدد النقاط من الإعدادات
            from database import get_points_per_order
            points = await get_points_per_order(db_pool)
            
            # تحديث حالة الطلب إلى completed
            await conn.execute(
                "UPDATE orders SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                order_id
            )
            
            # ========== إضافة النقاط للمستخدم هنا ==========
            # تحديث نقاط المستخدم
            await conn.execute(
                "UPDATE users SET total_points = total_points + $1, total_points_earned = total_points_earned + $1 WHERE user_id = $2",
                points, order['user_id']
            )
            
            # تحديث نقاط الطلب في جدول orders
            await conn.execute(
                "UPDATE orders SET points_earned = $1 WHERE id = $2",
                points, order_id
            )
            
            # تسجيل في سجل النقاط
            await conn.execute('''
                INSERT INTO points_history (user_id, points, action, description, created_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ''', order['user_id'], points, 'order_completed', f'نقاط من طلب مكتمل #{order_id}')
            
            logger.info(f"✅ تم إضافة {points} نقاط للمستخدم {order['user_id']} من الطلب المكتمل {order_id}")
            
            # ========== تحديث مستوى VIP مع تصحيح ==========
            from database import update_user_vip
            vip_info = await update_user_vip(db_pool, order['user_id'])
            
            # 🟢🟢🟢 سطور التصحيح 🟢🟢🟢
            logger.info(f"🔍 VIP UPDATE - User: {order['user_id']}")
            logger.info(f"🔍 VIP INFO: {vip_info}")
            
            # حساب إجمالي مشتريات المستخدم للتحقق
            total_spent = await conn.fetchval('''
                SELECT COALESCE(SUM(total_amount_syp), 0) 
                FROM orders 
                WHERE user_id = $1 AND status = 'completed'
            ''', order['user_id'])
            
            logger.info(f"🔍 TOTAL SPENT: {total_spent} SYP")
            # 🟢🟢🟢 نهاية التصحيح 🟢🟢🟢
            
            # جلب معلومات VIP للعرض
            if vip_info:
                vip_discount = vip_info.get('discount', 0)
                vip_level = vip_info.get('level', 0)
            else:
                vip_discount = 0
                vip_level = 0
                
            vip_icons = ["🟢", "🔵", "🟣", "🟡", "🔴"]
            vip_icon = vip_icons[vip_level] if vip_level < len(vip_icons) else "🟢"
            
            # حساب رصيد النقاط الجديد
            user_points = await conn.fetchval(
                "SELECT total_points FROM users WHERE user_id = $1",
                order['user_id']
            ) or 0
            
            # إرسال إشعار للمستخدم
            try:
                await bot.send_message(
                    order['user_id'],
                    f"✅ **تم تنفيذ طلبك #{order_id} بنجاح!**\n\n"
                    f"📱 التطبيق: {order['app_name']}\n"
                    f"⭐ نقاط مكتسبة: +{points}\n"
                    f"💰 رصيد النقاط الجديد: {user_points}\n"
                    f"👑 مستواك: {vip_icon} VIP {vip_level} (خصم {vip_discount}%)\n\n"
                    f"شكراً لاستخدامك خدماتنا"
                )
            except Exception as e:
                logger.error(f"❌ فشل إرسال رسالة للمستخدم: {e}")
            
            # إخفاء رسالة المجموعة
            await callback.message.edit_text(
                callback.message.text.replace("🔄 **جاري التنفيذ...**", "") + "\n\n✅ **تم التنفيذ بنجاح**",
                reply_markup=None
            )
            
            await callback.answer("✅ تم تأكيد التنفيذ")
                
    except Exception as e:
        logger.error(f"❌ خطأ في تأكيد التنفيذ: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("fail_order_"))
async def fail_order_from_group(callback: types.CallbackQuery, db_pool, bot: Bot):
    """تعذر تنفيذ الطلب من المجموعة - بدون إضافة نقاط"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            order = await conn.fetchrow(
                "SELECT user_id, total_amount_syp FROM orders WHERE id = $1",
                order_id
            )
            
            if order:
                # إعادة الرصيد للمستخدم (النقاط ما تضاف)
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                    order['total_amount_syp'], order['user_id']
                )
                
                # تحديث حالة الطلب إلى failed
                await conn.execute(
                    "UPDATE orders SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                    order_id
                )
                
                # إرسال إشعار للمستخدم
                try:
                    await bot.send_message(
                        order['user_id'],
                        f"❌ **تعذر تنفيذ طلبك #{order_id}**\n\n"
                        f"💰 تم إعادة {order['total_amount_syp']:,.0f} ل.س لرصيدك\n"
                        f"⭐ لم تتم إضافة نقاط لهذا الطلب\n\n"
                        f"نعتذر عن الإزعاج، يرجى المحاولة لاحقاً"
                    )
                except Exception as e:
                    logger.error(f"❌ فشل إرسال رسالة للمستخدم: {e}")
                
                # إخفاء رسالة المجموعة
                await callback.message.edit_text(
                    callback.message.text.replace("🔄 **جاري التنفيذ...**", "") + "\n\n❌ **تعذر التنفيذ وتم إعادة الرصيد**",
                    reply_markup=None
                )
                
                await callback.answer("❌ تم تحديث حالة الطلب")
            else:
                await callback.answer("❌ الطلب غير موجود", show_alert=True)
                
    except Exception as e:
        logger.error(f"❌ خطأ في تعذر التنفيذ: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)
