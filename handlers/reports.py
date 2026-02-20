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

logger = logging.getLogger(__name__)
router = Router()

class ReportStates(StatesGroup):
    waiting_report_period = State()

def is_admin(user_id):
    return user_id == ADMIN_ID or user_id in MODERATORS

async def generate_excel_report(db_pool, period='all'):
    """توليد تقرير Excel شامل"""
    try:
        output = BytesIO()
        
        async with db_pool.acquire() as conn:
            # 1. تقرير المستخدمين
            users_df = pd.DataFrame(await conn.fetch('''
                SELECT 
                    user_id, username, first_name, last_name, 
                    balance, total_points, vip_level, discount_percent,
                    total_deposits, total_orders, total_spent,
                    referral_count, referral_earnings,
                    created_at, last_activity, is_banned
                FROM users 
                ORDER BY created_at DESC
            '''))
            
            # 2. تقرير الإيداعات
            deposits_df = pd.DataFrame(await conn.fetch('''
                SELECT 
                    id, user_id, username, method, amount, amount_syp,
                    status, created_at, updated_at
                FROM deposit_requests 
                ORDER BY created_at DESC
            '''))
            
            # 3. تقرير الطلبات
            orders_df = pd.DataFrame(await conn.fetch('''
                SELECT 
                    o.id, o.user_id, o.username, 
                    a.name as app_name, o.quantity, o.total_amount_syp,
                    o.points_earned, o.status, o.target_id,
                    o.created_at, o.updated_at
                FROM orders o
                LEFT JOIN applications a ON o.app_id = a.id
                ORDER BY o.created_at DESC
            '''))
            
            # 4. تقرير النقاط
            points_df = pd.DataFrame(await conn.fetch('''
                SELECT 
                    id, user_id, points, action, description, created_at
                FROM points_history 
                ORDER BY created_at DESC
                LIMIT 1000
            '''))
            
            # 5. تقرير استرداد النقاط
            redemptions_df = pd.DataFrame(await conn.fetch('''
                SELECT 
                    id, user_id, username, points, amount_usd, amount_syp,
                    status, created_at, updated_at
                FROM redemption_requests 
                ORDER BY created_at DESC
            '''))
            
            # 6. إحصائيات عامة
            stats = await conn.fetchrow('''
                SELECT 
                    (SELECT COUNT(*) FROM users) as total_users,
                    (SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '1 day') as new_users_today,
                    (SELECT COALESCE(SUM(balance), 0) FROM users) as total_balance,
                    (SELECT COALESCE(SUM(total_points), 0) FROM users) as total_points,
                    (SELECT COUNT(*) FROM deposit_requests) as total_deposits,
                    (SELECT COALESCE(SUM(amount_syp), 0) FROM deposit_requests WHERE status = 'approved') as total_deposit_amount,
                    (SELECT COUNT(*) FROM orders) as total_orders,
                    (SELECT COALESCE(SUM(total_amount_syp), 0) FROM orders WHERE status = 'completed') as total_order_amount,
                    (SELECT COALESCE(SUM(points_earned), 0) FROM orders) as total_points_given
            ''')
            
            # إنشاء ملف Excel مع عدة sheets
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Sheet 1: ملخص عام
                summary_data = {
                    'البيان': [
                        'إجمالي المستخدمين',
                        'مستخدمين جدد اليوم',
                        'إجمالي الأرصدة',
                        'إجمالي النقاط',
                        'إجمالي الإيداعات',
                        'قيمة الإيداعات (ل.س)',
                        'إجمالي الطلبات',
                        'قيمة الطلبات (ل.س)',
                        'نقاط ممنوحة'
                    ],
                    'القيمة': [
                        stats['total_users'],
                        stats['new_users_today'],
                        f"{stats['total_balance']:,.0f} ل.س",
                        stats['total_points'],
                        stats['total_deposits'],
                        f"{stats['total_deposit_amount']:,.0f} ل.س",
                        stats['total_orders'],
                        f"{stats['total_order_amount']:,.0f} ل.س",
                        stats['total_points_given']
                    ]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='ملخص عام', index=False)
                
                # باقي البيانات
                if not users_df.empty:
                    users_df.to_excel(writer, sheet_name='المستخدمين', index=False)
                if not deposits_df.empty:
                    deposits_df.to_excel(writer, sheet_name='الإيداعات', index=False)
                if not orders_df.empty:
                    orders_df.to_excel(writer, sheet_name='الطلبات', index=False)
                if not points_df.empty:
                    points_df.to_excel(writer, sheet_name='النقاط', index=False)
                if not redemptions_df.empty:
                    redemptions_df.to_excel(writer, sheet_name='استرداد النقاط', index=False)
            
        output.seek(0)
        return output
    except Exception as e:
        logger.error(f"❌ خطأ في توليد التقرير: {e}")
        return None

async def send_daily_report(bot: Bot, db_pool):
    """إرسال التقرير اليومي للمشرفين"""
    try:
        # توليد التقرير
        excel_file = await generate_excel_report(db_pool, 'day')
        
        if excel_file:
            from config import ADMIN_ID, MODERATORS
            admin_ids = [ADMIN_ID] + MODERATORS
            
            # تنسيق التاريخ
            today = datetime.now().strftime('%Y-%m-%d')
            
            for admin_id in admin_ids:
                if admin_id:
                    try:
                        await bot.send_document(
                            chat_id=admin_id,
                            document=types.FSInputFile(excel_file, filename=f'report_{today}.xlsx'),
                            caption=f"📊 **التقرير اليومي - {today}**\n\n"
                                   f"✅ تم توليد التقرير بنجاح\n"
                                   f"⏰ وقت الإرسال: {datetime.now().strftime('%H:%M:%S')}"
                        )
                    except Exception as e:
                        logger.error(f"❌ فشل إرسال التقرير للمشرف {admin_id}: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال التقرير اليومي: {e}")

# ============= أزرار لوحة التحكم =============

@router.callback_query(F.data == "reports_menu")
async def reports_menu(callback: types.CallbackQuery):
    """قائمة التقارير"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📊 تقرير شامل", callback_data="full_report"),
        types.InlineKeyboardButton(text="📅 تقرير يومي", callback_data="daily_report")
    )
    builder.row(
        types.InlineKeyboardButton(text="💰 تقرير الأرباح", callback_data="profits_report"),
        types.InlineKeyboardButton(text="👥 تقرير المستخدمين", callback_data="users_report")
    )
    builder.row(
        types.InlineKeyboardButton(text="📱 تقرير التطبيقات", callback_data="apps_report"),
        types.InlineKeyboardButton(text="⭐ تقرير النقاط", callback_data="points_report")
    )
    builder.row(
        types.InlineKeyboardButton(text="💾 نسخ احتياطي", callback_data="backup_db"),
        types.InlineKeyboardButton(text="⚙️ إعدادات التقارير", callback_data="report_settings")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back_to_admin")
    )
    
    await callback.message.edit_text(
        "📊 **نظام التقارير والنسخ الاحتياطي**\n\n"
        "اختر نوع التقرير المطلوب:\n"
        "• تقارير شاملة بكل التفاصيل\n"
        "• نسخ احتياطي يومي تلقائي\n"
        "• إحصائيات دقيقة للأرباح",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "full_report")
async def full_report(callback: types.CallbackQuery, db_pool):
    """تقرير شامل"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري توليد التقرير الشامل...")
    
    excel_file = await generate_excel_report(db_pool)
    
    if excel_file:
        today = datetime.now().strftime('%Y-%m-%d_%H-%M')
        await callback.message.answer_document(
            document=types.BufferedInputFile(excel_file.getvalue(), filename=f'full_report_{today}.xlsx'),
            caption=f"📊 **التقرير الشامل**\n"
                   f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
    else:
        await callback.message.edit_text("❌ فشل في توليد التقرير")

@router.callback_query(F.data == "backup_db")
async def backup_database(callback: types.CallbackQuery, db_pool):
    """نسخ احتياطي لقاعدة البيانات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري إنشاء نسخة احتياطية...")
    
    excel_file = await generate_excel_report(db_pool)
    
    if excel_file:
        today = datetime.now().strftime('%Y-%m-%d_%H-%M')
        await callback.message.answer_document(
            document=types.BufferedInputFile(excel_file.getvalue(), filename=f'backup_{today}.xlsx'),
            caption=f"💾 **نسخة احتياطية كاملة**\n"
                   f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                   f"✅ تم حفظ جميع البيانات"
        )
    else:
        await callback.message.edit_text("❌ فشل في إنشاء النسخة الاحتياطية")