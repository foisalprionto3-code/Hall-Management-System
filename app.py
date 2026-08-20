import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, jsonify, g
from flask_socketio import SocketIO, emit, join_room
import pymysql
import pdfkit
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

load_dotenv()

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if os.environ.get('RENDER'):
        raise RuntimeError(
            'SECRET_KEY environment variable is required on Render.')
    SECRET_KEY = os.urandom(32).hex()

app = Flask(__name__)
app.secret_key = SECRET_KEY
socketio = SocketIO(app)

VALID_MAINTENANCE_STATUSES = ['Pending', 'In Progress', 'Resolved']
VALID_NOTICE_TARGET_ROLES = ['All', 'Admin', 'Student', 'Teacher']
VALID_FOOD_CATEGORIES = ['Non-Veg', 'Veg']

# Database connection details
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_NAME = os.environ.get('DB_NAME', 'nasa_home')


def get_db_connection():
    if 'db' not in g:
        g.db = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor
        )
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None and db.open:
        try:
            db.close()
        except:
            pass


def get_dashboard_endpoint():
    role = session.get('role')
    if role == 'Admin':
        return 'admin_dashboard'
    if role == 'Student':
        return 'student_dashboard'
    if role == 'Teacher':
        return 'teacher_dashboard'
    return None


def redirect_to_dashboard():
    dashboard_endpoint = get_dashboard_endpoint()
    if dashboard_endpoint:
        return redirect(url_for(dashboard_endpoint))

    session.clear()
    flash('Please login to continue.', 'error')
    return redirect(url_for('login'))


def redirect_forbidden():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect_forbidden()
            if role and session.get('role') != role:
                return redirect_forbidden()
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def serialize_timestamp(value):
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    return value


def ensure_notices_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''CREATE TABLE IF NOT EXISTS Notices (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            title VARCHAR(255) NOT NULL,
                            message TEXT NOT NULL,
                            target_role ENUM('All', 'Admin', 'Student', 'Teacher') DEFAULT 'All',
                            is_active BOOLEAN DEFAULT TRUE,
                            is_pinned BOOLEAN DEFAULT FALSE,
                            expires_at DATETIME NULL,
                            created_by INT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (created_by) REFERENCES Users(id) ON DELETE SET NULL
                          )''')
        conn.commit()
    finally:
        cursor.close()


def create_notification(user_id, message):
    if not user_id or not message:
        return None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO Notifications (user_id, message) VALUES (%s, %s)',
            (user_id, message)
        )
        conn.commit()

        notification_id = cursor.lastrowid
        cursor.execute(
            'SELECT id, user_id, message, is_read, created_at FROM Notifications WHERE id = %s',
            (notification_id,)
        )
        notification = cursor.fetchone()

        if notification and notification.get('created_at'):
            notification['created_at'] = serialize_timestamp(
                notification['created_at'])

        socketio.emit('notification:new', notification, room=f'user_{user_id}')
        return notification
    except Exception:
        conn.rollback()
        return None
    finally:
        cursor.close()


def create_role_notifications(roles, message, exclude_user_id=None):
    if not roles or not message:
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        placeholders = ', '.join(['%s'] * len(roles))
        query = f'SELECT id FROM Users WHERE role IN ({placeholders})'
        params = list(roles)

        if exclude_user_id is not None:
            query += ' AND id != %s'
            params.append(exclude_user_id)

        cursor.execute(query, tuple(params))
        recipients = [row['id'] for row in cursor.fetchall()]
    finally:
        cursor.close()

    for recipient_id in recipients:
        create_notification(recipient_id, message)


@app.route('/')
def index():
    return render_template('landing.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect_to_dashboard()


@app.route('/api/notifications')
def api_notifications():
    if 'user_id' not in session:
        return jsonify({'notifications': [], 'unread_count': 0}), 401

    limit = request.args.get('limit', default=15, type=int)
    limit = max(1, min(limit, 50))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT id, message, is_read, created_at
                      FROM Notifications
                      WHERE user_id = %s
                      ORDER BY created_at DESC
                      LIMIT %s''', (session['user_id'], limit))
    notifications = cursor.fetchall()

    cursor.execute(
        'SELECT COUNT(*) AS unread_count FROM Notifications WHERE user_id = %s AND is_read = 0',
        (session['user_id'],)
    )
    unread_count = cursor.fetchone()['unread_count']
    cursor.close()

    for notification in notifications:
        notification['created_at'] = serialize_timestamp(
            notification['created_at'])

    return jsonify({'notifications': notifications, 'unread_count': unread_count})


@app.route('/api/notifications/read/<int:notification_id>', methods=['POST'])
def api_mark_notification_read(notification_id):
    if 'user_id' not in session:
        return jsonify({'updated': False, 'unread_count': 0}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''UPDATE Notifications
                      SET is_read = TRUE
                      WHERE id = %s AND user_id = %s''',
                   (notification_id, session['user_id']))
    updated = cursor.rowcount > 0
    conn.commit()

    cursor.execute(
        'SELECT COUNT(*) AS unread_count FROM Notifications WHERE user_id = %s AND is_read = 0',
        (session['user_id'],)
    )
    unread_count = cursor.fetchone()['unread_count']
    cursor.close()

    return jsonify({'updated': updated, 'unread_count': unread_count})


@app.route('/api/notifications/read-all', methods=['POST'])
def api_mark_all_notifications_read():
    if 'user_id' not in session:
        return jsonify({'updated_count': 0, 'unread_count': 0}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''UPDATE Notifications
                      SET is_read = TRUE
                      WHERE user_id = %s AND is_read = FALSE''',
                   (session['user_id'],))
    updated_count = cursor.rowcount
    conn.commit()
    cursor.close()

    return jsonify({'updated_count': updated_count, 'unread_count': 0})


@app.route('/api/notices')
def api_notices():
    if 'user_id' not in session:
        return jsonify({'notices': []}), 401

    ensure_notices_table()

    limit = request.args.get('limit', default=15, type=int)
    limit = max(1, min(limit, 50))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT id, title, message, target_role, is_pinned, created_at, expires_at
                      FROM Notices
                      WHERE is_active = TRUE
                        AND (target_role = 'All' OR target_role = %s)
                        AND (expires_at IS NULL OR expires_at >= NOW())
                      ORDER BY is_pinned DESC, created_at DESC
                      LIMIT %s''', (session['role'], limit))
    notices = cursor.fetchall()
    cursor.close()

    for notice in notices:
        notice['created_at'] = serialize_timestamp(notice['created_at'])
        notice['expires_at'] = serialize_timestamp(notice['expires_at'])

    return jsonify({'notices': notices})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
        return render_template('login.html')

    email = request.form['email']
    password = request.form['password']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM Users WHERE email = %s', (email,))
        user = cursor.fetchone()
        cursor.close()
    except pymysql.err.OperationalError as e:
        flash(f'Database connection error: {str(e)}', 'error')
        return redirect(url_for('login'))

    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['role'] = user['role']
        session['full_name'] = user['full_name']
        flash('Login successful!', 'success')
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid credentials', 'error')
        return redirect(url_for('login'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        if role not in ['Admin', 'Student', 'Teacher']:
            flash('Invalid role selected', 'error')
            return redirect(url_for('register'))

        if role == 'Admin':
            admin_secret = request.form.get('admin_secret')
            configured_admin_secret = os.environ.get('ADMIN_SECRET')
            if not configured_admin_secret:
                flash('Admin registration is not configured on this server.', 'error')
                return redirect(url_for('register'))
            if admin_secret != configured_admin_secret:
                flash('Invalid admin secret code!', 'error')
                return redirect(url_for('register'))

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email exists
        cursor.execute('SELECT * FROM Users WHERE email = %s', (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            cursor.close()
            flash('Email already exists!', 'error')
            return redirect(url_for('register'))

        # Hash password
        hashed_password = generate_password_hash(password)

        # Insert user
        cursor.execute(
            'INSERT INTO Users (full_name, email, password, role) VALUES (%s, %s, %s, %s)',
            (full_name, email, hashed_password, role)
        )
        conn.commit()
        cursor.close()

        flash(f'Successfully registered as {role}. Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'Admin':
        return redirect_forbidden()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM Users WHERE role='Student'")
    students_count = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM Users WHERE role='Teacher'")
    teachers_count = cursor.fetchone()['count']
    cursor.execute(
        "SELECT COUNT(*) as count FROM Complaints WHERE status='Pending'")
    complaints_count = cursor.fetchone()['count']
    cursor.execute(
        "SELECT COUNT(*) as count FROM Maintenance_Requests WHERE status='Pending'")
    maintenance_count = cursor.fetchone()['count']
    conn.close()

    return render_template('admin/dashboard.html',
                           students_count=students_count,
                           teachers_count=teachers_count,
                           complaints_count=complaints_count,
                           maintenance_count=maintenance_count)

# --- ADMIN ROOM MANAGEMENT ---


@app.route('/admin/rooms', methods=['GET', 'POST'])
def admin_rooms():
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        room_number = request.form['room_number']
        capacity = request.form['capacity']
        teacher_id = request.form.get('teacher_id')
        if not teacher_id:
            teacher_id = None

        try:
            cursor.execute('INSERT INTO Rooms (room_number, capacity, teacher_id) VALUES (%s, %s, %s)',
                           (room_number, capacity, teacher_id))
            conn.commit()
            flash('Room added successfully!', 'success')
        except pymysql.err.IntegrityError:
            flash(
                f'Room {room_number} already exists. Please use a different room number.', 'error')
        except Exception as e:
            flash(f'Failed to add room: {e}', 'error')
        return redirect(url_for('admin_rooms'))

    cursor.execute('''SELECT r.*, u.full_name as teacher_name 
                      FROM Rooms r LEFT JOIN Users u ON r.teacher_id = u.id''')
    rooms = cursor.fetchall()

    cursor.execute("SELECT id, full_name FROM Users WHERE role='Teacher'")
    teachers = cursor.fetchall()

    # fetch current room assignments to display space
    cursor.execute(
        "SELECT room_id, COUNT(*) as current_occupancy FROM Room_Assignments GROUP BY room_id")
    occupancy = {str(row['room_id']): row['current_occupancy']
                 for row in cursor.fetchall()}

    conn.close()
    return render_template('admin/rooms.html', rooms=rooms, teachers=teachers, occupancy=occupancy)


@app.route('/admin/rooms/delete/<int:id>', methods=['POST'])
def delete_room(id):
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM Rooms WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    flash('Room deleted successfully!', 'success')
    return redirect(url_for('admin_rooms'))


@app.route('/admin/rooms/assign-teacher/<int:id>', methods=['POST'])
def assign_room_teacher(id):
    if session.get('role') != 'Admin':
        return redirect_forbidden()

    teacher_id = request.form.get('teacher_id')
    if not teacher_id:
        teacher_id = None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if teacher_id is not None:
            cursor.execute(
                "SELECT id FROM Users WHERE id = %s AND role = 'Teacher'", (teacher_id,))
            teacher = cursor.fetchone()
            if not teacher:
                flash('Selected user is not a valid teacher.', 'error')
                return redirect(url_for('admin_rooms'))

        cursor.execute(
            'UPDATE Rooms SET teacher_id = %s WHERE id = %s', (teacher_id, id))
        conn.commit()

        if cursor.rowcount == 0:
            flash('Room not found.', 'error')
        elif teacher_id is None:
            flash('Teacher removed from room successfully.', 'success')
        else:
            flash('Teacher assigned to room successfully.', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Failed to update room teacher: {e}', 'error')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_rooms'))

# --- ADMIN FOOD MANAGEMENT ---


@app.route('/admin/food', methods=['GET', 'POST'])
def admin_food():
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        price = request.form['price']
        if category not in VALID_FOOD_CATEGORIES:
            flash('Invalid food category selected.', 'error')
            return redirect(url_for('admin_food'))
        try:
            cursor.execute('INSERT INTO Food_Items (name, category, price) VALUES (%s, %s, %s)',
                           (name, category, price))
            conn.commit()
            flash('Food item added successfully!', 'success')
        except Exception as e:
            flash(f'Failed to add food item: {e}', 'error')
        return redirect(url_for('admin_food'))

    cursor.execute('SELECT * FROM Food_Items')
    foods = cursor.fetchall()
    conn.close()
    return render_template('admin/food.html', foods=foods)


@app.route('/admin/food/delete/<int:id>', methods=['POST'])
def delete_food(id):
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM Food_Items WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    flash('Food item deleted successfully!', 'success')
    return redirect(url_for('admin_food'))


# --- ADMIN ASSIGNMENTS ---
@app.route('/admin/assignments', methods=['GET', 'POST'])
def admin_assignments():
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        student_id = request.form['student_id']
        room_id = request.form['room_id']

        # Check capacity
        cursor.execute("SELECT capacity FROM Rooms WHERE id=%s", (room_id,))
        capacity = cursor.fetchone()['capacity']

        cursor.execute(
            "SELECT COUNT(*) as count FROM Room_Assignments WHERE room_id=%s", (room_id,))
        count = cursor.fetchone()['count']

        if count >= capacity:
            flash("Room is full. Please choose another room.", 'error')
        else:
            # check if student already has a room
            cursor.execute(
                "SELECT * FROM Room_Assignments WHERE student_id=%s", (student_id,))
            if cursor.fetchone():
                flash("Student already assigned to a room.", 'error')
            else:
                assigned_date = datetime.now().date()
                cursor.execute("INSERT INTO Room_Assignments (student_id, room_id, assigned_date) VALUES (%s, %s, %s)",
                               (student_id, room_id, assigned_date))
                conn.commit()

                cursor.execute(
                    'SELECT room_number, teacher_id FROM Rooms WHERE id = %s', (room_id,))
                room_info = cursor.fetchone()
                room_number = room_info['room_number'] if room_info else room_id

                create_notification(
                    student_id,
                    f'You have been assigned to room {room_number}.'
                )
                if room_info and room_info.get('teacher_id'):
                    create_notification(
                        room_info['teacher_id'],
                        f'A new student has been assigned to room {room_number}.'
                    )

                flash("Student assigned successfully!", 'success')

        return redirect(url_for('admin_assignments'))

    # Fetch Unassigned Students
    cursor.execute('''SELECT id, full_name FROM Users 
                      WHERE role='Student' AND id NOT IN (SELECT student_id FROM Room_Assignments)''')
    unassigned_students = cursor.fetchall()

    # Fetch Rooms
    cursor.execute('SELECT id, room_number FROM Rooms')
    rooms_list = cursor.fetchall()

    # Fetch Current Assignments
    cursor.execute('''SELECT ra.id, u.full_name, r.room_number, ra.assigned_date 
                      FROM Room_Assignments ra
                      JOIN Users u ON ra.student_id = u.id
                      JOIN Rooms r ON ra.room_id = r.id''')
    assignments = cursor.fetchall()

    conn.close()
    return render_template('admin/assignments.html',
                           unassigned_students=unassigned_students,
                           rooms=rooms_list,
                           assignments=assignments)


@app.route('/admin/assignments/remove/<int:id>', methods=['POST'])
def remove_assignment(id):
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''SELECT ra.student_id, r.room_number, r.teacher_id
                      FROM Room_Assignments ra
                      JOIN Rooms r ON ra.room_id = r.id
                      WHERE ra.id = %s''', (id,))
    assignment = cursor.fetchone()

    cursor.execute('DELETE FROM Room_Assignments WHERE id = %s', (id,))
    conn.commit()

    if assignment:
        create_notification(
            assignment['student_id'],
            f'Your room assignment for room {assignment["room_number"]} was removed.'
        )
        if assignment.get('teacher_id'):
            create_notification(
                assignment['teacher_id'],
                f'A student was removed from room {assignment["room_number"]}.'
            )

    conn.close()
    flash('Student removed from room successfully!', 'success')
    return redirect(url_for('admin_assignments'))

# --- ADMIN ORDERS, COMPLAINTS, MAINTENANCE ---


@app.route('/admin/orders')
def admin_orders():
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT o.id, u.full_name as student_name, o.total_amount, o.order_date, 
                      GROUP_CONCAT(CONCAT(f.name, " (", od.quantity, ")") SEPARATOR ", ") as items
                      FROM Orders o
                      JOIN Users u ON o.student_id = u.id
                      JOIN Order_Details od ON o.id = od.order_id
                      JOIN Food_Items f ON od.food_item_id = f.id
                      GROUP BY o.id
                      ORDER BY o.order_date DESC''')
    orders = cursor.fetchall()
    conn.close()
    return render_template('admin/orders.html', orders=orders)


@app.route('/admin/complaints')
def admin_complaints():
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT c.*, u.full_name, r.room_number 
                      FROM Complaints c
                      LEFT JOIN Users u ON c.student_id = u.id
                      LEFT JOIN Rooms r ON c.room_id = r.id
                      ORDER BY c.created_at DESC''')
    complaints = cursor.fetchall()
    conn.close()
    return render_template('admin/complaints.html', complaints=complaints)


@app.route('/admin/complaints/update/<int:id>', methods=['POST'])
def update_complaint(id):
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT student_id FROM Complaints WHERE id = %s', (id,))
    complaint = cursor.fetchone()

    cursor.execute(
        "UPDATE Complaints SET status='Reviewed' WHERE id=%s", (id,))
    conn.commit()

    if complaint and complaint.get('student_id'):
        create_notification(
            complaint['student_id'],
            'Your complaint has been reviewed by the admin.'
        )

    conn.close()
    flash('Complaint marked as reviewed.', 'success')
    return redirect(url_for('admin_complaints'))


@app.route('/admin/maintenance')
def admin_maintenance():
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT m.*, u.full_name, r.room_number 
                      FROM Maintenance_Requests m
                      JOIN Users u ON m.student_id = u.id
                      JOIN Rooms r ON m.room_id = r.id
                      ORDER BY m.created_at DESC''')
    requests = cursor.fetchall()
    conn.close()
    return render_template('admin/maintenance.html', requests=requests)


@app.route('/admin/maintenance/update/<int:id>/<status>', methods=['POST'])
def update_maintenance(id, status):
    if session.get('role') != 'Admin':
        return redirect_forbidden()
    if status not in VALID_MAINTENANCE_STATUSES:
        flash('Invalid maintenance status.', 'error')
        return redirect(url_for('admin_maintenance'))
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        'SELECT student_id FROM Maintenance_Requests WHERE id = %s', (id,))
    request_row = cursor.fetchone()

    cursor.execute(
        "UPDATE Maintenance_Requests SET status=%s WHERE id=%s", (status, id))
    conn.commit()

    if request_row and request_row.get('student_id'):
        create_notification(
            request_row['student_id'],
            f'Your maintenance request status is now "{status}".'
        )

    conn.close()
    flash(f'Maintenance request updated to {status}.', 'success')
    return redirect(url_for('admin_maintenance'))


# --- ADMIN FEES MANAGEMENT ---

@app.route('/admin/fees', methods=['GET', 'POST'])
def admin_fees():
    if session.get('role') != 'Admin':
        return redirect_forbidden()

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        student_id = request.form.get('student_id')
        amount = request.form.get('amount')
        due_date = request.form.get('due_date')

        if not student_id or not amount or not due_date:
            flash('All fields are required!', 'error')
        else:
            try:
                cursor.execute(
                    'INSERT INTO Hall_Fees (student_id, amount, due_date) VALUES (%s, %s, %s)',
                    (student_id, amount, due_date)
                )
                conn.commit()

                create_notification(
                    student_id,
                    f'New hall fee assigned: Tk {amount} due by {due_date}.'
                )

                flash('Hall fee assigned successfully!', 'success')
            except Exception as e:
                flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_fees'))

    # Get all students for the dropdown
    cursor.execute(
        "SELECT id, full_name, email FROM Users WHERE role='Student'")
    students = cursor.fetchall()

    # Get all fees
    cursor.execute('''SELECT h.*, u.full_name as student_name 
                      FROM Hall_Fees h
                      JOIN Users u ON h.student_id = u.id
                      ORDER BY h.due_date DESC''')
    fees = cursor.fetchall()

    cursor.close()

    return render_template('admin/fees.html', students=students, fees=fees)


@app.route('/admin/fees/delete/<int:id>', methods=['POST'])
def delete_fee(id):
    if session.get('role') != 'Admin':
        return redirect_forbidden()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM Hall_Fees WHERE id = %s', (id,))
    conn.commit()
    cursor.close()

    flash('Hall fee removed.', 'success')
    return redirect(url_for('admin_fees'))


@app.route('/admin/notices', methods=['GET', 'POST'])
def admin_notices():
    if session.get('role') != 'Admin':
        return redirect_forbidden()

    ensure_notices_table()

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        target_role = request.form.get('target_role', 'All')
        is_pinned = True if request.form.get('is_pinned') else False
        expires_at = request.form.get('expires_at') or None

        if not title or not message:
            flash('Title and message are required.', 'error')
        elif target_role not in VALID_NOTICE_TARGET_ROLES:
            flash('Invalid target role selected.', 'error')
        else:
            try:
                cursor.execute('''INSERT INTO Notices
                                  (title, message, target_role, is_pinned, created_by, expires_at)
                                  VALUES (%s, %s, %s, %s, %s, %s)''',
                               (title, message, target_role, is_pinned, session['user_id'], expires_at))
                conn.commit()
                flash('Notice published successfully!', 'success')

                socketio.emit('notice:new', {
                    'title': title,
                    'message': message,
                    'target_role': target_role,
                    'is_pinned': is_pinned,
                    'created_at': serialize_timestamp(datetime.now())
                })
            except Exception as e:
                conn.rollback()
                flash(f'Failed to publish notice: {e}', 'error')

        cursor.close()
        conn.close()
        return redirect(url_for('admin_notices'))

    cursor.execute('''SELECT n.*, u.full_name as created_by_name
                      FROM Notices n
                      LEFT JOIN Users u ON n.created_by = u.id
                      ORDER BY n.created_at DESC''')
    notices = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'admin/notices.html',
        notices=notices,
        target_roles=VALID_NOTICE_TARGET_ROLES
    )


@app.route('/admin/notices/toggle/<int:id>', methods=['POST'])
def admin_toggle_notice(id):
    if session.get('role') != 'Admin':
        return redirect_forbidden()

    ensure_notices_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''UPDATE Notices
                      SET is_active = CASE WHEN is_active = TRUE THEN FALSE ELSE TRUE END
                      WHERE id = %s''', (id,))
    conn.commit()

    if cursor.rowcount == 0:
        flash('Notice not found.', 'error')
    else:
        flash('Notice status updated.', 'success')

    cursor.close()
    conn.close()
    return redirect(url_for('admin_notices'))


@app.route('/admin/notices/pin/<int:id>', methods=['POST'])
def admin_pin_notice(id):
    if session.get('role') != 'Admin':
        return redirect_forbidden()

    ensure_notices_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''UPDATE Notices
                      SET is_pinned = CASE WHEN is_pinned = TRUE THEN FALSE ELSE TRUE END
                      WHERE id = %s''', (id,))
    conn.commit()

    if cursor.rowcount == 0:
        flash('Notice not found.', 'error')
    else:
        flash('Notice pin status updated.', 'success')

    cursor.close()
    conn.close()
    return redirect(url_for('admin_notices'))


@app.route('/admin/notices/delete/<int:id>', methods=['POST'])
def admin_delete_notice(id):
    if session.get('role') != 'Admin':
        return redirect_forbidden()

    ensure_notices_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM Notices WHERE id = %s', (id,))
    conn.commit()

    if cursor.rowcount == 0:
        flash('Notice not found.', 'error')
    else:
        flash('Notice deleted.', 'success')

    cursor.close()
    conn.close()
    return redirect(url_for('admin_notices'))


@app.route('/student')
def student_dashboard():
    if session.get('role') != 'Student':
        return redirect_forbidden()

    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get room
    cursor.execute('''SELECT r.room_number FROM Room_Assignments ra 
                      JOIN Rooms r ON ra.room_id = r.id 
                      WHERE ra.student_id = %s''', (student_id,))
    room_data = cursor.fetchone()
    my_room = room_data['room_number'] if room_data else "Not Assigned"

    # Get pending dues (meal payments + unpaid hall fees)
    cursor.execute(
        "SELECT SUM(amount) as pending_dues FROM Payments WHERE student_id=%s AND status='Pending'", (student_id,))
    dues_data = cursor.fetchone()
    payment_dues = float(dues_data['pending_dues']
                         ) if dues_data['pending_dues'] else 0.00

    cursor.execute(
        "SELECT SUM(amount) as hall_dues FROM Hall_Fees WHERE student_id=%s AND status='Unpaid'", (student_id,))
    hall_data = cursor.fetchone()
    hall_dues = float(hall_data['hall_dues']
                      ) if hall_data['hall_dues'] else 0.00

    pending_dues = payment_dues + hall_dues

    # Get recent orders count
    cursor.execute(
        "SELECT COUNT(*) as order_count FROM Orders WHERE student_id=%s", (student_id,))
    order_data = cursor.fetchone()
    order_count = order_data['order_count']

    conn.close()

    return render_template('student/dashboard.html',
                           my_room=my_room,
                           pending_dues=pending_dues,
                           order_count=order_count)

# --- STUDENT FOOD ORDERING ---


@app.route('/student/order-food', methods=['GET', 'POST'])
def student_order_food():
    if session.get('role') != 'Student':
        return redirect_forbidden()
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        try:
            item_ids = request.form.getlist('items[]')

            if not item_ids:
                flash('No items selected!', 'error')
                return redirect(url_for('student_order_food'))

            total_amount = 0
            order_details = []

            # Calculate total and prepare details
            for item_id in item_ids:
                try:
                    qty = int(request.form.get(f'qty_{item_id}', 1))
                except (TypeError, ValueError):
                    qty = 0

                if qty <= 0:
                    continue

                cursor.execute(
                    'SELECT id, price FROM Food_Items WHERE id=%s', (item_id,))
                food_item = cursor.fetchone()
                if not food_item:
                    flash(
                        'One of the selected food items is no longer available.', 'error')
                    return redirect(url_for('student_order_food'))

                price = food_item['price']
                total_amount += (float(price) * qty)
                order_details.append((food_item['id'], qty, price))

            if total_amount <= 0 or not order_details:
                flash(
                    'Please select at least one valid item with quantity greater than zero.', 'error')
                return redirect(url_for('student_order_food'))

            # Create Order
            cursor.execute('INSERT INTO Orders (student_id, total_amount) VALUES (%s, %s)',
                           (student_id, total_amount))
            order_id = cursor.lastrowid

            # Insert Details
            for detail in order_details:
                cursor.execute('INSERT INTO Order_Details (order_id, food_item_id, quantity, price) VALUES (%s, %s, %s, %s)',
                               (order_id, detail[0], detail[1], detail[2]))

            # Create a pending payment
            cursor.execute("INSERT INTO Payments (student_id, amount, payment_type, status) VALUES (%s, %s, 'Meal', 'Pending')",
                           (student_id, total_amount))

            conn.commit()

            create_role_notifications(
                ['Admin'],
                f'{session["full_name"]} placed a food order worth Tk {total_amount:.2f}.'
            )

            flash('Food ordered successfully! Payment added to pending dues.', 'success')
            return redirect(url_for('student_my_orders'))
        except Exception as e:
            conn.rollback()
            flash(f'Failed to place order: {e}', 'error')
            return redirect(url_for('student_order_food'))
        finally:
            cursor.close()
            conn.close()

    cursor.execute('SELECT * FROM Food_Items ORDER BY category, name')
    foods = cursor.fetchall()
    conn.close()

    return render_template('student/order_food.html', foods=foods)


@app.route('/student/my-orders')
def student_my_orders():
    if session.get('role') != 'Student':
        return redirect_forbidden()
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''SELECT o.id, o.total_amount, o.order_date, 
                      GROUP_CONCAT(CONCAT(f.name, " (", od.quantity, ")") SEPARATOR ", ") as items
                      FROM Orders o
                      JOIN Order_Details od ON o.id = od.order_id
                      JOIN Food_Items f ON od.food_item_id = f.id
                      WHERE o.student_id = %s
                      GROUP BY o.id
                      ORDER BY o.order_date DESC''', (student_id,))
    orders = cursor.fetchall()
    conn.close()

    return render_template('student/my_orders.html', orders=orders)


@app.route('/student/complaints', methods=['GET', 'POST'])
def student_complaints():
    if session.get('role') != 'Student':
        return redirect_forbidden()
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        description = request.form['description']
        is_anonymous = True if request.form.get('is_anonymous') else False

        cursor.execute(
            "SELECT room_id FROM Room_Assignments WHERE student_id=%s", (student_id,))
        room = cursor.fetchone()
        room_id = room['room_id'] if room else None

        cursor.execute('INSERT INTO Complaints (student_id, room_id, description, is_anonymous) VALUES (%s, %s, %s, %s)',
                       (student_id, room_id, description, is_anonymous))
        conn.commit()

        create_role_notifications(
            ['Admin'],
            f'New complaint submitted by {session["full_name"]}.'
        )

        if room_id:
            cursor.execute(
                'SELECT teacher_id, room_number FROM Rooms WHERE id = %s', (room_id,))
            room_info = cursor.fetchone()
            if room_info and room_info.get('teacher_id'):
                create_notification(
                    room_info['teacher_id'],
                    f'New complaint from room {room_info["room_number"]} requires review.'
                )

        flash('Complaint submitted successfully.', 'success')
        return redirect(url_for('student_complaints'))

    cursor.execute(
        'SELECT * FROM Complaints WHERE student_id=%s ORDER BY created_at DESC', (student_id,))
    complaints = cursor.fetchall()
    conn.close()

    return render_template('student/complaints.html', complaints=complaints)


@app.route('/student/maintenance', methods=['GET', 'POST'])
def student_maintenance():
    if session.get('role') != 'Student':
        return redirect_forbidden()
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        try:
            issue = request.form['issue']

            cursor.execute(
                "SELECT room_id FROM Room_Assignments WHERE student_id=%s", (student_id,))
            room = cursor.fetchone()

            if not room:
                flash(
                    'You must be assigned a room before requesting maintenance!', 'error')
            else:
                cursor.execute('INSERT INTO Maintenance_Requests (student_id, room_id, issue) VALUES (%s, %s, %s)',
                               (student_id, room['room_id'], issue))
                conn.commit()

                create_role_notifications(
                    ['Admin'],
                    f'New maintenance request submitted by {session["full_name"]}.'
                )

                cursor.execute(
                    'SELECT teacher_id, room_number FROM Rooms WHERE id = %s',
                    (room['room_id'],)
                )
                room_info = cursor.fetchone()
                if room_info and room_info.get('teacher_id'):
                    create_notification(
                        room_info['teacher_id'],
                        f'New maintenance request from room {room_info["room_number"]}.'
                    )

                flash('Maintenance request submitted.', 'success')

            return redirect(url_for('student_maintenance'))
        finally:
            cursor.close()
            conn.close()

    cursor.execute(
        'SELECT * FROM Maintenance_Requests WHERE student_id=%s ORDER BY created_at DESC', (student_id,))
    requests = cursor.fetchall()
    conn.close()

    return render_template('student/maintenance.html', requests=requests)


# --- STUDENT FEES MANAGEMENT ---

@app.route('/student/hall-fees')
def student_hall_fees():
    if session.get('role') != 'Student':
        return redirect_forbidden()

    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''SELECT * FROM Hall_Fees 
                      WHERE student_id=%s 
                      ORDER BY due_date DESC''', (student_id,))
    fees = cursor.fetchall()

    cursor.execute('''SELECT SUM(amount) as total_due 
                      FROM Hall_Fees 
                      WHERE student_id=%s AND status='Unpaid' ''', (student_id,))
    total_due = cursor.fetchone()['total_due'] or 0.0

    cursor.close()
    conn.close()
    return render_template('student/hall_fees.html', fees=fees, total_due=total_due)


@app.route('/student/hall-fees/pay/<int:id>', methods=['POST'])
def pay_hall_fee(id):
    if session.get('role') != 'Student':
        return redirect_forbidden()

    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT status, amount FROM Hall_Fees WHERE id=%s AND student_id=%s", (id, student_id))
    fee = cursor.fetchone()

    if not fee:
        flash('Fee record not found.', 'error')
    elif fee['status'] == 'Paid':
        flash('This fee is already paid.', 'info')
    else:
        # Mark the hall fee as paid
        cursor.execute(
            "UPDATE Hall_Fees SET status='Paid', paid_at=NOW() WHERE id=%s", (id,))

        # Create a record in the main Payments table so receipt generation still works uniformly
        cursor.execute(
            "INSERT INTO Payments (student_id, amount, payment_type, status, payment_date) VALUES (%s, %s, 'Hall Fee', 'Paid', NOW())",
            (student_id, fee['amount'])
        )
        conn.commit()

        create_role_notifications(
            ['Admin'],
            f'{session["full_name"]} paid hall fee of Tk {float(fee["amount"]):.2f}.'
        )

        flash('Hall fee payment successful!', 'success')

    cursor.close()
    conn.close()
    return redirect(url_for('student_hall_fees'))


@app.route('/student/payments')
def student_payments():
    if session.get('role') != 'Student':
        return redirect_forbidden()
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM Payments WHERE student_id=%s ORDER BY payment_date DESC', (student_id,))
    payments = cursor.fetchall()

    # Calculate Total Due
    cursor.execute(
        "SELECT SUM(amount) as dues FROM Payments WHERE student_id=%s AND status='Pending'", (student_id,))
    dues = cursor.fetchone()['dues'] or 0.0

    conn.close()
    return render_template('student/payments.html', payments=payments, dues=dues)


@app.route('/student/payments/pay/<int:id>', methods=['POST'])
def pay_amount(id):
    if session.get('role') != 'Student':
        return redirect_forbidden()

    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT status FROM Payments WHERE id=%s AND student_id=%s", (id, student_id))
    payment = cursor.fetchone()

    if not payment:
        conn.close()
        flash('Payment not found.', 'error')
        return redirect(url_for('student_payments'))

    if payment['status'] == 'Paid':
        conn.close()
        flash('This payment is already marked as paid.', 'info')
        return redirect(url_for('student_payments'))

    cursor.execute(
        "UPDATE Payments SET status='Paid' WHERE id=%s AND student_id=%s", (id, student_id))
    conn.commit()

    create_role_notifications(
        ['Admin'],
        f'{session["full_name"]} paid a pending meal due.'
    )

    conn.close()
    flash('Payment marked as paid (cash).', 'success')
    return redirect(url_for('student_payments'))


@app.route('/student/payments/receipt/<int:id>')
def download_receipt(id):
    if session.get('role') != 'Student':
        return redirect_forbidden()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM Payments WHERE id=%s AND student_id=%s', (id, session['user_id']))
    payment = cursor.fetchone()
    conn.close()

    if not payment:
        flash('Payment not found.')
        return redirect(url_for('student_payments'))

    html = render_template('student/receipt_pdf.html',
                           payment=payment, user_name=session['full_name'])

    # Needs wkhtmltopdf installed on system for pdfkit to work!
    # For demo purposes we can attempt to generate it or return HTML that looks like a PDF if not installed
    try:
        wkhtmltopdf_path = os.environ.get('WKHTMLTOPDF_PATH')
        config = pdfkit.configuration(
            wkhtmltopdf=wkhtmltopdf_path) if wkhtmltopdf_path else None

        pdf_options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
        }
        pdf = pdfkit.from_string(
            html, False, options=pdf_options, configuration=config)

        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=receipt_{id}.pdf'
        return response
    except Exception as e:
        print(f"PDF generation error: {e}")
        flash('PDF generation failed. Install wkhtmltopdf and set WKHTMLTOPDF_PATH on the server.', 'error')
        return redirect(url_for('student_payments'))


@app.route('/teacher')
def teacher_dashboard():
    if session.get('role') != 'Teacher':
        return redirect_forbidden()
    return render_template('teacher/dashboard.html')


@app.route('/teacher/rooms')
def teacher_rooms():
    if session.get('role') != 'Teacher':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, r.room_number, r.capacity, 
               (SELECT COUNT(*) FROM Room_Assignments WHERE room_id = r.id) as current_occupancy
        FROM Rooms r
        WHERE r.teacher_id = %s
    """, (session['user_id'],))
    rooms = cursor.fetchall()

    room_details = []
    for r in rooms:
        cursor.execute("""
            SELECT u.full_name, u.email, ra.assigned_date
            FROM Room_Assignments ra
            JOIN Users u ON ra.student_id = u.id
            WHERE ra.room_id = %s
        """, (r['id'],))
        students = cursor.fetchall()
        r['students'] = students
        room_details.append(r)

    cursor.close()
    conn.close()
    return render_template('teacher/rooms.html', rooms=room_details)


@app.route('/teacher/complaints')
def teacher_complaints():
    if session.get('role') != 'Teacher':
        return redirect_forbidden()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, u.full_name as student_name, r.room_number 
        FROM Complaints c
        LEFT JOIN Users u ON c.student_id = u.id
        LEFT JOIN Rooms r ON c.room_id = r.id
        WHERE r.teacher_id = %s
        ORDER BY c.created_at DESC
    """, (session['user_id'],))
    complaints = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('teacher/complaints.html', complaints=complaints)


@app.route('/teacher/complaints/update/<int:id>', methods=['POST'])
def teacher_update_complaint(id):
    if session.get('role') != 'Teacher':
        return redirect_forbidden()

    teacher_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''SELECT c.student_id
                      FROM Complaints c
                      JOIN Rooms r ON c.room_id = r.id
                      WHERE c.id = %s AND r.teacher_id = %s''',
                   (id, teacher_id))
    complaint = cursor.fetchone()

    if not complaint:
        flash('You are not allowed to update this complaint.', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('teacher_complaints'))

    cursor.execute('''UPDATE Complaints
                      SET status='Reviewed'
                      WHERE id = %s
                        AND room_id IN (SELECT id FROM Rooms WHERE teacher_id = %s)''',
                   (id, teacher_id))

    if cursor.rowcount == 0:
        flash('You are not allowed to update this complaint.', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('teacher_complaints'))

    conn.commit()

    if complaint.get('student_id'):
        create_notification(
            complaint['student_id'],
            'Your complaint has been reviewed by your assigned teacher.'
        )

    flash('Complaint marked as reviewed.', 'success')
    cursor.close()
    conn.close()
    return redirect(url_for('teacher_complaints'))


@app.route('/student/reading_room', methods=['GET', 'POST'])
def student_reading_room():
    if session.get('role') != 'Student':
        return redirect_forbidden()
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        try:
            booking_date = request.form['booking_date']
            time_slot = request.form['time_slot']

            cursor.execute('''INSERT INTO Reading_Room_Bookings (student_id, booking_date, time_slot)
                              VALUES (%s, %s, %s)''', (student_id, booking_date, time_slot))
            conn.commit()

            create_role_notifications(
                ['Admin'],
                f'{session["full_name"]} booked reading room on {booking_date} ({time_slot}).'
            )

            flash('Reading room booked successfully!', 'success')
        except Exception:
            flash('Slot already booked or invalid request.', 'error')
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('student_reading_room'))

    cursor.execute('''SELECT * FROM Reading_Room_Bookings 
                      WHERE student_id=%s AND booking_date >= CURDATE()
                      ORDER BY booking_date, time_slot''', (student_id,))
    bookings = cursor.fetchall()
    conn.close()
    return render_template('student/reading_room.html', bookings=bookings, current_date=datetime.now().date())


@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect_forbidden()

    conn = get_db_connection()
    cursor = conn.cursor()

    if session['role'] == 'Student':
        cursor.execute('''SELECT u.id, u.full_name as name, 'Teacher' as info
                          FROM Users u
                          JOIN Rooms r ON u.id = r.teacher_id
                          JOIN Room_Assignments ra ON r.id = ra.room_id
                          WHERE ra.student_id = %s''', (session['user_id'],))
        contacts = cursor.fetchall()
        base_tmpl = 'student/dashboard.html'
    elif session['role'] == 'Teacher':
        cursor.execute('''SELECT u.id, u.full_name as name, r.room_number as info
                          FROM Users u
                          JOIN Room_Assignments ra ON u.id = ra.student_id
                          JOIN Rooms r ON ra.room_id = r.id
                          WHERE r.teacher_id = %s''', (session['user_id'],))
        contacts = cursor.fetchall()
        base_tmpl = 'teacher/dashboard.html'
    else:
        contacts = []
        base_tmpl = 'admin/dashboard.html'

    cursor.close()
    conn.close()

    return render_template('chat.html', contacts=contacts, base_template=base_tmpl)


@app.route('/api/chat/<int:receiver_id>')
def get_chat_history(receiver_id):
    if 'user_id' not in session:
        return jsonify([])

    sender_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''SELECT * FROM Chat_Messages 
                      WHERE (sender_id = %s AND receiver_id = %s) 
                         OR (sender_id = %s AND receiver_id = %s)
                      ORDER BY sent_at ASC''',
                   (sender_id, receiver_id, receiver_id, sender_id))
    messages = cursor.fetchall()

    # Convert datetime to string for JSON serialization
    for m in messages:
        m['sent_at'] = m['sent_at'].strftime('%Y-%m-%d %H:%M')

    cursor.close()
    conn.close()

    return jsonify(messages)


@socketio.on('send_message')
def handle_message(data):
    sender_id = session.get('user_id')
    if not sender_id:
        return

    receiver_id = data['receiver_id']
    message = data['message']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO Chat_Messages (sender_id, receiver_id, message) 
                      VALUES (%s, %s, %s)''', (sender_id, receiver_id, message))
    conn.commit()
    msg_id = cursor.lastrowid

    cursor.execute('SELECT * FROM Chat_Messages WHERE id = %s', (msg_id,))
    msg_data = cursor.fetchone()
    msg_data['sent_at'] = msg_data['sent_at'].strftime('%Y-%m-%d %H:%M')

    cursor.close()
    conn.close()

    # Send to the receiver's room and the sender's room
    emit('receive_message', msg_data, room=f"user_{receiver_id}")
    emit('receive_message', msg_data, room=f"user_{sender_id}")


@socketio.on('join')
def on_join(data):
    if 'user_id' in session:
        room = f"user_{session['user_id']}"
        join_room(room)

# Placeholder for modular routes like /admin/rooms, /student/meals, etc.


if __name__ == '__main__':
    socketio.run(app, debug=True)
