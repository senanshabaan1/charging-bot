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
        
        # تحديد شرط التاريخ إذا كان تقرير يومي
        date_condition = ""
        if period == 'day':
            date_condition = "AND DATE(created_at) = CURRENT_DATE"
        
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
            
            # 2. تقرير الإيداعات (مع شرط التاريخ)
            deposits_df = pd.DataFrame(await conn.fetch(f'''
                SELECT 
                    id, user_id, username, method, amount, amount_syp,
                    status, created_at, updated_at
                FROM deposit_requests 
                WHERE 1=1 {date_condition}
                ORDER BY created_at DESC
            '''))
            
            # 3. تقرير الطلبات (مع شرط التاريخ)
            orders_df = pd.DataFrame(await conn.fetch(f'''
                SELECT 
                    o.id, o.user_id, o.username, 
                    a.name as app_name, o.quantity, o.total_amount_syp,
                    o.points_earned, o.status, o.target_id,
                    o.created_at, o.updated_at
                FROM orders o
                LEFT JOIN applications a ON o.app_id = a.id
                WHERE 1=1 {date_condition}
                ORDER BY o.created_at DESC
            '''))
            
            # 4. تقرير النقاط (مع شرط التاريخ)
            points_df = pd.DataFrame(await conn.fetch(f'''
                SELECT 
                    id, user_id, points, action, description, created_at
                FROM points_history 
                WHERE 1=1 {date_condition}
                ORDER BY created_at DESC
                LIMIT 1000
            '''))
            
            # 5. تقرير استرداد النقاط (مع شرط التاريخ)
            redemptions_df = pd.DataFrame(await conn.fetch(f'''
                SELECT 
                    id, user_id, username, points, amount_usd, amount_syp,
                    status, created_at, updated_at
                FROM redemption_requests 
                WHERE 1=1 {date_condition}
                ORDER BY created_at DESC
            '''))
            
            # 6. إحصائيات عامة (مع مراعاة التاريخ)
            if period == 'day':
                stats = await conn.fetchrow('''
                    SELECT 
                        (SELECT COUNT(*) FROM users) as total_users,
                        (SELECT COUNT(*) FROM users WHERE DATE(created_at) = CURRENT_DATE) as new_users_today,
                        (SELECT COALESCE(SUM(balance), 0) FROM users) as total_balance,
                        (SELECT COALESCE(SUM(total_points), 0) FROM users) as total_points,
                        (SELECT COUNT(*) FROM deposit_requests WHERE DATE(created_at) = CURRENT_DATE) as total_deposits,
                        (SELECT COALESCE(SUM(amount_syp), 0) FROM deposit_requests WHERE status = 'approved' AND DATE(created_at) = CURRENT_DATE) as total_deposit_amount,
                        (SELECT COUNT(*) FROM orders WHERE DATE(created_at) = CURRENT_DATE) as total_orders,
                        (SELECT COALESCE(SUM(total_amount_syp), 0) FROM orders WHERE status = 'completed' AND DATE(created_at) = CURRENT_DATE) as total_order_amount,
                        (SELECT COALESCE(SUM(points_earned), 0) FROM orders WHERE DATE(created_at) = CURRENT_DATE) as total_points_given
                ''')
            else:
                stats = await conn.fetchrow('''
                    SELECT 
                        (SELECT COUNT(*) FROM users) as total_users,
                        (SELECT COUNT(*) FROM users WHERE DATE(created_at) = CURRENT_DATE) as new_users_today,
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
        # توليد التقرير اليومي
        excel_file = await generate_excel_report(db_pool, 'day')
        
        if excel_file:
            from config import ADMIN_ID, MODERATORS
            admin_ids = [ADMIN_ID] + MODERATORS
            
            # تنسيق التاريخ
            today = datetime.now().strftime('%Y-%m-%d')
            
            for admin_id in admin_ids:
                if admin_id:
                    try:
                        # تحويل BytesIO إلى BufferedInputFile
                        file = types.BufferedInputFile(
                            file=excel_file.getvalue(),
                            filename=f'report_{today}.xlsx'
                        )
                        
                        await bot.send_document(
                            chat_id=admin_id,
                            document=file,
                            caption=f"📊 **التقرير اليومي - {today}**\n\n"
                                   f"✅ تم توليد التقرير بنجاح\n"
                                   f"⏰ وقت الإرسال: {datetime.now().strftime('%H:%M:%S')}"
                        )
                    except Exception as e:
                        logger.error(f"❌ فشل إرسال التقرير للمشرف {admin_id}: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال التقرير اليومي: {e}")

# ============= قائمة التقارير الرئيسية =============

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

# ============= دوال التقارير =============

@router.callback_query(F.data == "full_report")
async def full_report(callback: types.CallbackQuery, db_pool):
    """تقرير شامل"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري توليد التقرير الشامل...")
    
    excel_file = await generate_excel_report(db_pool, 'all')
    
    if excel_file:
        today = datetime.now().strftime('%Y-%m-%d_%H-%M')
        
        file = types.BufferedInputFile(
            file=excel_file.getvalue(),
            filename=f'full_report_{today}.xlsx'
        )
        
        await callback.message.answer_document(
            document=file,
            caption=f"📊 **التقرير الشامل**\n"
                   f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
    else:
        await callback.message.edit_text("❌ فشل في توليد التقرير")

@router.callback_query(F.data == "daily_report")
async def daily_report(callback: types.CallbackQuery, db_pool):
    """تقرير يومي"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري توليد التقرير اليومي...")
    
    excel_file = await generate_excel_report(db_pool, 'day')
    
    if excel_file:
        today = datetime.now().strftime('%Y-%m-%d')
        
        file = types.BufferedInputFile(
            file=excel_file.getvalue(),
            filename=f'daily_report_{today}.xlsx'
        )
        
        await callback.message.answer_document(
            document=file,
            caption=f"📅 **التقرير اليومي**\n"
                   f"📆 {today}"
        )
    else:
        await callback.message.edit_text("❌ فشل في توليد التقرير")

@router.callback_query(F.data == "profits_report")
async def profits_report(callback: types.CallbackQuery, db_pool):
    """تقرير الأرباح"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري توليد تقرير الأرباح...")
    
    async with db_pool.acquire() as conn:
        # إحصائيات الأرباح
        profits = await conn.fetchrow('''
            SELECT 
                COALESCE(SUM(total_amount_syp), 0) as total_orders_value,
                COALESCE(SUM(CASE WHEN status = 'completed' THEN total_amount_syp END), 0) as completed_orders_value,
                COUNT(*) as total_orders,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_orders
            FROM orders
        ''')
        
        deposits = await conn.fetchrow('''
            SELECT 
                COALESCE(SUM(amount_syp), 0) as total_deposits,
                COUNT(*) as deposit_count
            FROM deposit_requests
            WHERE status = 'approved'
        ''')
        
        # حساب الأرباح الصافية
        net_profit = profits['completed_orders_value'] - deposits['total_deposits']
        
    text = (
        f"💰 **تقرير الأرباح**\n\n"
        f"📊 **الطلبات:**\n"
        f"• إجمالي الطلبات: {profits['total_orders']}\n"
        f"• الطلبات المكتملة: {profits['completed_orders']}\n"
        f"• قيمة الطلبات الإجمالية: {profits['total_orders_value']:,.0f} ل.س\n"
        f"• قيمة المكتملة: {profits['completed_orders_value']:,.0f} ل.س\n\n"
        f"💳 **الإيداعات:**\n"
        f"• عدد الإيداعات: {deposits['deposit_count']}\n"
        f"• قيمة الإيداعات: {deposits['total_deposits']:,.0f} ل.س\n\n"
        f"💵 **صافي الأرباح:** {net_profit:,.0f} ل.س"
    )
    
    await callback.message.edit_text(text)

@router.callback_query(F.data == "users_report")
async def users_report(callback: types.CallbackQuery, db_pool):
    """تقرير المستخدمين"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        users_stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total_users,
                COUNT(CASE WHEN is_banned THEN 1 END) as banned_users,
                COUNT(CASE WHEN vip_level > 0 THEN 1 END) as vip_users,
                COALESCE(AVG(balance), 0) as avg_balance,
                COALESCE(SUM(balance), 0) as total_balance,
                COUNT(CASE WHEN DATE(created_at) = CURRENT_DATE THEN 1 END) as new_today
            FROM users
        ''')
        
        top_users = await conn.fetch('''
            SELECT username, total_spent, vip_level
            FROM users
            WHERE total_spent > 0
            ORDER BY total_spent DESC
            LIMIT 5
        ''')
    
    text = (
        f"👥 **تقرير المستخدمين**\n\n"
        f"📊 **إحصائيات:**\n"
        f"• إجمالي المستخدمين: {users_stats['total_users']}\n"
        f"• مستخدمين جدد اليوم: {users_stats['new_today']}\n"
        f"• المحظورين: {users_stats['banned_users']}\n"
        f"• أعضاء VIP: {users_stats['vip_users']}\n"
        f"• متوسط الرصيد: {users_stats['avg_balance']:,.0f} ل.س\n"
        f"• إجمالي الأرصدة: {users_stats['total_balance']:,.0f} ل.س\n\n"
    )
    
    if top_users:
        text += "🏆 **أكثر المستخدمين إنفاقاً:**\n"
        for i, user in enumerate(top_users, 1):
            username = user['username'] or f"مستخدم"
            text += f"{i}. {username} - {user['total_spent']:,.0f} ل.س (VIP {user['vip_level']})\n"
    
    await callback.message.edit_text(text)

@router.callback_query(F.data == "apps_report")
async def apps_report(callback: types.CallbackQuery, db_pool):
    """تقرير التطبيقات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        apps_stats = await conn.fetch('''
            SELECT 
                a.name,
                COUNT(o.id) as order_count,
                COALESCE(SUM(o.total_amount_syp), 0) as total_revenue
            FROM applications a
            LEFT JOIN orders o ON a.id = o.app_id AND o.status = 'completed'
            GROUP BY a.id, a.name
            ORDER BY total_revenue DESC
            LIMIT 10
        ''')
    
    text = "📱 **تقرير التطبيقات**\n\n"
    
    if apps_stats:
        for app in apps_stats:
            text += f"• **{app['name']}**\n"
            text += f"  طلبات: {app['order_count']} | إيرادات: {app['total_revenue']:,.0f} ل.س\n\n"
    else:
        text += "لا توجد بيانات كافية بعد."
    
    await callback.message.edit_text(text)

@router.callback_query(F.data == "points_report")
async def points_report(callback: types.CallbackQuery, db_pool):
    """تقرير النقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    async with db_pool.acquire() as conn:
        points_stats = await conn.fetchrow('''
            SELECT 
                COALESCE(SUM(total_points), 0) as total_points,
                COALESCE(SUM(total_points_earned), 0) as total_earned,
                COALESCE(SUM(total_points_redeemed), 0) as total_redeemed,
                COUNT(CASE WHEN total_points > 0 THEN 1 END) as users_with_points
            FROM users
        ''')
        
        redemptions = await conn.fetchrow('''
            SELECT 
                COUNT(*) as redemption_count,
                COALESCE(SUM(amount_syp), 0) as total_redemption_value
            FROM redemption_requests
            WHERE status = 'approved'
        ''')
    
    text = (
        f"⭐ **تقرير النقاط**\n\n"
        f"📊 **إحصائيات:**\n"
        f"• إجمالي النقاط: {points_stats['total_points']}\n"
        f"• نقاط مكتسبة: {points_stats['total_earned']}\n"
        f"• نقاط مستردة: {points_stats['total_redeemed']}\n"
        f"• مستخدمين لديهم نقاط: {points_stats['users_with_points']}\n\n"
        f"💰 **الاسترداد:**\n"
        f"• عدد عمليات الاسترداد: {redemptions['redemption_count']}\n"
        f"• قيمة المستردة: {redemptions['total_redemption_value']:,.0f} ل.س"
    )
    
    await callback.message.edit_text(text)

@router.callback_query(F.data == "backup_db")
async def backup_database(callback: types.CallbackQuery, db_pool):
    """نسخ احتياطي لقاعدة البيانات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري إنشاء نسخة احتياطية...")
    
    excel_file = await generate_excel_report(db_pool, 'all')
    
    if excel_file:
        today = datetime.now().strftime('%Y-%m-%d_%H-%M')
        
        file = types.BufferedInputFile(
            file=excel_file.getvalue(),
            filename=f'backup_{today}.xlsx'
        )
        
        await callback.message.answer_document(
            document=file,
            caption=f"💾 **نسخة احتياطية كاملة**\n"
                   f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                   f"✅ تم حفظ جميع البيانات"
        )
    else:
        await callback.message.edit_text("❌ فشل في إنشاء النسخة الاحتياطية")

@router.callback_query(F.data == "report_settings")
async def report_settings(callback: types.CallbackQuery):
    """إعدادات التقارير"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ تفعيل التقرير اليومي", callback_data="toggle_daily"),
        types.InlineKeyboardButton(text="⏰ تغيير وقت التقرير", callback_data="change_time")
    )
    builder.row(
        types.InlineKeyboardButton(text="👥 إرسال للمشرفين", callback_data="report_recipients"),
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="reports_menu")
    )
    
    await callback.message.edit_text(
        "⚙️ **إعدادات التقارير**\n\n"
        "• التقرير اليومي: ✅ مفعل\n"
        "• وقت الإرسال: 00:00\n"
        "• المستلمون: جميع المشرفين\n\n"
        "اختر الإجراء المطلوب:",
        reply_markup=builder.as_markup()
    )
