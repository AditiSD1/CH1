import os
import io
import uuid
import datetime
import json
import base64
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

try:
    from pypdf import pdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer,HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet
    REPORTLAB_AVAILABLE = True  
except ImportError:
    REPORTLAB_AVAILABLE = False
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'examify_super_secret_key_2026_production') 

db_path = os.path.join(app.root_path, 'examify.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'doc', 'docx', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'teacher' or 'student'
    department = db.Column(db.String(120), nullable=True) # For teachers
    roll_no = db.Column(db.String(60), nullable=True) # For students
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Material(db.Model):
    __tablename__ = 'materials'
    id = db.Column(db.String(36), primary_key=True, default=lambda: f"mat-{uuid.uuid4().hex[:6]}")
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    file_size = db.Column(db.String(30), nullable=False)
    page_count = db.Column(db.Integer, default=0)
    topics_json = db.Column(db.Text, nullable=False, default='[]')
    extracted_text = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(db.String(30), nullable=False)

    @property
    def topics(self):
        try:
            return json.loads(self.topics_json)
        except Exception:
            return []

class QuestionPaper(db.Model):
    __tablename__ = 'question_papers'
    id = db.Column(db.String(36), primary_key=True, default=lambda: f"paper-{uuid.uuid4().hex[:6]}")
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(120), nullable=False)
    difficulty = db.Column(db.String(30), nullable=False, default='Medium')
    total_marks = db.Column(db.Integer, default=50)
    duration_mins = db.Column(db.Integer, default=30)
    questions_json = db.Column(db.Text, nullable=False, default='[]')
    created_at = db.Column(db.String(30), nullable=False)

    @property
    def questions(self):
        try:
            return json.loads(self.questions_json)
        except Exception:
            return []

class ScheduledTest(db.Model):
    __tablename__ = 'scheduled_tests'
    id = db.Column(db.String(36), primary_key=True, default=lambda: f"test-{uuid.uuid4().hex[:6]}")
    teacher_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    paper_id = db.Column(db.String(36), db.ForeignKey('question_papers.id'), nullable=True)
    test_title = db.Column(db.String(255), nullable=False, default='AI Assessment Test')
    test_date = db.Column(db.String(30), nullable=False)
    test_time = db.Column(db.String(30), nullable=False)
    duration_mins = db.Column(db.Integer, default=30)
    passcode = db.Column(db.String(50), nullable=False, default='AI-2026')
    status = db.Column(db.String(30), default='Active')

class StudentAttempt(db.Model):
    __tablename__ = 'student_attempts'
    id = db.Column(db.String(36), primary_key=True, default=lambda: f"att-{uuid.uuid4().hex[:6]}")
    student_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    student_name = db.Column(db.String(120), nullable=False)
    student_email = db.Column(db.String(120), nullable=False)
    roll_no = db.Column(db.String(60), nullable=False)
    paper_id = db.Column(db.String(36), nullable=True)
    status = db.Column(db.String(30), default='Attempted')
    score = db.Column(db.Integer, default=0)
    total_marks = db.Column(db.Integer, default=50)
    percentage = db.Column(db.Float, default=0.0)
    grade = db.Column(db.String(10), default='N/A')
    submitted_at = db.Column(db.String(30), nullable=False)
    answers_json = db.Column(db.Text, default='{}')
    feedback = db.Column(db.Text, default='')

    @property
    def answers(self):
        try:
            return json.loads(self.answers_json)
        except Exception:
            return {}

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)