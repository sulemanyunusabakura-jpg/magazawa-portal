from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, creator, registrar, lecturer, student
    full_name = db.Column(db.String(150))
    email = db.Column(db.String(150))
    phone = db.Column(db.String(20))
    is_approved = db.Column(db.Boolean, default=False)
    
    # Student specific
    dob = db.Column(db.String(50))
    primary_school = db.Column(db.String(200))
    primary_cert = db.Column(db.String(255))
    sec_school = db.Column(db.String(200))
    sec_cert = db.Column(db.String(255))
    admission_status = db.Column(db.String(50), default="Pending")
    remita_invoice = db.Column(db.String(100))
    payment_status = db.Column(db.String(20), default="Unpaid")
    
    # Lecturer specific
    desired_courses = db.Column(db.String(255))

    # Relationships
    courses = db.relationship('Course', backref='student', lazy=True)
    results = db.relationship('Result', backref='student', lazy=True)
    materials = db.relationship('Material', backref='lecturer', lazy=True)

class Course(db.Model):
    __tablename__ = 'course'
    id = db.Column(db.Integer, primary_key=True)
    course_name = db.Column(db.String(100), nullable=False)
    course_code = db.Column(db.String(20))
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_code = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    unit = db.Column(db.Integer, nullable=False, default=1)
    semester = db.Column(db.String(10), nullable=False, default="1")
    grade = db.Column(db.String(5), nullable=False)  # A, AB, B, BC, C, CD, D, F
    level = db.Column(db.String(20), nullable=False, default="HND1")
    session = db.Column(db.String(20), nullable=False, default="2023/2024")

    @property
    def grade_point(self):
        points = {'A': 4.0, 'AB': 3.5, 'B': 3.0, 'BC': 2.5, 'C': 2.0, 'CD': 1.5, 'D': 1.0, 'F': 0.0}
        return points.get(self.grade.upper(), 0.0)

class Material(db.Model):
    __tablename__ = 'material'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    material_type = db.Column(db.String(50))
    file_path = db.Column(db.String(255))
    lecturer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    msg_type = db.Column(db.String(20), default='text')
    file_path = db.Column(db.String(255))

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')
