import os
from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Material, Message, Course, Result
from google import genai
from google.genai import types

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'magazawa_skills_technology_secret')

# DATABASE URI CONFIGURATION FOR RENDER
db_url = os.environ.get('DATABASE_URL', 'sqlite:///magazawa_portal.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ABSOLUTE PATH FOR UPLOAD DIRECTORY
app.config['UPLOAD_FOLDER'] = os.path.abspath(os.path.join(app.root_path, 'static', 'uploads'))
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# INITIALIZE GEMINI CLIENT
gemini_client = genai.Client()

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

with app.app_context():
    db.create_all()
    # Find existing admin or create a new one
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            role='admin',
            full_name='MST System Administrator',
            email='admin@magazawa.edu.ng',
            phone='08000000000',
            is_approved=True
        )
        db.session.add(admin)
        db.session.commit()
    else:
        # Guarantee admin password and approval are updated
        admin.password = generate_password_hash('admin123')
        admin.is_approved = True
        db.session.commit()

with app.app_context():
    db.create_all()
    
    # 1. ADMIN ACCOUNT
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            role='admin',
            full_name='MST System Administrator',
            email='admin@magazawa.edu.ng',
            phone='08000000000',
            is_approved=True
        )
        db.session.add(admin)

    # 2. CREATOR ACCOUNT
    creator = User.query.filter_by(role='creator').first()
    if not creator:
        creator = User(
            username='creator',
            password=generate_password_hash('creator123'),
            role='creator',
            full_name='System Creator',
            email='creator@magazawa.edu.ng',
            phone='08000000001',
            is_approved=True
        )
        db.session.add(creator)

    # 3. REGISTRAR ACCOUNT
    registrar = User.query.filter_by(role='registrar').first()
    if not registrar:
        registrar = User(
            username='registrar',
            password=generate_password_hash('registrar123'),
            role='registrar',
            full_name='MST Registrar Office',
            email='registrar@magazawa.edu.ng',
            phone='08000000002',
            is_approved=True
        )
        db.session.add(registrar)

    db.session.commit()
    
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
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            if not user.is_approved and user.role != 'admin':
                flash('Your account is pending approval by Magazawa Admin.', 'warning')
                return redirect(url_for('login'))

            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'lecturer':
                return redirect(url_for('lecturer_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid login credentials.', 'danger')
    return render_template('login.html')

@app.route('/apply/student', methods=['GET', 'POST'])
def apply_student():
    if request.method == 'POST':
        p_cert = request.files.get('primary_cert')
        s_cert = request.files.get('sec_cert')

        p_filename = secure_filename(p_cert.filename) if p_cert and p_cert.filename != "" else ""
        s_filename = secure_filename(s_cert.filename) if s_cert and s_cert.filename != "" else ""

        if p_cert and p_filename:
            p_cert.save(os.path.join(app.config['UPLOAD_FOLDER'], p_filename))
        if s_cert and s_filename:
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

@app.route('/dashboard/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin': 
        return redirect(url_for('login'))

    students = User.query.filter_by(role='student').all()
    lecturers = User.query.filter_by(role='lecturer').all()
    all_users = User.query.filter(User.id != current_user.id).all()
    messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()

    return render_template('admin_dashboard.html', 
                           students=students, 
                           lecturers=lecturers, 
                           all_users=all_users, 
                           messages=messages)

@app.route('/admin/ask_gemini', methods=['POST'])
@login_required
def ask_gemini():
    if current_user.role != 'admin':
        return {"error": "Unauthorized access"}, 403

    data = request.get_json()
    user_prompt = data.get('prompt', '').strip()

    if not user_prompt:
        return {"error": "Prompt cannot be empty"}, 400

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
        return {"response": response.text}

    except Exception as e:
        return {"error": f"Gemini API Error: {str(e)}"}, 500

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

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    receiver_id = request.form.get('receiver_id')
    content = request.form.get('content')
    if receiver_id and content:
        msg = Message(sender_id=current_user.id, receiver_id=receiver_id, content=content)
        db.session.add(msg)
        db.session.commit()
        flash('Message sent successfully!', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/manage_course', methods=['POST'])
@login_required
def manage_course():
    if current_user.role != 'admin':
        return redirect(url_for('login'))
    action = request.form.get('action')
    student_id = request.form.get('student_id')

    if action == 'add':
        course = Course(
            student_id=student_id, 
            course_name=request.form.get('course_name'), 
            course_code=request.form.get('course_code')
        )
        db.session.add(course)
    elif action == 'remove':
        course_id = request.form.get('course_id')
        Course.query.filter_by(id=course_id).delete()

    db.session.commit()
    flash('Course updated successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/manage_result', methods=['POST'])
@login_required
def manage_result():
    if current_user.role != 'admin':
        return redirect(url_for('login'))
    action = request.form.get('action')
    student_id = request.form.get('student_id')

    if action == 'add':
        res = Result(
            student_id=student_id, 
            course_name=request.form.get('course_name'), 
            score=request.form.get('score'), 
            grade=request.form.get('grade')
        )
        db.session.add(res)
    elif action == 'remove':
        result_id = request.form.get('result_id')
        Result.query.filter_by(id=result_id).delete()

    db.session.commit()
    flash('Result record updated successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/dashboard/lecturer', methods=['GET', 'POST'])
@login_required
def lecturer_dashboard():
    if current_user.role != 'lecturer': 
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        filename = ""
        if file and file.filename != "":
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        material = Material(
            title=request.form['title'],
            material_type=request.form['type'],
            file_path=filename,
            lecturer_id=current_user.id
        )
        db.session.add(material)
        db.session.commit()
        flash('Material / Voice Mail Uploaded Successfully.', 'success')
        return redirect(url_for('lecturer_dashboard'))

    materials = Material.query.filter_by(lecturer_id=current_user.id).all()
    users = User.query.filter(User.id != current_user.id).all()
    messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()
    
    return render_template(
        'lecturer_dashboard.html', 
        lecturer=current_user, 
        materials=materials, 
        users=users, 
        messages=messages
    )

@app.route('/dashboard/student')
@login_required
def student_dashboard():
    if current_user.role != 'student': 
        return redirect(url_for('login'))
    materials = Material.query.all()
    courses = Course.query.filter_by(student_id=current_user.id).all()
    results = Result.query.filter_by(student_id=current_user.id).all()
    users = User.query.filter(User.id != current_user.id).all()
    messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()
    return render_template('student_dashboard.html', student=current_user, materials=materials, courses=courses, results=results, users=users, messages=messages)

@app.route('/download_material/<path:filename>')
@login_required
def download_material(filename):
    clean_filename = os.path.basename(filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], clean_filename)

    if not os.path.exists(file_path):
        flash(f'File "{clean_filename}" was not found on the server directory.', 'danger')
        return redirect(url_for('student_dashboard'))

    return send_from_directory(app.config['UPLOAD_FOLDER'], clean_filename, as_attachment=True)

@app.route('/student/admission_letter')
@login_required
def admission_letter():
    if current_user.role != 'student':
        return redirect(url_for('login'))
    return render_template('admission_letter.html', student=current_user)

@app.route('/live_class/<room_name>')
@login_required
def live_class(room_name):
    return render_template('live_class.html', room_name=room_name, user=current_user)

@app.route('/lecturer/start_voice_class', methods=['POST'])
@login_required
def start_voice_class():
    if current_user.role != 'lecturer':
        flash('Unauthorized: Only lecturers can initiate voice calls.', 'danger')
        return redirect(url_for('login'))

    try:
        room_name = f"MST_Lecture_{current_user.id}"
        students = User.query.filter_by(role='student').all()
        for student in students:
            msg = Message(
                sender_id=current_user.id, 
                receiver_id=student.id, 
                content=f"LIVE LECTURE STARTED by {current_user.full_name}! Click the join button in your Messages section."
            )
            db.session.add(msg)

        db.session.commit()
        flash('Voice class started! All students have been notified.', 'success')
        return redirect(url_for('live_class', room_name=room_name))

    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while starting the call: {str(e)}', 'danger')
        return redirect(url_for('lecturer_dashboard'))

@app.route('/end_lecture/<int:lecturer_id>')
@login_required
def end_lecture(lecturer_id):
    if current_user.role != 'lecturer' or current_user.id != lecturer_id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('lecturer_dashboard'))

    students = User.query.filter_by(role='student').all()
    for student in students:
        msg = Message(
            sender_id=lecturer_id,
            receiver_id=student.id,
            content="LIVE LECTURE HAS ENDED. Thank you for participating."
        )
        db.session.add(msg)
    
    db.session.commit()
    flash('Lecture ended successfully.', 'info')
    return redirect(url_for('lecturer_dashboard'))

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
        flash('Result successfully transmitted to Admin dashboard!', 'success')
    return redirect(url_for('lecturer_dashboard'))
# --- REJECT STUDENT ---
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

# --- REJECT LECTURER ---
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

# --- TOGGLE PAYMENT STATUS ---
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
    # --- MASTER PASSWORD DIRECT LOGIN / SWITCHING ---
@app.route('/master_access', methods=['GET', 'POST'])
def master_access():
    if request.method == 'POST':
        master_pwd = request.form.get('master_password')
        target_role = request.form.get('target_role')
        
        # Verify master password
        if master_pwd == 'suleexpert':
            # Find any active user with that role or switch current user scope
            user = User.query.filter_by(role=target_role).first()
            if user:
                login_user(user)
                flash(f'Master access granted! Switched to {target_role.capitalize()} view.', 'success')
                if target_role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif target_role == 'creator':
                    return redirect(url_for('creator_dashboard'))
                elif target_role == 'registrar':
                    return redirect(url_for('registrar_dashboard'))
                elif target_role == 'lecturer':
                    return redirect(url_for('lecturer_dashboard'))
                elif target_role == 'student':
                    return redirect(url_for('student_dashboard'))
            else:
                flash(f'No user account exists yet for role: {target_role}', 'warning')
        else:
            flash('Invalid Master Password!', 'danger')
            
    return render_template('master_access.html')


# --- SEND ALL SCHOOL DATA TO REGISTRAR ---
@app.route('/admin/send_to_registrar', methods=['POST'])
@login_required
def send_to_registrar():
    if current_user.role != 'admin':
        return redirect(url_for('login'))

    registrar = User.query.filter_by(role='registrar').first()
    if not registrar:
        flash('No Registrar account found in database. Create one first.', 'danger')
        return redirect(url_for('admin_dashboard'))

    # Aggregate counts and stats
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


# --- CREATOR DASHBOARD ---
@app.route('/dashboard/creator')
@login_required
def creator_dashboard():
    total_students = User.query.filter_by(role='student').count()
    total_lecturers = User.query.filter_by(role='lecturer').count()
    total_admins = User.query.filter_by(role='admin').count()
    approved_students = User.query.filter_by(role='student', is_approved=True).count()
    approved_lecturers = User.query.filter_by(role='lecturer', is_approved=True).count()

    return render_template('creator_dashboard.html',
                           total_students=total_students,
                           total_lecturers=total_lecturers,
                           total_admins=total_admins,
                           approved_students=approved_students,
                           approved_lecturers=approved_lecturers)

# --- REGISTRAR DASHBOARD ---
@app.route('/dashboard/registrar')
@login_required
def registrar_dashboard():
    students = User.query.filter_by(role='student', is_approved=True).all()
    lecturers = User.query.filter_by(role='lecturer', is_approved=True).all()
    messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()

    return render_template('registrar_dashboard.html',
                           students=students,
                           lecturers=lecturers,
                           messages=messages)
    
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
