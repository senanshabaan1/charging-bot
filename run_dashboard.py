# run_dashboard.py
import logging
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import psycopg2
from config import DB_CONFIG, WEB_USERNAME, WEB_PASSWORD
import config
from functools import wraps
from datetime import datetime

# إنشاء تطبيق Flask
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "secret_key_for_session_management")

@app.route('/health')
def health():
    """مسار للتحقق من صحة الخدمة - مهم لـ Render"""
    return 'OK', 200

def get_db_connection():
    """إنشاء اتصال بقاعدة البيانات"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Error connecting to DB: {e}")
        return None

def login_required(f):
    """ديكوريتور للتحقق من تسجيل الدخول"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
@login_required
def login():
    """صفحة تسجيل الدخول"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == WEB_USERNAME and password == WEB_PASSWORD:
            session['logged_in'] = True
            flash('تم تسجيل الدخول بنجاح', 'success')
            return redirect(url_for('index'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    """تسجيل الخروج"""
    session.pop('logged_in', None)
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """الصفحة الرئيسية"""
    conn = get_db_connection()
    if not conn: 
        return "خطأ في الاتصال بقاعدة البيانات", 500

    cur = conn.cursor()

    # إحصائيات عامة
    cur.execute('SELECT COUNT(*) FROM users')
    total_users = cur.fetchone()[0] or 0

    cur.execute('SELECT SUM(balance) FROM users')
    total_balances = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM deposit_requests WHERE status = 'pending'")
    pending_deposits_count = cur.fetchone()[0] or 0

    # عد الطلبات المعلقة
    pending_orders_count = 0
    try:
        cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
        pending_orders_count = cur.fetchone()[0] or 0
    except:
        pass

    # قائمة المستخدمين
    cur.execute('SELECT user_id, username, balance, is_banned FROM users ORDER BY user_id DESC')
    users = cur.fetchall()

    # طلبات الشحن المعلقة
    cur.execute("""
        SELECT id, user_id, username, method, amount, amount_syp, 
               created_at, tx_info, photo_file_id
        FROM deposit_requests 
        WHERE status = 'pending' 
        ORDER BY created_at DESC
    """)
    pending_deposits_raw = cur.fetchall()
    
    pending_deposits = []
    for row in pending_deposits_raw:
        pending_deposits.append({
            'id': row[0],
            'user_id': row[1],
            'username': row[2] or f"user_{row[1]}",
            'method': row[3],
            'amount': row[4],
            'amount_syp': row[5],
            'created_at': row[6],
            'tx_info': row[7],
            'has_photo': row[8] is not None
        })

    # طلبات التطبيقات المعلقة
    pending_orders = []
    try:
        cur.execute("""
            SELECT o.id, u.username, a.name, o.quantity, o.total_amount_syp, 
                   o.status, o.created_at, o.app_id, o.target_id
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            JOIN applications a ON o.app_id = a.id
            WHERE o.status = 'pending'
            ORDER BY o.created_at DESC
        """)
        pending_orders = cur.fetchall()
    except:
        pass

    # جلب سعر الصرف من قاعدة البيانات
    try:
        cur.execute("SELECT value FROM bot_settings WHERE key = 'usd_to_syp'")
        rate_row = cur.fetchone()
        current_rate = float(rate_row[0]) if rate_row else 25000
    except:
        current_rate = 25000

    cur.close()
    conn.close()

    return render_template('index.html',
                           total_users=total_users,
                           total_balances=total_balances,
                           pending_deposits_count=pending_deposits_count,
                           pending_orders_count=pending_orders_count,
                           users=users,
                           pending_deposits=pending_deposits,
                           pending_orders=pending_orders,
                           rate=current_rate)

@app.route('/update_rate', methods=['POST'])
@login_required
def update_rate():
    """تحديث سعر الصرف"""
    new_rate = request.form.get('new_rate')
    try:
        new_rate_float = float(new_rate)
        
        # تحديث في قاعدة البيانات
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bot_settings (key, value, description) 
            VALUES ('usd_to_syp', %s, 'سعر صرف الدولار مقابل الليرة')
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
        """, (str(new_rate_float), str(new_rate_float)))
        conn.commit()
        cur.close()
        conn.close()
        
        # تحديث المتغير العام في config
        config.USD_TO_SYP = new_rate_float
        
        flash(f'✅ تم تحديث سعر الصرف إلى {new_rate_float}', 'success')
    except Exception as e:
        flash(f'❌ خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

# باقي الدوال (deposit_action, order_action, user_management, etc) كما هي...

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    logging.info(f"🌐 بدأ تشغيل لوحة التحكم على المنفذ {port}...")
    app.run(host=host, port=port, debug=False)
