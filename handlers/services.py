import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from api.client import get_api_client

logger = logging.getLogger(__name__)
router = Router()

# ================= سبعة: إعدادات مجموعة الإدارة =================
# ⚠️ ضع هنا آي دي مجموعة الإدارة الخاصة بك (غالباً تبدأ بـ -100)
ADMIN_GROUP_ID = -1004306551609 
# ===============================================================

@router.callback_query(F.data == "services_menu")
async def show_categories(callback: CallbackQuery, db_pool):
    """عرض قائمة الأقسام الرئيسية"""
    async with db_pool.acquire() as conn:
        categories = await conn.fetch("SELECT id, display_name, icon FROM categories ORDER BY sort_order ASC")
    
    if not categories:
        await callback.message.edit_text("❌ لا توجد أقسام متاحة حالياً. يجدر بالإدارة إجراء مزامنة للخدمات.")
        return

    keyboard = []
    for cat in categories:
        icon = cat['icon'] or '📁'
        keyboard.append([InlineKeyboardButton(text=f"{icon} {cat['display_name']}", callback_data=f"cat_{cat['id']}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")])
    
    await callback.message.edit_text(
        "📂 **اختر القسم المطلوب لتصفح الخدمات المتاحة:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("cat_"))
async def show_applications(callback: CallbackQuery, db_pool):
    """عرض الخدمات/التطبيقات التابعة لقسم معين"""
    cat_id = int(callback.data.split("_")[1])
    
    async with db_pool.acquire() as conn:
        apps = await conn.fetch("SELECT id, name, unit_price_usd, profit_percentage FROM applications WHERE category_id = $1 AND is_active = TRUE", cat_id)
        cat_name = await conn.fetchval("SELECT display_name FROM categories WHERE id = $1", cat_id)

    if not apps:
        await callback.query.answer("❌ لا توجد خدمات متاحة في هذا القسم حالياً.", show_alert=True)
        return

    keyboard = []
    for app in apps:
        # حساب السعر النهائي بالليرة أو العملة المعتمدة بناءً على سعر الأساس والربح
        base_price = float(app['unit_price_usd'])
        profit = float(app['profit_percentage'])
        final_price = base_price * (1 + profit / 100)
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"{app['name']} (السعر: {final_price:.2f})", 
                callback_data=f"app_{app['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 رجوع للأقسام", callback_data="services_menu")])
    
    await callback.message.edit_text(
        f"📱 **الخدمات التابعة لـ ({cat_name}):**\nاختر الخدمة المطلوبة:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("app_"))
async def select_application(callback: CallbackQuery, state: FSMContext):
    """تحديد الخدمة وطلب إدخال المعرف (Player ID أو رقم الحساب)"""
    app_id = int(callback.data.split("_")[1])
    
    await state.update_data(selected_app_id=app_id)
    
    # هنا يمكنك توجيه المستخدم لإدخال الـ ID الخاص باللعبة أو الخدمة
    await callback.message.edit_text(
        "🆔 **يرجى إرسال معرف اللاعب (Player ID) أو الحساب المراد الشحن له:**\n\n*(أرسل المعرف في رسالة نصية)*",
        parse_mode="Markdown"
    )
    # ملاحظة: قم بتفعيل حالة الـ FSM الخاصة باستقبال الـ ID لديك هنا

async def execute_order_process(bot: Bot, db_pool, user_id: int, app_id: int, quantity: int, player_id: str):
    """معالجة الطلب: محاولة آلياً عبر API، وإذا فشل يتم تحويله لمجموعة الإدارة تلقائياً"""
    api_client = get_api_client()
    
    async with db_pool.acquire() as conn:
        app_info = await conn.fetchrow("SELECT name, unit_price_usd, profit_percentage, api_service_id FROM applications WHERE id = $1", app_id)
    
    if not app_info or not app_info['api_service_id']:
        await bot.send_message(user_id, "❌ حدث خطأ، هذه الخدمة غير متوفرة أو غير مرتبطة بمورد خارجي.")
        return

    # محاولة إنشاء الطلب آلياً من خلال مسار المورد
    api_result = await api_client.create_order(
        product_id=int(app_info['api_service_id']),
        quantity=quantity,
        player_id=player_id
    )
    
    async with db_pool.acquire() as conn:
        if api_result.get("success"):
            # === 🟢 حالة النجاح الآلي التنفيذ الفوري ===
            order_id = api_result.get("order_id")
            
            await conn.execute(
                "INSERT INTO orders (user_id, app_id, app_name, quantity, target_id, status, api_response) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                user_id, app_id, app_info['name'], quantity, player_id, 'completed', str(api_result.get("raw"))
            )
            
            await bot.send_message(
                user_id,
                f"✅ **تم تنفيذ طلبك بنجاح وتسليمه آلياً!**\n\n"
                f"📦 الخدمة: {app_info['name']}\n"
                f"🆔 المعرف: `{player_id}`\n"
                f"🔖 رقم الطلب: `{order_id}`",
                parse_mode="Markdown"
            )
        else:
            # === 🔴 حالة التعذر / الرفض الآلي -> تحويل يدوي فوري لمجموعة الإدارة ===
            error_reason = api_result.get("error", "خطأ غير معروف من المصدر أو رصيد غير كافي")
            
            # تسجيل الطلب في قاعدة البيانات بحالة معلق يدوي (pending_manual)
            await conn.execute(
                "INSERT INTO orders (user_id, app_id, app_name, quantity, target_id, status, admin_notes) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                user_id, app_id, app_info['name'], quantity, player_id, 'pending_manual', error_reason
            )
            
            # صياغة الرسالة التفصيلية لمجموعة الإدارة
            admin_msg = (
                f"⚠️ **تنبيه: تعذر التنفيذ الآلي وتحويل الطلب إلى يدوي!**\n\n"
                f"👤 **معرف المستخدم:** `[ {user_id} ]`\n"
                f"📦 **الخدمة:** {app_info['name']}\n"
                f"🆔 **معرف اللاعب (ID):** `{player_id}`\n"
                f"🔢 **الكمية:** {quantity}\n"
                f"❌ **سبب التعذر من المورد:** `{error_reason}`\n\n"
                f"💡 *يرجى من الإدارة تنفيذ الطلب يدوياً وإعلام المستخدم.*"
            )
            
            try:
                await bot.send_message(ADMIN_GROUP_ID, admin_msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"⚠️ فشل إرسال تنبيه الطلب اليدوي لمجموعة الإدارة: {e}")
            
            # طمأنة المستخدم بأن طلبه قيد المراجعة اليدوية
            await bot.send_message(
                user_id,
                f"⏳ **تم استلام طلبك وهو قيد المراجعة والتنفيذ اليدوي من قبل الإدارة الآن.**\n\n"
                f"📦 الخدمة: {app_info['name']}\n"
                f"🆔 المعرف: `{player_id}`\n\n"
                f"سيتم إعلامك فور اكتمال الشحن!",
                parse_mode="Markdown"
            )
