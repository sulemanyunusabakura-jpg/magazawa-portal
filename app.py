import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_key_mst_portal"
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Database Initialization
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            payment_status TEXT DEFAULT 'pending',
            program TEXT,
            level TEXT,
            phone TEXT,
            profile_picture TEXT
        )
    ''')
    
    # Courses Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT NOT NULL,
            course_name TEXT NOT NULL,
            unit INTEGER DEFAULT 3,
            semester INTEGER DEFAULT 1,
            program TEXT,
            level TEXT
        )
    ''')

    # Student Course Enrollment Mapping Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            FOREIGN KEY (student_id) REFERENCES users (id),
            FOREIGN KEY (course_id) REFERENCES courses (id)
        )
    ''')
    
    # Results Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            course_code TEXT NOT NULL,
            title TEXT NOT NULL,
            unit INTEGER DEFAULT 3,
            semester INTEGER DEFAULT 1,
            grade TEXT NOT NULL,
            level TEXT DEFAULT 'HND2',
            session TEXT DEFAULT '2025/2026',
            FOREIGN KEY (student_id) REFERENCES users (id)
        )
    ''')
    
    # Materials Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            material_type TEXT DEFAULT 'Document',
            file_path TEXT NOT NULL
        )
    ''')
    
    # Messages Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create Default Admin Account if missing
    cursor.execute("SELECT * FROM users WHERE role = 'admin'")
    if not cursor.fetchone():
        hashed_pw = generate_password_hash("admin123")
        cursor.execute('''
            INSERT INTO users (username, password, full_name, role, payment_status)
            VALUES (?, ?, ?, 'admin', 'paid')
        ''', ('admin', hashed_pw, 'System Administrator'))
        
    conn.commit()
    conn.close()

init_db()

# CGPA Calculation Helper (4.0 Scale)
def calculate_cgpa(results):
    grade_points = {'A': 4.0, 'AB': 3.5, 'B': 3.25, 'BC': 3.0, 'C': 2.75, 'CD': 2.5, 'D': 2.25, 'E': 2.0, 'F': 0.0}
    total_units = 0
    total_points = 0.0
    for res in results:
        unit = int(res['unit']) if res['unit'] else 3
        grade = str(res['grade']).upper().strip()
        points = grade_points.get(grade, 0.0)
        total_units += unit
        total_points += (points * unit)
    return (total_points / total_units) if total_units > 0 else 0.0

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('admin_dashboard' if session.get('role') == 'admin' else 'student_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'student_dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

# Admin Dashboard & Logic
@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    students = conn.execute("SELECT * FROM users WHERE role = 'student'").fetchall()
    courses = conn.execute("SELECT * FROM courses").fetchall()
    materials = conn.execute("SELECT * FROM materials").fetchall()
    results = conn.execute("SELECT r.*, u.full_name FROM results r JOIN users u ON r.student_id = u.id").fetchall()
    conn.close()
    
    return render_template('admin_dashboard.html', students=students, courses=courses, materials=materials, results=results)

@app.route('/admin/add_course', methods=['POST'])
def add_course():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    course_code = request.form.get('course_code', '').strip().upper()
    course_name = request.form.get('course_name', '').strip()
    unit = int(request.form.get('unit', 3))
    semester = int(request.form.get('semester', 1))
    program = request.form.get('program', 'HND CME').strip()
    level = request.form.get('level', 'HND2').strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO courses (course_code, course_name, unit, semester, program, level)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (course_code, course_name, unit, semester, program, level))
    
    course_id = cursor.lastrowid
    
    # Automatically map newly added course to existing matching program/level students
    students = conn.execute("SELECT id FROM users WHERE role='student' AND (program = ? OR program IS NULL)", (program,)).fetchall()
    for student in students:
        cursor.execute("INSERT INTO student_courses (student_id, course_id) VALUES (?, ?)", (student['id'], course_id))
        
    conn.commit()
    conn.close()
    
    flash(f'Course {course_code} created and assigned to students successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/assign_course', methods=['POST'])
def assign_course():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    student_id = request.form.get('student_id')
    course_id = request.form.get('course_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    existing = cursor.execute("SELECT * FROM student_courses WHERE student_id = ? AND course_id = ?", (student_id, course_id)).fetchone()
    if not existing:
        cursor.execute("INSERT INTO student_courses (student_id, course_id) VALUES (?, ?)", (student_id, course_id))
        conn.commit()
        flash('Course assigned to student successfully!', 'success')
    else:
        flash('Student is already registered for this course.', 'warning')
        
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_result', methods=['POST'])
def add_result():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    student_identifier = request.form.get('student_id')
    course_code = request.form.get('course_code', '').strip().upper()
    title = request.form.get('title', '').strip()
    unit = int(request.form.get('unit', 3))
    semester = int(request.form.get('semester', 1))
    grade = request.form.get('grade', 'A').strip().upper()
    level = request.form.get('level', 'HND2').strip()
    session_yr = request.form.get('session', '2025/2026').strip()
    
    conn = get_db_connection()
    # Resolve student ID whether admin passed ID integer or admission username string
    student = conn.execute("SELECT id FROM users WHERE (id = ? OR username = ?) AND role = 'student'", (student_identifier, student_identifier)).fetchone()
    
    if not student:
        conn.close()
        flash('Error adding result: Selected student could not be found.', 'danger')
        return redirect(url_for('admin_dashboard'))
        
    conn.execute('''
        INSERT INTO results (student_id, course_code, title, unit, semester, grade, level, session)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (student['id'], course_code, title, unit, semester, grade, level, session_yr))
    
    conn.commit()
    conn.close()
    
    flash('Student result published successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/toggle_payment/<int:student_id>', methods=['POST'])
def toggle_payment(student_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    student = conn.execute("SELECT payment_status FROM users WHERE id = ?", (student_id,)).fetchone()
    if student:
        new_status = 'pending' if student['payment_status'] == 'paid' else 'paid'
        conn.execute("UPDATE users SET payment_status = ? WHERE id = ?", (new_status, student_id))
        conn.commit()
        flash(f'Payment status changed to {new_status.upper()}.', 'success')
        
    conn.close()
    return redirect(url_for('admin_dashboard'))

# Student Dashboard & Views
@app.route('/student')
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Please login as a student to access the portal.', 'warning')
        return redirect(url_for('login'))
        
    student_id = session['user_id']
    conn = get_db_connection()
    
    student = conn.execute("SELECT * FROM users WHERE id = ?", (student_id,)).fetchone()
    
    # Query assigned courses directly + match program/level courses dynamically
    courses = conn.execute('''
        SELECT DISTINCT c.* FROM courses c
        LEFT JOIN student_courses sc ON c.id = sc.course_id
        WHERE sc.student_id = ? OR c.program = ? OR c.program IS NULL
    ''', (student_id, student['program'])).fetchall()
    
    results = conn.execute("SELECT * FROM results WHERE student_id = ?", (student_id,)).fetchall()
    materials = conn.execute("SELECT * FROM materials").fetchall()
    messages = conn.execute("SELECT * FROM messages WHERE receiver_id = ? ORDER BY timestamp DESC", (student_id,)).fetchall()
    
    cgpa = calculate_cgpa(results)
    conn.close()
    
    return render_template('student_dashboard.html', student=student, courses=courses, results=results, materials=materials, messages=messages, cgpa=cgpa)

@app.route('/download/<filename>')
def download_material(filename):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    sender_id = session['user_id']
    receiver_id = request.form.get('receiver_id')
    content = request.form.get('content', '').strip()
    
    if receiver_id and content:
        conn = get_db_connection()
        conn.execute("INSERT INTO messages (sender_id, receiver_id, content) VALUES (?, ?, ?)", (sender_id, receiver_id, content))
        conn.commit()
        conn.close()
        flash('Message dispatched!', 'success')
        
    return redirect(url_for('student_dashboard' if session.get('role') == 'student' else 'admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
