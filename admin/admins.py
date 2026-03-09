# admin/admins.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from utils import is_admin, format_datetime, is_owner
from handlers.keyboards import get_confirmation_keyboard
from database.admin import get_all_admins, add_admin, remove_admin, get_admin_info, get_admin_logs
from database.users import get_user_by_id
from cache import cached, clear_cache  # ✅ استيراد الكاش

logger = logging.getLogger(__name__)
router = Router(name="admin_admins")

class AdminManageStates(StatesGroup):
    waiting_admin_id = State()           # للإضافة
    waiting_admin_info_id = State()      # للمعلومات

# ✅ كاش لقائمة المشرفين (دقيقتين)
@cached(ttl=120, key_prefix="admins_list")
async def get_cached_admins(db_pool):
    """جلب قائمة المشرفين مع كاش دقيقتين"""
    return await get_all_admins(db_pool)

# ✅ كاش لمعلومات مشرف محدد (دقيقة واحدة)
@cached(ttl=60, key_prefix="admin_info")
async def get_cached_admin_info(db_pool, admin_id):
    """جلب معلومات مشرف معين مع كاش دقيقة"""
    return await get_admin_info(db_pool, admin_id)

# ✅ كاش لسجل النشاطات (3 دقائق)
@cached(ttl=180, key_prefix="admin_logs")
async def get_cached_admin_logs(db_pool, limit=30):
    """جلب سجل النشاطات مع كاش 3 دقائق"""
    return await get_admin_logs(db_pool, limit)

# إدارة المشرفين
@router.callback_query(F.data == "manage_admins")
async def manage_admins_menu(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المشرفين"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    admins = await get_cached_admins(db_pool)
    
    admins_text = "👑 <b>قائمة المشرفين</b>\n\n"
    for admin in admins:
        role_icon = "👑" if admin['role'] == 'owner' else "🛡️"
        username = f"@{admin['username']}" if admin['username'] else f"ID: {admin['user_id']}"
        name = admin['first_name'] or ""
        admins_text += f"{role_icon} {username}\n   🆔 <code>{admin['user_id']}</code>\n   📝 {name}\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="➕ إضافة مشرف", callback_data="add_admin"),
        types.InlineKeyboardButton(text="❌ إزالة مشرف", callback_data="remove_admin")
    )
    builder.row(
        types.InlineKeyboardButton(text="📋 معلومات مشرف", callback_data="admin_info"),
        types.InlineKeyboardButton(text="📊 سجل النشاطات", callback_data="admin_logs")
    )
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع للوحة التحكم", callback_data="back_to_admin"))
    
    await callback.message.edit_text(admins_text, reply_markup=builder.as_markup(), parse_mode="HTML")

# ============= إضافة مشرف =============

@router.callback_query(F.data == "add_admin")
async def add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء إضافة مشرف جديد"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ التحقق من أن المستخدم هو المالك (owner)
    if not is_owner(callback.from_user.id):
        return await callback.answer("⚠️ فقط المالك يمكنه إضافة مشرفين", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await callback.message.edit_text(
        "👤 <b>إضافة مشرف جديد</b>\n\n"
        "أدخل الآيدي (ID) الخاص بالمستخدم الذي تريد إضافته كمشرف:\n\n"
        "💡 يمكن للمستخدم الحصول على آيديه عبر إرسال /id للبوت\n\n"
        "أو أرسل /cancel للإلغاء",
        parse_mode="HTML"
    )
    await state.set_state(AdminManageStates.waiting_admin_id)

@router.message(AdminManageStates.waiting_admin_id)
async def add_admin_confirm(message: types.Message, state: FSMContext, db_pool):
    """تأكيد إضافة مشرف"""
    if not is_admin(message.from_user.id):
        return
    
    # ✅ التحقق من أن المستخدم هو المالك
    if not is_owner(message.from_user.id):
        await message.answer("⚠️ فقط المالك يمكنه إضافة مشرفين")
        await state.clear()
        return
    
    try:
        new_admin_id = int(message.text.strip())
        
        # ✅ التحقق من أن الآيدي ليس المالك نفسه
        if new_admin_id == message.from_user.id:
            return await message.answer(
                "❌ <b>لا يمكنك إضافة نفسك كمشرف</b> (أنت المالك بالفعل)",
                reply_markup=get_cancel_keyboard(),
                parse_mode="HTML"
            )
        
        user = await get_user_by_id(db_pool, new_admin_id)
        
        if not user:
            return await message.answer(
                "❌ <b>المستخدم غير موجود</b> في قاعدة البيانات.\n"
                "يجب على المستخدم استخدام البوت مرة واحدة على الأقل.\n\n"
                "أو أرسل /cancel للإلغاء",
                reply_markup=get_cancel_keyboard(),
                parse_mode="HTML"
            )
        
        success, msg = await add_admin(db_pool, new_admin_id, message.from_user.id)
        
        if success:
            # ✅ مسح الكاش بعد إضافة مشرف
            clear_cache("admins_list")
            clear_cache(f"admin_info:{new_admin_id}")
            
            await message.answer(
                f"✅ <b>تمت إضافة المشرف بنجاح!</b>\n\n"
                f"👤 المستخدم: @{user['username'] or 'غير معروف'}\n"
                f"🆔 الآيدي: <code>{new_admin_id}</code>\n\n"
                f"🔸 ملاحظة: قد تحتاج إلى إعادة تشغيل البوت لتفعيل الصلاحيات.",
                parse_mode="HTML"
            )
            
            try:
                await message.bot.send_message(
                    new_admin_id,
                    f"🎉 <b>مبروك! تمت إضافتك كمشرف في البوت</b>\n\n"
                    f"🔸 يمكنك الآن استخدام لوحة التحكم عبر إرسال /admin\n"
                    f"👤 تمت الإضافة بواسطة: @{message.from_user.username}",
                    parse_mode="HTML"
                )
            except:
                pass
        else:
            await message.answer(f"❌ {msg}", parse_mode="HTML")
        
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إدخال آيدي صحيح (أرقام فقط):", reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}", parse_mode="HTML")
        await state.clear()

# ============= إزالة مشرف =============

@router.callback_query(F.data == "remove_admin")
async def remove_admin_list(callback: types.CallbackQuery, db_pool):
    """عرض قائمة المشرفين للإزالة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ التحقق من أن المستخدم هو المالك
    if not is_owner(callback.from_user.id):
        return await callback.answer("⚠️ فقط المالك يمكنه إزالة مشرفين", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    admins = await get_cached_admins(db_pool)
    
    # فلترة المشرفين: نعرض فقط المشرفين العاديين (admin) وليس المالك (owner)
    admins_to_show = [a for a in admins if a['role'] != 'owner']
    
    if not admins_to_show:
        await callback.answer("❌ لا يوجد مشرفين للإزالة", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    
    for admin in admins_to_show:
        username = f"@{admin['username']}" if admin['username'] else f"ID: {admin['user_id']}"
        builder.row(types.InlineKeyboardButton(
            text=f"❌ {username}",
            callback_data=f"remove_admin_{admin['user_id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_admins"))
    
    await callback.message.edit_text(
        "🗑️ <b>اختر المشرف للإزالة:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("remove_admin_"))
async def remove_admin_confirm(callback: types.CallbackQuery, db_pool):
    """تأكيد إزالة مشرف"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    admin_id = int(callback.data.split("_")[2])
    
    # ✅ التحقق من أن المستخدم لا يحاول إزالة نفسه
    if admin_id == callback.from_user.id:
        return await callback.answer("❌ لا يمكنك إزالة نفسك من المشرفين", show_alert=True)
    
    user = await get_user_by_id(db_pool, admin_id)
    username = user['username'] if user else str(admin_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ نعم، أزله", callback_data=f"confirm_remove_admin_{admin_id}"),
        types.InlineKeyboardButton(text="❌ لا", callback_data="manage_admins")
    )
    
    await callback.message.edit_text(
        f"⚠️ <b>تأكيد إزالة مشرف</b>\n\n"
        f"هل أنت متأكد من إزالة @{username} من قائمة المشرفين؟",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("confirm_remove_admin_"))
async def remove_admin_execute(callback: types.CallbackQuery, db_pool):
    """تنفيذ إزالة المشرف"""
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    admin_id = int(callback.data.split("_")[3])
    
    # ✅ التحقق من أن المستخدم لا يحاول إزالة نفسه
    if admin_id == callback.from_user.id:
        return await callback.answer("❌ لا يمكنك إزالة نفسك من المشرفين", show_alert=True)
    
    success, msg = await remove_admin(db_pool, admin_id, callback.from_user.id)
    
    if success:
        # ✅ مسح الكاش بعد إزالة مشرف
        clear_cache("admins_list")
        clear_cache(f"admin_info:{admin_id}")
        clear_cache("admin_logs")
        
        await callback.answer("✅ تمت إزالة المشرف بنجاح")
        await callback.message.edit_text("✅ <b>تمت إزالة المشرف بنجاح</b>", parse_mode="HTML")
        
        # إشعار المشرف الذي تمت إزالته
        try:
            await callback.bot.send_message(
                admin_id,
                f"⚠️ <b>تمت إزالتك من قائمة المشرفين</b>\n\n"
                f"👤 تمت الإزالة بواسطة: @{callback.from_user.username}\n"
                f"📞 للاستفسار، تواصل مع المالك.",
                parse_mode="HTML"
            )
        except:
            pass
    else:
        await callback.answer(f"❌ {msg}", show_alert=True)

# ============= معلومات مشرف =============

@router.callback_query(F.data == "admin_info")
async def admin_info_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء البحث عن معلومات مشرف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    await callback.message.edit_text(
        "👤 <b>أدخل آيدي المشرف للحصول على معلوماته:</b>\n\n"
        "أو أرسل /cancel للإلغاء",
        parse_mode="HTML"
    )
    
    await callback.message.answer(
        "أدخل الآيدي الآن:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(AdminManageStates.waiting_admin_info_id)


@router.message(AdminManageStates.waiting_admin_info_id)
async def admin_info_show(message: types.Message, state: FSMContext, db_pool):
    """عرض معلومات المشرف"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        admin_id = int(message.text.strip())
        
        # ✅ استخدام الكاش
        info = await get_cached_admin_info(db_pool, admin_id)
        
        if not info:
            await message.answer("❌ المشرف غير موجود أو ليس لديه صلاحيات", parse_mode="HTML")
            await state.clear()
            return
        
        user = info['user']
        stats = info['stats']
        role_icon = "👑" if info['role'] == 'owner' else "🛡️"
        
        # تنسيق آخر النشاطات
        recent_text = ""
        if info['recent_actions']:
            recent_text = "\n📋 <b>آخر النشاطات:</b>\n"
            for action in info['recent_actions'][:5]:
                date = format_datetime(action['created_at'], "%Y-%m-%d %H:%M")
                action_name = {
                    'add_admin': '➕ إضافة مشرف',
                    'remove_admin': '➖ إزالة مشرف',
                    'approve_deposit': '✅ موافقة شحن',
                    'reject_deposit': '❌ رفض شحن',
                    'approve_order': '✅ موافقة طلب',
                    'reject_order': '❌ رفض طلب',
                    'broadcast': '📢 رسالة جماعية'
                }.get(action['action'], action['action'])
                recent_text += f"• {action_name} - {date}\n"
        
        text = (
            f"{role_icon} <b>معلومات المشرف</b>\n\n"
            f"🆔 <b>الآيدي:</b> <code>{user['user_id']}</code>\n"
            f"👤 <b>اليوزر:</b> @{user['username'] or 'غير معروف'}\n"
            f"📝 <b>الاسم:</b> {user.get('first_name', '')} {user.get('last_name', '')}\n"
            f"👑 <b>الصلاحية:</b> {info['role']}\n\n"
            f"📊 <b>إحصائيات:</b>\n"
            f"• عدد الموافقات: {stats.get('approvals', 0)}\n"
            f"• عدد الرفض: {stats.get('rejections', 0)}\n"
            f"• مشرفين أضافهم: {stats.get('admins_added', 0)}\n"
            f"• مشرفين أزالهم: {stats.get('admins_removed', 0)}\n"
            f"• إجمالي النشاطات: {stats.get('total_actions', 0)}\n"
            f"{recent_text}"
        )
        
        await message.answer(text, parse_mode="HTML")
        await state.clear()
        
    except ValueError:
        await message.answer("❌ يرجى إدخال آيدي صحيح (أرقام فقط)", parse_mode="HTML")
        await state.clear()
    except Exception as e:
        logger.error(f"خطأ في معلومات المشرف: {e}")
        await message.answer(f"❌ حدث خطأ: {str(e)}", parse_mode="HTML")
        await state.clear()


# ============= سجل النشاطات =============

@router.callback_query(F.data == "admin_logs")
async def admin_logs_show(callback: types.CallbackQuery, db_pool):
    """عرض سجل نشاطات المشرفين"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ استخدام الكاش
    logs = await get_cached_admin_logs(db_pool, 30)
    
    if not logs:
        await callback.answer("📭 لا توجد نشاطات مسجلة", show_alert=True)
        return
    
    text = "📊 <b>سجل نشاطات المشرفين</b>\n\n"
    
    for log in logs[:20]:  # عرض أول 20 فقط
        date = format_datetime(log['created_at'], "%Y-%m-%d %H:%M")
        username = f"@{log['username']}" if log['username'] else f"ID: {log['user_id']}"
        
        action_names = {
            'add_admin': '➕ إضافة مشرف',
            'remove_admin': '➖ إزالة مشرف',
            'approve_deposit': '✅ موافقة شحن',
            'reject_deposit': '❌ رفض شحن',
            'approve_order': '✅ موافقة طلب',
            'reject_order': '❌ رفض طلب',
            'approve_redemption': '✅ موافقة استرداد',
            'reject_redemption': '❌ رفض استرداد',
            'broadcast': '📢 رسالة جماعية'
        }
        
        action_text = action_names.get(log['action'], log['action'])
        
        text += f"• {username}\n"
        text += f"  {action_text} - {date}\n"
        text += f"  📝 {log['details']}\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 تحديث", callback_data="refresh_admin_logs"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="manage_admins"))
    
    await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "refresh_admin_logs")
async def refresh_admin_logs(callback: types.CallbackQuery, db_pool):
    """تحديث سجل النشاطات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    # ✅ إطفاء الزر فوراً
    await callback.answer()
    
    # ✅ مسح الكاش وجلب بيانات جديدة
    clear_cache("admin_logs")
    await admin_logs_show(callback, db_pool)


# ============= معالج المدخلات الخاطئة =============

@router.message(AdminManageStates.waiting_admin_id)
@router.message(AdminManageStates.waiting_admin_info_id)
async def wrong_input_handler(message: types.Message, state: FSMContext):
    """معالج المدخلات الخاطئة"""
    if message.text in ["/cancel", "/الغاء", "❌ إلغاء"]:
        await state.clear()
        await message.answer("✅ تم الإلغاء", reply_markup=get_cancel_keyboard())
        return
    
    await message.answer(
        "❌ يرجى إدخال آيدي صحيح (أرقام فقط)\nأو أرسل /cancel للإلغاء",
        reply_markup=get_cancel_keyboard()
    )
