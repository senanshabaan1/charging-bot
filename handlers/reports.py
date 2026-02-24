# handlers/reports.py
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
import asyncio
import logging
import os
from io import BytesIO
from config import ADMIN_ID, MODERATORS
from handlers.time_utils import format_damascus_time, get_damascus_time_now
from handlers.keyboards import get_back_inline_keyboard
from database import get_report_settings, update_report_setting, get_exchange_rate

logger = logging.getLogger(__name__)
router = Router()

class ReportStates(StatesGroup):
    waiting_report_period = State()
    waiting_report_time = State()

def is_admin(user_id):
    """التحقق من صلاحيات المشرف"""
    return user_id == ADMIN_ID or user_id in MODERATORS

def prepare_df_for_excel(df):
    """تحسين الـ DataFrame لتقليل استهلاك الذاكرة وتعديل التواريخ للإكسل"""
    if df.empty:
        return df
    
    for col in df.columns:
        # إذا كان العمود يحتوي على تواريخ، نقوم بإزالة المنطقة الزمنية لتوافق الإكسل
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            try:
                df[col] = pd.to_datetime(df[col]).dt.tz_localize(None)
            except:
                pass
    return df

async def create_excel_report(data, sheet_name="Report"):
    """إنشاء ملف إكسل في الذاكرة (BytesIO) لتوفير الرام وتجنب تخزين ملفات على رندر"""
    loop = asyncio.get_event_loop()
    
    def generate():
        output = BytesIO()
        df = pd.DataFrame(data)
        df = prepare_df_for_excel(df)
        
        # استخدام Engine openpyxl بطريقة محسنة
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            
            # تنسيق بسيط وسريع للأعمدة
            worksheet = writer.sheets[sheet_name]
            header_fill = PatternFill(start_color='D7E4BC', end_color='D7E4BC', fill_type='solid')
            header_font = Font(bold=True)
            
            for cell in worksheet[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center')

        output.seek(0)
        return output

    # تشغيل في Thread منفصل لكي لا يتوقف البوت عن الرد أثناء معالجة البيانات
    return await loop.run_in_executor(None, generate)

# ============= معالجات التقارير (Handlers) =============

@router.callback_query(F.data == "admin_reports")
async def reports_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ غير مصرح لك", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📊 تقرير المبيعات (24 ساعة)", callback_data="report_sales_24h"))
    builder.row(types.InlineKeyboardButton(text="💰 تقرير الإيداعات (24 ساعة)", callback_data="report_deposits_24h"))
    builder.row(types.InlineKeyboardButton(text="⚙️ إعدادات التقارير التلقائية", callback_data="report_settings"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_main"))
    
    await callback.message.edit_text(
        "📊 **قسم التقارير والإحصائيات**\n\nاختر نوع التقرير المطلوب استخراجه بصيغة إكسل:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("report_"))
async def generate_quick_report(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id): return
    
    report_type = callback.data
    if report_type == "report_settings": return # سيتم معالجته في دالة أخرى
    
    await callback.message.edit_text("⏳ جاري استخراج البيانات وتحويلها لملف Excel...")
    
    async with db_pool.acquire() as conn:
        if report_type == "report_sales_24h":
            query = "SELECT * FROM orders WHERE created_at > NOW() - INTERVAL '24 hours' ORDER BY created_at DESC"
            filename = f"sales_{get_damascus_time_now().strftime('%Y%m%d')}.xlsx"
            data = await conn.fetch(query)
        elif report_type == "report_deposits_24h":
            query = "SELECT * FROM deposit_requests WHERE created_at > NOW() - INTERVAL '24 hours' ORDER BY created_at DESC"
            filename = f"deposits_{get_damascus_time_now().strftime('%Y%m%d')}.xlsx"
            data = await conn.fetch(query)
        else:
            return

    if not data:
        return await callback.message.edit_text("📭 لا توجد سجلات جديدة في الـ 24 ساعة الماضية.", 
                                         reply_markup=get_back_inline_keyboard("admin_reports"))

    try:
        # تحويل البيانات إلى قاموس تمهيداً للإكسل
        data_dict = [dict(r) for r in data]
        excel_file = await create_excel_report(data_dict)
        
        # إرسال الملف باستخدام BufferedInputFile لضمان عدم استهلاك مساحة القرص
        input_file = types.BufferedInputFile(excel_file.getvalue(), filename=filename)
        
        await callback.message.answer_document(
            document=input_file,
            caption=f"✅ تقرير جاهز\n📅 تم التوليد في: {format_damascus_time(datetime.now())}"
        )
        await callback.message.delete()
    except Exception as e:
        logger.error(f"Error in report generation: {e}")
        await callback.message.edit_text(f"❌ فشل إنشاء التقرير: {str(e)}")

# ============= إعدادات التقارير التلقائية =============

@router.callback_query(F.data == "report_settings")
async def show_report_settings(callback: types.CallbackQuery, db_pool):
    if not is_admin(callback.from_user.id): return
    
    settings = await get_report_settings(db_pool)
    status = "✅ مفعلة" if settings.get('auto_reports_enabled') else "❌ معطلة"
    period = settings.get('report_period', 'daily')
    time_str = settings.get('report_time', '09:00')
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text=f"الحالة: {status}", callback_data="toggle_auto_reports"))
    builder.row(
        types.InlineKeyboardButton(text=f"الفترة: {period}", callback_data="change_report_period"),
        types.InlineKeyboardButton(text=f"الوقت: {time_str}", callback_data="change_report_time")
    )
    builder.row(types.InlineKeyboardButton(text="👤 مستلمي التقارير", callback_data="manage_report_recipients"))
    builder.row(types.InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_reports"))
    
    await callback.message.edit_text(
        "⚙️ **إعدادات التقارير التلقائية**\n\nقم بضبط وقت إرسال التقارير اليومية للمشرفين:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "toggle_daily_report")
async def toggle_daily_report(callback: types.CallbackQuery, db_pool):
    """تبديل تفعيل التقرير اليومي"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    settings = await get_report_settings(db_pool)
    current = settings.get('daily_report_enabled', 'true')
    new_value = 'false' if current == 'true' else 'true'
    
    await update_report_setting(db_pool, 'daily_report_enabled', new_value)
    await report_settings(callback, db_pool)

@router.callback_query(F.data == "change_report_time")
async def change_report_time_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تغيير وقت التقرير"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text(
        "⏰ **تغيير وقت التقرير اليومي**\n\n"
        "أدخل الوقت الجديد بصيغة HH:MM (مثال: 23:30)\n\n"
        "❌ للإلغاء أرسل /cancel"
    )
    await state.set_state(ReportStates.waiting_report_time)

@router.message(ReportStates.waiting_report_time)
async def change_report_time_final(message: types.Message, state: FSMContext, db_pool):
    """حفظ وقت التقرير الجديد"""
    if not is_admin(message.from_user.id):
        return
    
    time_pattern = r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'
    
    if not re.match(time_pattern, message.text.strip()):
        await message.answer(
            "❌ صيغة غير صحيحة!\n"
            "الرجاء إدخال الوقت بصيغة HH:MM (مثال: 14:30)\n"
            "أو أرسل /cancel للإلغاء"
        )
        return
    
    new_time = message.text.strip()
    await update_report_setting(db_pool, 'report_time', new_time)
    
    await message.answer(f"✅ تم تحديث وقت التقرير إلى {new_time}\n"
                         f"⏳ سيتم إرسال التقرير يومياً الساعة {new_time}")
    await state.clear()

@router.callback_query(F.data == "change_recipients")
async def change_recipients(callback: types.CallbackQuery, db_pool):
    """تغيير مستلمي التقارير"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    settings = await get_report_settings(db_pool)
    current = settings.get('report_recipients', 'owner_only')
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="👑 المالك فقط" + (" ✅" if current == 'owner_only' else ""),
            callback_data="set_recipients_owner_only"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="👥 جميع المشرفين" + (" ✅" if current == 'all_admins' else ""),
            callback_data="set_recipients_all_admins"
        )
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="report_settings")
    )
    
    await callback.message.edit_text(
        "👤 **اختر مستلمي التقارير:**\n\n"
        "• المالك فقط: التقرير يرسل للمالك فقط\n"
        "• جميع المشرفين: يرسل لكل المشرفين",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("set_recipients_"))
async def set_recipients(callback: types.CallbackQuery, db_pool):
    """تحديد مستلمي التقارير"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    recipient_type = callback.data.replace("set_recipients_", "")
    await update_report_setting(db_pool, 'report_recipients', recipient_type)
    
    await callback.answer("✅ تم تحديث المستلمين")
    await report_settings(callback, db_pool)
