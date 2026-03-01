# dashboard.py
import logging
import os
import asyncio
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_CONFIG, WEB_USERNAME, WEB_PASSWORD
import config
from functools import wraps
import urllib.parse
import random
import string

# إنشاء تطبيق Flask
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "".join(random.choices(string.ascii_letters + string.digits, k=32)))

# إعدادات إضافية للسيرفر
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_SECURE'] = True
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.filters['strftime'] = lambda x, f: x.strftime(f) if x else ''
app.jinja_env.filters['format_number'] = lambda x: f"{x:,.0f}".replace(',', '.') if x else '0'

# إعداد logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.route('/health')
def health():
    """مسار للتحقق من صحة الخدمة"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()}), 200

def get_db_connection():
    """إنشاء اتصال بقاعدة البيانات مع دعم كل الطرق"""
    try:
        # 1. محاولة استخدام DATABASE_URL من متغيرات البيئة أولاً
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            # تعديل الرابط إذا كان يبدأ بـ postgres://
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
            
            logger.info("🔗 Connecting via DATABASE_URL")
            conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
            logger.info("✅ Connected successfully")
            return conn
        
        # 2. استخدام DB_CONFIG من config.py
        logger.info(f"🔗 Connecting via DB_CONFIG: {DB_CONFIG.get('host', 'unknown')}")
        conn = psycopg2.connect(
            host=DB_CONFIG.get("host"),
            port=DB_CONFIG.get("port", 6543),
            database=DB_CONFIG.get("database", "postgres"),
            user=DB_CONFIG.get("user", "postgres"),
            password=DB_CONFIG.get("password"),
            cursor_factory=RealDictCursor
        )
        logger.info("✅ Connected successfully")
        return conn
        
    except psycopg2.OperationalError as e:
        logger.error(f"❌ Database connection failed: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return None

def login_required(f):
    """ديكوريتور للتحقق من تسجيل الدخول"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('الرجاء تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """ديكوريتور للتحقق من صلاحيات المشرف المطلق"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('الرجاء تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('login'))
        
        # التحقق من أن المستخدم هو ADMIN
        if session.get('user_id') != config.ADMIN_ID and session.get('username') != config.WEB_USERNAME:
            flash('غير مصرح لك بالوصول إلى هذه الصفحة', 'danger')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function

def log_admin_action(user_id, action, details):
    """تسجيل إجراءات المشرفين"""
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO logs (user_id, action, details, created_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ''', (user_id, action, details))
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        logger.error(f"Failed to log admin action: {e}")

@app.route('/login', methods=['GET', 'POST'])
def login():
    """صفحة تسجيل الدخول"""
    if 'logged_in' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # التحقق من بيانات الدخول
        if username == WEB_USERNAME and password == WEB_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            session['user_id'] = config.ADMIN_ID
            session['is_super_admin'] = True
            
            log_admin_action(config.ADMIN_ID, 'login', 'تسجيل دخول ناجح')
            flash('✅ تم تسجيل الدخول بنجاح', 'success')
            return redirect(url_for('index'))
        
        # التحقق من وجود المشرفين في قاعدة البيانات (للمشرفين الإضافيين)
        try:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute('''
                    SELECT user_id, role FROM admins 
                    WHERE username = %s AND password_hash = %s
                ''', (username, password))  # في الإنتاج استخدم hashing
                admin = cur.fetchone()
                cur.close()
                conn.close()
                
                if admin:
                    session['logged_in'] = True
                    session['username'] = username
                    session['user_id'] = admin['user_id']
                    session['role'] = admin['role']
                    
                    log_admin_action(admin['user_id'], 'login', 'تسجيل دخول مشرف')
                    flash('✅ تم تسجيل الدخول بنجاح', 'success')
                    return redirect(url_for('index'))
        except Exception as e:
            logger.error(f"Login error: {e}")
        
        flash('❌ اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    """تسجيل الخروج"""
    user_id = session.get('user_id')
    if user_id:
        log_admin_action(user_id, 'logout', 'تسجيل خروج')
    
    session.clear()
    flash('✅ تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """الصفحة الرئيسية"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('index.html', error=True)

    cur = conn.cursor()
    
    try:
        # إحصائيات عامة
        cur.execute('SELECT COUNT(*) as total FROM users')
        total_users = cur.fetchone()['total'] or 0

        cur.execute('SELECT COALESCE(SUM(balance), 0) as total FROM users')
        total_balances = cur.fetchone()['total'] or 0

        cur.execute("SELECT COUNT(*) as count FROM deposit_requests WHERE status = 'pending'")
        pending_deposits_count = cur.fetchone()['count'] or 0

        cur.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'pending'")
        pending_orders_count = cur.fetchone()['count'] or 0

        cur.execute("SELECT COUNT(*) as count FROM users WHERE is_banned = TRUE")
        banned_users = cur.fetchone()['count'] or 0
        
        cur.execute("SELECT COALESCE(SUM(total_points), 0) as total FROM users")
        total_points = cur.fetchone()['total'] or 0

        # إحصائيات اليوم
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cur.execute("SELECT COUNT(*) as count FROM users WHERE created_at >= %s", (today_start,))
        new_users_today = cur.fetchone()['count'] or 0

        # جلب سعر الصرف
        cur.execute("SELECT value FROM bot_settings WHERE key = 'usd_to_syp'")
        rate_row = cur.fetchone()
        current_rate = float(rate_row['value']) if rate_row else config.USD_TO_SYP

        # جلب آخر 5 مستخدمين
        cur.execute("SELECT user_id, username, first_name, balance, is_banned, created_at FROM users ORDER BY created_at DESC LIMIT 5")
        recent_users = cur.fetchall()

        # جلب آخر 5 طلبات شحن معلقة
        cur.execute("""
            SELECT id, user_id, username, method, amount_syp, created_at
            FROM deposit_requests 
            WHERE status = 'pending' 
            ORDER BY created_at DESC LIMIT 5
        """)
        recent_deposits = cur.fetchall()

        # جلب آخر 5 طلبات تطبيقات معلقة
        cur.execute("""
            SELECT o.id, u.username, a.name, o.quantity, o.total_amount_syp, o.created_at
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            JOIN applications a ON o.app_id = a.id
            WHERE o.status = 'pending'
            ORDER BY o.created_at DESC LIMIT 5
        """)
        recent_orders = cur.fetchall()

    except Exception as e:
        logger.error(f"Error in index: {e}")
        flash(f'❌ خطأ في جلب البيانات: {str(e)}', 'danger')
        return render_template('index.html', error=True)
    finally:
        cur.close()
        conn.close()

    return render_template('index.html',
                           total_users=total_users,
                           total_balances=total_balances,
                           pending_deposits_count=pending_deposits_count,
                           pending_orders_count=pending_orders_count,
                           banned_users=banned_users,
                           total_points=total_points,
                           new_users_today=new_users_today,
                           recent_users=recent_users,
                           recent_deposits=recent_deposits,
                           recent_orders=recent_orders,
                           rate=current_rate)

@app.route('/update_rate', methods=['POST'])
@login_required
def update_rate():
    """تحديث سعر الصرف"""
    new_rate = request.form.get('new_rate')
    
    if not new_rate:
        flash('❌ الرجاء إدخال سعر الصرف', 'danger')
        return redirect(request.referrer or url_for('index'))
    
    try:
        new_rate_float = float(new_rate)
        
        conn = get_db_connection()
        if not conn:
            flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
            return redirect(url_for('index'))
            
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bot_settings (key, value, description) 
            VALUES ('usd_to_syp', %s, 'سعر صرف الدولار مقابل الليرة')
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
        """, (str(new_rate_float), str(new_rate_float)))
        conn.commit()
        cur.close()
        conn.close()
        
        # تحديث المتغير العام
        config.USD_TO_SYP = new_rate_float
        
        user_id = session.get('user_id')
        log_admin_action(user_id, 'update_rate', f'تحديث سعر الصرف إلى {new_rate_float}')
        
        flash(f'✅ تم تحديث سعر الصرف إلى {new_rate_float:,.0f} ل.س', 'success')
    except Exception as e:
        logger.error(f"Error updating rate: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    
    return redirect(request.referrer or url_for('index'))

# ============= إدارة المستخدمين =============

@app.route('/users')
@login_required
def users_management():
    """إدارة المستخدمين"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('users.html', users=[], user_stats={})

    cur = conn.cursor()
    
    try:
        # جلب جميع المستخدمين
        cur.execute("""
            SELECT user_id, username, first_name, last_name, balance, is_banned, 
                   created_at, total_deposits, total_orders, total_points, vip_level,
                   discount_percent, referral_count
            FROM users 
            ORDER BY created_at DESC
        """)
        users = cur.fetchall()
        
        # إحصائيات المستخدمين
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN is_banned THEN 1 ELSE 0 END) as banned,
                COALESCE(SUM(balance), 0) as total_balance,
                COALESCE(SUM(total_points), 0) as total_points,
                COUNT(CASE WHEN created_at >= NOW() - INTERVAL '1 day' THEN 1 END) as new_today
            FROM users
        """)
        user_stats = cur.fetchone()
        
    except Exception as e:
        logger.error(f"Error in users_management: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        users = []
        user_stats = {'total': 0, 'banned': 0, 'total_balance': 0, 'total_points': 0, 'new_today': 0}
    finally:
        cur.close()
        conn.close()
    
    return render_template('users.html', users=users, user_stats=user_stats)

@app.route('/api/user/<int:user_id>')
@login_required
def get_user_api(user_id):
    """جلب معلومات المستخدم عبر API"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection error'}), 500

    cur = conn.cursor()
    
    try:
        # معلومات المستخدم الأساسية
        cur.execute("""
            SELECT user_id, username, first_name, last_name, balance, is_banned, 
                   created_at, last_activity, total_deposits, total_orders, 
                   total_points, vip_level, discount_percent, referral_count,
                   total_spent, manual_vip, referral_earnings
            FROM users 
            WHERE user_id = %s
        """, (user_id,))
        user = cur.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # إحصائيات الإيداعات
        cur.execute("""
            SELECT 
                COUNT(*) as total_count,
                COALESCE(SUM(amount_syp), 0) as total_amount,
                COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_count,
                COALESCE(SUM(CASE WHEN status = 'approved' THEN amount_syp ELSE 0 END), 0) as approved_amount
            FROM deposit_requests 
            WHERE user_id = %s
        """, (user_id,))
        deposits_stats = cur.fetchone()
        
        # إحصائيات الطلبات
        cur.execute("""
            SELECT 
                COUNT(*) as total_count,
                COALESCE(SUM(total_amount_syp), 0) as total_amount,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_count,
                COALESCE(SUM(CASE WHEN status = 'completed' THEN total_amount_syp ELSE 0 END), 0) as completed_amount,
                COALESCE(SUM(points_earned), 0) as total_points_earned
            FROM orders 
            WHERE user_id = %s
        """, (user_id,))
        orders_stats = cur.fetchone()
        
        # سجل النقاط (آخر 5)
        cur.execute("""
            SELECT points, action, description, created_at
            FROM points_history 
            WHERE user_id = %s
            ORDER BY created_at DESC LIMIT 5
        """, (user_id,))
        points_history = cur.fetchall()
        
        # آخر 5 طلبات
        cur.execute("""
            SELECT o.id, a.name, o.quantity, o.total_amount_syp, o.status, o.created_at
            FROM orders o
            JOIN applications a ON o.app_id = a.id
            WHERE o.user_id = %s
            ORDER BY o.created_at DESC LIMIT 5
        """, (user_id,))
        recent_orders = cur.fetchall()
        
        # حساب مستوى VIP الصحيح
        vip_levels = {
            0: {'name': 'VIP 0', 'icon': '🟢', 'discount': 0},
            1: {'name': 'VIP 1', 'icon': '🔵', 'discount': 1},
            2: {'name': 'VIP 2', 'icon': '🟣', 'discount': 2},
            3: {'name': 'VIP 3', 'icon': '🟡', 'discount': 4},
        }
        
        vip_info = vip_levels.get(user['vip_level'], vip_levels[0])
        
        result = {
            'user': dict(user),
            'vip': {
                'level': user['vip_level'],
                'name': vip_info['name'],
                'icon': vip_info['icon'],
                'discount': user['discount_percent'],
                'manual': user['manual_vip']
            },
            'deposits': dict(deposits_stats),
            'orders': dict(orders_stats),
            'points_history': [dict(h) for h in points_history],
            'recent_orders': [dict(o) for o in recent_orders]
        }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in get_user_api: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/user/<int:user_id>/toggle_ban', methods=['POST'])
@login_required
def toggle_user_ban(user_id):
    """تبديل حالة حظر المستخدم"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('users_management'))

    cur = conn.cursor()
    
    try:
        cur.execute("SELECT is_banned, username FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        
        if not user:
            flash('❌ المستخدم غير موجود', 'danger')
            return redirect(url_for('users_management'))
        
        new_status = not user['is_banned']
        cur.execute("UPDATE users SET is_banned = %s WHERE user_id = %s", (new_status, user_id))
        conn.commit()
        
        status_text = 'حظر' if new_status else 'إلغاء حظر'
        log_admin_action(session.get('user_id'), f'toggle_ban_{user_id}', 
                        f'{status_text} للمستخدم {user["username"] or user_id}')
        
        flash(f'✅ تم {"حظر" if new_status else "إلغاء حظر"} المستخدم {user_id}', 'success')
        
    except Exception as e:
        logger.error(f"Error toggling ban: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('users_management'))

@app.route('/user/<int:user_id>/update_balance', methods=['POST'])
@login_required
def update_user_balance(user_id):
    """تحديث رصيد المستخدم"""
    action = request.form.get('action')
    amount = request.form.get('amount')
    
    if not amount:
        flash('❌ الرجاء إدخال المبلغ', 'danger')
        return redirect(url_for('users_management'))
    
    try:
        amount = float(amount)
        if amount <= 0:
            flash('❌ المبلغ يجب أن يكون أكبر من 0', 'danger')
            return redirect(url_for('users_management'))
    except ValueError:
        flash('❌ المبلغ غير صحيح', 'danger')
        return redirect(url_for('users_management'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('users_management'))

    cur = conn.cursor()
    
    try:
        cur.execute("SELECT balance, username FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        
        if not user:
            flash('❌ المستخدم غير موجود', 'danger')
            return redirect(url_for('users_management'))
        
        new_balance = user['balance']
        if action == 'add':
            new_balance += amount
        elif action == 'set':
            new_balance = amount
        elif action == 'subtract':
            new_balance -= amount
            if new_balance < 0:
                flash('❌ الرصيد لا يمكن أن يكون سالباً', 'danger')
                return redirect(url_for('users_management'))
        else:
            flash('❌ إجراء غير معروف', 'danger')
            return redirect(url_for('users_management'))
        
        cur.execute("UPDATE users SET balance = %s WHERE user_id = %s", (new_balance, user_id))
        conn.commit()
        
        action_text = {
            'add': f'إضافة {amount:,.0f}',
            'set': f'تعيين إلى {amount:,.0f}',
            'subtract': f'خصم {amount:,.0f}'
        }.get(action, 'تحديث')
        
        log_admin_action(session.get('user_id'), f'update_balance_{user_id}', 
                        f'{action_text} ليرة للمستخدم {user["username"] or user_id}')
        
        flash(f'✅ تم تحديث الرصيد بنجاح. الرصيد الجديد: {new_balance:,.0f} ل.س', 'success')
        
    except Exception as e:
        logger.error(f"Error updating balance: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('users_management'))

@app.route('/user/<int:user_id>/add_points', methods=['POST'])
@login_required
def add_user_points(user_id):
    """إضافة نقاط للمستخدم"""
    points = request.form.get('points')
    
    if not points:
        flash('❌ الرجاء إدخال عدد النقاط', 'danger')
        return redirect(url_for('users_management'))
    
    try:
        points = int(points)
        if points <= 0:
            flash('❌ عدد النقاط يجب أن يكون أكبر من 0', 'danger')
            return redirect(url_for('users_management'))
    except ValueError:
        flash('❌ عدد النقاط غير صحيح', 'danger')
        return redirect(url_for('users_management'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('users_management'))

    cur = conn.cursor()
    
    try:
        cur.execute("SELECT username, total_points FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        
        if not user:
            flash('❌ المستخدم غير موجود', 'danger')
            return redirect(url_for('users_management'))
        
        cur.execute("""
            UPDATE users 
            SET total_points = total_points + %s, total_points_earned = total_points_earned + %s 
            WHERE user_id = %s
        """, (points, points, user_id))
        
        cur.execute('''
            INSERT INTO points_history (user_id, points, action, description, created_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ''', (user_id, points, 'admin_add', f'إضافة نقاط من الأدمن: {points}'))
        
        conn.commit()
        
        log_admin_action(session.get('user_id'), f'add_points_{user_id}', 
                        f'إضافة {points} نقطة للمستخدم {user["username"] or user_id}')
        
        flash(f'✅ تم إضافة {points} نقطة للمستخدم', 'success')
        
    except Exception as e:
        logger.error(f"Error adding points: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('users_management'))

@app.route('/user/<int:user_id>/set_vip', methods=['POST'])
@login_required
def set_user_vip(user_id):
    """تعيين مستوى VIP للمستخدم"""
    level = request.form.get('level')
    discount = request.form.get('discount')
    manual = request.form.get('manual', 'true') == 'true'
    
    try:
        level = int(level)
        discount = float(discount)
        
        if level < 0 or level > 5:
            flash('❌ مستوى VIP غير صحيح', 'danger')
            return redirect(url_for('users_management'))
        
        if discount < 0 or discount > 100:
            flash('❌ نسبة الخصم غير صحيحة', 'danger')
            return redirect(url_for('users_management'))
        
    except ValueError:
        flash('❌ البيانات غير صحيحة', 'danger')
        return redirect(url_for('users_management'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('users_management'))

    cur = conn.cursor()
    
    try:
        cur.execute("SELECT username FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        
        if not user:
            flash('❌ المستخدم غير موجود', 'danger')
            return redirect(url_for('users_management'))
        
        cur.execute("""
            UPDATE users 
            SET vip_level = %s, discount_percent = %s, manual_vip = %s
            WHERE user_id = %s
        """, (level, discount, manual, user_id))
        conn.commit()
        
        log_admin_action(session.get('user_id'), f'set_vip_{user_id}', 
                        f'تعيين مستوى VIP {level} بخصم {discount}% للمستخدم {user["username"] or user_id}')
        
        flash(f'✅ تم تعيين مستوى VIP {level} بخصم {discount}%', 'success')
        
    except Exception as e:
        logger.error(f"Error setting VIP: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('users_management'))

@app.route('/user/<int:user_id>/send_message', methods=['POST'])
@login_required
def send_user_message(user_id):
    """إرسال رسالة خاصة لمستخدم"""
    message_text = request.form.get('message')
    
    if not message_text:
        flash('❌ الرجاء إدخال نص الرسالة', 'danger')
        return redirect(url_for('users_management'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('users_management'))

    cur = conn.cursor()
    
    try:
        cur.execute("SELECT username FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        
        if not user:
            flash('❌ المستخدم غير موجود', 'danger')
            return redirect(url_for('users_management'))
        
        # هنا يمكن إضافة إرسال الرسالة عبر البوت
        # سجل الرسالة في قاعدة البيانات
        cur.execute('''
            INSERT INTO admin_messages (user_id, message, sent_by, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        ''', (user_id, message_text, session.get('user_id')))
        conn.commit()
        
        log_admin_action(session.get('user_id'), f'send_message_{user_id}', 
                        f'إرسال رسالة للمستخدم {user["username"] or user_id}')
        
        flash(f'✅ تم إرسال الرسالة إلى المستخدم {user_id}', 'success')
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('users_management'))

# ============= إدارة الأقسام =============

@app.route('/categories')
@login_required
def categories_management():
    """إدارة الأقسام"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('categories.html', categories=[])

    cur = conn.cursor()
    
    try:
        cur.execute("SELECT id, name, display_name, icon, sort_order FROM categories ORDER BY sort_order")
        categories = cur.fetchall()
        
    except Exception as e:
        logger.error(f"Error in categories_management: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        categories = []
    finally:
        cur.close()
        conn.close()
    
    return render_template('categories.html', categories=categories)

@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    """إضافة قسم جديد"""
    name = request.form.get('name')
    display_name = request.form.get('display_name')
    icon = request.form.get('icon', '📁')
    sort_order = request.form.get('sort_order', 0)
    
    if not name or not display_name:
        flash('❌ الرجاء إدخال جميع البيانات المطلوبة', 'danger')
        return redirect(url_for('categories_management'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('categories_management'))

    cur = conn.cursor()
    
    try:
        # التحقق من عدم وجود اسم مكرر
        cur.execute("SELECT id FROM categories WHERE name = %s", (name,))
        if cur.fetchone():
            flash(f'❌ قسم باسم "{name}" موجود مسبقاً', 'danger')
            return redirect(url_for('categories_management'))
        
        cur.execute("""
            INSERT INTO categories (name, display_name, icon, sort_order)
            VALUES (%s, %s, %s, %s)
        """, (name, display_name, icon, int(sort_order)))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'add_category', f'إضافة قسم {display_name}')
        
        flash(f'✅ تم إضافة القسم "{display_name}" بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error adding category: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('categories_management'))

@app.route('/edit_category/<int:cat_id>', methods=['POST'])
@login_required
def edit_category(cat_id):
    """تعديل قسم"""
    name = request.form.get('name')
    display_name = request.form.get('display_name')
    icon = request.form.get('icon')
    sort_order = request.form.get('sort_order')
    
    if not name or not display_name:
        flash('❌ الرجاء إدخال جميع البيانات المطلوبة', 'danger')
        return redirect(url_for('categories_management'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('categories_management'))

    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE categories 
            SET name = %s, display_name = %s, icon = %s, sort_order = %s
            WHERE id = %s
        """, (name, display_name, icon, int(sort_order), cat_id))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'edit_category', f'تعديل قسم {display_name}')
        
        flash(f'✅ تم تحديث القسم "{display_name}" بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error editing category: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('categories_management'))

@app.route('/delete_category/<int:cat_id>', methods=['POST'])
@login_required
def delete_category(cat_id):
    """حذف قسم"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('categories_management'))

    cur = conn.cursor()
    
    try:
        # التحقق من عدم وجود تطبيقات في هذا القسم
        cur.execute("SELECT COUNT(*) as count FROM applications WHERE category_id = %s", (cat_id,))
        count = cur.fetchone()['count']
        
        if count > 0:
            flash(f'❌ لا يمكن حذف القسم لأنه يحتوي على {count} تطبيق/تطبيقات', 'danger')
            return redirect(url_for('categories_management'))
        
        cur.execute("SELECT display_name FROM categories WHERE id = %s", (cat_id,))
        category = cur.fetchone()
        
        cur.execute("DELETE FROM categories WHERE id = %s", (cat_id,))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'delete_category', f'حذف قسم {category["display_name"]}')
        
        flash(f'✅ تم حذف القسم بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error deleting category: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('categories_management'))

# ============= إدارة التطبيقات =============

@app.route('/applications')
@login_required
def applications_management():
    """إدارة التطبيقات"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('applications.html', applications=[], categories=[])

    cur = conn.cursor()
    
    try:
        # جلب الأقسام
        cur.execute("SELECT id, name, display_name, icon FROM categories ORDER BY sort_order")
        categories = cur.fetchall()
        
        # جلب التطبيقات مع أقسامها
        cur.execute("""
            SELECT a.id, a.name, a.unit_price_usd, a.min_units, a.profit_percentage, 
                   a.category_id, c.display_name as category_name, c.icon as category_icon,
                   a.type, a.is_active, a.created_at
            FROM applications a
            LEFT JOIN categories c ON a.category_id = c.id
            ORDER BY c.sort_order, a.id DESC
        """)
        applications = cur.fetchall()
        
        # جلب سعر الصرف
        cur.execute("SELECT value FROM bot_settings WHERE key = 'usd_to_syp'")
        rate_row = cur.fetchone()
        current_rate = float(rate_row['value']) if rate_row else config.USD_TO_SYP
        
    except Exception as e:
        logger.error(f"Error in applications_management: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        applications = []
        categories = []
        current_rate = config.USD_TO_SYP
    finally:
        cur.close()
        conn.close()
    
    return render_template('applications.html',
                          applications=applications,
                          categories=categories,
                          rate=current_rate)

@app.route('/add_application', methods=['POST'])
@login_required
def add_application():
    """إضافة تطبيق جديد"""
    name = request.form.get('name')
    unit_price = request.form.get('unit_price')
    min_units = request.form.get('min_units')
    profit_percentage = request.form.get('profit_percentage', 10)
    category_id = request.form.get('category_id')
    app_type = request.form.get('type', 'service')
    
    if not all([name, unit_price, min_units, category_id]):
        flash('❌ الرجاء إدخال جميع البيانات المطلوبة', 'danger')
        return redirect(url_for('applications_management'))
    
    try:
        conn = get_db_connection()
        if not conn:
            flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
            return redirect(url_for('applications_management'))
            
        cur = conn.cursor()
        
        # التحقق إذا كان التطبيق موجوداً بالفعل
        cur.execute("SELECT id FROM applications WHERE name = %s", (name,))
        if cur.fetchone():
            flash(f'❌ التطبيق "{name}" موجود بالفعل!', 'danger')
            return redirect(url_for('applications_management'))
        
        cur.execute("""
            INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, category_id, type, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
        """, (name, float(unit_price), int(min_units), float(profit_percentage), category_id, app_type))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'add_application', f'إضافة تطبيق {name}')
        
        flash(f'✅ تم إضافة التطبيق "{name}" بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error adding application: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

    return redirect(url_for('applications_management'))

@app.route('/edit_application/<int:app_id>', methods=['POST'])
@login_required
def edit_application(app_id):
    """تعديل تطبيق"""
    name = request.form.get('name')
    unit_price = request.form.get('unit_price')
    min_units = request.form.get('min_units')
    profit_percentage = request.form.get('profit_percentage', 10)
    category_id = request.form.get('category_id')
    app_type = request.form.get('type', 'service')
    is_active = request.form.get('is_active', 'false') == 'true'

    if not all([name, unit_price, min_units, category_id]):
        flash('❌ الرجاء إدخال جميع البيانات المطلوبة', 'danger')
        return redirect(url_for('applications_management'))

    try:
        conn = get_db_connection()
        if not conn:
            flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
            return redirect(url_for('applications_management'))
            
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE applications 
            SET name = %s, unit_price_usd = %s, min_units = %s, profit_percentage = %s, 
                category_id = %s, type = %s, is_active = %s
            WHERE id = %s
        """, (name, float(unit_price), int(min_units), float(profit_percentage), 
              category_id, app_type, is_active, app_id))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'edit_application', f'تعديل تطبيق {name}')
        
        flash(f'✅ تم تحديث التطبيق "{name}" بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error editing application: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

    return redirect(url_for('applications_management'))

@app.route('/delete_application/<int:app_id>', methods=['POST'])
@login_required
def delete_application(app_id):
    """حذف تطبيق"""
    try:
        conn = get_db_connection()
        if not conn:
            flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
            return redirect(url_for('applications_management'))
            
        cur = conn.cursor()
        
        # الحصول على اسم التطبيق قبل الحذف
        cur.execute("SELECT name FROM applications WHERE id = %s", (app_id,))
        app = cur.fetchone()
        
        if not app:
            flash('❌ التطبيق غير موجود', 'danger')
            return redirect(url_for('applications_management'))
        
        # حذف الخيارات المرتبطة أولاً
        cur.execute("DELETE FROM product_options WHERE product_id = %s", (app_id,))
        
        # حذف التطبيق
        cur.execute("DELETE FROM applications WHERE id = %s", (app_id,))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'delete_application', f'حذف تطبيق {app["name"]}')
        
        flash(f'✅ تم حذف التطبيق "{app["name"]}" بنجاح', 'success')
            
    except Exception as e:
        logger.error(f"Error deleting application: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

    return redirect(url_for('applications_management'))

@app.route('/toggle_application/<int:app_id>', methods=['POST'])
@login_required
def toggle_application(app_id):
    """تفعيل/تعطيل تطبيق"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection error'}), 500
            
        cur = conn.cursor()
        
        cur.execute("SELECT is_active FROM applications WHERE id = %s", (app_id,))
        app = cur.fetchone()
        
        if not app:
            return jsonify({'success': False, 'error': 'Application not found'}), 404
        
        new_status = not app['is_active']
        cur.execute("UPDATE applications SET is_active = %s WHERE id = %s", (new_status, app_id))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'toggle_application', 
                        f'{"تفعيل" if new_status else "تعطيل"} تطبيق {app_id}')
        
        return jsonify({'success': True, 'is_active': new_status})
        
    except Exception as e:
        logger.error(f"Error toggling application: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

# ============= إدارة خيارات المنتجات =============

@app.route('/api/options/<int:product_id>')
@login_required
def get_product_options(product_id):
    """جلب خيارات منتج معين"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection error'}), 500

    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id, name, quantity, price_usd, description, is_active, sort_order
            FROM product_options 
            WHERE product_id = %s AND is_active = TRUE
            ORDER BY sort_order, price_usd
        """, (product_id,))
        options = cur.fetchall()
        
        return jsonify([dict(opt) for opt in options])
        
    except Exception as e:
        logger.error(f"Error fetching options: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/product/<int:product_id>/options')
@login_required
def product_options(product_id):
    """صفحة إدارة خيارات المنتج"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('applications_management'))

    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT a.*, c.display_name as category_name, c.icon as category_icon
            FROM applications a
            LEFT JOIN categories c ON a.category_id = c.id
            WHERE a.id = %s
        """, (product_id,))
        product = cur.fetchone()
        
        if not product:
            flash('❌ المنتج غير موجود', 'danger')
            return redirect(url_for('applications_management'))
        
        cur.execute("""
            SELECT id, name, quantity, price_usd, description, is_active, sort_order, created_at
            FROM product_options 
            WHERE product_id = %s
            ORDER BY sort_order, price_usd
        """, (product_id,))
        options = cur.fetchall()
        
        # جلب سعر الصرف
        cur.execute("SELECT value FROM bot_settings WHERE key = 'usd_to_syp'")
        rate_row = cur.fetchone()
        current_rate = float(rate_row['value']) if rate_row else config.USD_TO_SYP
        
    except Exception as e:
        logger.error(f"Error in product_options: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        return redirect(url_for('applications_management'))
    finally:
        cur.close()
        conn.close()
    
    return render_template('options.html',
                          product=product,
                          options=options,
                          rate=current_rate)

@app.route('/product/<int:product_id>/add_option', methods=['POST'])
@login_required
def add_product_option(product_id):
    """إضافة خيار جديد لمنتج"""
    name = request.form.get('name')
    quantity = request.form.get('quantity')
    price_usd = request.form.get('price_usd')
    description = request.form.get('description')
    sort_order = request.form.get('sort_order', 0)
    
    if not all([name, quantity, price_usd]):
        flash('❌ الرجاء إدخال جميع البيانات المطلوبة', 'danger')
        return redirect(url_for('product_options', product_id=product_id))
    
    try:
        quantity = int(quantity)
        price_usd = float(price_usd)
        sort_order = int(sort_order)
        
        if quantity <= 0 or price_usd <= 0:
            flash('❌ الكمية والسعر يجب أن يكونا أكبر من 0', 'danger')
            return redirect(url_for('product_options', product_id=product_id))
        
    except ValueError:
        flash('❌ البيانات غير صحيحة', 'danger')
        return redirect(url_for('product_options', product_id=product_id))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('product_options', product_id=product_id))

    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO product_options (product_id, name, quantity, price_usd, description, sort_order, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
        """, (product_id, name, quantity, price_usd, description, sort_order))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'add_option', 
                        f'إضافة خيار {name} للمنتج {product_id}')
        
        flash(f'✅ تم إضافة الخيار "{name}" بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error adding option: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('product_options', product_id=product_id))

@app.route('/option/<int:option_id>/edit', methods=['POST'])
@login_required
def edit_option(option_id):
    """تعديل خيار"""
    name = request.form.get('name')
    quantity = request.form.get('quantity')
    price_usd = request.form.get('price_usd')
    description = request.form.get('description')
    sort_order = request.form.get('sort_order', 0)
    
    if not all([name, quantity, price_usd]):
        flash('❌ الرجاء إدخال جميع البيانات المطلوبة', 'danger')
        return redirect(request.referrer)
    
    try:
        quantity = int(quantity)
        price_usd = float(price_usd)
        sort_order = int(sort_order)
        
    except ValueError:
        flash('❌ البيانات غير صحيحة', 'danger')
        return redirect(request.referrer)
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(request.referrer)

    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE product_options 
            SET name = %s, quantity = %s, price_usd = %s, description = %s, sort_order = %s
            WHERE id = %s
        """, (name, quantity, price_usd, description, sort_order, option_id))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'edit_option', f'تعديل خيار {option_id}')
        
        flash(f'✅ تم تحديث الخيار بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error editing option: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(request.referrer)

@app.route('/option/<int:option_id>/toggle', methods=['POST'])
@login_required
def toggle_option(option_id):
    """تفعيل/تعطيل خيار"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database connection error'}), 500

    cur = conn.cursor()
    
    try:
        cur.execute("SELECT is_active, product_id FROM product_options WHERE id = %s", (option_id,))
        option = cur.fetchone()
        
        if not option:
            return jsonify({'success': False, 'error': 'Option not found'}), 404
        
        new_status = not option['is_active']
        cur.execute("UPDATE product_options SET is_active = %s WHERE id = %s", (new_status, option_id))
        conn.commit()
        
        return jsonify({'success': True, 'is_active': new_status})
        
    except Exception as e:
        logger.error(f"Error toggling option: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/option/<int:option_id>/delete', methods=['POST'])
@login_required
def delete_option(option_id):
    """حذف خيار (soft delete)"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(request.referrer)

    cur = conn.cursor()
    
    try:
        cur.execute("UPDATE product_options SET is_active = FALSE WHERE id = %s", (option_id,))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'delete_option', f'حذف خيار {option_id}')
        
        flash(f'✅ تم حذف الخيار بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error deleting option: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(request.referrer)

@app.route('/product/<int:product_id>/apply_template/<template_name>', methods=['POST'])
@login_required
def apply_option_template(product_id, template_name):
    """تطبيق قالب خيارات جاهز"""
    templates = {
        'instagram': [
            {'name': '100 متابع', 'quantity': 100, 'price_usd': 0.99},
            {'name': '500 متابع', 'quantity': 500, 'price_usd': 4.99},
            {'name': '1000 متابع', 'quantity': 1000, 'price_usd': 9.99},
            {'name': '2500 متابع', 'quantity': 2500, 'price_usd': 24.99},
            {'name': '5000 متابع', 'quantity': 5000, 'price_usd': 49.99},
        ],
        'tiktok': [
            {'name': '100 متابع', 'quantity': 100, 'price_usd': 0.99},
            {'name': '500 متابع', 'quantity': 500, 'price_usd': 4.99},
            {'name': '1000 متابع', 'quantity': 1000, 'price_usd': 9.99},
            {'name': '2500 متابع', 'quantity': 2500, 'price_usd': 24.99},
            {'name': '5000 متابع', 'quantity': 5000, 'price_usd': 49.99},
        ],
        'telegram_stars': [
            {'name': '50 نجمة', 'quantity': 50, 'price_usd': 0.99},
            {'name': '100 نجمة', 'quantity': 100, 'price_usd': 1.99},
            {'name': '250 نجمة', 'quantity': 250, 'price_usd': 4.99},
            {'name': '500 نجمة', 'quantity': 500, 'price_usd': 9.99},
            {'name': '1000 نجمة', 'quantity': 1000, 'price_usd': 19.99},
        ],
        'pubg': [
            {'name': '60 UC', 'quantity': 60, 'price_usd': 1.20},
            {'name': '180 UC', 'quantity': 180, 'price_usd': 3.30},
            {'name': '325 UC', 'quantity': 325, 'price_usd': 5.50},
            {'name': '660 UC', 'quantity': 660, 'price_usd': 10.99},
            {'name': '1800 UC', 'quantity': 1800, 'price_usd': 27.99},
            {'name': '3850 UC', 'quantity': 3850, 'price_usd': 54.99},
        ],
        'freefire': [
            {'name': '50 ماسة', 'quantity': 50, 'price_usd': 0.99},
            {'name': '100 ماسة', 'quantity': 100, 'price_usd': 1.99},
            {'name': '250 ماسة', 'quantity': 250, 'price_usd': 4.99},
            {'name': '500 ماسة', 'quantity': 500, 'price_usd': 9.99},
            {'name': '1000 ماسة', 'quantity': 1000, 'price_usd': 19.99},
        ],
        'monthly': [
            {'name': 'شهر واحد', 'quantity': 30, 'price_usd': 4.99},
            {'name': '3 أشهر', 'quantity': 90, 'price_usd': 12.99},
            {'name': '6 أشهر', 'quantity': 180, 'price_usd': 24.99},
            {'name': '12 شهر', 'quantity': 365, 'price_usd': 49.99},
        ],
        'yearly': [
            {'name': 'سنة واحدة', 'quantity': 365, 'price_usd': 49.99},
            {'name': 'سنتين', 'quantity': 730, 'price_usd': 89.99},
            {'name': '3 سنوات', 'quantity': 1095, 'price_usd': 129.99},
        ],
    }
    
    template = templates.get(template_name)
    if not template:
        flash('❌ قالب غير موجود', 'danger')
        return redirect(url_for('product_options', product_id=product_id))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('product_options', product_id=product_id))

    cur = conn.cursor()
    
    try:
        # حذف الخيارات القديمة (soft delete)
        cur.execute("UPDATE product_options SET is_active = FALSE WHERE product_id = %s", (product_id,))
        
        # إضافة الخيارات الجديدة
        for i, opt in enumerate(template):
            cur.execute("""
                INSERT INTO product_options (product_id, name, quantity, price_usd, sort_order, is_active)
                VALUES (%s, %s, %s, %s, %s, TRUE)
            """, (product_id, opt['name'], opt['quantity'], opt['price_usd'], i))
        
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'apply_template', 
                        f'تطبيق قالب {template_name} على المنتج {product_id}')
        
        flash(f'✅ تم تطبيق القالب بنجاح!', 'success')
        
    except Exception as e:
        logger.error(f"Error applying template: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('product_options', product_id=product_id))

# ============= إدارة النقاط =============

@app.route('/points')
@login_required
def points_management():
    """إدارة النقاط"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('points.html', settings={})

    cur = conn.cursor()
    
    try:
        # جلب إعدادات النقاط
        cur.execute("SELECT key, value FROM bot_settings WHERE key IN ('points_per_order', 'points_per_referral', 'points_to_usd')")
        settings = {row['key']: row['value'] for row in cur.fetchall()}
        
        # جلب طلبات الاسترداد المعلقة
        cur.execute("""
            SELECT r.*, u.username 
            FROM redemption_requests r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.status = 'pending'
            ORDER BY r.created_at DESC
        """)
        pending_redemptions = cur.fetchall()
        
        # جلب آخر 20 عملية استرداد
        cur.execute("""
            SELECT r.*, u.username 
            FROM redemption_requests r
            JOIN users u ON r.user_id = u.user_id
            ORDER BY r.created_at DESC LIMIT 20
        """)
        recent_redemptions = cur.fetchall()
        
        # إحصائيات النقاط
        cur.execute("""
            SELECT 
                COALESCE(SUM(total_points), 0) as total_points,
                COALESCE(SUM(total_points_earned), 0) as total_earned,
                COALESCE(SUM(total_points_redeemed), 0) as total_redeemed,
                COUNT(*) as users_with_points
            FROM users
            WHERE total_points > 0
        """)
        points_stats = cur.fetchone()
        
    except Exception as e:
        logger.error(f"Error in points_management: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        settings = {}
        pending_redemptions = []
        recent_redemptions = []
        points_stats = {}
    finally:
        cur.close()
        conn.close()
    
    return render_template('points.html',
                          settings=settings,
                          pending_redemptions=pending_redemptions,
                          recent_redemptions=recent_redemptions,
                          points_stats=points_stats)

@app.route('/points/update_settings', methods=['POST'])
@login_required
def update_points_settings():
    """تحديث إعدادات النقاط"""
    points_per_order = request.form.get('points_per_order')
    points_per_referral = request.form.get('points_per_referral')
    points_to_usd = request.form.get('points_to_usd')
    
    try:
        points_per_order = int(points_per_order) if points_per_order else 1
        points_per_referral = int(points_per_referral) if points_per_referral else 1
        points_to_usd = int(points_to_usd) if points_to_usd else 100
        
    except ValueError:
        flash('❌ البيانات غير صحيحة', 'danger')
        return redirect(url_for('points_management'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('points_management'))

    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO bot_settings (key, value) VALUES ('points_per_order', %s)
            ON CONFLICT (key) DO UPDATE SET value = %s
        """, (str(points_per_order), str(points_per_order)))
        
        cur.execute("""
            INSERT INTO bot_settings (key, value) VALUES ('points_per_referral', %s)
            ON CONFLICT (key) DO UPDATE SET value = %s
        """, (str(points_per_referral), str(points_per_referral)))
        
        cur.execute("""
            INSERT INTO bot_settings (key, value) VALUES ('points_to_usd', %s)
            ON CONFLICT (key) DO UPDATE SET value = %s
        """, (str(points_to_usd), str(points_to_usd)))
        
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'update_points_settings', 
                        f'تحديث إعدادات النقاط: طلب={points_per_order}, إحالة={points_per_referral}, دولار={points_to_usd}')
        
        flash(f'✅ تم تحديث إعدادات النقاط بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error updating points settings: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('points_management'))

@app.route('/redemption/<int:redemption_id>/approve', methods=['POST'])
@login_required
def approve_redemption(redemption_id):
    """الموافقة على طلب استرداد نقاط"""
    notes = request.form.get('notes', '')
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('points_management'))

    cur = conn.cursor()
    
    try:
        # جلب معلومات الطلب
        cur.execute("""
            SELECT user_id, points, amount_syp 
            FROM redemption_requests 
            WHERE id = %s AND status = 'pending'
        """, (redemption_id,))
        req = cur.fetchone()
        
        if not req:
            flash('❌ طلب الاسترداد غير موجود أو تمت معالجته مسبقاً', 'danger')
            return redirect(url_for('points_management'))
        
        # تحديث رصيد المستخدم
        cur.execute("""
            UPDATE users 
            SET balance = balance + %s, total_points = total_points - %s, total_points_redeemed = total_points_redeemed + %s
            WHERE user_id = %s
        """, (req['amount_syp'], req['points'], req['points'], req['user_id']))
        
        # تحديث حالة الطلب
        cur.execute("""
            UPDATE redemption_requests 
            SET status = 'approved', processed_by = %s, processed_at = CURRENT_TIMESTAMP, admin_notes = %s
            WHERE id = %s
        """, (session.get('user_id'), notes, redemption_id))
        
        # تسجيل في سجل النقاط
        cur.execute('''
            INSERT INTO points_history (user_id, points, action, description, created_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ''', (req['user_id'], req['points'], 'redeem_approved', f'تمت الموافقة على استرداد نقاط: {req["points"]}'))
        
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'approve_redemption', 
                        f'الموافقة على استرداد نقاط {redemption_id}')
        
        flash(f'✅ تمت الموافقة على طلب الاسترداد وإضافة {req["amount_syp"]:,.0f} ل.س للمستخدم', 'success')
        
    except Exception as e:
        logger.error(f"Error approving redemption: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('points_management'))

@app.route('/redemption/<int:redemption_id>/reject', methods=['POST'])
@login_required
def reject_redemption(redemption_id):
    """رفض طلب استرداد نقاط"""
    notes = request.form.get('notes', '')
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('points_management'))

    cur = conn.cursor()
    
    try:
        # جلب معلومات الطلب
        cur.execute("""
            SELECT user_id, points 
            FROM redemption_requests 
            WHERE id = %s AND status = 'pending'
        """, (redemption_id,))
        req = cur.fetchone()
        
        if not req:
            flash('❌ طلب الاسترداد غير موجود أو تمت معالجته مسبقاً', 'danger')
            return redirect(url_for('points_management'))
        
        # تحديث حالة الطلب
        cur.execute("""
            UPDATE redemption_requests 
            SET status = 'rejected', processed_by = %s, processed_at = CURRENT_TIMESTAMP, admin_notes = %s
            WHERE id = %s
        """, (session.get('user_id'), notes, redemption_id))
        
        # تسجيل في سجل النقاط
        cur.execute('''
            INSERT INTO points_history (user_id, points, action, description, created_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ''', (req['user_id'], req['points'], 'redeem_rejected', f'تم رفض استرداد نقاط: {req["points"]} - {notes}'))
        
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'reject_redemption', 
                        f'رفض استرداد نقاط {redemption_id}')
        
        flash(f'✅ تم رفض طلب الاسترداد', 'success')
        
    except Exception as e:
        logger.error(f"Error rejecting redemption: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('points_management'))

# ============= إدارة المشرفين =============

@app.route('/admins')
@login_required
@admin_required
def admins_management():
    """إدارة المشرفين"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('admins.html', admins=[])

    cur = conn.cursor()
    
    try:
        # جلب قائمة المشرفين
        cur.execute("""
            SELECT a.*, u.username, u.first_name 
            FROM admins a
            JOIN users u ON a.user_id = u.user_id
            ORDER BY a.role, a.created_at
        """)
        admins = cur.fetchall()
        
        # جلب سجل النشاطات
        cur.execute("""
            SELECT * FROM logs 
            WHERE user_id IN (SELECT user_id FROM admins)
            ORDER BY created_at DESC LIMIT 50
        """)
        logs = cur.fetchall()
        
    except Exception as e:
        logger.error(f"Error in admins_management: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        admins = []
        logs = []
    finally:
        cur.close()
        conn.close()
    
    return render_template('admins.html', admins=admins, logs=logs)

@app.route('/add_admin', methods=['POST'])
@login_required
@admin_required
def add_admin():
    """إضافة مشرف جديد"""
    user_id = request.form.get('user_id')
    role = request.form.get('role', 'moderator')
    
    if not user_id:
        flash('❌ الرجاء إدخال آيدي المستخدم', 'danger')
        return redirect(url_for('admins_management'))
    
    try:
        user_id = int(user_id)
    except ValueError:
        flash('❌ آيدي المستخدم غير صحيح', 'danger')
        return redirect(url_for('admins_management'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('admins_management'))

    cur = conn.cursor()
    
    try:
        # التحقق من وجود المستخدم
        cur.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
        if not cur.fetchone():
            flash('❌ المستخدم غير موجود في قاعدة البيانات', 'danger')
            return redirect(url_for('admins_management'))
        
        # التحقق من عدم وجوده كمشرف مسبقاً
        cur.execute("SELECT user_id FROM admins WHERE user_id = %s", (user_id,))
        if cur.fetchone():
            flash('❌ المستخدم مشرف مسبقاً', 'danger')
            return redirect(url_for('admins_management'))
        
        cur.execute("""
            INSERT INTO admins (user_id, role, added_by, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """, (user_id, role, session.get('user_id')))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'add_admin', f'إضافة مشرف {user_id} بدور {role}')
        
        flash(f'✅ تم إضافة المستخدم {user_id} كمشرف', 'success')
        
    except Exception as e:
        logger.error(f"Error adding admin: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('admins_management'))

@app.route('/remove_admin/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def remove_admin(user_id):
    """إزالة مشرف"""
    if user_id == config.ADMIN_ID:
        flash('❌ لا يمكن إزالة المشرف الأساسي', 'danger')
        return redirect(url_for('admins_management'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('admins_management'))

    cur = conn.cursor()
    
    try:
        cur.execute("DELETE FROM admins WHERE user_id = %s", (user_id,))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'remove_admin', f'إزالة مشرف {user_id}')
        
        flash(f'✅ تم إزالة المستخدم {user_id} من قائمة المشرفين', 'success')
        
    except Exception as e:
        logger.error(f"Error removing admin: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('admins_management'))

# ============= إدارة VIP =============

@app.route('/vip')
@login_required
def vip_management():
    """إدارة نظام VIP"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('vip.html', levels=[], users=[])

    cur = conn.cursor()
    
    try:
        # جلب مستويات VIP
        cur.execute("SELECT * FROM vip_levels ORDER BY level")
        vip_levels = cur.fetchall()
        
        # جلب مستخدمي VIP
        cur.execute("""
            SELECT user_id, username, first_name, vip_level, discount_percent, 
                   manual_vip, total_spent, created_at
            FROM users
            WHERE vip_level > 0 OR manual_vip = TRUE
            ORDER BY vip_level DESC, total_spent DESC
            LIMIT 50
        """)
        vip_users = cur.fetchall()
        
        # إحصائيات VIP
        cur.execute("""
            SELECT 
                vip_level,
                COUNT(*) as user_count,
                COALESCE(SUM(total_spent), 0) as total_spent
            FROM users
            WHERE vip_level > 0
            GROUP BY vip_level
            ORDER BY vip_level
        """)
        vip_stats = cur.fetchall()
        
    except Exception as e:
        logger.error(f"Error in vip_management: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        vip_levels = []
        vip_users = []
        vip_stats = []
    finally:
        cur.close()
        conn.close()
    
    return render_template('vip.html',
                          levels=vip_levels,
                          users=vip_users,
                          stats=vip_stats)

@app.route('/vip/update_level/<int:level>', methods=['POST'])
@login_required
def update_vip_level(level):
    """تحديث مستوى VIP"""
    name = request.form.get('name')
    min_spent = request.form.get('min_spent')
    discount_percent = request.form.get('discount_percent')
    icon = request.form.get('icon')
    
    try:
        min_spent = float(min_spent)
        discount_percent = float(discount_percent)
    except ValueError:
        flash('❌ البيانات غير صحيحة', 'danger')
        return redirect(url_for('vip_management'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('vip_management'))

    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE vip_levels 
            SET name = %s, min_spent = %s, discount_percent = %s, icon = %s
            WHERE level = %s
        """, (name, min_spent, discount_percent, icon, level))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'update_vip_level', f'تحديث مستوى VIP {level}')
        
        flash(f'✅ تم تحديث مستوى VIP {level} بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error updating VIP level: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('vip_management'))

# ============= إرسال رسالة جماعية =============

@app.route('/broadcast')
@login_required
def broadcast_page():
    """صفحة إرسال رسالة جماعية"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('broadcast.html')

    cur = conn.cursor()
    
    try:
        cur.execute("SELECT COUNT(*) as total FROM users")
        total_users = cur.fetchone()['total'] or 0
        
        cur.execute("SELECT COUNT(*) as active FROM users WHERE NOT is_banned")
        active_users = cur.fetchone()['active'] or 0
        
    except Exception as e:
        logger.error(f"Error in broadcast_page: {e}")
        total_users = 0
        active_users = 0
    finally:
        cur.close()
        conn.close()
    
    return render_template('broadcast.html',
                          total_users=total_users,
                          active_users=active_users)

@app.route('/send_broadcast', methods=['POST'])
@login_required
def send_broadcast():
    """إرسال رسالة جماعية"""
    message = request.form.get('message')
    target = request.form.get('target', 'all')  # all, active, specific
    specific_users = request.form.get('specific_users', '')
    
    if not message:
        flash('❌ الرجاء إدخال نص الرسالة', 'danger')
        return redirect(url_for('broadcast_page'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('broadcast_page'))

    cur = conn.cursor()
    
    try:
        if target == 'specific' and specific_users:
            # إرسال لمستخدمين محددين
            user_ids = [int(uid.strip()) for uid in specific_users.split('\n') if uid.strip()]
            query = "SELECT user_id, username FROM users WHERE user_id = ANY(%s)"
            cur.execute(query, (user_ids,))
        else:
            # إرسال للكل أو للمستخدمين النشطين فقط
            query = "SELECT user_id, username FROM users"
            if target == 'active':
                query += " WHERE NOT is_banned"
            cur.execute(query)
        
        users = cur.fetchall()
        
        # هنا يتم إرسال الرسائل عبر البوت
        # سنقوم بتسجيلها في قاعدة البيانات
        for user in users:
            cur.execute("""
                INSERT INTO broadcast_queue (user_id, message, status, created_at)
                VALUES (%s, %s, 'pending', CURRENT_TIMESTAMP)
            """, (user['user_id'], message))
        
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'broadcast', 
                        f'إرسال رسالة جماعية إلى {len(users)} مستخدم')
        
        flash(f'✅ تمت إضافة {len(users)} رسالة إلى قائمة الإرسال', 'success')
        
    except Exception as e:
        logger.error(f"Error sending broadcast: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('broadcast_page'))

# ============= الإحصائيات =============

@app.route('/statistics')
@login_required
def statistics_page():
    """صفحة الإحصائيات"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('statistics.html')

    cur = conn.cursor()
    
    try:
        # إحصائيات المستخدمين
        cur.execute("""
            SELECT 
                COUNT(*) as total_users,
                COUNT(CASE WHEN is_banned THEN 1 END) as banned_users,
                COALESCE(SUM(balance), 0) as total_balance,
                COALESCE(SUM(total_deposits), 0) as total_deposits,
                COALESCE(SUM(total_orders), 0) as total_orders_count,
                COALESCE(SUM(total_spent), 0) as total_spent
            FROM users
        """)
        users_stats = cur.fetchone()
        
        # إحصائيات الطلبات
        cur.execute("""
            SELECT 
                COUNT(*) as total_orders,
                COALESCE(SUM(total_amount_syp), 0) as total_amount,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_orders,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_orders,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_orders,
                COALESCE(SUM(points_earned), 0) as total_points_given
            FROM orders
        """)
        orders_stats = cur.fetchone()
        
        # إحصائيات الإيداعات
        cur.execute("""
            SELECT 
                COUNT(*) as total_deposits,
                COALESCE(SUM(amount_syp), 0) as total_amount,
                COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_deposits,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_deposits
            FROM deposit_requests
        """)
        deposits_stats = cur.fetchone()
        
        # إحصائيات النقاط
        cur.execute("""
            SELECT 
                COALESCE(SUM(total_points), 0) as total_points,
                COALESCE(SUM(total_points_earned), 0) as total_earned,
                COALESCE(SUM(total_points_redeemed), 0) as total_redeemed,
                COUNT(DISTINCT user_id) as users_with_points
            FROM users
        """)
        points_stats = cur.fetchone()
        
        # إحصائيات يومية لآخر 7 أيام
        cur.execute("""
            WITH dates AS (
                SELECT generate_series(
                    CURRENT_DATE - INTERVAL '6 days',
                    CURRENT_DATE,
                    INTERVAL '1 day'
                )::date AS date
            )
            SELECT 
                d.date,
                COUNT(DISTINCT u.user_id) as new_users,
                COUNT(DISTINCT o.id) as orders_count,
                COALESCE(SUM(o.total_amount_syp), 0) as orders_amount,
                COUNT(DISTINCT dr.id) as deposits_count,
                COALESCE(SUM(dr.amount_syp), 0) as deposits_amount
            FROM dates d
            LEFT JOIN users u ON DATE(u.created_at) = d.date
            LEFT JOIN orders o ON DATE(o.created_at) = d.date
            LEFT JOIN deposit_requests dr ON DATE(dr.created_at) = d.date AND dr.status = 'approved'
            GROUP BY d.date
            ORDER BY d.date
        """)
        daily_stats = cur.fetchall()
        
        # أكثر التطبيقات طلباً
        cur.execute("""
            SELECT a.name, COUNT(o.id) as order_count, COALESCE(SUM(o.total_amount_syp), 0) as total_amount
            FROM orders o
            JOIN applications a ON o.app_id = a.id
            WHERE o.status = 'completed'
            GROUP BY a.name
            ORDER BY order_count DESC
            LIMIT 10
        """)
        top_apps = cur.fetchall()
        
        # أكثر المستخدمين إنفاقاً
        cur.execute("""
            SELECT user_id, username, first_name, total_spent
            FROM users
            WHERE total_spent > 0
            ORDER BY total_spent DESC
            LIMIT 10
        """)
        top_spenders = cur.fetchall()
        
    except Exception as e:
        logger.error(f"Error in statistics_page: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        users_stats = orders_stats = deposits_stats = points_stats = {}
        daily_stats = top_apps = top_spenders = []
    finally:
        cur.close()
        conn.close()
    
    return render_template('statistics.html',
                          users_stats=users_stats,
                          orders_stats=orders_stats,
                          deposits_stats=deposits_stats,
                          points_stats=points_stats,
                          daily_stats=daily_stats,
                          top_apps=top_apps,
                          top_spenders=top_spenders)

# ============= إعدادات البوت =============

@app.route('/settings')
@login_required
@admin_required
def settings_page():
    """صفحة إعدادات البوت"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('settings.html')

    cur = conn.cursor()
    
    try:
        # جلب جميع الإعدادات
        cur.execute("SELECT key, value, description FROM bot_settings ORDER BY key")
        settings_list = cur.fetchall()
        settings = {row['key']: row for row in settings_list}
        
        # جلب أرقام سيرياتل
        cur.execute("SELECT value FROM bot_settings WHERE key = 'syriatel_numbers'")
        syriatel_row = cur.fetchone()
        syriatel_numbers = syriatel_row['value'].split(',') if syriatel_row and syriatel_row['value'] else config.SYRIATEL_NUMS
        
    except Exception as e:
        logger.error(f"Error in settings_page: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        settings = {}
        syriatel_numbers = config.SYRIATEL_NUMS
    finally:
        cur.close()
        conn.close()
    
    return render_template('settings.html',
                          settings=settings,
                          syriatel_numbers=syriatel_numbers)

@app.route('/update_setting/<key>', methods=['POST'])
@login_required
@admin_required
def update_setting(key):
    """تحديث إعداد معين"""
    value = request.form.get('value')
    
    if value is None:
        flash('❌ الرجاء إدخال القيمة', 'danger')
        return redirect(url_for('settings_page'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('settings_page'))

    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO bot_settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
        """, (key, value, value))
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'update_setting', f'تحديث إعداد {key}')
        
        flash(f'✅ تم تحديث الإعداد {key} بنجاح', 'success')
        
    except Exception as e:
        logger.error(f"Error updating setting: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('settings_page'))

@app.route('/update_syriatel_numbers', methods=['POST'])
@login_required
@admin_required
def update_syriatel_numbers():
    """تحديث أرقام سيرياتل"""
    numbers = request.form.get('numbers', '')
    
    numbers_list = [num.strip() for num in numbers.split('\n') if num.strip()]
    numbers_str = ','.join(numbers_list)
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('settings_page'))

    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO bot_settings (key, value, description) 
            VALUES ('syriatel_numbers', %s, 'أرقام سيرياتل كاش')
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
        """, (numbers_str, numbers_str))
        conn.commit()
        
        # تحديث في config
        config.SYRIATEL_NUMS = numbers_list
        
        log_admin_action(session.get('user_id'), 'update_syriatel', f'تحديث أرقام سيرياتل')
        
        flash(f'✅ تم تحديث أرقام سيرياتل بنجاح ({len(numbers_list)} رقم)', 'success')
        
    except Exception as e:
        logger.error(f"Error updating syriatel numbers: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('settings_page'))

# ============= تصفير البوت =============

@app.route('/reset_bot', methods=['POST'])
@login_required
@admin_required
def reset_bot():
    """تصفير البوت"""
    confirm = request.form.get('confirm')
    new_rate = request.form.get('new_rate')
    
    if confirm != 'YES':
        flash('❌ الرجاء كتابة YES للتأكيد', 'danger')
        return redirect(url_for('settings_page'))
    
    try:
        new_rate = float(new_rate) if new_rate else config.USD_TO_SYP
    except ValueError:
        flash('❌ سعر الصرف غير صحيح', 'danger')
        return redirect(url_for('settings_page'))
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('settings_page'))

    cur = conn.cursor()
    
    try:
        # حذف جميع البيانات
        cur.execute("DELETE FROM points_history")
        cur.execute("DELETE FROM redemption_requests")
        cur.execute("DELETE FROM deposit_requests")
        cur.execute("DELETE FROM orders")
        
        # الاحتفاظ بالمشرفين فقط
        admin_ids = [config.ADMIN_ID] + config.MODERATORS
        if admin_ids:
            admin_ids_str = ','.join([str(id) for id in admin_ids if id])
            cur.execute(f"DELETE FROM users WHERE user_id NOT IN ({admin_ids_str})")
            
            # تصفير المشرفين
            for admin_id in admin_ids:
                if admin_id:
                    cur.execute("""
                        UPDATE users 
                        SET balance = 0, total_points = 0, total_deposits = 0, total_orders = 0,
                            referral_count = 0, referral_earnings = 0, total_points_earned = 0,
                            total_points_redeemed = 0, vip_level = 0, total_spent = 0,
                            discount_percent = 0, manual_vip = FALSE
                        WHERE user_id = %s
                    """, (admin_id,))
        else:
            cur.execute("DELETE FROM users")
        
        # تحديث سعر الصرف
        cur.execute("""
            INSERT INTO bot_settings (key, value) VALUES ('usd_to_syp', %s)
            ON CONFLICT (key) DO UPDATE SET value = %s
        """, (str(new_rate), str(new_rate)))
        
        # إعادة تعيين إعدادات النقاط
        cur.execute("""
            INSERT INTO bot_settings (key, value) VALUES ('points_per_order', '1')
            ON CONFLICT (key) DO UPDATE SET value = '1'
        """)
        cur.execute("""
            INSERT INTO bot_settings (key, value) VALUES ('points_per_referral', '1')
            ON CONFLICT (key) DO UPDATE SET value = '1'
        """)
        cur.execute("""
            INSERT INTO bot_settings (key, value) VALUES ('points_to_usd', '100')
            ON CONFLICT (key) DO UPDATE SET value = '100'
        """)
        
        conn.commit()
        
        log_admin_action(session.get('user_id'), 'reset_bot', f'تصفير البوت')
        
        flash(f'✅ تم تصفير البوت بنجاح! سعر الصرف الجديد: {new_rate:,.0f} ل.س', 'success')
        
    except Exception as e:
        logger.error(f"Error resetting bot: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('settings_page'))

# ============= معالجة طلبات الشحن =============

@app.route('/deposits')
@login_required
def deposits_management():
    """إدارة طلبات الشحن"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('deposits.html', deposits=[])

    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT d.*, u.username, u.first_name
            FROM deposit_requests d
            JOIN users u ON d.user_id = u.user_id
            ORDER BY 
                CASE WHEN d.status = 'pending' THEN 1 ELSE 2 END,
                d.created_at DESC
            LIMIT 100
        """)
        deposits = cur.fetchall()
        
    except Exception as e:
        logger.error(f"Error in deposits_management: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        deposits = []
    finally:
        cur.close()
        conn.close()
    
    return render_template('deposits.html', deposits=deposits)

@app.route('/deposit/<int:deposit_id>/process', methods=['POST'])
@login_required
def process_deposit(deposit_id):
    """معالجة طلب شحن"""
    action = request.form.get('action')
    notes = request.form.get('notes', '')
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('deposits_management'))

    cur = conn.cursor()
    
    try:
        if action == 'approve':
            # جلب معلومات الطلب
            cur.execute("""
                SELECT user_id, amount_syp 
                FROM deposit_requests 
                WHERE id = %s AND status = 'pending'
            """, (deposit_id,))
            deposit = cur.fetchone()
            
            if deposit:
                # تحديث رصيد المستخدم
                cur.execute("""
                    UPDATE users 
                    SET balance = balance + %s, total_deposits = total_deposits + %s 
                    WHERE user_id = %s
                """, (deposit['amount_syp'], deposit['amount_syp'], deposit['user_id']))
                
                # تحديث حالة الطلب
                cur.execute("""
                    UPDATE deposit_requests 
                    SET status = 'approved', processed_by = %s, processed_at = CURRENT_TIMESTAMP, admin_notes = %s
                    WHERE id = %s
                """, (session.get('user_id'), notes, deposit_id))
                
                flash(f'✅ تمت الموافقة على طلب الشحن #{deposit_id}', 'success')
        
        elif action == 'reject':
            cur.execute("""
                UPDATE deposit_requests 
                SET status = 'rejected', processed_by = %s, processed_at = CURRENT_TIMESTAMP, admin_notes = %s
                WHERE id = %s
            """, (session.get('user_id'), notes, deposit_id))
            flash(f'✅ تم رفض طلب الشحن #{deposit_id}', 'info')
        
        conn.commit()
        
        log_admin_action(session.get('user_id'), f'process_deposit_{action}', 
                        f'معالجة طلب شحن {deposit_id}: {action}')
        
    except Exception as e:
        logger.error(f"Error processing deposit: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('deposits_management'))

# ============= معالجة طلبات التطبيقات =============

@app.route('/orders')
@login_required
def orders_management():
    """إدارة طلبات التطبيقات"""
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('orders.html', orders=[])

    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT o.*, u.username, u.first_name, a.name as app_name
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            JOIN applications a ON o.app_id = a.id
            ORDER BY 
                CASE WHEN o.status = 'pending' THEN 1 
                     WHEN o.status = 'processing' THEN 2
                     ELSE 3 END,
                o.created_at DESC
            LIMIT 100
        """)
        orders = cur.fetchall()
        
    except Exception as e:
        logger.error(f"Error in orders_management: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
        orders = []
    finally:
        cur.close()
        conn.close()
    
    return render_template('orders.html', orders=orders)

@app.route('/order/<int:order_id>/process', methods=['POST'])
@login_required
def process_order(order_id):
    """معالجة طلب تطبيق"""
    action = request.form.get('action')
    notes = request.form.get('notes', '')
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('orders_management'))

    cur = conn.cursor()
    
    try:
        if action == 'approve':
            cur.execute("""
                UPDATE orders 
                SET status = 'processing', admin_notes = %s, processed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (notes, order_id))
            flash(f'✅ تمت الموافقة على الطلب #{order_id}', 'success')
        
        elif action == 'complete':
            # جلب معلومات الطلب لإضافة النقاط
            cur.execute("""
                SELECT user_id, points_earned 
                FROM orders 
                WHERE id = %s
            """, (order_id,))
            order = cur.fetchone()
            
            if order and order['points_earned']:
                cur.execute("""
                    UPDATE users 
                    SET total_points = total_points + %s, total_points_earned = total_points_earned + %s
                    WHERE user_id = %s
                """, (order['points_earned'], order['points_earned'], order['user_id']))
            
            cur.execute("""
                UPDATE orders 
                SET status = 'completed', admin_notes = %s, completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (notes, order_id))
            flash(f'✅ تم تأكيد تنفيذ الطلب #{order_id}', 'success')
        
        elif action == 'fail':
            # جلب معلومات الطلب لإعادة الرصيد
            cur.execute("""
                SELECT user_id, total_amount_syp 
                FROM orders 
                WHERE id = %s AND status IN ('pending', 'processing')
            """, (order_id,))
            order = cur.fetchone()
            
            if order:
                cur.execute("""
                    UPDATE users 
                    SET balance = balance + %s 
                    WHERE user_id = %s
                """, (order['total_amount_syp'], order['user_id']))
            
            cur.execute("""
                UPDATE orders 
                SET status = 'failed', admin_notes = %s, completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (notes, order_id))
            flash(f'✅ تم إلغاء الطلب #{order_id} وإعادة الرصيد', 'info')
        
        conn.commit()
        
        log_admin_action(session.get('user_id'), f'process_order_{action}', 
                        f'معالجة طلب {order_id}: {action}')
        
    except Exception as e:
        logger.error(f"Error processing order: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('orders_management'))

# ============= البحث =============

@app.route('/search')
@login_required
def search():
    """صفحة البحث"""
    query = request.args.get('q', '')
    search_type = request.args.get('type', 'all')
    
    if not query:
        return render_template('search.html', results={}, query=query)
    
    conn = get_db_connection()
    if not conn:
        flash('❌ خطأ في الاتصال بقاعدة البيانات', 'danger')
        return render_template('search.html', results={}, query=query)

    cur = conn.cursor()
    results = {}
    
    try:
        # البحث في المستخدمين
        if search_type in ['all', 'users']:
            cur.execute("""
                SELECT user_id, username, first_name, last_name, balance, is_banned, created_at
                FROM users
                WHERE user_id::text LIKE %s 
                   OR username ILIKE %s 
                   OR first_name ILIKE %s
                LIMIT 20
            """, (f'%{query}%', f'%{query}%', f'%{query}%'))
            results['users'] = cur.fetchall()
        
        # البحث في الطلبات
        if search_type in ['all', 'orders']:
            cur.execute("""
                SELECT o.id, o.user_id, u.username, a.name, o.status, o.created_at
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                JOIN applications a ON o.app_id = a.id
                WHERE o.id::text LIKE %s OR o.target_id ILIKE %s
                LIMIT 20
            """, (f'%{query}%', f'%{query}%'))
            results['orders'] = cur.fetchall()
        
        # البحث في طلبات الشحن
        if search_type in ['all', 'deposits']:
            cur.execute("""
                SELECT d.id, d.user_id, u.username, d.amount_syp, d.status, d.created_at
                FROM deposit_requests d
                JOIN users u ON d.user_id = u.user_id
                WHERE d.id::text LIKE %s OR d.tx_info ILIKE %s
                LIMIT 20
            """, (f'%{query}%', f'%{query}%'))
            results['deposits'] = cur.fetchall()
        
    except Exception as e:
        logger.error(f"Error in search: {e}")
        flash(f'❌ خطأ: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return render_template('search.html', results=results, query=query)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    logger.info(f"🌐 بدأ تشغيل لوحة التحكم على المنفذ {port}...")
    logger.info(f"🔧 Debug mode: {debug}")
    
    app.run(host=host, port=port, debug=debug)