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
import re
from io import BytesIO
from config import ADMIN_ID, MODERATORS
from handlers.time_utils import format_damascus_time, get_damascus_time_now
from handlers.keyboards import get_back_inline_keyboard
from database import get_report_settings, update_report_setting, get_exchange_rate
from utils import is_admin
logger = logging.getLogger(__name__)
router = Router()

class ReportStates(StatesGroup):
    waiting_report_period = State()
    waiting_report_time = State()

def remove_timezone_from_df(df):
    """إزالة معلومات المنطقة الزمنية من أعمدة التاريخ في DataFrame"""
    if df.empty:
        return df
    
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            try:
                df[col] = pd.to_datetime(df[col]).dt.tz_localize(None)
            except:
                pass
    return df

# ============= توليد تقرير Excel =============

async def generate_excel_report(db_pool, period='all'):
    """توليد تقرير Excel شامل"""
    try:
        output = BytesIO()
        
        async with db_pool.acquire() as conn:
            # ضبط المنطقة الزمنية
            await conn.execute("SET TIMEZONE TO 'Asia/Damascus'")
            
            # 1. تقرير المستخدمين
            users_df = pd.DataFrame(await conn.fetch('''
                SELECT 
                    user_id, username, first_name, last_name, 
                    balance, total_points, vip_level, discount_percent,
                    total_deposits, total_orders, total_spent,
                    referral_count, referral_earnings,
                    created_at AT TIME ZONE 'Asia/Damascus' as created_at, 
                    last_activity AT TIME ZONE 'Asia/Damascus' as last_activity, 
                    is_banned
                FROM users 
                ORDER BY created_at DESC
            '''))
            
            # 2. تقرير الإيداعات
            deposits_query = '''
                SELECT 
                    id, user_id, username, method, amount, amount_syp,
                    status, created_at AT TIME ZONE 'Asia/Damascus' as created_at, 
                    updated_at AT TIME ZONE 'Asia/Damascus' as updated_at
                FROM deposit_requests 
            '''
            if period == 'day':
                deposits_query += " WHERE DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE"
            deposits_query += " ORDER BY created_at DESC"
            deposits_df = pd.DataFrame(await conn.fetch(deposits_query))
            
            # 3. تقرير الطلبات
            orders_query = '''
                SELECT 
                    o.id, o.user_id, o.username, 
                    COALESCE(a.name, o.app_name) as app_name, 
                    o.quantity, o.total_amount_syp,
                    o.points_earned, o.status, o.target_id,
                    o.created_at AT TIME ZONE 'Asia/Damascus' as created_at,
                    o.updated_at AT TIME ZONE 'Asia/Damascus' as updated_at
                FROM orders o
                LEFT JOIN applications a ON o.app_id = a.id
            '''
            if period == 'day':
                orders_query += " WHERE DATE(o.created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE"
            orders_query += " ORDER BY o.created_at DESC"
            orders_df = pd.DataFrame(await conn.fetch(orders_query))
            
            # 4. تقرير النقاط
            points_query = '''
                SELECT 
                    id, user_id, points, action, description, 
                    created_at AT TIME ZONE 'Asia/Damascus' as created_at
                FROM points_history 
            '''
            if period == 'day':
                points_query += " WHERE DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE"
            points_query += " ORDER BY created_at DESC LIMIT 1000"
            points_df = pd.DataFrame(await conn.fetch(points_query))
            
            # 5. تقرير استرداد النقاط
            redemptions_query = '''
                SELECT 
                    id, user_id, username, points, amount_usd, amount_syp,
                    created_at AT TIME ZONE 'Asia/Damascus' as created_at,
                    updated_at AT TIME ZONE 'Asia/Damascus' as updated_at
                FROM redemption_requests 
            '''
            if period == 'day':
                redemptions_query += " WHERE DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE"
            redemptions_query += " ORDER BY created_at DESC"
            redemptions_df = pd.DataFrame(await conn.fetch(redemptions_query))
            
            # 6. إحصائيات عامة
            if period == 'day':
                stats = await conn.fetchrow('''
                    SELECT 
                        (SELECT COUNT(*) FROM users) as total_users,
                        (SELECT COUNT(*) FROM users WHERE DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE) as new_users_today,
                        (SELECT COALESCE(SUM(balance), 0) FROM users) as total_balance,
                        (SELECT COALESCE(SUM(total_points), 0) FROM users) as total_points,
                        (SELECT COUNT(*) FROM deposit_requests WHERE DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE) as total_deposits,
                        (SELECT COALESCE(SUM(amount_syp), 0) FROM deposit_requests WHERE status = 'approved' AND DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE) as total_deposit_amount,
                        (SELECT COUNT(*) FROM orders WHERE DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE) as total_orders,
                        (SELECT COALESCE(SUM(total_amount_syp), 0) FROM orders WHERE status = 'completed' AND DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE) as total_order_amount,
                        (SELECT COALESCE(SUM(points_earned), 0) FROM orders WHERE DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE) as total_points_given
                ''')
            else:
                stats = await conn.fetchrow('''
                    SELECT 
                        (SELECT COUNT(*) FROM users) as total_users,
                        (SELECT COUNT(*) FROM users WHERE DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE) as new_users_today,
                        (SELECT COALESCE(SUM(balance), 0) FROM users) as total_balance,
                        (SELECT COALESCE(SUM(total_points), 0) FROM users) as total_points,
                        (SELECT COUNT(*) FROM deposit_requests) as total_deposits,
                        (SELECT COALESCE(SUM(amount_syp), 0) FROM deposit_requests WHERE status = 'approved') as total_deposit_amount,
                        (SELECT COUNT(*) FROM orders) as total_orders,
                        (SELECT COALESCE(SUM(total_amount_syp), 0) FROM orders WHERE status = 'completed') as total_order_amount,
                        (SELECT COALESCE(SUM(points_earned), 0) FROM orders) as total_points_given
                ''')
            
            # إزالة المنطقة الزمنية من جميع البيانات
            users_df = remove_timezone_from_df(users_df)
            deposits_df = remove_timezone_from_df(deposits_df)
            orders_df = remove_timezone_from_df(orders_df)
            points_df = remove_timezone_from_df(points_df)
            redemptions_df = remove_timezone_from_df(redemptions_df)
            
            # إنشاء ملف Excel
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # ملخص عام
                if stats:
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
                            f"{stats['total_balance']:,.0f} ل.س" if stats['total_balance'] else "0 ل.س",
                            stats['total_points'] or 0,
                            stats['total_deposits'] or 0,
                            f"{stats['total_deposit_amount']:,.0f} ل.س" if stats['total_deposit_amount'] else "0 ل.س",
                            stats['total_orders'] or 0,
                            f"{stats['total_order_amount']:,.0f} ل.س" if stats['total_order_amount'] else "0 ل.س",
                            stats['total_points_given'] or 0
                        ]
                    }
                    summary_df = pd.DataFrame(summary_data)
                    summary_df.to_excel(writer, sheet_name='ملخص عام', index=False)
                
                # باقي الأوراق
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
        import traceback
        traceback.print_exc()
        return None

# ============= إرسال التقرير اليومي التلقائي =============

async def send_daily_report(bot: Bot, db_pool):
    """إرسال التقرير اليومي للمشرفين"""
    try:
        settings = await get_report_settings(db_pool)
        
        if settings.get('daily_report_enabled') != 'true':
            logger.info("📊 التقرير اليومي معطل")
            return
        
        excel_file = await generate_excel_report(db_pool, 'day')
        
        if excel_file:
            recipients = []
            if settings.get('report_recipients') == 'owner_only':
                recipients = [ADMIN_ID]
            else:
                recipients = [ADMIN_ID] + MODERATORS
            
            today = get_damascus_time_now().strftime('%Y-%m-%d')
            
            for admin_id in recipients:
                if admin_id:
                    try:
                        file = types.BufferedInputFile(
                            file=excel_file.getvalue(),
                            filename=f'report_{today}.xlsx'
                        )
                        
                        await bot.send_document(
                            chat_id=admin_id,
                            document=file,
                            caption=f"📊 **التقرير اليومي - {today}**\n\n"
                                   f"✅ تم توليد التقرير بنجاح\n"
                                   f"⏰ وقت الإرسال: {get_damascus_time_now().strftime('%H:%M:%S')}"
                        )
                    except Exception as e:
                        logger.error(f"❌ فشل إرسال التقرير للمشرف {admin_id}: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال التقرير اليومي: {e}")

# ============= قائمة التقارير =============

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
        "اختر نوع التقرير المطلوب:",
        reply_markup=builder.as_markup()
    )

# ============= التقارير المختلفة =============

@router.callback_query(F.data == "full_report")
async def full_report(callback: types.CallbackQuery, db_pool):
    """تقرير شامل"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري توليد التقرير الشامل...")
    
    excel_file = await generate_excel_report(db_pool, 'all')
    
    if excel_file:
        today = get_damascus_time_now().strftime('%Y-%m-%d_%H-%M')
        
        file = types.BufferedInputFile(
            file=excel_file.getvalue(),
            filename=f'full_report_{today}.xlsx'
        )
        
        await callback.message.answer_document(
            document=file,
            caption=f"📊 **التقرير الشامل**\n"
                   f"📅 {get_damascus_time_now().strftime('%Y-%m-%d %H:%M')}"
        )
    else:
        await callback.message.edit_text("❌ فشل في توليد التقرير")

@router.callback_query(F.data == "daily_report")
async def daily_report(callback: types.CallbackQuery, db_pool):
    """تقرير يومي"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري توليد التقرير اليومي...")
    
    try:
        excel_file = await generate_excel_report(db_pool, 'day')
        
        if excel_file:
            today = get_damascus_time_now().strftime('%Y-%m-%d')
            
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
    except Exception as e:
        logger.error(f"❌ خطأ في daily_report: {e}")
        await callback.message.edit_text(f"❌ خطأ: {str(e)}")

@router.callback_query(F.data == "profits_report")
async def profits_report(callback: types.CallbackQuery, db_pool):
    """تقرير الأرباح المفصل لكل تطبيق مع إجماليات (كملف)"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري حساب الأرباح...")
    
    exchange_rate = await get_exchange_rate(db_pool)
    
    async with db_pool.acquire() as conn:
        # نجيب كل الطلبات المكتملة
        orders = await conn.fetch('''
            SELECT 
                o.id,
                o.quantity,
                o.total_amount_syp as final_price_syp,
                o.total_amount_syp / $1 as final_price_usd,
                -- سعر المورد حسب نوع الطلب
                CASE 
                    WHEN o.variant_id IS NOT NULL THEN 
                        (SELECT price_usd FROM product_options WHERE id = o.variant_id)
                    ELSE 
                        a.unit_price_usd * o.quantity
                END as supplier_total_usd,
                a.profit_percentage as app_profit_percent,
                a.name as app_name,
                u.vip_level,
                u.discount_percent as user_discount
            FROM orders o
            JOIN applications a ON o.app_id = a.id
            JOIN users u ON o.user_id = u.user_id
            WHERE o.status = 'completed'
            ORDER BY a.name, o.created_at DESC
        ''', exchange_rate)
        
        if not orders:
            await callback.message.edit_text("📊 لا توجد مبيعات مكتملة بعد.")
            return
        
        # هيكل البيانات لكل تطبيق
        apps_data = {}
        
        # متغيرات للإجماليات الكلية
        total_all_revenue_usd = 0
        total_all_supplier_usd = 0
        total_all_profit_before_discount_usd = 0
        total_all_profit_after_discount_usd = 0
        total_all_discount_usd = 0
        
        for order in orders:
            app_name = order['app_name']
            final_price_usd = float(order['final_price_usd'] or 0)
            supplier_total_usd = float(order['supplier_total_usd'] or 0)
            app_profit_percent = float(order['app_profit_percent'] or 0)
            user_discount = float(order['user_discount'] or 0)
            
            # السعر بعد الربح (قبل الخصم)
            price_after_profit_usd = supplier_total_usd * (1 + app_profit_percent / 100)
            
            # الخصم
            discount_usd = price_after_profit_usd * (user_discount / 100)
            
            # الربح قبل الخصم
            profit_before_discount_usd = price_after_profit_usd - supplier_total_usd
            
            # الربح بعد الخصم
            profit_after_discount_usd = (price_after_profit_usd - discount_usd) - supplier_total_usd
            
            # إذا التطبيق جديد في القاموس
            if app_name not in apps_data:
                apps_data[app_name] = {
                    'orders_count': 0,
                    'revenue_usd': 0,
                    'supplier_usd': 0,
                    'profit_before_usd': 0,
                    'profit_after_usd': 0,
                    'discount_usd': 0,
                    'profit_percent': app_profit_percent
                }
            
            # تحديث إحصائيات التطبيق
            apps_data[app_name]['orders_count'] += 1
            apps_data[app_name]['revenue_usd'] += final_price_usd
            apps_data[app_name]['supplier_usd'] += supplier_total_usd
            apps_data[app_name]['profit_before_usd'] += profit_before_discount_usd
            apps_data[app_name]['profit_after_usd'] += profit_after_discount_usd
            apps_data[app_name]['discount_usd'] += discount_usd
            
            # تحديث الإجماليات الكلية
            total_all_revenue_usd += final_price_usd
            total_all_supplier_usd += supplier_total_usd
            total_all_profit_before_discount_usd += profit_before_discount_usd
            total_all_profit_after_discount_usd += profit_after_discount_usd
            total_all_discount_usd += discount_usd
        
        # بناء التقرير
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("📊 تقرير الأرباح التفصيلي")
        report_lines.append(f"💵 سعر الصرف: {exchange_rate:,.0f} ل.س = 1$")
        report_lines.append(f"📅 التاريخ: {get_damascus_time_now().strftime('%Y-%m-%d %H:%M')}")
        report_lines.append("=" * 60)
        report_lines.append("")
        
        # تفاصيل كل تطبيق
        report_lines.append("📱 تفاصيل التطبيقات:")
        report_lines.append("-" * 60)
        
        for app_name, data in apps_data.items():
            revenue_syp = data['revenue_usd'] * exchange_rate
            supplier_syp = data['supplier_usd'] * exchange_rate
            profit_before_syp = data['profit_before_usd'] * exchange_rate
            profit_after_syp = data['profit_after_usd'] * exchange_rate
            discount_syp = data['discount_usd'] * exchange_rate
            
            profit_margin = (data['profit_after_usd'] / data['revenue_usd'] * 100) if data['revenue_usd'] > 0 else 0
            
            report_lines.append(f"🔸 {app_name}")
            report_lines.append(f"   • عدد الطلبات: {data['orders_count']}")
            report_lines.append(f"   • نسبة ربح التطبيق: {data['profit_percent']}%")
            report_lines.append(f"   • الإيرادات: ${data['revenue_usd']:,.2f} ({revenue_syp:,.0f} ل.س)")
            report_lines.append(f"   • سعر المورد: ${data['supplier_usd']:,.2f} ({supplier_syp:,.0f} ل.س)")
            report_lines.append(f"   • الخصم الممنوح: ${data['discount_usd']:,.2f} ({discount_syp:,.0f} ل.س)")
            report_lines.append(f"   • الربح قبل الخصم: ${data['profit_before_usd']:,.2f} ({profit_before_syp:,.0f} ل.س)")
            report_lines.append(f"   • الربح بعد الخصم: ${data['profit_after_usd']:,.2f} ({profit_after_syp:,.0f} ل.س) (نسبة {profit_margin:.1f}%)")
            report_lines.append("")
        
        # الإجماليات الكلية
        report_lines.append("=" * 60)
        report_lines.append("📈 الإجماليات الكلية:")
        report_lines.append("-" * 60)
        
        total_revenue_syp = total_all_revenue_usd * exchange_rate
        total_supplier_syp = total_all_supplier_usd * exchange_rate
        total_profit_before_syp = total_all_profit_before_discount_usd * exchange_rate
        total_profit_after_syp = total_all_profit_after_discount_usd * exchange_rate
        total_discount_syp = total_all_discount_usd * exchange_rate
        
        total_profit_margin = (total_all_profit_after_discount_usd / total_all_revenue_usd * 100) if total_all_revenue_usd > 0 else 0
        total_discount_percent = (total_all_discount_usd / (total_all_supplier_usd + total_all_profit_before_discount_usd) * 100) if (total_all_supplier_usd + total_all_profit_before_discount_usd) > 0 else 0
        
        report_lines.append(f"💰 إجمالي الإيرادات: ${total_all_revenue_usd:,.2f} ({total_revenue_syp:,.0f} ل.س)")
        report_lines.append(f"📦 إجمالي سعر المورد: ${total_all_supplier_usd:,.2f} ({total_supplier_syp:,.0f} ل.س)")
        report_lines.append(f"🎁 إجمالي الخصم: ${total_all_discount_usd:,.2f} ({total_discount_syp:,.0f} ل.س) (نسبة {total_discount_percent:.1f}%)")
        report_lines.append(f"💎 إجمالي الربح قبل الخصم: ${total_all_profit_before_discount_usd:,.2f} ({total_profit_before_syp:,.0f} ل.س)")
        report_lines.append(f"✅ إجمالي الربح بعد الخصم: ${total_all_profit_after_discount_usd:,.2f} ({total_profit_after_syp:,.0f} ل.س)")
        report_lines.append(f"📊 هامش الربح الإجمالي: {total_profit_margin:.1f}%")
        report_lines.append("=" * 60)
        report_lines.append("")
        report_lines.append("✨ التقرير من إعداد LINK BOT")
        
        # تحويل النص لملف
        report_text = "\n".join(report_lines)
        
        from io import BytesIO
        file = BytesIO()
        file.write(report_text.encode('utf-8'))
        file.seek(0)
        
        filename = f"profits_report_{get_damascus_time_now().strftime('%Y-%m-%d_%H-%M')}.txt"
        
        await callback.message.answer_document(
            types.BufferedInputFile(
                file=file.getvalue(),
                filename=filename
            ),
            caption="✅ تم إنشاء تقرير الأرباح المفصل"
        )

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
        today = get_damascus_time_now().strftime('%Y-%m-%d_%H-%M')
        
        file = types.BufferedInputFile(
            file=excel_file.getvalue(),
            filename=f'backup_{today}.xlsx'
        )
        
        await callback.message.answer_document(
            document=file,
            caption=f"💾 **نسخة احتياطية كاملة**\n"
                   f"📅 {get_damascus_time_now().strftime('%Y-%m-%d %H:%M')}\n\n"
                   f"✅ تم حفظ جميع البيانات"
        )
    else:
        await callback.message.edit_text("❌ فشل في إنشاء النسخة الاحتياطية")

# ============= إعدادات التقارير =============

@router.callback_query(F.data == "report_settings")
async def report_settings(callback: types.CallbackQuery, db_pool):
    """إعدادات التقارير"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    settings = await get_report_settings(db_pool)
    
    enabled_status = "✅ مفعل" if settings.get('daily_report_enabled') == 'true' else "❌ معطل"
    recipients_text = "👑 المالك فقط" if settings.get('report_recipients') == 'owner_only' else "👥 جميع المشرفين"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔁 تبديل التفعيل", callback_data="toggle_daily_report")
    )
    builder.row(
        types.InlineKeyboardButton(text="⏰ تغيير وقت التقرير", callback_data="change_report_time")
    )
    builder.row(
        types.InlineKeyboardButton(text="👤 تغيير المستلمين", callback_data="change_recipients")
    )
    builder.row(
        types.InlineKeyboardButton(text="🔙 رجوع", callback_data="reports_menu")
    )
    
    await callback.message.edit_text(
        f"⚙️ **إعدادات التقارير**\n\n"
        f"• حالة التقرير اليومي: {enabled_status}\n"
        f"• وقت الإرسال: {settings.get('report_time', '00:00')}\n"
        f"• المستلمون: {recipients_text}\n\n"
        f"اختر الإجراء المطلوب:",
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
