import os
import uuid
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, flash, Response, 
    send_from_directory, jsonify, session
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, or_, text
from sqlalchemy.exc import SQLAlchemyError
from models import db, User, Material, Message, Course, Result
from google import genai
from google.genai import types

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'magazawa_skills_technology_secret')

# DATABASE URI CONFIGURATION FOR RENDER & LOCAL DEVS
db_url = os.environ.get('DATABASE_URL', 'sqlite:///magazawa_portal.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Optimize PostgreSQL pooled connections & hide diagnostic parameters globally
if 'postgresql' in db_url:
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'hide_parameters': True
    }

# ABSOLUTE PATH FOR UPLOAD DIRECTORY
app.config['UPLOAD_FOLDER'] = os.path.abspath(os.path.join(app.root_path, 'static', 'uploads'))
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'ppt', 'pptx', 'mp3', 'wav', 'mp4', 'webm'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    if '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lstrip('.').lower()
    return ext in ALLOWED_EXTENSIONS

# SAFE GEMINI CLIENT INITIALIZATION
gemini_api_key = os.environ.get('GEMINI_API_KEY')
gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- CUSTOM DECORATOR: FEES PAYMENT CHECK ---
def payment_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role == 'student' and getattr(current_user, 'payment_status', '') != 'Paid':
            flash("Access Restricted: Please complete your school fees payment to unlock this section.", "warning")
            return redirect(url_for('student_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- SAFE DB SCHEMA SYNC AND AUTO MIGRATION ---
def auto_migrate_db():
    """Safely checks and synchronizes database schema without throwing unhandled exceptions."""
    with app.app_context():
        try:
            db.create_all()
            with db.engine.connect() as conn:
                # Synchronize Material table
                conn.execute(text("ALTER TABLE material ADD COLUMN IF NOT EXISTS upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"))

                # Synchronize Result table
                conn.execute(text("ALTER TABLE result ADD COLUMN IF NOT EXISTS title VARCHAR(200);"))
                conn.execute(text("ALTER TABLE result ADD COLUMN IF NOT EXISTS course_name VARCHAR(200);"))
                conn.execute(text("ALTER TABLE result ADD COLUMN IF NOT EXISTS course_code VARCHAR(100);"))
                conn.execute(text("ALTER TABLE result ADD COLUMN IF NOT EXISTS score VARCHAR(50);"))
                conn.execute(text("ALTER TABLE result ADD COLUMN IF NOT EXISTS unit INTEGER DEFAULT 1;"))
                conn.execute(text("ALTER TABLE result ADD COLUMN IF NOT EXISTS semester VARCHAR(20);"))
                conn.execute(text("ALTER TABLE result ADD COLUMN IF NOT EXISTS level VARCHAR(20);"))
                conn.execute(text("ALTER TABLE result ADD COLUMN IF NOT EXISTS session VARCHAR(20);"))
                conn.execute(text("ALTER TABLE result ADD COLUMN IF NOT EXISTS reg_number VARCHAR(100);"))
                
                # Synchronize User table
                conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS profile_picture VARCHAR(255);"))
                conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS is_suspended BOOLEAN DEFAULT FALSE;"))

                # Synchronize Course table
                conn.execute(text("ALTER TABLE course ADD COLUMN IF NOT EXISTS unit INTEGER DEFAULT 1;"))
                conn.execute(text("ALTER TABLE course ADD COLUMN IF NOT EXISTS semester VARCHAR(20);"))
                conn.execute(text("ALTER TABLE course ADD COLUMN IF NOT EXISTS student_id INTEGER;"))
                conn.commit()
        except Exception as e:
            print(f"Schema verification notice: {e}")

# INITIALIZE DATABASE & ACCOUNTS ON STARTUP
with app.app_context():
    auto_migrate_db()

    try:
        default_accounts = [
            ('admin', 'admin123', 'admin', 'MST System Administrator', 'admin@magazawa.edu.ng', '08000000000'),
            ('creator', 'creator123', 'creator', 'System Creator', 'creator@magazawa.edu.ng', '08000000001'),
            ('registrar', 'registrar123', 'registrar', 'MST Registrar Office', 'registrar@magazawa.edu.ng', '08000000002'),
        ]

        for username, pwd, role, full_name, email, phone in default_accounts:
            user = User.query.filter_by(role=role).first()
            if not user:
                user = User(
                    username=username,
                    password=generate_password_hash(pwd),
                    role=role,
                    full_name=full_name,
                    email=email,
                    phone=phone,
                    is_approved=True
                )
                db.session.add(user)
            else:
                user.is_approved = True

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Startup initialization error: {e}")

# --- BASE ROUTES ---
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/robots.txt')
def robots():
    content = "User-agent: *\nAllow: /\n"
    return Response(content, mimetype='text/plain')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            user = User.query.filter_by(username=username).first()
        except Exception:
            db.session.rollback()
            flash('Database error encountered. Please try logging in again.', 'danger')
            return render_template('login.html')

        if user and check_password_hash(user.password, password):
            if getattr(user, 'is_suspended', False):
                flash('Your account has been suspended by Administration. Contact support.', 'danger')
                return redirect(url_for('login'))

            if not user.is_approved and user.role not in ['admin', 'creator', 'registrar']:
                flash('Your account is pending approval by Magazawa Admin.', 'warning')
                return redirect(url_for('login'))

            login_user(user)
            role_routes = {
                'admin': 'admin_dashboard',
                'creator': 'creator_dashboard',
                'registrar': 'registrar_dashboard',
                'lecturer': 'lecturer_dashboard',
                'student': 'student_dashboard'
            }
            return redirect(url_for(role_routes.get(user.role, 'student_dashboard')))
        else:
            flash('Invalid login credentials.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- APPLICATION FORM ROUTES ---
@app.route('/apply/student', methods=['GET', 'POST'])
def apply_student():
    if request.method == 'POST':
        p_cert = request.files.get('primary_cert')
        s_cert = request.files.get('sec_cert')

        p_filename, s_filename = "", ""

        if p_cert and allowed_file(p_cert.filename):
            ext = os.path.splitext(p_cert.filename)[1].lstrip('.').lower()
            p_filename = secure_filename(f"primary_{uuid.uuid4().hex[:8]}.{ext}")
            p_cert.save(os.path.join(app.config['UPLOAD_FOLDER'], p_filename))

        if s_cert and allowed_file(s_cert.filename):
            ext = os.path.splitext(s_cert.filename)[1].lstrip('.').lower()
            s_filename = secure_filename(f"sec_{uuid.uuid4().hex[:8]}.{ext}")
            s_cert.save(os.path.join(app.config['UPLOAD_FOLDER'], s_filename))

        new_student = User(
            username=request.form['email'],
            password=generate_password_hash(request.form['password']),
            role='student',
            full_name=request.form['full_name'],
            email=request.form['email'],
            phone=request.form['phone'],
            dob=request.form.get('dob', ''),
            primary_school=request.form.get('primary_school', ''),
            primary_cert=p_filename,
            sec_school=request.form.get('sec_school', ''),
            sec_cert=s_filename
        )
        db.session.add(new_student)
        db.session.commit()
        flash('Application submitted to Magazawa Skills and Technology! Await admission approval.', 'success')
        return redirect(url_for('login'))
    return render_template('apply_student.html')

@app.route('/apply/lecturer', methods=['GET', 'POST'])
def apply_lecturer():
    if request.method == 'POST':
        new_lecturer = User(
            username=request.form['email'],
            password=generate_password_hash(request.form['password']),
            role='lecturer',
            full_name=request.form['full_name'],
            email=request.form['email'],
            phone=request.form['phone'],
            desired_courses=request.form.get('courses', '')
        )
        db.session.add(new_lecturer)
        db.session.commit()
        flash('Lecturer application submitted successfully!', 'success')
        return redirect(url_for('login'))
    return render_template('apply_lecturer.html')

# --- DASHBOARD ROUTES ---
@app.route('/dashboard/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin': 
        return redirect(url_for('login'))

    try:
        students = User.query.filter_by(role='student').all()
        lecturers = User.query.filter_by(role='lecturer').all()
        all_users = User.query.filter(User.id != current_user.id).all()
        messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()
        courses = Course.query.all()
        results = Result.query.all()
    except Exception as e:
        db.session.rollback()
        flash(f"Database query notice: {str(e).split('[SQL:')[0].strip()}", "warning")
        students, lecturers, all_users, messages, courses, results = [], [], [], [], [], []

    return render_template('admin_dashboard.html', students=students, lecturers=lecturers, all_users=all_users, messages=messages, courses=courses, results=results)

@app.route('/dashboard/creator')
@login_required
def creator_dashboard():
    try:
        total_students = User.query.filter_by(role='student').count()
        total_lecturers = User.query.filter_by(role='lecturer').count()
        total_admins = User.query.filter_by(role='admin').count()
        approved_students = User.query.filter_by(role='student', is_approved=True).count()
        approved_lecturers = User.query.filter_by(role='lecturer', is_approved=True).count()
    except Exception:
        db.session.rollback()
        total_students = total_lecturers = total_admins = approved_students = approved_lecturers = 0

    return render_template('creator_dashboard.html',
                           total_students=total_students,
                           total_lecturers=total_lecturers,
                           total_admins=total_admins,
                           approved_students=approved_students,
                           approved_lecturers=approved_lecturers)

@app.route('/dashboard/registrar')
@login_required
def registrar_dashboard():
    try:
        students = User.query.filter_by(role='student', is_approved=True).all()
        lecturers = User.query.filter_by(role='lecturer', is_approved=True).all()
        messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()
    except Exception:
        db.session.rollback()
        students, lecturers, messages = [], [], []

    return render_template('registrar_dashboard.html', students=students, lecturers=lecturers, messages=messages)

@app.route('/dashboard/lecturer', methods=['GET', 'POST'])
@login_required
def lecturer_dashboard():
    if current_user.role != 'lecturer': 
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        filename = ""
        if file and allowed_file(file.filename):
            ext = os.path.splitext(file.filename)[1].lstrip('.').lower()
            filename = secure_filename(f"material_{uuid.uuid4().hex[:8]}.{ext}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        material = Material(
            title=request.form['title'],
            material_type=request.form['type'],
            file_path=filename,
            lecturer_id=current_user.id
        )
        db.session.add(material)
        db.session.commit()
        flash('Material Uploaded Successfully.', 'success')
        return redirect(url_for('lecturer_dashboard'))

    try:
        materials = Material.query.filter_by(lecturer_id=current_user.id).all()
        users = User.query.filter(User.id != current_user.id).all()
        messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()
    except Exception:
        db.session.rollback()
        materials, users, messages = [], [], []

    return render_template('lecturer_dashboard.html', lecturer=current_user, materials=materials, users=users, messages=messages)

@app.route('/student_dashboard')
@login_required
def student_dashboard():
    if current_user.role != 'student' and current_user.role not in ['admin', 'creator']:
        flash("Access restricted to student accounts.", "warning")
        return redirect(url_for('login'))

    user_id = current_user.id
    
    # 1. Registered Courses for this student (or general courses fallback)
    courses = Course.query.filter(or_(Course.student_id == user_id, Course.student_id == None)).all()

    # 2. Results for this student (matches by student_id or email/username reg_number)
    results = Result.query.filter(
        or_(
            Result.student_id == user_id,
            Result.reg_number.ilike(current_user.username),
            Result.reg_number.ilike(current_user.email or '')
        )
    ).all()
    
    # 3. NBTE 4.0 Scale CGPA Calculation
    total_units = 0
    total_points = 0
    grade_points = {'A': 4.0, 'AB': 3.5, 'B': 3.0, 'BC': 2.5, 'C': 2.0, 'CD': 1.5, 'D': 1.0, 'F': 0.0}
    
    for row in results:
        unit = getattr(row, 'unit', 1) or 1
        grade = (getattr(row, 'grade', 'F') or 'F').upper().strip()
        point = grade_points.get(grade, 0.0)
        total_units += unit
        total_points += (unit * point)
        
    cgpa = (total_points / total_units) if total_units > 0 else 0.0

    # 4. Lecture Materials & Messages
    materials = Material.query.all()
    messages = Message.query.filter_by(receiver_id=user_id).order_by(Message.timestamp.desc()).all()

    return render_template(
        'student_dashboard.html',
        student=current_user,
        courses=courses,
        results=results,
        cgpa=cgpa,
        materials=materials,
        messages=messages
    )

# --- ADMIN ACTIONS ---
@app.route('/admin/ask_gemini', methods=['POST'])
@login_required
def ask_gemini():
    if current_user.role != 'admin':
        return jsonify({"error": "Unauthorized access"}), 403

    if not gemini_client:
        return jsonify({"error": "Gemini API key is not configured in environment variables."}), 500

    data = request.get_json() or {}
    user_prompt = data.get('prompt', '').strip()

    if not user_prompt:
        return jsonify({"error": "Prompt cannot be empty"}), 400

    total_students = User.query.filter_by(role='student').count()
    total_lecturers = User.query.filter_by(role='lecturer').count()
    pending_students = User.query.filter_by(role='student', is_approved=False).count()

    portal_context = (
        f"Live Portal Stats: Total Students = {total_students}, "
        f"Total Lecturers = {total_lecturers}, "
        f"Pending Student Approvals = {pending_students}."
    )

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=f"You are a helpful AI assistant integrated into the Magazawa Skills & Technology Admin Dashboard. {portal_context} Answer clearly and professionally."
            )
        )
        return jsonify({"response": response.text})

    except Exception as e:
        return jsonify({"error": f"Gemini API Error: {str(e)}"}), 500

@app.route('/admin/approve_student/<int:id>')
@login_required
def approve_student(id):
    if current_user.role != 'admin': 
        return redirect(url_for('login'))
    student = db.session.get(User, id)
    if student:
        student.is_approved = True
        student.admission_status = "Admitted"
        student.remita_invoice = f"MST-RRR-{id}089234"
        db.session.commit()
        flash(f'Admission granted to {student.full_name}. Remita RRR generated.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject_student/<int:id>')
@login_required
def reject_student(id):
    if current_user.role != 'admin':
        return redirect(url_for('login'))
    student = db.session.get(User, id)
    if student:
        db.session.delete(student)
        db.session.commit()
        flash('Student application rejected and removed.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_lecturer/<int:id>')
@login_required
def approve_lecturer(id):
    if current_user.role != 'admin': 
        return redirect(url_for('login'))
    lecturer = db.session.get(User, id)
    if lecturer:
        lecturer.is_approved = True
        db.session.commit()
        flash(f'Lecturer {lecturer.full_name} approved successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject_lecturer/<int:id>')
@login_required
def reject_lecturer(id):
    if current_user.role != 'admin':
        return redirect(url_for('login'))
    lecturer = db.session.get(User, id)
    if lecturer:
        db.session.delete(lecturer)
        db.session.commit()
        flash('Lecturer application rejected and removed.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_payment/<int:id>')
@login_required
def approve_payment(id):
    if current_user.role != 'admin':
        return redirect(url_for('login'))
    student = db.session.get(User, id)
    if student:
        student.payment_status = "Paid"
        db.session.commit()
        flash(f'Payment confirmed for {student.full_name}.', 'success')
    return redirect(url_for('admin_dashboard'))

# --- STUDENT SUSPENSION TOGGLE ROUTE ---
@app.route('/admin/toggle_suspension/<int:user_id>', methods=['POST'])
@login_required
def toggle_suspension(user_id):
    if current_user.role != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('login'))

    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "warning")
        return redirect(url_for('admin_dashboard'))
    
    # Toggle suspension state regardless of admission/payment status
    user.is_suspended = not getattr(user, 'is_suspended', False)
    db.session.commit()

    if user.is_suspended:
        flash(f"Account for {user.full_name} has been suspended.", "warning")
    else:
        flash(f"Account for {user.full_name} has been reactivated.", "success")

    return redirect(url_for('admin_dashboard'))

# --- COURSE MANAGEMENT ROUTES ---
@app.route('/admin/add_course', methods=['POST'])
@login_required
def add_course():
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    student_id = request.form.get('student_id')
    course_name = request.form.get('course_name', '').strip()
    course_code = request.form.get('course_code', '').strip()
    unit = request.form.get('unit', '1')
    semester = request.form.get('semester', '1')

    if not course_name or not course_code:
        flash('Course Name and Course Code are required.', 'danger')
        return redirect(url_for('admin_dashboard'))

    try:
        unit_val = int(unit) if str(unit).isdigit() else 1
        student_id_val = int(student_id) if student_id and str(student_id).isdigit() else None

        new_course = Course(
            student_id=student_id_val,
            course_name=course_name,
            course_code=course_code,
            unit=unit_val,
            semester=semester
        )
        db.session.add(new_course)
        db.session.commit()
        flash('Course assigned successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        clean_error = str(e).split('(Background on this error')[0].split('[SQL:')[0].strip()
        flash(f'Error adding course: {clean_error}', 'danger')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_course/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    try:
        course = db.get_or_404(Course, course_id)
        db.session.delete(course)
        db.session.commit()
        flash('Course removed successfully!', 'info')
    except Exception as e:
        db.session.rollback()
        clean_error = str(e).split('(Background on this error')[0].split('[SQL:')[0].strip()
        flash(f'Error removing course: {clean_error}', 'danger')

    return redirect(url_for('admin_dashboard'))

# --- MANAGE & DELETE RESULT ROUTES ---
@app.route('/manage_result', methods=['POST'])
@login_required
def manage_result():
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('admin_dashboard'))

    action = request.form.get('action')
    
    if action == 'add':
        student_id = request.form.get('student_id')
        raw_title = request.form.get('title', '').strip() or request.form.get('course_name', '').strip()
        course_code = request.form.get('course_code', '').strip()
        score = request.form.get('score', '').strip()
        grade = request.form.get('grade', '').strip()
        unit = request.form.get('unit', '1')
        semester = request.form.get('semester', '1')
        level = request.form.get('level', 'HND1')
        session_val = request.form.get('session', '2023/2024')

        if not student_id or not raw_title or not grade:
            flash('Please select a student and provide the Course Title & Grade.', 'danger')
            return redirect(url_for('admin_dashboard'))

        if not course_code:
            parts = raw_title.split()
            course_code = parts[-1] if len(parts) > 1 else raw_title

        try:
            student_id_val = int(student_id)
            unit_val = int(unit) if str(unit).isdigit() else 1

            target_student = db.session.get(User, student_id_val)
            reg_num = target_student.username if target_student else None

            new_result = Result(
                student_id=student_id_val,
                reg_number=reg_num,
                title=raw_title,
                course_name=raw_title,
                course_code=course_code,
                score=score,
                grade=grade,
                unit=unit_val,
                semester=str(semester),
                level=level,
                session=session_val
            )

            db.session.add(new_result)
            db.session.commit()
            flash('Grade posted to student profile successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            clean_error = str(e).split('(Background on this error')[0].split('[SQL:')[0].strip()
            flash(f'Error adding result: {clean_error}', 'danger')

    elif action == 'remove':
        result_id = request.form.get('result_id')
        if result_id and str(result_id).isdigit():
            result_to_delete = db.session.get(Result, int(result_id))
            if result_to_delete:
                db.session.delete(result_to_delete)
                db.session.commit()
                flash('Result record deleted successfully.', 'info')
            else:
                flash('Result Record ID not found.', 'warning')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_result/<int:result_id>', methods=['POST'])
@login_required
def delete_result(result_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    result = db.session.get(Result, result_id)
    if result:
        db.session.delete(result)
        db.session.commit()
        flash('Student result record deleted successfully.', 'success')
    else:
        flash('Result record not found.', 'warning')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/send_to_registrar', methods=['POST'])
@login_required
def send_to_registrar():
    if current_user.role != 'admin':
        return redirect(url_for('login'))

    registrar = User.query.filter_by(role='registrar').first()
    if not registrar:
        flash('No Registrar account found in database.', 'danger')
        return redirect(url_for('admin_dashboard'))

    total_students = User.query.filter_by(role='student', is_approved=True).count()
    total_lecturers = User.query.filter_by(role='lecturer', is_approved=True).count()
    total_courses = Course.query.count()
    total_results = Result.query.count()

    summary_report = (
        f" OFFICIAL SCHOOL DATA TRANSFER FROM ADMIN\n"
        f"----------------------------------------\n"
        f"• Total Approved Lecturers: {total_lecturers}\n"
        f"• Total Approved Students: {total_students}\n"
        f"• Total Active Courses: {total_courses}\n"
        f"• Total Results Logged: {total_results}\n"
        f"Status: ALL ADMIN WORK COMPLETED & VERIFIED."
    )

    msg = Message(sender_id=current_user.id, receiver_id=registrar.id, content=summary_report)
    db.session.add(msg)
    db.session.commit()

    flash('Complete school data report successfully transmitted to the Registrar!', 'success')
    return redirect(url_for('admin_dashboard'))

# --- MASTER PASS ACCESS OVERRIDE ---
@app.route('/master_access', methods=['GET', 'POST'])
def master_access():
    if request.method == 'POST':
        master_pwd = request.form.get('master_password')
        target_role = request.form.get('target_role')

        if master_pwd == 'suleexpert':
            user = User.query.filter_by(role=target_role).first()
            if user:
                login_user(user)
                flash(f'Master access granted! Switched to {target_role.capitalize()} view.', 'success')
                role_routes = {
                    'admin': 'admin_dashboard',
                    'creator': 'creator_dashboard',
                    'registrar': 'registrar_dashboard',
                    'lecturer': 'lecturer_dashboard',
                    'student': 'student_dashboard'
                }
                return redirect(url_for(role_routes.get(target_role, 'login')))
            else:
                flash(f'No user account exists yet for role: {target_role}', 'warning')
        else:
            flash('Invalid Master Password!', 'danger')

    return render_template('master_access.html')

# --- LECTURER ACTIONS & MESSAGING ---
@app.route('/lecturer/submit_result', methods=['POST'])
@login_required
def submit_result_to_admin():
    if current_user.role != 'lecturer':
        return redirect(url_for('login'))

    student_name = request.form.get('student_name')
    reg_number = request.form.get('reg_number')
    course_name = request.form.get('course_name')
    score = request.form.get('score')

    admin = User.query.filter_by(role='admin').first()
    if admin:
        result_payload = (
            f"RESULT SUBMISSION FROM LECTURER ({current_user.full_name}):\n"
            f"- Student Name: {student_name}\n"
            f"- Reg Number/Email: {reg_number}\n"
            f"- Course: {course_name}\n"
            f"- Score: {score}"
        )
        msg = Message(sender_id=current_user.id, receiver_id=admin.id, content=result_payload)
        db.session.add(msg)
        db.session.commit()
        flash('Student result submitted directly to Admin inbox.', 'success')
    else:
        flash('Unable to forward result. Admin account not found.', 'danger')

    return redirect(url_for('lecturer_dashboard'))

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    receiver_id = request.form.get('receiver_id')
    content = request.form.get('content', '').strip()
    
    if content and receiver_id:
        msg = Message(
            sender_id=current_user.id,
            receiver_id=int(receiver_id),
            content=content
        )
        db.session.add(msg)
        db.session.commit()
        flash('Message sent successfully!', 'success')
    else:
        flash('Message content cannot be empty.', 'warning')
        
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/student/download/<filename>')
@login_required
@payment_required
def download_material(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# --- MANUAL DATABASE SCHEMA FIX ROUTE ---
@app.route('/fix_results_db')
def fix_results_db():
    try:
        student = User.query.filter(User.username.ilike('%sulemanexpert2000@gmail.com%')).first()
        if not student:
            return "Student account not found in database."

        updated_count = Result.query.filter(
            or_(
                Result.reg_number.ilike(student.username),
                Result.reg_number.ilike(student.email)
            )
        ).update({Result.student_id: student.id}, synchronize_session=False)

        db.session.commit()
        return f"SUCCESS! Linked {updated_count} result record(s) to Student ID: {student.id} ({student.username})."
    except Exception as e:
        db.session.rollback()
        return f"Database Error: {str(e)}"
        
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
