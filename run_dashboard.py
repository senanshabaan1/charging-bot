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
@app.route('/user_management')
@login_required
def user_management():
    """إدارة المستخدمين"""
    conn = get_db_connection()
    if not conn:
        return "خطأ في الاتصال بقاعدة البيانات", 500

    cur = conn.cursor()
    
    # جلب المستخدمين
    cur.execute("SELECT user_id, username, balance, is_banned, created_at FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    
    # إحصائيات المستخدمين
    cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_banned THEN 1 ELSE 0 END) as banned FROM users")
    user_stats = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return render_template('users.html',
                          users=users,
                          user_stats=user_stats,
                          rate=config.USD_TO_SYP)

@app.route('/user_action/<int:user_id>', methods=['POST'])
@login_required
def user_action(user_id):
    """إجراءات على المستخدم"""
    action = request.form.get('action')
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        if action == 'toggle_ban':
            # تبديل حالة الحظر
            cur.execute('UPDATE users SET is_banned = NOT is_banned WHERE user_id = %s', (user_id,))
            flash(f'تم تغيير حالة حظر المستخدم {user_id}', 'info')

        elif action == 'set_balance':
            new_bal = request.form.get('balance')
            if new_bal:
                cur.execute('UPDATE users SET balance = %s WHERE user_id = %s', (float(new_bal), user_id))
                flash(f'تم تحديث رصيد المستخدم {user_id} إلى {new_bal}', 'success')

        conn.commit()
    except Exception as e:
        flash(f'حدث خطأ: {e}', 'danger')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('user_management'))

@app.route('/applications')
@login_required
def applications_management():
    """إدارة التطبيقات"""
    conn = get_db_connection()
    if not conn:
        return "خطأ في الاتصال بقاعدة البيانات", 500

    cur = conn.cursor()
    
    # جلب الأقسام
    cur.execute("SELECT id, name, display_name, icon FROM categories ORDER BY sort_order")
    categories = cur.fetchall()
    
    # جلب التطبيقات مع أقسامها
    cur.execute("""
        SELECT a.id, a.name, a.unit_price_usd, a.min_units, a.profit_percentage, 
               a.category_id, c.display_name as category_name, c.icon as category_icon
        FROM applications a
        LEFT JOIN categories c ON a.category_id = c.id
        ORDER BY c.sort_order, a.id
    """)
    applications = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('applications.html',
                          applications=applications,
                          categories=categories,
                          rate=config.USD_TO_SYP)

@app.route('/add_application', methods=['POST'])
@login_required
def add_application():
    """إضافة تطبيق جديد"""
    name = request.form.get('name')
    unit_price = request.form.get('unit_price')
    min_units = request.form.get('min_units')
    profit_percentage = request.form.get('profit_percentage', 10)
    category_id = request.form.get('category_id')
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # التحقق إذا كان التطبيق موجوداً بالفعل
        cur.execute("SELECT id FROM applications WHERE name = %s", (name,))
        existing = cur.fetchone()
        
        if existing:
            flash(f'التطبيق "{name}" موجود بالفعل!', 'danger')
        else:
            cur.execute(
                "INSERT INTO applications (name, unit_price_usd, min_units, profit_percentage, category_id) VALUES (%s, %s, %s, %s, %s)",
                (name, float(unit_price), int(min_units), float(profit_percentage), category_id)
            )
            conn.commit()
            
            flash(f'✅ تم إضافة التطبيق "{name}" بنجاح', 'success')
            
    except Exception as e:
        flash(f'حدث خطأ: {e}', 'danger')
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

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "UPDATE applications SET name = %s, unit_price_usd = %s, min_units = %s, profit_percentage = %s, category_id = %s WHERE id = %s",
            (name, float(unit_price), int(min_units), float(profit_percentage), category_id, app_id)
        )
        conn.commit()
        
        flash(f'✅ تم تحديث التطبيق "{name}" بنجاح', 'success')
        
    except Exception as e:
        flash(f'حدث خطأ: {e}', 'danger')
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
        cur = conn.cursor()
        
        # الحصول على اسم التطبيق قبل الحذف
        cur.execute("SELECT name FROM applications WHERE id = %s", (app_id,))
        app = cur.fetchone()
        
        if app:
            app_name = app[0]
            cur.execute("DELETE FROM applications WHERE id = %s", (app_id,))
            conn.commit()
            flash(f'✅ تم حذف التطبيق "{app_name}" بنجاح', 'success')
        else:
            flash('❌ التطبيق غير موجود', 'danger')
            
    except Exception as e:
        flash(f'حدث خطأ: {e}', 'danger')
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

    return redirect(url_for('applications_management'))

@app.route('/categories')
@login_required
def categories_management():
    """إدارة الأقسام"""
    conn = get_db_connection()
    if not conn:
        return "خطأ في الاتصال بقاعدة البيانات", 500

    cur = conn.cursor()
    
    # جلب الأقسام
    cur.execute("SELECT id, name, display_name, icon, sort_order FROM categories ORDER BY sort_order")
    categories = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('categories.html',
                          categories=categories)

@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    """إضافة قسم جديد"""
    name = request.form.get('name')
    display_name = request.form.get('display_name')
    icon = request.form.get('icon', '📁')
    sort_order = request.form.get('sort_order', 0)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "INSERT INTO categories (name, display_name, icon, sort_order) VALUES (%s, %s, %s, %s)",
            (name, display_name, icon, int(sort_order))
        )
        conn.commit()
        
        flash(f'✅ تم إضافة القسم "{display_name}" بنجاح', 'success')
        
    except Exception as e:
        flash(f'حدث خطأ: {e}', 'danger')
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
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

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "UPDATE categories SET name = %s, display_name = %s, icon = %s, sort_order = %s WHERE id = %s",
            (name, display_name, icon, int(sort_order), cat_id)
        )
        conn.commit()
        
        flash(f'✅ تم تحديث القسم "{display_name}" بنجاح', 'success')
        
    except Exception as e:
        flash(f'حدث خطأ: {e}', 'danger')
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

    return redirect(url_for('categories_management'))

@app.route('/delete_category/<int:cat_id>', methods=['POST'])
@login_required
def delete_category(cat_id):
    """حذف قسم"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # التحقق من عدم وجود تطبيقات في هذا القسم
        cur.execute("SELECT COUNT(*) FROM applications WHERE category_id = %s", (cat_id,))
        count = cur.fetchone()[0]
        
        if count > 0:
            flash(f'❌ لا يمكن حذف القسم لأنه يحتوي على {count} تطبيق/تطبيقات', 'danger')
        else:
            cur.execute("DELETE FROM categories WHERE id = %s", (cat_id,))
            conn.commit()
            flash(f'✅ تم حذف القسم بنجاح', 'success')
            
    except Exception as e:
        flash(f'حدث خطأ: {e}', 'danger')
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

    return redirect(url_for('categories_management'))

@app.route('/deposit_action/<int:deposit_id>', methods=['POST'])
@login_required
def deposit_action(deposit_id):
    """معالجة طلب الإيداع"""
    action = request.form.get('action')
    notes = request.form.get('notes', '')
    
    conn = get_db_connection()
    if not conn:
        flash('خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('index'))

    cur = conn.cursor()

    try:
        if action == 'approve':
            # جلب معلومات الطلب
            cur.execute("SELECT user_id, amount_syp FROM deposit_requests WHERE id = %s", (deposit_id,))
            deposit = cur.fetchone()
            
            if deposit:
                user_id, amount_syp = deposit
                # تحديث رصيد المستخدم
                cur.execute("UPDATE users SET balance = balance + %s, total_deposits = total_deposits + %s WHERE user_id = %s", 
                           (amount_syp, amount_syp, user_id))
                # تحديث حالة الطلب
                cur.execute("UPDATE deposit_requests SET status = 'approved', admin_notes = %s WHERE id = %s", (notes, deposit_id))
                flash(f'تمت الموافقة على طلب الشحن #{deposit_id} وإضافة {amount_syp} ل.س للمستخدم {user_id}', 'success')
        
        elif action == 'reject':
            cur.execute("UPDATE deposit_requests SET status = 'rejected', admin_notes = %s WHERE id = %s", (notes, deposit_id))
            flash(f'تم رفض طلب الشحن #{deposit_id}', 'info')

        conn.commit()
    except Exception as e:
        flash(f'حدث خطأ: {e}', 'danger')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('index'))

@app.route('/order_action/<int:order_id>', methods=['POST'])
@login_required
def order_action(order_id):
    """معالجة طلب التطبيق"""
    action = request.form.get('action')
    notes = request.form.get('notes', '')
    
    conn = get_db_connection()
    if not conn:
        flash('خطأ في الاتصال بقاعدة البيانات', 'danger')
        return redirect(url_for('index'))

    cur = conn.cursor()

    try:
        if action == 'complete':
            # تحديث حالة الطلب إلى مكتمل
            cur.execute("UPDATE orders SET status = 'completed', admin_notes = %s WHERE id = %s", 
                       (notes, order_id))
            flash(f'تم تأكيد تنفيذ الطلب #{order_id}', 'success')
        
        elif action == 'failed':
            # جلب معلومات الطلب لإعادة الرصيد
            cur.execute("SELECT user_id, total_amount_syp FROM orders WHERE id = %s", (order_id,))
            order = cur.fetchone()
            
            if order:
                user_id, amount_syp = order
                # إعادة الرصيد للمستخدم
                cur.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", 
                           (amount_syp, user_id))
                # تحديث حالة الطلب إلى فاشل
                cur.execute("UPDATE orders SET status = 'failed', admin_notes = %s WHERE id = %s", 
                           (notes, order_id))
                flash(f'تم إلغاء الطلب #{order_id} وإعادة الرصيد للمستخدم', 'info')

        conn.commit()
    except Exception as e:
        flash(f'حدث خطأ: {e}', 'danger')
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('index'))

@app.route('/get_user_info/<int:user_id>')
@login_required
def get_user_info(user_id):
    """جلب معلومات المستخدم بصيغة JSON"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT user_id, username, balance, is_banned, created_at,
               total_deposits, total_orders, last_activity
        FROM users WHERE user_id = %s
    """, (user_id,))
    user = cur.fetchone()
    
    cur.execute("""
        SELECT COUNT(*), SUM(amount_syp) 
        FROM deposit_requests 
        WHERE user_id = %s AND status = 'approved'
    """, (user_id,))
    deposits = cur.fetchone()
    
    cur.execute("""
        SELECT COUNT(*), SUM(total_amount_syp) 
        FROM orders 
        WHERE user_id = %s AND status = 'completed'
    """, (user_id,))
    orders = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if user:
        return jsonify({
            'user_id': user[0],
            'username': user[1] or 'غير محدد',
            'balance': user[2],
            'is_banned': user[3],
            'created_at': user[4].strftime('%Y-%m-%d %H:%M:%S') if user[4] else 'غير محدد',
            'total_deposits': user[5] or 0,
            'total_orders': user[6] or 0,
            'last_activity': user[7].strftime('%Y-%m-%d %H:%M:%S') if user[7] else 'غير محدد',
            'approved_deposits_count': deposits[0] or 0,
            'approved_deposits_amount': deposits[1] or 0,
            'completed_orders_count': orders[0] or 0,
            'completed_orders_amount': orders[1] or 0
        })
    
    return jsonify({'error': 'User not found'})
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    logging.info(f"🌐 بدأ تشغيل لوحة التحكم على المنفذ {port}...")
    app.run(host=host, port=port, debug=False)
