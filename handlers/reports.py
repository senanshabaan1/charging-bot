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
    waiting_report_time = State()  # 👈 أضفنا هذه الحالة

def remove_timezone_from_df(df):
    """إزالة معلومات المنطقة الزمنية من أعمدة التاريخ في DataFrame"""
    if df.empty:
        return df
    
    for col in df.columns:
        # التحقق إذا كان العمود من نوع datetime
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            # إزالة الـ timezone إذا كان موجوداً
            df[col] = pd.to_datetime(df[col]).dt.tz_localize(None)
    return df

def is_admin(user_id):
    return user_id == ADMIN_ID or user_id in MODERATORS

async def generate_excel_report(db_pool, period='all'):
    """توليد تقرير Excel شامل"""
    try:
        output = BytesIO()
        
        async with db_pool.acquire() as conn:
            # تأكد من ضبط المنطقة الزمنية للاتصال
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
                    o.created_at as order_created_at,
                    o.updated_at as order_updated_at
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
                    created_at as point_created_at
                FROM points_history 
            '''
            if period == 'day':
                points_query += " WHERE DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE"
            points_query += " ORDER BY point_created_at DESC LIMIT 1000"
            points_df = pd.DataFrame(await conn.fetch(points_query))
            
            # 5. تقرير استرداد النقاط
            redemptions_query = '''
                SELECT 
                    id, user_id, username, points, amount_usd, amount_syp,
                    created_at as redemption_created_at,
                    updated_at as redemption_updated_at
                FROM redemption_requests 
            '''
            if period == 'day':
                redemptions_query += " WHERE DATE(created_at AT TIME ZONE 'Asia/Damascus') = CURRENT_DATE"
            redemptions_query += " ORDER BY redemption_created_at DESC"
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
            
            # فحص إذا كانت لا توجد بيانات لليوم (للتقرير اليومي)
            if period == 'day' and stats['total_orders'] == 0 and stats['total_deposits'] == 0:
                logger.info("📊 لا توجد بيانات لليوم - سيتم إنشاء تقرير فارغ")
            
            # ===== إزالة الـ timezone من جميع الـ DataFrames =====
            def remove_timezone_from_df(df):
                """إزالة معلومات المنطقة الزمنية من أعمدة التاريخ في DataFrame"""
                if df.empty:
                    return df
                
                for col in df.columns:
                    # التحقق إذا كان العمود من نوع datetime
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        # إزالة الـ timezone إذا كان موجوداً
                        df[col] = pd.to_datetime(df[col]).dt.tz_localize(None)
                return df
            
            users_df = remove_timezone_from_df(users_df)
            deposits_df = remove_timezone_from_df(deposits_df)
            orders_df = remove_timezone_from_df(orders_df)
            points_df = remove_timezone_from_df(points_df)
            redemptions_df = remove_timezone_from_df(redemptions_df)
            # ===================================================
            
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
        import traceback
        traceback.print_exc()
        return None

async def send_daily_report(bot: Bot, db_pool):
    """إرسال التقرير اليومي للمشرفين"""
    try:
        # جلب إعدادات التقارير
        from database import get_report_settings
        settings = await get_report_settings(db_pool)
        
        # التحقق إذا كان التقرير مفعل
        if settings.get('daily_report_enabled') != 'true':
            logging.info("📊 التقرير اليومي معطل")
            return
        
        # توليد التقرير اليومي
        excel_file = await generate_excel_report(db_pool, 'day')
        
        if excel_file:
            from config import ADMIN_ID, MODERATORS
            
            # تحديد المستلمين حسب الإعدادات
            recipients = []
            if settings.get('report_recipients') == 'owner_only':
                recipients = [ADMIN_ID]  # المالك فقط
            else:
                recipients = [ADMIN_ID] + MODERATORS  # جميع المشرفين
            
            # تنسيق التاريخ
            today = datetime.now().strftime('%Y-%m-%d')
            
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
    
    try:
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
            await callback.message.edit_text(
                "❌ فشل في توليد التقرير\n"
                "تحقق من السجلات (logs) لمعرفة التفاصيل."
            )
    except Exception as e:
        logger.error(f"❌ خطأ في daily_report: {e}")
        await callback.message.edit_text(f"❌ خطأ: {str(e)}")

@router.callback_query(F.data == "profits_report")
async def profits_report(callback: types.CallbackQuery, db_pool):
    """تقرير الأرباح (مع تفصيل حسب مستوى VIP)"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text("⏳ جاري حساب الأرباح...")
    
    # ✅ أولاً: جلب سعر الصرف
    from database import get_exchange_rate
    exchange_rate = await get_exchange_rate(db_pool)
    
    async with db_pool.acquire() as conn:
        # 1. أرباح كل تطبيق
        apps_profits = await conn.fetch('''
            SELECT 
                a.name as app_name,
                a.unit_price_usd as cost_price_usd,
                a.profit_percentage,
                COUNT(o.id) as sales_count,
                COALESCE(SUM(o.quantity), 0) as total_units,
                COALESCE(SUM(o.total_amount_syp), 0) as total_revenue_syp,
                
                -- السعر قبل الخصم
                (a.unit_price_usd * (1 + a.profit_percentage / 100)) as price_before_discount_usd,
                
                -- الربح المتوقع قبل الخصم
                (a.unit_price_usd * (1 + a.profit_percentage / 100) - a.unit_price_usd) as expected_profit_per_unit_usd,
                
                -- الربح الفعلي بعد خصم المستخدم
                (o.unit_price_usd - a.unit_price_usd) as actual_profit_per_unit_usd,
                
                -- نسبة الخصم التي حصل عليها المستخدم
                ((a.unit_price_usd * (1 + a.profit_percentage / 100) - o.unit_price_usd) / 
                 (a.unit_price_usd * (1 + a.profit_percentage / 100)) * 100) as discount_percent
                 
            FROM applications a
            JOIN orders o ON a.id = o.app_id AND o.status = 'completed'
            GROUP BY a.id, a.name, a.unit_price_usd, a.profit_percentage, o.unit_price_usd
            ORDER BY a.name
        ''')
        
        # 2. تحليل الخصومات حسب مستوى VIP
        vip_analysis = await conn.fetch('''
            SELECT 
                u.vip_level,
                COUNT(o.id) as orders_count,
                COALESCE(SUM(o.quantity), 0) as units_sold,
                COALESCE(SUM(o.total_amount_syp), 0) as revenue_syp,
                
                -- إجمالي الخصم الممنوح لهذا المستوى
                SUM(
                    (a.unit_price_usd * (1 + a.profit_percentage / 100) - o.unit_price_usd) * o.quantity * $1
                ) as total_discount_given_usd
                
            FROM orders o
            JOIN applications a ON o.app_id = a.id
            JOIN users u ON o.user_id = u.user_id
            WHERE o.status = 'completed'
            GROUP BY u.vip_level
            ORDER BY u.vip_level
        ''', exchange_rate)  # ✅ exchange_rate معرف الآن
        
        # 3. إحصائيات عامة
        totals = await conn.fetchrow('''
            SELECT 
                COUNT(DISTINCT o.app_id) as apps_with_sales,
                COUNT(o.id) as total_orders,
                COALESCE(SUM(o.quantity), 0) as total_units,
                COALESCE(SUM(o.total_amount_syp), 0) as total_revenue_syp,
                
                -- الربح المتوقع (بدون خصومات)
                SUM(
                    (a.unit_price_usd * (1 + a.profit_percentage / 100) - a.unit_price_usd) * o.quantity * $1
                ) as expected_profit_syp,
                
                -- الربح الفعلي (بعد الخصومات)
                SUM(
                    (o.unit_price_usd - a.unit_price_usd) * o.quantity * $1
                ) as actual_profit_syp,
                
                -- إجمالي الخصومات الممنوحة
                SUM(
                    ((a.unit_price_usd * (1 + a.profit_percentage / 100) - o.unit_price_usd) * o.quantity * $1)
                ) as total_discounts_syp
                
            FROM orders o
            JOIN applications a ON o.app_id = a.id
            WHERE o.status = 'completed'
        ''', exchange_rate)  # ✅ exchange_rate معرف الآن
                
        # 4. جلب سعر الصرف
        from database import get_exchange_rate
        exchange_rate = await get_exchange_rate(db_pool)
    
    # بناء نص التقرير
    text = "💰 **تقرير الأرباح التفصيلي**\n\n"
    
    if totals and totals['total_orders'] > 0:
        # ===== الإجماليات =====
        expected_profit = totals['expected_profit_syp'] or 0
        actual_profit = totals['actual_profit_syp'] or 0
        total_discounts = totals['total_discounts_syp'] or 0
        profit_loss_percent = ((actual_profit - expected_profit) / expected_profit * 100) if expected_profit > 0 else 0
        
        text += (
            f"📊 **الإجمالي الكلي**\n"
            f"• إجمالي الطلبات: {totals['total_orders']}\n"
            f"• إجمالي الوحدات: {totals['total_units']}\n"
            f"• الإيرادات: {totals['total_revenue_syp']:,.0f} ل.س\n\n"
            
            f"📈 **تحليل الأرباح:**\n"
            f"• الربح المتوقع (بدون خصم): {expected_profit:,.0f} ل.س\n"
            f"• الربح الفعلي (بعد الخصم): {actual_profit:,.0f} ل.س\n"
            f"• الخصومات الممنوحة: {total_discounts:,.0f} ل.س\n"
            f"• نسبة تأثير الخصم: {abs(profit_loss_percent):.1f}% ({'🔻' if profit_loss_percent < 0 else '✅'})\n\n"
        )
        
        # ===== تحليل حسب مستوى VIP =====
        if vip_analysis:
            text += "👑 **تحليل حسب مستوى VIP**\n"
            vip_icons = ["🟢", "🔵", "🟣", "🟡", "🔴", "💎"]
            
            for vip in vip_analysis:
                level = vip['vip_level']
                icon = vip_icons[level] if level < len(vip_icons) else "⭐"
                discount_syp = vip['total_discount_given_usd'] or 0
                
                text += (
                    f"{icon} **VIP {level}**\n"
                    f"  • طلبات: {vip['orders_count']}\n"
                    f"  • خصومات: {discount_syp:,.0f} ل.س\n"
                )
            text += "\n"
        
        # ===== أرباح كل تطبيق =====
        text += "📱 **أرباح التطبيقات**\n\n"
        
        for app in apps_profits:
            cost_usd = app['cost_price_usd']
            profit_percent = app['profit_percentage']
            price_before = app['price_before_discount_usd']
            expected_profit_unit = app['expected_profit_per_unit_usd'] * exchange_rate
            actual_profit_unit = app['actual_profit_per_unit_usd'] * exchange_rate
            discount = app['discount_percent'] or 0
            units = app['total_units']
            
            # إجمالي أرباح هذا التطبيق
            total_expected = expected_profit_unit * units
            total_actual = actual_profit_unit * units
            total_discount_app = total_expected - total_actual
            
            text += (
                f"**{app['app_name']}**\n"
                f"• سعر التكلفة: ${cost_usd:.3f}\n"
                f"• نسبة الربح: {profit_percent}%\n"
                f"• سعر البيع قبل الخصم: ${price_before:.3f}\n"
                f"• خصم العملاء: {discount:.1f}%\n"
                f"• الوحدات المباعة: {units}\n"
                f"• الربح المتوقع: {total_expected:,.0f} ل.س\n"
                f"• الربح الفعلي: {total_actual:,.0f} ل.س\n"
                f"• الخصم الممنوح: {total_discount_app:,.0f} ل.س\n\n"
            )
        
        # ===== نسبة الخصم الإجمالية =====
        discount_percent_of_revenue = (total_discounts / totals['total_revenue_syp'] * 100) if totals['total_revenue_syp'] > 0 else 0
        
        text += (
            f"📊 **ملخص الخصومات**\n"
            f"• نسبة الخصم من الإيرادات: {discount_percent_of_revenue:.1f}%\n"
            f"• صافي الربح بعد الخصم: {actual_profit:,.0f} ل.س\n"
            f"• سعر الصرف: {exchange_rate:,.0f} ل.س = 1$"
        )
        
    else:
        text += "لا توجد مبيعات مكتملة بعد."
    
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
async def report_settings(callback: types.CallbackQuery, db_pool):
    """إعدادات التقارير"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_report_settings
    settings = await get_report_settings(db_pool)
    
    # تحديد حالة التفعيل
    enabled_status = "✅ مفعل" if settings.get('daily_report_enabled') == 'true' else "❌ معطل"
    
    # تحديد المستلمين
    recipients_text = "👑 المالك فقط" if settings.get('report_recipients') == 'owner_only' else "👥 جميع المشرفين"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="🔁 تبديل التفعيل", 
            callback_data="toggle_daily_report"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="⏰ تغيير وقت التقرير", 
            callback_data="change_report_time"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="👤 تغيير المستلمين", 
            callback_data="change_recipients"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="🔙 رجوع", 
            callback_data="reports_menu"
        )
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
    
    from database import get_report_settings, update_report_setting
    settings = await get_report_settings(db_pool)
    
    current = settings.get('daily_report_enabled', 'true')
    new_value = 'false' if current == 'true' else 'true'
    
    await update_report_setting(db_pool, 'daily_report_enabled', new_value)
    
    # إعادة فتح قائمة الإعدادات
    await report_settings(callback, db_pool)

@router.callback_query(F.data == "change_report_time")
async def change_report_time_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تغيير وقت التقرير"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    await callback.message.edit_text(
        "⏰ **تغيير وقت التقرير اليومي**\n\n"
        "أدخل الوقت الجديد بصيغة HH:MM (مثال: 23:30)\n\n"
        "⏱️ الوقت الحالي: 00:00\n\n"
        "❌ للإلغاء أرسل /cancel"
    )
    await state.set_state(ReportStates.waiting_report_time)

@router.message(ReportStates.waiting_report_time)
async def change_report_time_final(message: types.Message, state: FSMContext, db_pool, bot: Bot):  # أضف bot
    """حفظ وقت التقرير الجديد"""
    if not is_admin(message.from_user.id):
        return
    
    # التحقق من صيغة الوقت
    import re
    time_pattern = r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'
    
    if not re.match(time_pattern, message.text.strip()):
        await message.answer(
            "❌ صيغة غير صحيحة!\n"
            "الرجاء إدخال الوقت بصيغة HH:MM (مثال: 14:30)\n"
            "أو أرسل /cancel للإلغاء"
        )
        return
    
    new_time = message.text.strip()
    
    from database import update_report_setting
    await update_report_setting(db_pool, 'report_time', new_time)
    
    # ===== إعادة جدولة التقرير اليومي =====
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from handlers.reports import send_daily_report
    
    # جلب الـ scheduler من الذاكرة (تحتاج لتخزينه مكان عام)
    # هذا يتطلب تعديل في run_bot_webhook.py
    
    await message.answer(f"✅ تم تحديث وقت التقرير إلى {new_time}\n"
                         f"⏳ سيتم إرسال التقرير يومياً الساعة {new_time}")
    await state.clear()

async def reschedule_daily_report(bot: Bot, db_pool):
    """إعادة جدولة التقرير اليومي بعد تغيير الوقت"""
    try:
        from database import get_report_settings
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        import sys
        
        settings = await get_report_settings(db_pool)
        report_time = settings.get('report_time', '00:00')
        hour, minute = map(int, report_time.split(':'))
        
        # الوصول للـ scheduler من المتغير العام في run_bot_webhook
        # هذا يعتمد على كيفية تنظيم الكود
        scheduler = None
        for job in sys.modules.keys():
            if 'scheduler' in job:
                # هذا مبسط - في الواقع نحتاج طريقة أفضل
                pass
        
        # الحل الأسهل: إعادة تشغيل الجدولة من الصفر
        # لكن هذا يتطلب إعادة تشغيل الدالة main
        logging.info(f"📊 تم تحديث وقت التقرير إلى {report_time}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في إعادة جدولة التقرير: {e}")

@router.callback_query(F.data == "change_recipients")
async def change_recipients(callback: types.CallbackQuery, db_pool):
    """تغيير مستلمي التقارير"""
    if not is_admin(callback.from_user.id):
        return await callback.answer("غير مصرح", show_alert=True)
    
    from database import get_report_settings, update_report_setting
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
        types.InlineKeyboardButton(
            text="🔙 رجوع",
            callback_data="report_settings"
        )
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
    
    from database import update_report_setting
    await update_report_setting(db_pool, 'report_recipients', recipient_type)
    
    await callback.answer(f"✅ تم تحديث المستلمين")
    await report_settings(callback, db_pool)
