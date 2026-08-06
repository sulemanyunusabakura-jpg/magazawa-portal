Ioimport os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Material, Message

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'magazawa_skills_technology_secret')

# DATABASE URI CONFIGURATION FOR RENDER
db_url = os.environ.get('DATABASE_URL', 'sqlite:///magazawa_portal.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    # FIXED: Replaced deprecated query.get() with db.session.get()
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

@app.route('/')
def home():
    return redirect(url_for('login'))

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
        
        p_filename = secure_filename(p_cert.filename) if p_cert else ""
        s_filename = secure_filename(s_cert.filename) if s_cert else ""
        
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
    users = User.query.filter(User.id != current_user.id).all()
    messages = Message.query.filter_by(receiver_id=current_user.id).all()
    return render_template('admin_dashboard.html', students=students, lecturers=lecturers, users=users, messages=messages)

@app.route('/admin/approve_student/<int:id>')
@login_required
def approve_student(id):
    if current_user.role != 'admin': 
        return redirect(url_for('login'))
    # FIXED: Updated deprecated query.get() to db.session.get()
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
    # FIXED: Updated deprecated query.get() to db.session.get()
    lecturer = db.session.get(User, id)
    if lecturer:
        lecturer.is_approved = True
        db.session.commit()
        flash(f'Lecturer {lecturer.full_name} approved successfully.', 'success')
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
    messages = Message.query.filter_by(receiver_id=current_user.id).all()
    return render_template('lecturer_dashboard.html', materials=materials, users=users, messages=messages)

@app.route('/dashboard/student')
@login_required
def student_dashboard():
    if current_user.role != 'student': 
        return redirect(url_for('login'))
    materials = Material.query.all()
    users = User.query.filter(User.id != current_user.id).all()
    messages = Message.query.filter_by(receiver_id=current_user.id).all()
    return render_template('student_dashboard.html', student=current_user, materials=materials, users=users, messages=messages)

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    receiver_id = request.form['receiver_id']
    content = request.form['content']
    msg = Message(sender_id=current_user.id, receiver_id=receiver_id, content=content)
    db.session.add(msg)
    db.session.commit()
    flash('Message sent successfully!', 'success')
    return redirect(request.referrer or url_for('login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
# Route 1: Direct Messaging
@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    receiver_id = request.form.get('receiver_id')
    content = request.form.get('content')
    msg = Message(sender_id=current_user.id, receiver_id=receiver_id, content=content)
    db.session.add(msg)
    db.session.commit()
    flash('Message sent successfully!', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))

# Route 2: Course Management
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

# Route 3: Result Upload Management
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
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
