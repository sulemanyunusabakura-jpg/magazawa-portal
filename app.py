import io
import os
import uuid
from functools import wraps
from google import genai
from google.genai import types
import qrcode
from reportlab.lib import colors
# ReportLab Imports for Professional PDF Generation
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
import requests
from sqlalchemy import inspect, or_, text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from flask import (
    Flask,
    Response,
    jsonify,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from models import Course, Material, Message, Result, User, AuditLog, db
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY', 'magazawa_skills_technology_secret'
)

# --- PAYSTACK CONFIGURATION ---
PAYSTACK_SECRET_KEY = os.environ.get(
    'PAYSTACK_SECRET_KEY', 'sk_test_placeholder_key'
)

# --- DATABASE CONNECTION & CONFIGURATION ---
db_url = os.environ.get('DATABASE_URL', 'sqlite:///magazawa_portal.db')
if db_url.startswith('postgres://'):
  db_url = db_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if 'postgresql' in db_url:
  app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
      'pool_pre_ping': True,
      'pool_recycle': 300,
      'hide_parameters': True,
  }

# ABSOLUTE PATH FOR UPLOAD DIRECTORY
app.config['UPLOAD_FOLDER'] = os.path.abspath(
    os.path.join(app.root_path, 'static', 'uploads')
)
ALLOWED_EXTENSIONS = {
    'pdf',
    'png',
    'jpg',
    'jpeg',
    'gif',
    'doc',
    'docx',
    'ppt',
    'pptx',
    'mp3',
    'wav',
    'mp4',
    'webm',
}
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
    if (
        current_user.role == 'student'
        and getattr(current_user, 'payment_status', '') != 'Paid'
    ):
      flash(
          'Access Restricted: Please complete your school fees payment to'
          ' unlock this section.',
          'warning',
      )
      return redirect(url_for('student_dashboard'))
    return f(*args, **kwargs)

  return decorated_function


# --- AUTOMATIC DATABASE SCHEMA INITIALIZATION AND MIGRATION ---
def auto_migrate_db():
  """Creates tables and synchronizes database schema gracefully."""
  with app.app_context():
    try:
      db.create_all()
      with db.engine.connect() as conn:
        # Synchronize Course table
        conn.execute(
            text(
                'ALTER TABLE course ADD COLUMN IF NOT EXISTS lecturer_id'
                ' INTEGER;'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE course ADD COLUMN IF NOT EXISTS student_id'
                ' INTEGER;'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE course ADD COLUMN IF NOT EXISTS unit INTEGER'
                ' DEFAULT 1;'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE course ADD COLUMN IF NOT EXISTS semester'
                ' VARCHAR(20);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE course ADD COLUMN IF NOT EXISTS code'
                ' VARCHAR(50);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE course ADD COLUMN IF NOT EXISTS title'
                ' VARCHAR(200);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE course ADD COLUMN IF NOT EXISTS department'
                ' VARCHAR(100);'
            )
        )

        # Synchronize Message table
        conn.execute(
            text(
                'ALTER TABLE message ADD COLUMN IF NOT EXISTS is_read BOOLEAN'
                ' DEFAULT FALSE;'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE message ADD COLUMN IF NOT EXISTS msg_type'
                " VARCHAR(50) DEFAULT 'text';"
            )
        )
        conn.execute(
            text(
                'ALTER TABLE message ADD COLUMN IF NOT EXISTS file_path'
                ' VARCHAR(255);'
            )
        )

        # Synchronize User table columns
        conn.execute(
            text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS status'
                ' VARCHAR(50);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS reg_number'
                ' VARCHAR(100);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS level'
                ' VARCHAR(20);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS program'
                ' VARCHAR(100);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS department'
                ' VARCHAR(100);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS profile_picture'
                ' VARCHAR(255);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS payment_status'
                ' VARCHAR(50);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS remita_invoice'
                ' VARCHAR(100);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS admission_status'
                ' VARCHAR(50);'
            )
        )

        # Synchronize Material table
        conn.execute(
            text(
                'ALTER TABLE material ADD COLUMN IF NOT EXISTS upload_date'
                ' TIMESTAMP DEFAULT CURRENT_TIMESTAMP;'
            )
        )

        # Synchronize Result table
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS title'
                ' VARCHAR(200);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS course_name'
                ' VARCHAR(200);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS course_code'
                ' VARCHAR(100);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS score'
                ' VARCHAR(50);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS grade_point FLOAT'
                ' DEFAULT 0.0;'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS unit INTEGER'
                ' DEFAULT 1;'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS semester'
                ' VARCHAR(20);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS level'
                ' VARCHAR(20);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS session'
                ' VARCHAR(20);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS reg_number'
                ' VARCHAR(100);'
            )
        )
        conn.execute(
            text(
                'ALTER TABLE result ADD COLUMN IF NOT EXISTS uploaded_at'
                ' TIMESTAMP DEFAULT CURRENT_TIMESTAMP;'
            )
        )

        conn.commit()
    except Exception as e:
      print(f'Schema verification notice: {e}')


# INITIALIZE DATABASE & DEFAULT SYSTEM ACCOUNTS ON STARTUP
with app.app_context():
  auto_migrate_db()

  try:
    default_accounts = [
        (
            'admin',
            'admin123',
            'admin',
            'MST System Administrator',
            'admin@magazawa.edu.ng',
            '08000000000',
        ),
        (
            'creator',
            'creator123',
            'creator',
            'System Creator',
            'creator@magazawa.edu.ng',
            '08000000001',
        ),
        (
            'registrar',
            'registrar123',
            'registrar',
            'MST Registrar Office',
            'registrar@magazawa.edu.ng',
            '08000000002',
        ),
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
            is_approved=True,
        )
        db.session.add(user)
      else:
        user.is_approved = True

    db.session.commit()
  except Exception as e:
    db.session.rollback()
    print(f'Startup initialization warning: {e}')


# --- FILE SERVING ROUTES FOR UPLOADED MEDIA ---
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/static/uploads/<path:filename>')
def static_uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# --- BASE ROUTES ---
@app.route('/')
def home():
  return redirect(url_for('login'))


@app.route('/robots.txt')
def robots():
  content = 'User-agent: *\nAllow: /\n'
  return Response(content, mimetype='text/plain')


@app.route('/login', methods=['GET', 'POST'])
def login():
  if request.method == 'POST':
    identifier = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    try:
      user = User.query.filter(
          or_(
              User.username.ilike(identifier),
              User.email.ilike(identifier),
              User.reg_number.ilike(identifier),
          )
      ).first()
    except Exception:
      db.session.rollback()
      flash('Database lookup error. Please try logging in again.', 'danger')
      return render_template('login.html')

    if user and check_password_hash(user.password, password):
      if not getattr(
          user, 'is_approved', False
      ) and user.role not in ['admin', 'creator', 'registrar']:
        flash(
            'Your account is pending approval by Magazawa Admin.', 'warning'
        )
        return redirect(url_for('login'))

      login_user(user)
      role_routes = {
          'admin': 'admin_dashboard',
          'creator': 'creator_dashboard',
          'registrar': 'registrar_dashboard',
          'lecturer': 'lecturer_dashboard',
          'student': 'student_dashboard',
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
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()

    # Check for existing account
    existing = User.query.filter(
        or_(User.username.ilike(email), User.email.ilike(email))
    ).first()
    if existing:
      flash('An account with this email already exists. Please log in.', 'info')
      return redirect(url_for('login'))

    # Certificate uploads
    p_cert = request.files.get('primary_cert')
    s_cert = request.files.get('sec_cert')
    p_filename, s_filename = '', ''

    if p_cert and allowed_file(p_cert.filename):
      ext = os.path.splitext(p_cert.filename)[1].lstrip('.').lower()
      p_filename = secure_filename(f'primary_{uuid.uuid4().hex[:8]}.{ext}')
      p_cert.save(os.path.join(app.config['UPLOAD_FOLDER'], p_filename))

    if s_cert and allowed_file(s_cert.filename):
      ext = os.path.splitext(s_cert.filename)[1].lstrip('.').lower()
      s_filename = secure_filename(f'sec_{uuid.uuid4().hex[:8]}.{ext}')
      s_cert.save(os.path.join(app.config['UPLOAD_FOLDER'], s_filename))

    # Profile Picture upload
    profile_pic = request.files.get('profile_picture')
    pic_filename = ''
    if profile_pic and allowed_file(profile_pic.filename):
      ext = os.path.splitext(profile_pic.filename)[1].lstrip('.').lower()
      pic_filename = secure_filename(f'profile_{uuid.uuid4().hex[:8]}.{ext}')
      profile_pic.save(os.path.join(app.config['UPLOAD_FOLDER'], pic_filename))

    new_student = User(
        username=email,
        password=generate_password_hash(password),
        role='student',
        full_name=full_name,
        email=email,
        phone=phone,
        dob=request.form.get('dob', ''),
        primary_school=request.form.get('primary_school', ''),
        primary_cert=p_filename,
        sec_school=request.form.get('sec_school', ''),
        sec_cert=s_filename,
        profile_picture=pic_filename,
        is_approved=False,  # Requires admin approval
        admission_status='Pending',  # Requires admin admission
        payment_status='Pending',
    )
    db.session.add(new_student)
    db.session.commit()
    flash(
        'Application submitted successfully! Please wait for Admin approval'
        ' before logging in.',
        'success',
    )
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
        desired_courses=request.form.get('courses', ''),
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
    messages = (
        Message.query.filter_by(receiver_id=current_user.id)
        .order_by(Message.timestamp.desc())
        .all()
    )
    courses = Course.query.order_by(Course.id.desc()).all()
  except Exception as e:
    db.session.rollback()
    flash(f"Database status notice: {str(e).split('[SQL:')[0].strip()}", 'warning')
    students, lecturers, all_users, messages, courses = [], [], [], [], []

  return render_template(
      'admin_dashboard.html',
      students=students,
      lecturers=lecturers,
      all_users=all_users,
      messages=messages,
      courses=courses,
  )


@app.route('/admin/add_course', methods=['POST'])
@login_required
def add_course():
  if current_user.role != 'admin':
    flash('Unauthorized access.', 'danger')
    return redirect(url_for('login'))

  student_id = request.form.get('student_id')
  course_name = request.form.get('course_name', '').strip() or request.form.get(
      'title', ''
  ).strip()
  course_code = request.form.get('course_code', '').strip() or request.form.get(
      'code', ''
  ).strip()
  unit = request.form.get('unit', '1')
  semester = request.form.get('semester', '1')

  if not course_name or not course_code:
    flash('Course Name and Course Code are required.', 'danger')
    return redirect(url_for('admin_dashboard'))

  try:
    unit_val = int(unit) if str(unit).isdigit() else 1
    student_id_val = (
        int(student_id) if student_id and str(student_id).isdigit() else None
    )

    new_course = Course(
        student_id=student_id_val,
        course_name=course_name,
        course_code=course_code,
        unit=unit_val,
        semester=str(semester),
    )
    db.session.add(new_course)
    db.session.commit()
    flash('Course added successfully!', 'success')
  except Exception as e:
    db.session.rollback()
    clean_error = (
        str(e).split('(Background on this error')[0].split('[SQL:')[0].strip()
    )
    flash(f'Error adding course: {clean_error}', 'danger')

  return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
def delete_course(course_id):
  if current_user.role != 'admin':
    flash('Unauthorized access.', 'danger')
    return redirect(url_for('login'))

  try:
    course = db.session.get(Course, course_id)
    if course:
      db.session.delete(course)
      db.session.commit()
      flash('Course removed successfully!', 'info')
    else:
      flash('Course not found or already deleted.', 'warning')
  except Exception as e:
    db.session.rollback()
    clean_error = (
        str(e).split('(Background on this error')[0].split('[SQL:')[0].strip()
    )
    flash(f'Error removing course: {clean_error}', 'danger')

  return redirect(url_for('admin_dashboard'))


@app.route('/dashboard/creator')
@login_required
def creator_dashboard():
  try:
    total_students = User.query.filter_by(role='student').count()
    total_lecturers = User.query.filter_by(role='lecturer').count()
    total_admins = User.query.filter_by(role='admin').count()
    approved_students = User.query.filter_by(
        role='student', is_approved=True
    ).count()
    approved_lecturers = User.query.filter_by(
        role='lecturer', is_approved=True
    ).count()
  except Exception:
    db.session.rollback()
    total_students = total_lecturers = total_admins = approved_students = (
        approved_lecturers
    ) = 0

  return render_template(
      'creator_dashboard.html',
      total_students=total_students,
      total_lecturers=total_lecturers,
      total_admins=total_admins,
      approved_students=approved_students,
      approved_lecturers=approved_lecturers,
  )


@app.route('/dashboard/registrar')
@login_required
def registrar_dashboard():
  try:
    students = User.query.filter_by(role='student', is_approved=True).all()
    lecturers = User.query.filter_by(role='lecturer', is_approved=True).all()
    messages = (
        Message.query.filter_by(receiver_id=current_user.id)
        .order_by(Message.timestamp.desc())
        .all()
    )
  except Exception:
    db.session.rollback()
    students, lecturers, messages = [], [], []

  return render_template(
      'registrar_dashboard.html',
      students=students,
      lecturers=lecturers,
      messages=messages,
  )


@app.route('/dashboard/lecturer', methods=['GET', 'POST'])
@login_required
def lecturer_dashboard():
  if current_user.role != 'lecturer':
    return redirect(url_for('login'))

  if request.method == 'POST':
    file = request.files.get('file')
    filename = ''
    if file and allowed_file(file.filename):
      ext = os.path.splitext(file.filename)[1].lstrip('.').lower()
      filename = secure_filename(f'material_{uuid.uuid4().hex[:8]}.{ext}')
      file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    material = Material(
        title=request.form['title'],
        material_type=request.form['type'],
        file_path=filename,
        lecturer_id=current_user.id,
    )
    db.session.add(material)
    db.session.commit()
    flash('Material Uploaded Successfully.', 'success')
    return redirect(url_for('lecturer_dashboard'))

  try:
    materials = Material.query.filter_by(lecturer_id=current_user.id).all()
    users = User.query.filter(User.id != current_user.id).all()
    messages = (
        Message.query.filter_by(receiver_id=current_user.id)
        .order_by(Message.timestamp.desc())
        .all()
    )
  except Exception:
    db.session.rollback()
    materials, users, messages = [], [], []

  return render_template(
      'lecturer_dashboard.html',
      lecturer=current_user,
      materials=materials,
      users=users,
      messages=messages,
  )


@app.route('/student_dashboard')
@login_required
def student_dashboard():
  if current_user.role != 'student' and current_user.role not in [
      'admin',
      'creator',
  ]:
    flash('Access restricted to student accounts.', 'warning')
    return redirect(url_for('login'))

  user_id = current_user.id

  courses = Course.query.filter(
      or_(Course.student_id == user_id, Course.student_id == None)
  ).all()

  results = Result.query.filter(
      or_(
          Result.student_id == user_id,
          Result.reg_number.ilike(current_user.username),
          Result.reg_number.ilike(current_user.email or ''),
      )
  ).all()

  total_units = 0
  total_points = 0
  grade_points_map = {
      'A': 4.0,
      'AB': 3.5,
      'B': 3.0,
      'BC': 2.5,
      'C': 2.0,
      'CD': 1.5,
      'D': 1.0,
      'F': 0.0,
  }

  for row in results:
    unit = getattr(row, 'unit', 1) or 1
    grade = (getattr(row, 'grade', 'F') or 'F').upper().strip()
    point = getattr(row, 'grade_point', None)
    if point is None:
      point = grade_points_map.get(grade, 0.0)
    total_units += unit
    total_points += unit * point

  cgpa = (total_points / total_units) if total_units > 0 else 0.0

  materials = Material.query.all()
  messages = (
      Message.query.filter_by(receiver_id=user_id)
      .order_by(Message.timestamp.desc())
      .all()
  )

  return render_template(
      'student_dashboard.html',
      student=current_user,
      courses=courses,
      results=results,
      cgpa=cgpa,
      materials=materials,
      messages=messages,
  )


# --- QR CODE GENERATION & VERIFICATION ROUTES ---
@app.route('/generate_qr/<int:student_id>')
def generate_qr(student_id):
  """Generates dynamic PNG QR Code pointing to student verification URL."""
  verify_url = url_for('verify_student', student_id=student_id, _external=True)
  img = qrcode.make(verify_url)
  buf = io.BytesIO()
  img.save(buf, format='PNG')
  buf.seek(0)
  return send_file(buf, mimetype='image/png')


@app.route('/verify/<int:student_id>')
def verify_student(student_id):
  """Public endpoint to verify student record via QR code scan."""
  student = db.session.get(User, student_id)
  if not student or student.role != 'student':
    return (
        jsonify({
            'status': 'error',
            'message': 'Invalid student record or student not found.',
        }),
        404,
    )

  return jsonify({
      'status': 'verified',
      'institution': 'Magazawa Skills and Technology',
      'full_name': student.full_name,
      'reg_number': student.reg_number or student.username,
      'admission_status': getattr(student, 'admission_status', 'Admitted'),
      'payment_status': getattr(student, 'payment_status', 'Pending'),
      'program': (
          getattr(student, 'program', '')
          or 'Computer Engineering & Applied Technology'
      ),
  })


@app.route('/verify/<txn_ref>')
def verify_receipt(txn_ref):
  """Public verification endpoint for payment receipt references."""
  student = User.query.filter_by(remita_invoice=txn_ref).first()
  if not student:
    return (
        jsonify({
            'status': 'error',
            'message': 'Invalid transaction reference.',
        }),
        404,
    )

  return jsonify({
      'status': 'valid',
      'institution': 'Magazawa Skills and Technology',
      'transaction_reference': txn_ref,
      'student_name': student.full_name,
      'payment_status': student.payment_status,
  })


# --- PROFESSIONAL FEATURE 1: AUTOMATED PDF ADMISSION LETTER GENERATOR ---
@app.route('/student/admission_letter')
@login_required
def download_admission_letter():
  if (
      current_user.role != 'student'
      or getattr(current_user, 'admission_status', '') != 'Admitted'
  ):
    flash('Admission letter is only available for admitted students.', 'warning')
    return redirect(url_for('student_dashboard'))

  buffer = io.BytesIO()
  pdf = canvas.Canvas(buffer, pagesize=letter)

  # Official Letterhead Header
  pdf.setFont('Helvetica-Bold', 18)
  pdf.setFillColor(colors.HexColor('#0f172a'))
  pdf.drawString(50, 740, 'MAGAZAWA SKILLS AND TECHNOLOGY')
  pdf.setFont('Helvetica', 10)
  pdf.setFillColor(colors.HexColor('#475569'))
  pdf.drawString(
      50, 725, 'Office of the Registrar | Official Provisional Admission Letter'
  )
  pdf.setStrokeColor(colors.HexColor('#cbd5e1'))
  pdf.line(50, 715, 560, 715)

  # Student Details Box
  pdf.setFont('Helvetica-Bold', 11)
  pdf.setFillColor(colors.HexColor('#1e293b'))
  pdf.drawString(50, 680, f'Date: September 2026')
  pdf.drawString(50, 660, f'Candidate Name: {current_user.full_name}')
  pdf.drawString(50, 640, f'Registration Email: {current_user.username}')
  pdf.drawString(
      50,
      620,
      'Program:'
      f' {getattr(current_user, "program", "") or "Computer Engineering & Applied Technology"}',
  )

  # Body Content
  pdf.setFont('Helvetica', 11)
  body_text = (
      f'Dear {current_user.full_name},\n\nWe are pleased to inform you that you'
      ' have been offered provisional admission into Magazawa Skills and'
      ' Technology for the current academic session.\n\nPlease proceed to your'
      ' online portal dashboard to clear your tuition fees via our secure'
      ' payment system. Once verified, you will be granted access to download'
      ' course materials, print your Digital ID Card, and register your'
      ' semester modules.'
  )

  text_obj = pdf.beginText(50, 570)
  text_obj.setFont('Helvetica', 11)
  text_obj.setLeading(16)
  for line in body_text.split('\n'):
    text_obj.textLine(line)
  pdf.drawText(text_obj)

  # Embed Verification QR Code on Letter
  verify_url = url_for(
      'verify_student', student_id=current_user.id, _external=True
  )
  qr_img = qrcode.make(verify_url)
  qr_buffer = io.BytesIO()
  qr_img.save(qr_buffer, format='PNG')
  qr_buffer.seek(0)
  pdf.drawImage(ImageReader(qr_buffer), 450, 610, width=90, height=90)

  # Signature Block
  pdf.line(50, 380, 560, 380)
  pdf.setFont('Helvetica-Bold', 10)
  pdf.drawString(50, 360, "Signed: Registrar's Office")
  pdf.drawString(50, 345, 'Magazawa Skills & Technology Portal Management')

  pdf.showPage()
  pdf.save()
  buffer.seek(0)

  return send_file(
      buffer,
      as_attachment=True,
      download_name=f'Admission_Letter_{current_user.username}.pdf',
      mimetype='application/pdf',
  )


# --- PROFESSIONAL FEATURE 2: DIGITAL ID CARD GENERATOR ---
@app.route('/student/id_card')
@login_required
def download_id_card():
  if current_user.role != 'student':
    return redirect(url_for('student_dashboard'))

  buffer = io.BytesIO()
  pdf = canvas.Canvas(buffer, pagesize=(350, 220))  # ID Card Standard Dimensions

  # Header Panel
  pdf.setFillColor(colors.HexColor('#0f172a'))
  pdf.rect(0, 170, 350, 50, fill=1)

  pdf.setFillColor(colors.white)
  pdf.setFont('Helvetica-Bold', 12)
  pdf.drawString(15, 195, 'MAGAZAWA SKILLS & TECH')
  pdf.setFont('Helvetica', 8)
  pdf.drawString(15, 180, 'STUDENT IDENTIFICATION CARD')

  # Profile Photo Rendering
  photo_path = None
  if getattr(current_user, 'profile_picture', None):
    possible_path = os.path.join(
        app.config['UPLOAD_FOLDER'], current_user.profile_picture
    )
    if os.path.exists(possible_path):
      photo_path = possible_path

  if photo_path:
    try:
      pdf.drawImage(photo_path, 15, 65, width=80, height=95)
    except Exception:
      pdf.rect(15, 65, 80, 95)
  else:
    pdf.setStrokeColor(colors.gray)
    pdf.rect(15, 65, 80, 95)
    pdf.setFont('Helvetica', 8)
    pdf.setFillColor(colors.black)
    pdf.drawString(25, 105, 'NO PHOTO')

  # Student Info Text
  pdf.setFillColor(colors.HexColor('#0f172a'))
  pdf.setFont('Helvetica-Bold', 11)
  pdf.drawString(105, 145, (current_user.full_name or 'Student')[:20])

  pdf.setFont('Helvetica', 8)
  pdf.drawString(105, 128, f'ID/Reg: {(current_user.username or "")[:18]}')
  pdf.drawString(105, 113, f'Role: Student')
  pdf.drawString(
      105,
      98,
      'Status:'
      f' {getattr(current_user, "admission_status", "Admitted") or "Admitted"}',
  )
  pdf.drawString(
      105, 83, f'Phone: {getattr(current_user, "phone", "N/A") or "N/A"}'
  )

  # QR Code Verification on ID Card
  verify_url = url_for(
      'verify_student', student_id=current_user.id, _external=True
  )
  qr_img = qrcode.make(verify_url)
  qr_buffer = io.BytesIO()
  qr_img.save(qr_buffer, format='PNG')
  qr_buffer.seek(0)
  pdf.drawImage(ImageReader(qr_buffer), 275, 75, width=65, height=65)

  # Card Bottom Strip
  pdf.setFillColor(colors.HexColor('#2563eb'))
  pdf.rect(0, 0, 350, 15, fill=1)
  pdf.setFillColor(colors.white)
  pdf.setFont('Helvetica-Bold', 7)
  pdf.drawCentredString(
      175, 4, 'PROPERTY OF MAGAZAWA SKILLS AND TECHNOLOGY PORTAL'
  )

  pdf.showPage()
  pdf.save()
  buffer.seek(0)

  return send_file(
      buffer,
      as_attachment=True,
      download_name=f'ID_Card_{current_user.username}.pdf',
      mimetype='application/pdf',
  )


# --- PROFESSIONAL FEATURE 3: ONLINE FEE PAYMENT INTEGRATION (PAYSTACK) ---
@app.route('/paystack/initialize', methods=['POST'])
@login_required
def initialize_paystack():
  if current_user.role != 'student':
    return jsonify({'error': 'Unauthorized'}), 403

  amount_kobo = 2500000  # Tuition amount (25,000 NGN in Kobo)
  url = 'https://api.paystack.co/transaction/initialize'
  headers = {
      'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
      'Content-Type': 'application/json',
  }
  payload = {
      'email': current_user.email or current_user.username,
      'amount': amount_kobo,
      'callback_url': url_for('verify_paystack', _external=True),
  }

  try:
    response = requests.post(url, json=payload, headers=headers)
    res_data = response.json()
    if res_data.get('status'):
      return redirect(res_data['data']['authorization_url'])
    else:
      flash(
          f"Payment Initialization Failed: {res_data.get('message')}", 'danger'
      )
  except Exception as e:
    flash(f'Payment Gateway Error: {str(e)}', 'danger')

  return redirect(url_for('student_dashboard'))


@app.route('/paystack/verify')
@login_required
def verify_paystack():
  reference = request.args.get('reference')
  if not reference:
    flash('Invalid transaction reference.', 'warning')
    return redirect(url_for('student_dashboard'))

  url = f'https://api.paystack.co/transaction/verify/{reference}'
  headers = {'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}'}

  try:
    response = requests.get(url, headers=headers)
    res_data = response.json()

    if res_data.get('status') and res_data['data']['status'] == 'success':
      current_user.payment_status = 'Paid'
      current_user.remita_invoice = f'PST-{reference[:10].upper()}'
      db.session.commit()
      flash(
          'Payment Successful! Your school fee status has been updated.',
          'success',
      )
    else:
      flash('Payment Verification Failed.', 'danger')
  except Exception as e:
    db.session.rollback()
    flash(f'Verification Error: {str(e)}', 'danger')

  return redirect(url_for('student_dashboard'))


# --- PROFESSIONAL FEATURE 4: AUTOMATED FEE RECEIPT PDF GENERATOR ---
@app.route('/download-receipt')
@login_required
@payment_required
def download_receipt():
  student_name = current_user.full_name or 'Student'
  student_id = getattr(current_user, 'reg_number', '') or current_user.username
  amount = '25,000 NGN'
  txn_ref = (
      getattr(current_user, 'remita_invoice', '') or 'PAYSTACK_REF_VERIFIED'
  )
  date_paid = 'September 2026'

  # 1. Create PDF in memory
  buffer = io.BytesIO()
  p = canvas.Canvas(buffer, pagesize=letter)

  # Header
  p.setFont('Helvetica-Bold', 18)
  p.drawString(100, 750, 'MAGAZAWA SKILLS & TECHNOLOGY')
  p.setFont('Helvetica', 12)
  p.drawString(100, 730, 'Official Fee Payment Receipt')
  p.line(100, 720, 500, 720)

  # Payment Details
  p.setFont('Helvetica-Bold', 10)
  p.drawString(100, 680, f'Student Name: {student_name}')
  p.drawString(100, 660, f'Student ID / Reg: {student_id}')
  p.drawString(100, 640, f'Amount Paid: {amount}')
  p.drawString(100, 620, f'Transaction Ref: {txn_ref}')
  p.drawString(100, 600, f'Payment Date: {date_paid}')
  p.drawString(100, 580, 'Status: SUCCESSFUL / PAID')

  # 2. Generate Verification QR Code
  verify_url = url_for('verify_receipt', txn_ref=txn_ref, _external=True)
  qr_img = qrcode.make(verify_url)
  qr_buffer = io.BytesIO()
  qr_img.save(qr_buffer, format='PNG')
  qr_buffer.seek(0)

  # Draw QR Code on PDF
  p.drawImage(ImageReader(qr_buffer), 380, 580, width=120, height=120)

  # Footer
  p.line(100, 550, 500, 550)
  p.setFont('Helvetica-Oblique', 9)
  p.drawString(
      100,
      535,
      'This is a computer-generated receipt and requires no physical signature.',
  )

  p.showPage()
  p.save()
  buffer.seek(0)

  return send_file(
      buffer,
      as_attachment=True,
      download_name=f'Receipt_{student_id}.pdf',
      mimetype='application/pdf',
  )


# --- PROFESSIONAL FEATURE 5: OFFICIAL RESULT SLIP GENERATOR ---
@app.route('/student/result_slip')
@login_required
@payment_required
def download_result_slip():
  results = Result.query.filter(
      or_(
          Result.student_id == current_user.id,
          Result.reg_number.ilike(current_user.username),
      )
  ).all()

  buffer = io.BytesIO()
  pdf = canvas.Canvas(buffer, pagesize=letter)

  # Document Header
  pdf.setFont('Helvetica-Bold', 16)
  pdf.setFillColor(colors.HexColor('#0f172a'))
  pdf.drawString(50, 750, 'MAGAZAWA SKILLS AND TECHNOLOGY')
  pdf.setFont('Helvetica', 10)
  pdf.drawString(50, 735, 'OFFICIAL SEMESTER RESULT STATEMENT')
  pdf.line(50, 725, 560, 725)

  # Student Data
  pdf.setFont('Helvetica-Bold', 10)
  pdf.drawString(50, 700, f'Student Name: {current_user.full_name}')
  pdf.drawString(50, 685, f'Registration Email/No: {current_user.username}')

  # Embed Verification QR Code on Result Slip
  verify_url = url_for(
      'verify_student', student_id=current_user.id, _external=True
  )
  qr_img = qrcode.make(verify_url)
  qr_buffer = io.BytesIO()
  qr_img.save(qr_buffer, format='PNG')
  qr_buffer.seek(0)
  pdf.drawImage(ImageReader(qr_buffer), 470, 665, width=80, height=80)

  # Table Header
  y = 640
  pdf.setFillColor(colors.HexColor('#f1f5f9'))
  pdf.rect(50, y - 5, 510, 20, fill=1)
  pdf.setFillColor(colors.black)
  pdf.drawString(55, y, 'Course Title')
  pdf.drawString(320, y, 'Code')
  pdf.drawString(410, y, 'Score')
  pdf.drawString(480, y, 'Grade')

  # Table Rows
  y -= 25
  pdf.setFont('Helvetica', 10)
  for r in results:
    pdf.drawString(
        55, y, (getattr(r, 'title', '') or getattr(r, 'course_name', 'Course'))[:35]
    )
    pdf.drawString(320, y, str(getattr(r, 'course_code', 'N/A')))
    pdf.drawString(410, y, str(getattr(r, 'score', 'N/A')))
    pdf.drawString(480, y, str(getattr(r, 'grade', 'N/A')))
    y -= 20

  pdf.showPage()
  pdf.save()
  buffer.seek(0)

  return send_file(
      buffer,
      as_attachment=True,
      download_name=f'Result_Slip_{current_user.username}.pdf',
      mimetype='application/pdf',
  )


# --- ADMIN ACTIONS ---
@app.route('/admin/ask_gemini', methods=['POST'])
@login_required
def ask_gemini():
  if current_user.role != 'admin':
    return jsonify({'error': 'Unauthorized access'}), 403

  if not gemini_client:
    return (
        jsonify({
            'error': (
                'Gemini API key is not configured in environment variables.'
            )
        }),
        500,
    )

  data = request.get_json() or {}
  user_prompt = data.get('prompt', '').strip()

  if not user_prompt:
    return jsonify({'error': 'Prompt cannot be empty'}), 400

  total_students = User.query.filter_by(role='student').count()
  total_lecturers = User.query.filter_by(role='lecturer').count()
  pending_students = User.query.filter_by(
      role='student', is_approved=False
  ).count()

  portal_context = (
      f'Live Portal Stats: Total Students = {total_students}, Total Lecturers'
      f' = {total_lecturers}, Pending Student Approvals = {pending_students}.'
  )

  try:
    response = gemini_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                'You are a helpful AI assistant integrated into the Magazawa'
                f' Skills & Technology Admin Dashboard. {portal_context} Answer'
                ' clearly and professionally.'
            )
        ),
    )
    return jsonify({'response': response.text})

  except Exception as e:
    return jsonify({'error': f'Gemini API Error: {str(e)}'}), 500


@app.route('/admin/approve_student/<int:id>', methods=['GET', 'POST'])
@login_required
def approve_student(id):
  if current_user.role != 'admin':
    return redirect(url_for('login'))
  student = db.session.get(User, id)
  if student:
    student.is_approved = True
    student.admission_status = 'Admitted'
    student.remita_invoice = f'MST-RRR-{id}089234'
    db.session.commit()
    flash(
        f'Admission granted to {student.full_name}. Remita RRR generated.',
        'success',
    )
  return redirect(url_for('admin_dashboard'))


@app.route('/admin/reject_student/<int:id>', methods=['GET', 'POST'])
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


@app.route('/admin/approve_lecturer/<int:id>', methods=['GET', 'POST'])
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


@app.route('/admin/reject_lecturer/<int:id>', methods=['GET', 'POST'])
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


@app.route('/admin/approve_payment/<int:id>', methods=['GET', 'POST'])
@login_required
def approve_payment(id):
  if current_user.role != 'admin':
    return redirect(url_for('login'))
  student = db.session.get(User, id)
  if student:
    student.payment_status = 'Paid'
    db.session.commit()
    flash(f'Payment confirmed for {student.full_name}.', 'success')
  return redirect(url_for('admin_dashboard'))


@app.route('/admin/toggle_user_status/<int:user_id>', methods=['POST'])
@login_required
def toggle_user_status(user_id):
  if current_user.role != 'admin':
    flash('Unauthorized access.', 'danger')
    return redirect(url_for('login'))

  target_user = db.session.get(User, user_id)
  if target_user:
    target_user.is_approved = not target_user.is_approved
    db.session.commit()
    status_str = 'approved' if target_user.is_approved else 'suspended/disabled'
    flash(
        f'Account status for {target_user.full_name} changed to {status_str}.',
        'success',
    )
  else:
    flash('User account not found.', 'warning')

  return redirect(url_for('admin_dashboard'))


# --- MANAGE RESULT ROUTE ---
@app.route('/manage_result', methods=['POST'])
@login_required
def manage_result():
  if current_user.role != 'admin':
    flash('Unauthorized access.', 'danger')
    return redirect(url_for('admin_dashboard'))

  action = request.form.get('action')

  if action == 'add':
    student_id = request.form.get('student_id')
    raw_title = request.form.get('title', '').strip() or request.form.get(
        'course_name', ''
    ).strip()
    course_code = request.form.get('course_code', '').strip()
    score = request.form.get('score', '').strip()
    grade = request.form.get('grade', '').strip().upper()
    unit = request.form.get('unit', '1')
    semester = request.form.get('semester', '1')
    level = request.form.get('level', 'HND1')
    session_val = request.form.get('session', '2023/2024')

    if not student_id or not raw_title or not grade:
      flash(
          'Please select a student and provide the Course Title & Grade.',
          'danger',
      )
      return redirect(url_for('admin_dashboard'))

    if not course_code:
      parts = raw_title.split()
      course_code = parts[-1] if len(parts) > 1 else raw_title

    grade_points_map = {
        'A': 4.0,
        'AB': 3.5,
        'B': 3.0,
        'BC': 2.5,
        'C': 2.0,
        'CD': 1.5,
        'D': 1.0,
        'F': 0.0,
    }
    gp_val = grade_points_map.get(grade, 0.0)

    try:
      student_id_val = int(student_id)
      unit_val = int(unit) if str(unit).isdigit() else 1

      target_student = db.session.get(User, student_id_val)
      reg_num = target_student.username if target_student else None

      result_kwargs = {
          'student_id': student_id_val,
          'reg_number': reg_num,
          'title': raw_title,
          'course_name': raw_title,
          'course_code': course_code,
          'score': score,
          'grade': grade,
          'unit': unit_val,
          'semester': str(semester),
          'level': level,
          'session': session_val,
      }

      if hasattr(Result, 'grade_point'):
        result_kwargs['grade_point'] = gp_val

      new_result = Result(**result_kwargs)

      db.session.add(new_result)
      db.session.commit()
      flash('Grade posted to student profile successfully!', 'success')
    except Exception as e:
      db.session.rollback()
      clean_error = (
          str(e).split('(Background on this error')[0].split('[SQL:')[0].strip()
      )
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


# --- HELPER: AUDIT LOGGING ---
def log_action(action, details=None):
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_id = current_user.id if current_user.is_authenticated else None
    log_entry = AuditLog(user_id=user_id, action=action, details=details, ip_address=ip)
    db.session.add(log_entry)
    db.session.commit()

# --- BULK CSV IMPORT FOR STUDENTS ---
@app.route('/admin/import/students', methods=['POST'])
@login_required
def import_students_csv():
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('admin_dashboard'))

    file = request.files.get('file')
    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid CSV file.', 'danger')
        return redirect(url_for('admin_dashboard'))

    stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
    csv_reader = csv.DictReader(stream)

    count = 0
    for row in csv_reader:
        full_name = row.get('full_name')
        email = row.get('email')
        reg_number = row.get('reg_number')

        if email and not User.query.filter_by(email=email).first():
            student = User(
                full_name=full_name,
                email=email,
                reg_number=reg_number,
                role='student',
                is_approved=True
            )
            student.set_password('DefaultPassword123!')
            db.session.add(student)
            count += 1

    db.session.commit()
    log_action('BULK_STUDENT_IMPORT', f'Imported {count} students via CSV')
    flash(f'Successfully imported {count} students!', 'success')
    return redirect(url_for('admin_dashboard'))

# --- EXPORT DATA TO CSV ROUTE ---
@app.route('/admin/export/<data_type>')
@login_required
def export_csv(data_type):
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('admin_dashboard'))

    output = io.StringIO()
    writer = csv.writer(output)

    if data_type == 'students':
        writer.writerow(['ID', 'Full Name', 'Email', 'Reg Number', 'Payment Status', 'Account Status'])
        students = User.query.filter_by(role='student').all()
        for s in students:
            writer.writerow([s.id, s.full_name, s.email, s.reg_number, s.payment_status, s.status])
        filename = "students_export.csv"

    elif data_type == 'results':
        writer.writerow(['Student ID', 'Course Code', 'Course Title', 'Score', 'Grade', 'Semester', 'Level'])
        results = Result.query.all()
        for r in results:
            writer.writerow([r.student_id, r.course_code, r.course_name, r.score, r.grade, r.semester, r.level])
        filename = "results_export.csv"

    else:
        flash('Invalid export entity', 'danger')
        return redirect(url_for('admin_dashboard'))

    log_action('DATA_EXPORT', f'Exported {data_type} to CSV')

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
            )


@app.route('/admin/send_to_registrar', methods=['POST'])
@login_required
def send_to_registrar():
  if current_user.role != 'admin':
    return redirect(url_for('login'))

  registrar = User.query.filter_by(role='registrar').first()
  if not registrar:
    flash('No Registrar account found in database.', 'danger')
    return redirect(url_for('admin_dashboard'))

  total_students = User.query.filter_by(
      role='student', is_approved=True
  ).count()
  total_lecturers = User.query.filter_by(
      role='lecturer', is_approved=True
  ).count()
  total_courses = Course.query.count()
  total_results = Result.query.count()

  summary_report = (
      ' OFFICIAL SCHOOL DATA TRANSFER FROM ADMIN\n'
      '----------------------------------------\n'
      f'• Total Approved Lecturers: {total_lecturers}\n'
      f'• Total Approved Students: {total_students}\n'
      f'• Total Active Courses: {total_courses}\n'
      f'• Total Results Logged: {total_results}\n'
      'Status: ALL ADMIN WORK COMPLETED & VERIFIED.'
  )

  msg = Message(
      sender_id=current_user.id,
      receiver_id=registrar.id,
      content=summary_report,
  )
  db.session.add(msg)
  db.session.commit()

  flash(
      'Complete school data report successfully transmitted to the Registrar!',
      'success',
  )
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
        flash(
            'Master access granted! Switched to'
            f' {target_role.capitalize()} view.',
            'success',
        )
        role_routes = {
            'admin': 'admin_dashboard',
            'creator': 'creator_dashboard',
            'registrar': 'registrar_dashboard',
            'lecturer': 'lecturer_dashboard',
            'student': 'student_dashboard',
        }
        return redirect(url_for(role_routes.get(target_role, 'login')))
      else:
        flash(
            f'No user account exists yet for role: {target_role}', 'warning'
        )
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
        f'RESULT SUBMISSION FROM LECTURER ({current_user.full_name}):\n- Student'
        f' Name: {student_name}\n- Reg Number/Email: {reg_number}\n- Course:'
        f' {course_name}\n- Score: {score}'
    )
    msg = Message(
        sender_id=current_user.id, receiver_id=admin.id, content=result_payload
    )
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
        content=content,
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
  return send_from_directory(
      app.config['UPLOAD_FOLDER'], filename, as_attachment=True
  )


@app.route('/circuit_analyzer')
def circuit_analyzer():
    try:
        return render_template('circuit_analyzer.html')
    except Exception as e:
        return f"<h3>Circuit Analyzer Route Ready</h3><p>Template error: {str(e)}</p>"


# --- ADMIN ROUTE: ASSIGN / UPDATE REGISTRATION NUMBER ---
@app.route('/admin/assign_reg_number/<int:student_id>', methods=['POST'])
@login_required
def assign_reg_number(student_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
    
    new_reg_no = request.form.get('reg_number', '').strip()
    student = db.session.get(User, student_id)
    
    if student and student.role == 'student':
        student.reg_number = new_reg_no
        
        # Optionally sync existing orphaned results to this student
        Result.query.filter(Result.reg_number.ilike(new_reg_no)).update(
            {Result.student_id: student.id}, synchronize_session=False
        )
        
        db.session.commit()
        flash(f'Registration number for {student.full_name} updated to: {new_reg_no}', 'success')
    else:
        flash('Student record not found.', 'warning')
        
    return redirect(url_for('admin_dashboard'))


# --- MANUAL DATABASE SCHEMA FIX ROUTE ---
@app.route('/fix_results_db')
def fix_results_db():
  try:
    student = User.query.filter(
        User.username.ilike('%sulemanexpert2000@gmail.com%')
    ).first()
    if not student:
      return 'Student account not found in database.'

    updated_count = Result.query.filter(
        or_(
            Result.reg_number.ilike(student.username),
            Result.reg_number.ilike(student.email),
        )
    ).update({Result.student_id: student.id}, synchronize_session=False)

    db.session.commit()
    return (
        f'SUCCESS! Linked {updated_count} result record(s) to Student ID:'
        f' {student.id} ({student.username}).'
    )
  except Exception as e:
    db.session.rollback()
    return f'Database Error: {str(e)}'


if __name__ == '__main__':
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port=port)
