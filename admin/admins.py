# admin/admins.py
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from .utils import is_admin, format_message_text, safe_edit_message
from handlers.keyboards import get_cancel_keyboard

logger = logging.getLogger(__name__)
router = Router(name="admin_admins")

class AdminManageStates(StatesGroup):
    waiting_admin_id = State()

# إدارة المشرفين
@router.callback_query(F.data == "manage_admins")
async def manage_admins_menu(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_all_admins
    admins = await get_all_admins(db_pool)
    
    admins_text = "👑 **قائمة المشرفين**\n\n"
    for admin in admins:
        role_icon = "👑" if admin['role'] == 'owner' else "🛡️"
        username = f"@{admin['username']}" if admin['username'] else f"ID: {admin['user_id']}"
        name = admin['first_name'] or ""
        admins_text += f"{role_icon} {username}\n   🆔 `{admin['user_id']}`\n   📝 {name}\n\n"
    
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
    
    await callback.message.edit_text(admins_text, reply_markup=builder.as_markup())

# إضافة مشرف
@router.callback_query(F.data == "add_admin")
async def add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text(
        "👤 **إضافة مشرف جديد**\n\n"
        "أدخل الآيدي (ID) الخاص بالمستخدم الذي تريد إضافته كمشرف:\n\n"
        "💡 يمكن للمستخدم الحصول على آيديه عبر إرسال /id للبوت\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    await state.set_state(AdminManageStates.waiting_admin_id)

@router.message(AdminManageStates.waiting_admin_id)
async def add_admin_confirm(message: types.Message, state: FSMContext, db_pool):
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_admin_id = int(message.text.strip())
        
        from database import add_admin, get_user_by_id
        user = await get_user_by_id(db_pool, new_admin_id)
        
        if not user:
            return await message.answer(
                "❌ المستخدم غير موجود في قاعدة البيانات.\n"
                "يجب على المستخدم استخدام البوت مرة واحدة على الأقل.\n\n"
                "أو أرسل /cancel للإلغاء",
                reply_markup=get_cancel_keyboard()
            )
        
        success, msg = await add_admin(db_pool, new_admin_id, message.from_user.id)
        
        if success:
            await message.answer(
                f"✅ **تمت إضافة المشرف بنجاح!**\n\n"
                f"👤 المستخدم: @{user['username'] or 'غير معروف'}\n"
                f"🆔 الآيدي: `{new_admin_id}`\n\n"
                f"🔸 ملاحظة: قد تحتاج إلى إعادة تشغيل البوت لتفعيل الصلاحيات."
            )
            
            try:
                await message.bot.send_message(
                    new_admin_id,
                    f"🎉 **مبروك! تمت إضافتك كمشرف في البوت**\n\n"
                    f"🔸 يمكنك الآن استخدام لوحة التحكم عبر إرسال /admin\n"
                    f"👤 تمت الإضافة بواسطة: @{message.from_user.username}"
                )
            except:
                pass
        else:
            await message.answer(f"❌ {msg}")
        
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إدخال آيدي صحيح (أرقام فقط):", reply_markup=get_cancel_keyboard())
    except Exception as e:
        await message.answer(f"❌ حدث خطأ: {str(e)}")
        await state.clear()