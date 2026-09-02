from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # admin, creator, registrar, lecturer, student
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    is_approved = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='active')  # active, suspended
    profile_picture = db.Column(db.String(255), nullable=True)

    # Student-specific fields
    reg_number = db.Column(db.String(100), unique=True, nullable=True)
    level = db.Column(db.String(20), default='ND1')
    dob = db.Column(db.String(20))
    primary_school = db.Column(db.String(255))
    primary_cert = db.Column(db.String(255))
    sec_school = db.Column(db.String(255))
    sec_cert = db.Column(db.String(255))
    program = db.Column(db.String(255))
    payment_status = db.Column(db.String(20), default='Unpaid')
    remita_invoice = db.Column(db.String(100))
    admission_status = db.Column(db.String(50), default='Admitted')

    # Lecturer-specific fields
    desired_courses = db.Column(db.Text)
    department = db.Column(db.String(150), nullable=True)

    # Relationships
    materials = db.relationship('Material', backref='lecturer', lazy=True, cascade="all, delete-orphan")
    registered_courses = db.relationship('Course', backref='enrolled_student', lazy=True, foreign_keys='Course.student_id')
    assigned_courses = db.relationship('Course', backref='assigned_lecturer', lazy=True, foreign_keys='Course.lecturer_id')
    results = db.relationship('Result', backref='student', lazy=True, cascade="all, delete-orphan")


class Material(db.Model):
    __tablename__ = 'material'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    material_type = db.Column(db.String(50), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    lecturer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class Message(db.Model):
    __tablename__ = 'message'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=True)
    msg_type = db.Column(db.String(20), default='text')
    file_path = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')


class Course(db.Model):
    __tablename__ = 'course'

    id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(20), nullable=False)
    course_name = db.Column(db.String(150), nullable=False)
    unit = db.Column(db.Integer, default=3)
    semester = db.Column(db.String(20), default='1')
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class Result(db.Model):
    __tablename__ = 'result'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reg_number = db.Column(db.String(100), nullable=True)
    title = db.Column(db.String(200), nullable=True)
    course_name = db.Column(db.String(200), nullable=True)
    course_code = db.Column(db.String(100), nullable=True)
    score = db.Column(db.Float, nullable=True)
    grade = db.Column(db.String(10), nullable=False)
    grade_point = db.Column(db.Float, nullable=True)
    unit = db.Column(db.Integer, default=3)
    semester = db.Column(db.String(20), nullable=True)
    level = db.Column(db.String(20), nullable=True)
    session = db.Column(db.String(20), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
