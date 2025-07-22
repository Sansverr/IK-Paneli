# app/database.py

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

db = SQLAlchemy()

user_personnel_link = db.Table('user_personnel_link',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('personnel_id', db.Integer, db.ForeignKey('personnel.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(50), nullable=False, default='user')
    personnel = db.relationship('Personnel', secondary=user_personnel_link, back_populates='users')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Personnel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
    # --- YENİ: Orijinal mantığı korumak için TC Kimlik No sütunu eklendi ---
    tc_kimlik_no = db.Column(db.String(11), unique=True, nullable=False)
    position = db.Column(db.String(100))
    department = db.Column(db.String(100))
    start_date = db.Column(db.Date)
    phone_number = db.Column(db.String(20))
    address = db.Column(db.String(200))
    email = db.Column(db.String(120), unique=True)

    users = db.relationship('User', secondary=user_personnel_link, back_populates='personnel')
    leave_requests = db.relationship('LeaveRequest', backref='personnel', lazy=True)
    performance_reviews = db.relationship('PerformanceReview', backref='personel', lazy=True)

# Diğer modeller (LeaveRequest, PasswordResetRequest vb.) değişmeden kalır...
class LeaveRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    personnel_id = db.Column(db.Integer, db.ForeignKey('personnel.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Beklemede')

class PasswordResetRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    new_password = db.Column(db.String(256), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    user = db.relationship('User')

class PerformancePeriod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reviews = db.relationship('PerformanceReview', backref='period', lazy='dynamic')

class PerformanceReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey('performance_period.id'), nullable=False)
    personnel_id = db.Column(db.Integer, db.ForeignKey('personnel.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    comments = db.Column(db.Text, nullable=True)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    personnel_id = db.Column(db.Integer, db.ForeignKey('personnel.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    personnel = db.relationship('Personnel', backref=db.backref('documents', lazy=True))
