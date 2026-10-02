# admin/categories.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from utils import is_admin, safe_edit_message, get_state_data_field, is_owner
from handlers.keyboards import get_confirmation_keyboard
from cache import cached, clear_cache  # ✅ استيراد الكاش

logger = logging.getLogger(__name__)
router = Router(name="admin_categories")

class CategoryStates(StatesGroup):
    waiting_category_name = State()
    waiting_category_display_name = State()
    waiting_category_icon = State()
    waiting_category_sort = State()
    waiting_edit_category_value = State()

# ✅ كاش للأقسام (5 دقائق)
@cached(ttl=300, key_prefix="categories")
async def get_cached_categories(db_pool):
    """جلب جميع الأقسام مع كاش 5 دقائق"""
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM categories ORDER BY sort_order")

# ✅ كاش لعدد المنتجات في كل قسم
@cached(ttl=60, key_prefix="category_products_count")
async def get_cached_products_count(db_pool, category_id):
    """جلب عدد المنتجات في قسم معين مع كاش دقيقة"""
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM applications WHERE category_id = $1",
            category_id
        ) or 0

# ============= إدارة الأقسام الرئيسية =============

@router.callback_query(F.data == "manage_categories")
async def manage_categories_menu(callback: types.CallbackQuery, db_pool):
    """عرض قائمة الأقسام"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    categories = await get_cached_categories(db_pool)
    
    text = "📁 **إدارة الأقسام**\n\n"
    
    if not categories:
        text += "⚠️ لا توجد أقسام حالياً."
    else:
        for cat in categories:
            # جلب عدد المنتجات في هذا القسم
            products_count = await get_cached_products_count(db_pool, cat['id'])
            text += f"{cat['icon']} **{cat['display_name']}**\n"
            text += f"   🆔: {cat['id']} | ترتيب: {cat['sort_order']}\n"
            text += f"   الاسم الداخلي: `{cat['name']}`\n"
            text += f"   📦 عدد المنتجات: {products_count}\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ إضافة قسم جديد", callback_data="add_category"))
    builder.row(types.InlineKeyboardButton(text="✏️ تعديل قسم", callback_data="edit_category"))
    builder.row(types.InlineKeyboardButton(text="🗑️ حذف قسم", callback_data="delete_category"))
    builder.row(types.InlineKeyboardButton(text="🔄 ترتيب الأقسام", callback_data="reorder_categories"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin"))
    
    await safe_edit_message(
        callback.message,
        text,
        reply_markup=builder.as_markup()
    )

# ============= إضافة قسم جديد =============

@router.callback_query(F.data == "add_category")
async def add_category_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء إضافة قسم جديد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await safe_edit_message(
        callback.message,
        "➕ **إضافة قسم جديد - الخطوة 1/4**\n\n"
        "📝 **أدخل الاسم الداخلي للقسم:**\n"
        "(يستخدم في البرمجة، بدون مسافات)\n"
        "مثال: `games`\nمثال: `chat_apps`\n\n"
        "❌ أرسل /cancel للإلغاء"
    )
    await state.set_state(CategoryStates.waiting_category_name)

@router.message(CategoryStates.waiting_category_name)
async def add_category_step_name(message: types.Message, state: FSMContext):
    """استلام الاسم الداخلي للقسم"""
    if not is_admin(message.from_user.id):
        return
    
    name = message.text.strip()
    if not name or ' ' in name:
        await message.answer(
            "❌ الاسم يجب أن يكون بدون مسافات. استخدم شرطة سفلية `_` بدلاً من المسافة.\n"
            "مثال: `games` أو `chat_apps`\n\nأدخل اسم داخلي صحيح:",
            
            parse_mode="Markdown"
        )
        return
    
    await state.update_data(category_name=name)
    await message.answer(
        "➕ **إضافة قسم جديد - الخطوة 2/4**\n\n"
        f"📝 **أدخل الاسم المعروض للقسم:**\n"
        f"(الاسم الذي سيظهر للمستخدمين)\n"
        f"الاسم الداخلي: **{name}**\n\n"
        f"مثال: `🎮 ألعاب`\nمثال: `💬 تطبيقات دردشة`\n\n"
        f"أو أرسل /cancel للإلغاء",
        
        parse_mode="Markdown"
    )
    await state.set_state(CategoryStates.waiting_category_display_name)

@router.message(CategoryStates.waiting_category_display_name)
async def add_category_step_display_name(message: types.Message, state: FSMContext):
    """استلام الاسم المعروض للقسم"""
    if not is_admin(message.from_user.id):
        return
    
    display_name = message.text.strip()
    if len(display_name) < 2:
        await message.answer("❌ الاسم المعروض قصير جداً. أدخل اسم أطول:", reply_markup=get_cancel_keyboard())
        return
    
    await state.update_data(category_display_name=display_name)
    await message.answer(
        "➕ **إضافة قسم جديد - الخطوة 3/4**\n\n"
        "🎨 **أدخل الأيقونة للقسم:**\n"
        f"الاسم الداخلي: **{await get_state_data_field(state, 'category_name')}**\n"
        f"الاسم المعروض: **{display_name}**\n\n"
        "مثال: `🎮` للألعاب\nمثال: `💬` للدردشة\n"
        "أو اتركه فارغاً للايقونة الافتراضية `📁`\n\n"
        "أو أرسل /cancel للإلغاء",
    
        parse_mode="Markdown"
    )
    await state.set_state(CategoryStates.waiting_category_icon)

@router.message(CategoryStates.waiting_category_icon)
async def add_category_step_icon(message: types.Message, state: FSMContext):
    """استلام الأيقونة للقسم"""
    if not is_admin(message.from_user.id):
        return
    
    icon = message.text.strip() if message.text and message.text != "-" else "📁"
    await state.update_data(category_icon=icon)
    
    await message.answer(
        "➕ **إضافة قسم جديد - الخطوة 4/4**\n\n"
        "🔢 **أدخل ترتيب القسم (رقم):**\n"
        "الأقسام تظهر حسب الترتيب تصاعدياً\n"
        "مثال: `1` (يظهر أولاً)\nمثال: `5` (يظهر خامساً)\n\n"
        "أرسل /cancel للإلغاء",
    
        parse_mode="Markdown"
    )
    await state.set_state(CategoryStates.waiting_category_sort)

@router.message(CategoryStates.waiting_category_sort)
async def add_category_step_sort(message: types.Message, state: FSMContext, db_pool):
    """استلام ترتيب القسم وحفظه"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        sort_order = int(message.text.strip())
    except ValueError:
        await message.answer("❌ يرجى إدخال رقم صحيح للترتيب:", reply_markup=get_cancel_keyboard())
        return
    
    data = await state.get_data()
    name = data['category_name']
    display_name = data['category_display_name']
    icon = data.get('category_icon', '📁')
    
    async with db_pool.acquire() as conn:
        # التحقق من عدم وجود اسم مكرر
        existing = await conn.fetchval("SELECT id FROM categories WHERE name = $1", name)
        if existing:
            await message.answer(
                f"❌ قسم باسم **{name}** موجود مسبقاً.\nالرجاء استخدام اسم داخلي مختلف.",
                
                parse_mode="Markdown"
            )
            await state.clear()
            return
        
        await conn.execute('''
            INSERT INTO categories (name, display_name, icon, sort_order)
            VALUES ($1, $2, $3, $4)
        ''', name, display_name, icon, sort_order)
        
        # ✅ مسح الكاش بعد إضافة قسم جديد
        clear_cache("categories")
    
    await message.answer(
        f"✅ **تم إضافة القسم بنجاح!**\n\n"
        f"• الاسم الداخلي: `{name}`\n"
        f"• الاسم المعروض: {display_name}\n"
        f"• الأيقونة: {icon}\n"
        f"• الترتيب: {sort_order}",
        parse_mode="Markdown"
    )
    await state.clear()

# ============= عرض قائمة الأقسام للتعديل =============

@router.callback_query(F.data == "edit_category")
async def edit_category_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة الأقسام للتعديل"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    categories = await get_cached_categories(db_pool)
    
    if not categories:
        return await callback.answer("❌ لا توجد أقسام", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        products_count = await get_cached_products_count(db_pool, cat['id'])
        builder.row(types.InlineKeyboardButton(
            text=f"✏️ {cat['icon']} {cat['display_name']} ({products_count} منتج)",
            callback_data=f"edit_cat_{cat['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_categories"))
    await safe_edit_message(
        callback.message,
        "✏️ **اختر القسم للتعديل:**",
        reply_markup=builder.as_markup()
    )

# ============= دوال التعديل =============

@router.callback_query(F.data.startswith("edit_cat_display_"))
async def edit_category_display_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تعديل الاسم المعروض"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    try:
        cat_id = int(callback.data.split("_")[3])
        await state.update_data(edit_field='display_name', category_id=cat_id)
        
        await callback.message.answer(
            "📝 **أدخل الاسم المعروض الجديد:**\n\n"
            "مثال: `🎮 ألعاب جديدة`\n"
            "مثال: `💬 تطبيقات دردشة`\n\n"
            " أرسل /cancel للإلغاء",
            
            parse_mode="Markdown"
        )
        await state.set_state(CategoryStates.waiting_edit_category_value)
    except Exception as e:
        logger.error(f"خطأ في edit_category_display_start: {e}")
        await callback.answer("❌ حدث خطأ", show_alert=True)


@router.callback_query(F.data.startswith("edit_cat_icon_"))
async def edit_category_icon_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تعديل الأيقونة"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    try:
        cat_id = int(callback.data.split("_")[3])
        await state.update_data(edit_field='icon', category_id=cat_id)
        
        await callback.message.answer(
            "🎨 **أدخل الأيقونة الجديدة:**\n\n"
            "مثال: `🎮`\n"
            "مثال: `💬`\n"
            "مثال: `📱`\n"
            "مثال: `🎯`\n\n"
            " أرسل /cancel للإلغاء",
            
            parse_mode="Markdown"
        )
        await state.set_state(CategoryStates.waiting_edit_category_value)
    except Exception as e:
        logger.error(f"خطأ في edit_category_icon_start: {e}")
        await callback.answer("❌ حدث خطأ", show_alert=True)


@router.callback_query(F.data.startswith("edit_cat_sort_"))
async def edit_category_sort_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تعديل الترتيب"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    try:
        cat_id = int(callback.data.split("_")[3])
        await state.update_data(edit_field='sort_order', category_id=cat_id)
        
        await callback.message.answer(
            "🔢 **أدخل الترتيب الجديد (رقم):**\n\n"
            "مثال: `1` (يظهر أولاً)\n"
            "مثال: `5` (يظهر خامساً)\n\n"
            "📌 الأرقام الأصغر تظهر أولاً\n\n"
            " أرسل /cancel للإلغاء",
            
            parse_mode="Markdown"
        )
        await state.set_state(CategoryStates.waiting_edit_category_value)
    except Exception as e:
        logger.error(f"خطأ في edit_category_sort_start: {e}")
        await callback.answer("❌ حدث خطأ", show_alert=True)


@router.callback_query(F.data.startswith("edit_cat_"))
async def edit_category_menu(callback: types.CallbackQuery, state: FSMContext, db_pool):
    """عرض قائمة تعديل القسم"""
    # ✅ نتأكد إنه مش من الأنواع المحددة
    if callback.data.startswith(("edit_cat_display_", "edit_cat_icon_", "edit_cat_sort_")):
        return
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    parts = callback.data.split("_")
    if len(parts) != 3:
        return
    
    cat_id = int(parts[2])
    
    async with db_pool.acquire() as conn:
        category = await conn.fetchrow("SELECT * FROM categories WHERE id = $1", cat_id)
    
    if not category:
        return await callback.answer("❌ القسم غير موجود", show_alert=True)
    
    await state.update_data(category_id=cat_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text=f"📝 تعديل الاسم المعروض (الحالي: {category['display_name']})", 
        callback_data=f"edit_cat_display_{cat_id}"
    ))
    builder.row(types.InlineKeyboardButton(
        text=f"🎨 تعديل الأيقونة (الحالية: {category['icon']})", 
        callback_data=f"edit_cat_icon_{cat_id}"
    ))
    builder.row(types.InlineKeyboardButton(
        text=f"🔢 تعديل الترتيب (الحالي: {category['sort_order']})", 
        callback_data=f"edit_cat_sort_{cat_id}"
    ))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="edit_category"))
    
    text = (
        f"✏️ **تعديل القسم**\n\n"
        f"**البيانات الحالية:**\n"
        f"• الاسم الداخلي: `{category['name']}`\n"
        f"• الاسم المعروض: {category['display_name']}\n"
        f"• الأيقونة: {category['icon']}\n"
        f"• الترتيب: {category['sort_order']}\n\n"
        f"اختر ما تريد تعديله:"
    )
    
    await safe_edit_message(
        callback.message,
        text,
        reply_markup=builder.as_markup()
    )

# ============= حفظ التعديلات =============

@router.message(CategoryStates.waiting_edit_category_value)
async def edit_category_save(message: types.Message, state: FSMContext, db_pool):
    """حفظ التعديل على القسم"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم إلغاء العملية")
        return
    
    data = await state.get_data()
    if not data or 'category_id' not in data or 'edit_field' not in data:
        await state.clear()
        await message.answer("❌ انتهت صلاحية الجلسة. ابدأ من جديد.")
        return
    
    cat_id = data['category_id']
    field = data['edit_field']
    value = message.text.strip()
    
    try:
        # التحقق من صحة المدخلات
        if field == 'display_name':
            if len(value) < 2 or len(value) > 50:
                await message.answer("❌ الاسم يجب أن يكون بين 2 و 50 حرف:", reply_markup=get_cancel_keyboard())
                return
            update_value = value
            field_name = "الاسم المعروض"
            
        elif field == 'icon':
            if len(value) > 10:
                await message.answer("❌ الأيقونة طويلة جداً. استخدم رمز واحد أو رمزين:", reply_markup=get_cancel_keyboard())
                return
            update_value = value if value else "📁"
            field_name = "الأيقونة"
            
        elif field == 'sort_order':
            try:
                sort_val = int(value)
                if sort_val < 0 or sort_val > 999:
                    await message.answer("❌ الرقم خارج النطاق المسموح (0-999):", reply_markup=get_cancel_keyboard())
                    return
                update_value = sort_val
                field_name = "الترتيب"
            except ValueError:
                await message.answer("❌ يرجى إدخال رقم صحيح:", reply_markup=get_cancel_keyboard())
                return
        
        else:
            await message.answer("❌ حقل غير معروف")
            await state.clear()
            return
        
        # تنفيذ التحديث في قاعدة البيانات
        async with db_pool.acquire() as conn:
            # التحقق من وجود القسم
            category_check = await conn.fetchval("SELECT id FROM categories WHERE id = $1", cat_id)
            if not category_check:
                await message.answer("❌ القسم غير موجود!")
                await state.clear()
                return
            
            # تنفيذ التحديث
            await conn.execute(f"UPDATE categories SET {field} = $1 WHERE id = $2", update_value, cat_id)
            
            # جلب البيانات المحدثة
            category = await conn.fetchrow("SELECT * FROM categories WHERE id = $1", cat_id)
        
        # ✅ مسح الكاش بعد التحديث
        clear_cache("categories")
        
        await message.answer(
            f"✅ **تم التحديث بنجاح!**\n\n"
            f"• {field_name} تم تحديثه إلى: **{update_value}**\n"
            f"• القسم: {category['icon']} {category['display_name']}",
            parse_mode="Markdown"
        )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"خطأ في تعديل القسم: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()

# ============= ترتيب الأقسام =============

@router.callback_query(F.data == "reorder_categories")
async def reorder_categories_start(callback: types.CallbackQuery, db_pool):
    """بدء إعادة ترتيب الأقسام"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    categories = await get_cached_categories(db_pool)
    
    text = "🔄 **إعادة ترتيب الأقسام**\n\n"
    text += "الأقسام الحالية بالترتيب:\n"
    
    for cat in categories:
        text += f"{cat['sort_order']}. {cat['icon']} {cat['display_name']}\n"
    
    text += "\n📝 أرسل الترتيب الجديد بالصيغة:\n"
    text += "`المعرف:الترتيب, المعرف:الترتيب`\n"
    text += "مثال: `3:1, 1:2, 2:3`"
    
    await callback.message.answer(text, reply_markup=get_cancel_keyboard())
    # يمكن إضافة حالة FSM هنا إذا أردت

# ============= حذف قسم =============

@router.callback_query(F.data == "delete_category")
async def delete_category_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة الأقسام للحذف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    categories = await get_cached_categories(db_pool)
    
    if not categories:
        return await callback.answer("❌ لا توجد أقسام", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        products_count = await get_cached_products_count(db_pool, cat['id'])
        
        # منع حذف القسم الافتراضي
        if cat['name'] == 'chat_apps':
            text = f"🔒 {cat['icon']} {cat['display_name']} ({products_count} منتج) - افتراضي"
            callback_data = "cannot_delete_default"
        else:
            text = f"🗑️ {cat['icon']} {cat['display_name']} ({products_count} منتج)"
            callback_data = f"del_cat_{cat['id']}"
        
        builder.row(types.InlineKeyboardButton(text=text, callback_data=callback_data))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_categories"))
    await safe_edit_message(
        callback.message,
        "🗑️ **اختر القسم للحذف:**\n\n"
        "⚠️ تحذير: حذف القسم سيؤدي إلى حذف جميع المنتجات المرتبطة به!\n"
        "🔒 الأقسام المقفلة لا يمكن حذفها.",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "cannot_delete_default")
async def cannot_delete_default(callback: types.CallbackQuery):
    """منع حذف القسم الافتراضي"""
    await callback.answer("❌ لا يمكن حذف القسم الافتراضي", show_alert=True)

@router.callback_query(F.data.startswith("del_cat_"))
async def delete_category_confirm(callback: types.CallbackQuery, db_pool):
    """تأكيد حذف القسم"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    try:
        cat_id = int(callback.data.split("_")[2])
        
        async with db_pool.acquire() as conn:
            category = await conn.fetchrow("SELECT * FROM categories WHERE id = $1", cat_id)
            if not category:
                return await callback.answer("❌ القسم غير موجود", show_alert=True)
            
            products_count = await conn.fetchval("SELECT COUNT(*) FROM applications WHERE category_id = $1", cat_id)
            products = []
            if products_count > 0:
                products = await conn.fetch("SELECT name FROM applications WHERE category_id = $1 LIMIT 5", cat_id)
        
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ نعم، احذف نهائياً", callback_data=f"confirm_del_cat_{cat_id}"),
            types.InlineKeyboardButton(text="❌ لا، تراجع", callback_data="delete_category")
        )
        
        warning = ""
        products_list = ""
        if products_count > 0:
            warning = f"\n\n⚠️ **تحذير شديد:** هذا القسم يحتوي على **{products_count} منتج**!"
            if products:
                products_list = "\n\nمنتجات ستُحذف:\n"
                for p in products:
                    products_list += f"• {p['name']}\n"
                if products_count > 5:
                    products_list += f"• ... و{products_count - 5} منتجات أخرى"
        
        await safe_edit_message(
            callback.message,
            f"⚠️ **تأكيد حذف القسم**\n\n"
            f"هل أنت متأكد من حذف هذا القسم نهائياً؟\n\n"
            f"• **القسم:** {category['icon']} {category['display_name']}\n"
            f"• **المعرف:** {cat_id}"
            f"{warning}"
            f"{products_list}\n\n"
            f"**هذا الإجراء لا يمكن التراجع عنه!**",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.error(f"خطأ في delete_category_confirm: {e}")
        await callback.answer("❌ حدث خطأ", show_alert=True)

# admin/categories.py - تحديث دالة delete_category_execute

@router.callback_query(F.data.startswith("confirm_del_cat_"))
async def delete_category_execute(callback: types.CallbackQuery, db_pool):
    """تنفيذ حذف القسم"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    try:
        cat_id = int(callback.data.split("_")[3])
        
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # جلب معلومات القسم قبل الحذف
                category = await conn.fetchrow("SELECT * FROM categories WHERE id = $1", cat_id)
                if not category:
                    return await callback.answer("❌ القسم غير موجود", show_alert=True)
                
                # منع حذف القسم الافتراضي
                if category['name'] == 'chat_apps':
                    return await callback.answer("❌ لا يمكن حذف القسم الافتراضي", show_alert=True)
                
                # ✅ حساب عدد المنتجات قبل الحذف
                products_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM applications WHERE category_id = $1",
                    cat_id
                )
                
                # ✅ حذف المنتجات المرتبطة أولاً
                await conn.execute(
                    "DELETE FROM applications WHERE category_id = $1",
                    cat_id
                )
                
                # ✅ حذف القسم
                await conn.execute(
                    "DELETE FROM categories WHERE id = $1",
                    cat_id
                )
        
        # ✅ مسح الكاش بعد الحذف
        clear_cache("categories")
        clear_cache("category_products_count")
        
        # ✅ رسالة نجاح مع العدد
        await callback.answer(
            f"✅ تم حذف القسم {category['display_name']} و {products_count} منتج بنجاح",
            show_alert=True
        )
        
        # ✅ العودة لقائمة الأقسام
        await delete_category_list(callback, db_pool)
        
    except Exception as e:
        logger.error(f"❌ خطأ في delete_category_execute: {e}")
        await callback.answer(f"❌ حدث خطأ: {str(e)}", show_alert=True)
