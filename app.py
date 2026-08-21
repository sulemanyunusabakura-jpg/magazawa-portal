import os
import uuid
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_from_directory, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text
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

# ABSOLUTE PATH FOR UPLOAD DIRECTORY
app.config['UPLOAD_FOLDER'] = os.path.abspath(os.path.join(app.root_path, 'static', 'uploads'))
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'ppt', 'pptx', 'mp3', 'wav', 'mp4', 'webm'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# SAFE GEMINI CLIENT INITIALIZATION
gemini_api_key = os.environ.get('GEMINI_API_KEY')
gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        db.session.rollback()
        return None

# --- CUSTOM DECORATOR: FEES PAYMENT CHECK ---
def payment_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        payment_status = getattr(current_user, 'payment_status', 'Unpaid') or 'Unpaid'
        if current_user.role == 'student' and str(payment_status).strip().lower() != 'paid':
            flash("Access Restricted: Please complete your school fees payment to unlock this section.", "warning")
            return redirect(url_for('student_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- AUTOMATIC SCHEMA MIGRATION FUNCTION ---
def auto_migrate_db():
    """Inspects existing tables and automatically adds missing columns without dropping data."""
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()

            # 1. MIGRATE MESSAGE TABLE
            if 'message' in tables:
                columns = [col['name'] for col in inspector.get_columns('message')]
                with db.engine.connect() as conn:
                    if 'msg_type' not in columns:
                        conn.execute(text("ALTER TABLE message ADD COLUMN msg_type VARCHAR(20) DEFAULT 'text';"))
                        conn.commit()
                    if 'file_path' not in columns:
                        conn.execute(text("ALTER TABLE message ADD COLUMN file_path VARCHAR(255);"))
                        conn.commit()

            # 2. MIGRATE USER TABLE
            if 'user' in tables:
                user_columns = [col['name'] for col in inspector.get_columns('user')]
                with db.engine.connect() as conn:
                    for col_name, col_type, default in [
                        ('payment_status', 'VARCHAR(20)', "'Unpaid'"),
                        ('remita_invoice', 'VARCHAR(100)', "NULL"),
                        ('admission_status', 'VARCHAR(50)', "'Admitted'"),
                        ('desired_courses', 'TEXT', "NULL")
                    ]:
                        if col_name not in user_columns:
                            try:
                                conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col_name} {col_type} DEFAULT {default};'))
                                conn.commit()
                            except Exception:
                                try:
                                    conn.execute(text(f'ALTER TABLE user ADD COLUMN {col_name} {col_type} DEFAULT {default};'))
                                    conn.commit()
                                except Exception:
                                    pass
        except Exception as e:
            print(f"Schema auto-migration notice: {e}")

# INITIALIZE DATABASE & ACCOUNTS ON STARTUP
with app.app_context():
    try:
        db.create_all()
        auto_migrate_db()
    except Exception as e:
        print(f"Database creation error: {e}")

    try:
        # DEFAULT ACCOUNTS SETUP
        for role, name, email, phone in [
            ('admin', 'MST System Administrator', 'admin@magazawa.edu.ng', '08000000000'),
            ('creator', 'System Creator', 'creator@magazawa.edu.ng', '08000000001'),
            ('registrar', 'MST Registrar Office', 'registrar@magazawa.edu.ng', '08000000002')
        ]:
            acc = User.query.filter_by(role=role).first()
            if not acc:
                acc = User(
                    username=role,
                    password=generate_password_hash(f'{role}123'),
                    role=role,
                    full_name=name,
                    email=email,
                    phone=phone,
                    is_approved=True
                )
                db.session.add(acc)
            else:
                acc.is_approved = True

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
            flash('Database sync error. Please try logging in again.', 'danger')
            return render_template('login.html')

        if user and check_password_hash(user.password, password):
            if not getattr(user, 'is_approved', False) and user.role not in ['admin', 'creator', 'registrar']:
                flash('Your account is pending approval by Magazawa Admin.', 'warning')
                return redirect(url_for('login'))

            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'creator':
                return redirect(url_for('creator_dashboard'))
            elif user.role == 'registrar':
                return redirect(url_for('registrar_dashboard'))
            elif user.role == 'lecturer':
                return redirect(url_for('lecturer_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid login credentials.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- DASHBOARD ROUTES ---
@app.route('/dashboard/lecturer', methods=['GET', 'POST'])
@login_required
def lecturer_dashboard():
    if current_user.role != 'lecturer': 
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        filename = ""
        if file and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f"material_{uuid.uuid4().hex[:8]}.{ext}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        try:
            material = Material(
                title=request.form['title'],
                material_type=request.form['type'],
                file_path=filename,
                lecturer_id=current_user.id
            )
            db.session.add(material)
            db.session.commit()
            flash('Material Uploaded Successfully.', 'success')
        except Exception:
            db.session.rollback()
            flash('Failed to upload material due to database error.', 'danger')

        return redirect(url_for('lecturer_dashboard'))

    materials, users, messages = [], [], []
    try:
        materials = Material.query.filter_by(lecturer_id=current_user.id).all()
    except Exception:
        db.session.rollback()

    try:
        users = User.query.filter(User.id != current_user.id).all()
    except Exception:
        db.session.rollback()

    try:
        messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()
    except Exception:
        db.session.rollback()

    return render_template('lecturer_dashboard.html', lecturer=current_user, materials=materials, users=users, messages=messages)

@app.route('/dashboard/student')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))

    courses, results, materials = [], [], []

    try:
        courses = Course.query.filter_by(student_id=current_user.id).all()
    except Exception:
        db.session.rollback()

    try:
        results = Result.query.filter_by(student_id=current_user.id).all()
    except Exception:
        db.session.rollback()

    try:
        payment_status = getattr(current_user, 'payment_status', 'Unpaid') or 'Unpaid'
        has_paid = str(payment_status).strip().lower() == 'paid'
        materials = Material.query.all() if has_paid else []
    except Exception:
        db.session.rollback()

    return render_template(
        'student_dashboard.html',
        student=current_user,
        courses=courses,
        results=results,
        materials=materials
    )

@app.route('/dashboard/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin': 
        return redirect(url_for('login'))

    students, lecturers, all_users, messages = [], [], [], []
    try:
        students = User.query.filter_by(role='student').all()
        lecturers = User.query.filter_by(role='lecturer').all()
        all_users = User.query.filter(User.id != current_user.id).all()
        messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()
    except Exception:
        db.session.rollback()

    return render_template('admin_dashboard.html', students=students, lecturers=lecturers, all_users=all_users, messages=messages)

@app.route('/dashboard/creator')
@login_required
def creator_dashboard():
    total_students = total_lecturers = total_admins = approved_students = approved_lecturers = 0
    try:
        total_students = User.query.filter_by(role='student').count()
        total_lecturers = User.query.filter_by(role='lecturer').count()
        total_admins = User.query.filter_by(role='admin').count()
        approved_students = User.query.filter_by(role='student', is_approved=True).count()
        approved_lecturers = User.query.filter_by(role='lecturer', is_approved=True).count()
    except Exception:
        db.session.rollback()

    return render_template('creator_dashboard.html',
                           total_students=total_students,
                           total_lecturers=total_lecturers,
                           total_admins=total_admins,
                           approved_students=approved_students,
                           approved_lecturers=approved_lecturers)

@app.route('/dashboard/registrar')
@login_required
def registrar_dashboard():
    students, lecturers, messages = [], [], []
    try:
        students = User.query.filter_by(role='student', is_approved=True).all()
        lecturers = User.query.filter_by(role='lecturer', is_approved=True).all()
        messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()
    except Exception:
        db.session.rollback()

    return render_template('registrar_dashboard.html', students=students, lecturers=lecturers, messages=messages)

# --- APPLICATION FORM ROUTES ---
@app.route('/apply/student', methods=['GET', 'POST'])
def apply_student():
    if request.method == 'POST':
        p_cert = request.files.get('primary_cert')
        s_cert = request.files.get('sec_cert')

        p_filename, s_filename = "", ""

        if p_cert and allowed_file(p_cert.filename):
            ext = p_cert.filename.rsplit('.', 1)[1].lower()
            p_filename = secure_filename(f"primary_{uuid.uuid4().hex[:8]}.{ext}")
            p_cert.save(os.path.join(app.config['UPLOAD_FOLDER'], p_filename))

        if s_cert and allowed_file(s_cert.filename):
            ext = s_cert.filename.rsplit('.', 1)[1].lower()
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

# --- OTHER ACTIONS ---
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
        
    return redirect(request.referrer or url_for('login'))

@app.route('/student/download/<filename>')
@login_required
@payment_required
def download_material(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
