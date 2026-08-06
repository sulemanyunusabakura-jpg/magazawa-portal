from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    
    dob = db.Column(db.String(50), nullable=True)
    primary_school = db.Column(db.String(200), nullable=True)
    primary_cert = db.Column(db.String(250), nullable=True)
    sec_school = db.Column(db.String(200), nullable=True)
    sec_cert = db.Column(db.String(250), nullable=True)
    
    is_approved = db.Column(db.Boolean, default=False)
    admission_status = db.Column(db.String(50), default="Pending")
    remita_invoice = db.Column(db.String(100), nullable=True)

    desired_courses = db.Column(db.String(200), nullable=True)

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    material_type = db.Column(db.String(50), nullable=False)
    file_path = db.Column(db.String(300), nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_name = db.Column(db.String(100), nullable=False)
    course_code = db.Column(db.String(20), nullable=False)

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_name = db.Column(db.String(100), nullable=False)
    score = db.Column(db.Float, nullable=False)
    grade = db.Column(db.String(5), nullable=False)
