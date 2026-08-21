from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

# SINGLE DATABASE INSTANCE
db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    __table_args__ = {'extend_existing': True}  # PREVENTS "Table 'user' is already defined" ERROR

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(150))
    email = db.Column(db.String(150))
    phone = db.Column(db.String(20))
    dob = db.Column(db.String(50))
    primary_school = db.Column(db.String(150))
    primary_cert = db.Column(db.String(255))
    sec_school = db.Column(db.String(150))
    sec_cert = db.Column(db.String(255))
    is_approved = db.Column(db.Boolean, default=False)
    admission_status = db.Column(db.String(50), default="Pending")
    desired_courses = db.Column(db.Text)
    remita_invoice = db.Column(db.String(100))
    payment_status = db.Column(db.String(20), default="Unpaid")

class Material(db.Model):
    __tablename__ = 'material'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    material_type = db.Column(db.String(50))
    file_path = db.Column(db.String(255))
    lecturer_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Message(db.Model):
    __tablename__ = 'message'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text, nullable=False)
    msg_type = db.Column(db.String(20), default='text')
    file_path = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Course(db.Model):
    __tablename__ = 'course'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    course_name = db.Column(db.String(150), nullable=False)
    course_code = db.Column(db.String(50))

class Result(db.Model):
    __tablename__ = 'result'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    course_name = db.Column(db.String(150))
    score = db.Column(db.String(10))
    grade = db.Column(db.String(5))
