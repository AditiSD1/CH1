import os
import io
import uuid
import datetime
import re
import json
import base64
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer,HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
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

# Helper for parsing scheduled test window
def parse_test_window(scheduled):
    if not scheduled:
        now = datetime.datetime.now()
        start_dt = now
        end_dt = now + datetime.timedelta(minutes=30)
        return {
            'start_dt': start_dt,
            'end_dt': end_dt,
            'start_str': start_dt.strftime('%d %b %Y, %I:%M %p'),
            'end_str': end_dt.strftime('%d %b %Y, %I:%M %p'),
            'start_time_only': start_dt.strftime('%I:%M %p'),
            'end_time_only': end_dt.strftime('%I:%M %p'),
            'status': 'ACTIVE',
            'remaining_start_sec': 0,
            'remaining_end_sec': 1800
        }

    t_date = scheduled.test_date or datetime.datetime.now().strftime('%Y-%m-%d')
    t_time = scheduled.test_time or '10:00 AM'
    duration = scheduled.duration_mins or 30

    time_str = f"{t_date} {t_time}".strip()
    start_dt = None
    
    formats = [
        "%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %I:%M%p", "%d-%m-%Y %H:%M", "%Y/%m/%d %H:%M"
    ]
    for fmt in formats:
        try:
            start_dt = datetime.datetime.strptime(time_str, fmt)
            break
        except ValueError:
            pass

    if not start_dt:
        try:
            d_parts = [int(x) for x in t_date.split('-')]
            clean_time = t_time.upper().replace('AM','').replace('PM','').strip()
            t_parts = [int(x) for x in clean_time.split(':')]
            hour = t_parts[0]
            if 'PM' in t_time.upper() and hour < 12:
                hour += 12
            start_dt = datetime.datetime(d_parts[0], d_parts[1], d_parts[2], hour, t_parts[1])
        except Exception:
            start_dt = datetime.datetime.now()

    end_dt = start_dt + datetime.timedelta(minutes=duration)
    now = datetime.datetime.now()

    if now < start_dt:
        status = 'UPCOMING'
        rem_start = int((start_dt - now).total_seconds())
        rem_end = 0
    elif start_dt <= now <= end_dt:
        status = 'ACTIVE'
        rem_start = 0
        rem_end = int((end_dt - now).total_seconds())
    else:
        status = 'ENDED'
        rem_start = 0
        rem_end = 0

    return {
        'start_dt': start_dt,
        'end_dt': end_dt,
        'start_str': start_dt.strftime('%d %b %Y, %I:%M %p'),
        'end_str': end_dt.strftime('%d %b %Y, %I:%M %p'),
        'start_time_only': start_dt.strftime('%I:%M %p'),
        'end_time_only': end_dt.strftime('%I:%M %p'),
        'status': status,
        'remaining_start_sec': max(0, rem_start),
        'remaining_end_sec': max(0, rem_end)
    }

def generate_qr_code(text):
    if not QRCODE_AVAILABLE:
        return ""
    try:
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#22d3ee", back_color="#0a0e17")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"QR Code Error: {e}")
        return ""

def process_pdf_material(filepath, filename):
    extracted_text = ""
    page_count = 0
    topics = []

    if PYPDF_AVAILABLE and filename.lower().endswith('.pdf'):
        try:
            reader = PdfReader(filepath)
            page_count = len(reader.pages)
            for page in reader.pages[:15]:
                text = page.extract_text() or ""
                extracted_text += text + " "
        except Exception as e:
            print(f"pypdf extraction error: {e}")

    if not extracted_text:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                extracted_text = f.read(5000)
        except Exception:
            extracted_text = filename.replace('_', ' ').replace('-', ' ')

    # Extract keywords/topics
    words = re.findall(r'\b[A-Za-z]{4,}\b', extracted_text)
    stopwords = {'this', 'that', 'with', 'from', 'have', 'were', 'which', 'their', 'about', 'there', 'would', 'could', 'should', 'page'}
    filtered = [w.title() for w in words if w.lower() not in stopwords]

    term_counts = {}
    for word in filtered:
        term_counts[word] = term_counts.get(word, 0) + 1
    
    sorted_topics = sorted(term_counts.items(), key=lambda x: x[1], reverse=True)
    topics = [item[0] for item in sorted_topics[:5]]

    if not topics:
        topics = ['Core Concepts', 'Chapter Analysis', 'Key Principles']

    return extracted_text.strip(), page_count, topics

def call_gemini_api(prompt, api_key=None):
    """
    Direct Integration with Google Gemini API (gemini-1.5-flash)
    Generates content using Gemini REST API.
    """
    key = api_key or os.environ.get('GEMINI_API_KEY', '')
    if not key or len(key.strip()) < 5:
        return None

    try:
        import urllib.request
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={key.strip()}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            text_content = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_content)
    except Exception as e:
        print(f"Gemini API Call Error: {e}")
        return None

def generate_ai_question_paper(materials, difficulty='Medium'):
    all_topics = []
    source_text = ""
    for m in materials:
        all_topics.extend(m.topics)
        if m.extracted_text:
            source_text += m.extracted_text[:2000] + " "

    # 1. Attempt live Google Gemini API call if GEMINI_API_KEY environment variable or key is configured
    gemini_prompt = f"""
You are an expert educational assessment creator.
Based on the following extracted course material text and topics:
Topics: {json.dumps(all_topics)}
Excerpt: {source_text[:1500]}
Difficulty Level: {difficulty}

Generate a JSON object with 3 Multiple Choice Questions (5 marks each) and 2 Descriptive Questions (15 and 20 marks).
Return JSON matching this exact structure:
[
  {{
    "id": "q1",
    "type": "mcq",
    "question": "Question text?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "answer": "Option A",
    "explanation": "Explanation text",
    "marks": 5
  }},
  {{
    "id": "q4",
    "type": "descriptive",
    "question": "Descriptive question?",
    "model_answer": "Model solution text",
    "keywords": ["keyword1", "keyword2"],
    "marks": 15
  }}
]
"""
    gemini_result = call_gemini_api(gemini_prompt)
    if gemini_result and isinstance(gemini_result, list) and len(gemini_result) > 0:
        print("Successfully generated question paper using Google Gemini API!")
        return gemini_result

    # 2. Intelligent Topic-Based Fallback Generator if no Gemini key is set
    top1 = all_topics[0] if len(all_topics) > 0 else 'Core Concept'
    top2 = all_topics[1] if len(all_topics) > 1 else 'System Principles'
    top3 = all_topics[2] if len(all_topics) > 2 else 'Performance Analysis'

    questions = [
        {
            'id': 'q1',
            'type': 'mcq',
            'question': f"What is the primary objective when evaluating '{top1}' in the study material?",
            'options': [
                f"To systematically analyze {top1} principles",
                'To increase processing latency',
                'To bypass input validation protocols',
                'To reduce memory allocation limits'
            ],
            'answer': f"To systematically analyze {top1} principles",
            'explanation': f'Extracted directly from study notes on {top1}.',
            'marks': 5
        },
        {
            'id': 'q2',
            'type': 'mcq',
            'question': f"Which core methodology is emphasized for '{top2}'?",
            'options': [
                'Iterative Optimization Protocol',
                'Static Record Keeping',
                'Unsupervised Fallback Routine',
                'Manual Batch Deletion'
            ],
            'answer': 'Iterative Optimization Protocol',
            'explanation': f'Primary methodology identified for {top2}.',
            'marks': 5
        },
        {
            'id': 'q3',
            'type': 'mcq',
            'question': f"What is the expected outcome when applying guidelines for '{top3}'?",
            'options': [
                'Minimizing operational error rates',
                'Doubling runtime execution time',
                'Deleting log history',
                'Disabling security tokens'
            ],
            'answer': 'Minimizing operational error rates',
            'explanation': 'Key performance metric highlighted in course notes.',
            'marks': 5
        },
        {
            'id': 'q4',
            'type': 'descriptive',
            'question': f"Explain how {top1} and {top2} interact within the context of the course material.",
            'model_answer': f"The study material details how {top1} establishes foundational framework rules, while {top2} applies these rules to optimize operational throughput.",
            'keywords': [top1.lower(), top2.lower(), 'analysis', 'concept', 'evaluation'],
            'marks': 15
        },
        {
            'id': 'q5',
            'type': 'descriptive',
            'question': f"Provide a comprehensive overview of key takeaways regarding {top3}.",
            'model_answer': f"The study material provides structured guidance on {top3}, emphasizing systematic evaluation, performance optimization, and robust error control.",
            'keywords': [top3.lower(), 'principles', 'guidance', 'performance', 'evaluation'],
            'marks': 20
        }
    ]

    return questions

def create_pdf_question_paper(paper):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, textColor=colors.HexColor('#1e1b4b'), alignment=1, spaceAfter=6)
    sub_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontName='Helvetica', fontSize=10, textColor=colors.HexColor('#475569'), alignment=1, spaceAfter=12)
    section_style = ParagraphStyle('DocSec', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#4338ca'), spaceBefore=10, spaceAfter=6)
    question_style = ParagraphStyle('DocQ', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#0f172a'), spaceBefore=6, spaceAfter=4)
    body_style = ParagraphStyle('DocBody', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#334155'), spaceAfter=4)

    story.append(Paragraph(paper.title, title_style))
    story.append(Paragraph(f"Subject: {paper.subject} | Total Marks: {paper.total_marks} | Duration: {paper.duration_mins} Mins", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=12))

    story.append(Paragraph("Section A: Multiple Choice Questions", section_style))
    q_num = 1
    for q in paper.questions:
        if q['type'] == 'mcq':
            story.append(Paragraph(f"Q{q_num}. {q['question']} [{q['marks']} Marks]", question_style))
            for idx, opt in enumerate(q['options'], 1):
                story.append(Paragraph(f"   ({chr(64+idx)}) {opt}", body_style))
            story.append(Spacer(1, 4))
            q_num += 1

    story.append(Spacer(1, 8))
    story.append(Paragraph("Section B: Descriptive Questions", section_style))
    for q in paper.questions:
        if q['type'] == 'descriptive':
            story.append(Paragraph(f"Q{q_num}. {q['question']} [{q['marks']} Marks]", question_style))
            story.append(Paragraph("   Answer: ______________________________________________________________________", body_style))
            story.append(Paragraph("   ______________________________________________________________________________", body_style))
            story.append(Spacer(1, 6))
            q_num += 1

    doc.build(story)
    buffer.seek(0)
    return buffer

# ==============================================================================
# ROUTES
# ==============================================================================

@app.route('/')
def index():
    if session.get('role') == 'teacher':
        return redirect(url_for('upload_materials'))
    elif session.get('role') == 'student':
        return redirect(url_for('student_test'))
    return redirect(url_for('teacher_login'))

# -----------------------------------------------
# PAGE 1: TEACHER LOGIN & SIGN UP
# -----------------------------------------------
@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(email=email, role='teacher').first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = 'teacher'
            session['user_name'] = user.name
            session['user_email'] = user.email
            session['department'] = user.department or 'General'
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('upload_materials'))
        else:
            flash('Invalid educator credentials. Please check email/password or Sign Up.', 'error')

    return render_template('teacher_login.html')

@app.route('/teacher/register', methods=['POST'])
def teacher_register():
    name = request.form.get('name', '').strip()
    department = request.form.get('department', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()

    if not name or not email or not password:
        flash('Please complete all fields to sign up.', 'error')
        return redirect(url_for('teacher_login'))

    existing = User.query.filter_by(email=email).first()
    if existing:
        flash('An account with this email already exists. Please log in.', 'error')
        return redirect(url_for('teacher_login'))

    new_user = User(
        name=name,
        department=department,
        email=email,
        password_hash=generate_password_hash(password),
        role='teacher'
    )
    db.session.add(new_user)
    db.session.commit()

    session['user_id'] = new_user.id
    session['role'] = 'teacher'
    session['user_name'] = name
    session['user_email'] = email
    session['department'] = department

    flash('Educator Account registered successfully!', 'success')
    return redirect(url_for('upload_materials'))

# ----------------------------------------------
# PAGE 2: UPLOAD & MANAGE STUDY MATERIALS (PYPDF)
# -----------------------------------------------
@app.route('/teacher/upload', methods=['GET', 'POST'])
def upload_materials():
    if session.get('role') != 'teacher':
        flash('Please log in as an educator to access this page.', 'error')
        return redirect(url_for('teacher_login'))

    user_id = session.get('user_id')

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected.', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            extracted_text, page_count, topics = process_pdf_material(filepath, filename)

            ext = filename.rsplit('.', 1)[1].upper()
            size_mb = round(os.path.getsize(filepath) / (1024 * 1024), 2)
            file_size_str = f"{size_mb if size_mb > 0 else '0.3'} MB"

            new_mat = Material(
                user_id=user_id,
                filename=filename,
                file_type=f"{ext} Document",
                file_size=file_size_str,
                page_count=page_count,
                topics_json=json.dumps(topics),
                extracted_text=extracted_text[:3000],
                uploaded_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            )
            db.session.add(new_mat)
            db.session.commit()

            flash(f'Study material "{filename}" uploaded and parsed successfully!', 'success')
            return redirect(url_for('upload_materials'))

    materials = Material.query.filter_by(user_id=user_id).order_by(Material.uploaded_at.desc()).all()
    # Also include unassigned if any
    if not materials:
        materials = Material.query.order_by(Material.uploaded_at.desc()).all()

    formatted_materials = [
        {
            'id': m.id,
            'name': m.filename,
            'size': m.file_size,
            'uploaded_at': m.uploaded_at,
            'type': m.file_type,
            'page_count': m.page_count,
            'topics': m.topics
        } for m in materials
    ]

    return render_template('upload_materials.html', materials=formatted_materials)

@app.route('/teacher/material/delete/<mat_id>', methods=['POST'])
def delete_material(mat_id):
    if session.get('role') != 'teacher':
        return redirect(url_for('teacher_login'))
    
    mat = Material.query.get(mat_id)
    if mat:
        db.session.delete(mat)
        db.session.commit()
        flash('Study material removed from database.', 'info')
    return redirect(url_for('upload_materials'))

@app.route('/teacher/generate-paper', methods=['POST'])
def generate_paper():
    if session.get('role') != 'teacher':
        return redirect(url_for('teacher_login'))

    user_id = session.get('user_id')
    materials = Material.query.filter_by(user_id=user_id).all()
    if not materials:
        materials = Material.query.all()

    if not materials:
        flash('Please upload at least one study material file before generating a paper.', 'error')
        return redirect(url_for('upload_materials'))

    difficulty = request.form.get('difficulty', 'Medium')
    source_mat = materials[0]

    questions = generate_ai_question_paper(materials, difficulty)

    paper = QuestionPaper(
        user_id=user_id or source_mat.user_id,
        title=f"Assessment: {source_mat.filename.rsplit('.', 1)[0].replace('_', ' ').title()}",
        subject=session.get('department', 'Educational Assessment'),
        difficulty=difficulty,
        total_marks=50,
        duration_mins=30,
        questions_json=json.dumps(questions),
        created_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    )
    db.session.add(paper)
    db.session.commit()

    # Also create default ScheduledTest if none exists
    scheduled = ScheduledTest.query.filter_by(teacher_id=paper.user_id).first()
    if not scheduled:
        scheduled = ScheduledTest(
            teacher_id=paper.user_id,
            paper_id=paper.id,
            test_title=paper.title,
            test_date=datetime.datetime.now().strftime('%Y-%m-%d'),
            test_time='10:00 AM',
            duration_mins=30,
            passcode='AI-2026'
        )
        db.session.add(scheduled)
    else:
        scheduled.paper_id = paper.id
        scheduled.test_title = paper.title

    db.session.commit()

    flash(f'Question Paper generated successfully!', 'success')
    return redirect(url_for('question_paper'))

# ----------------------------------------------------------
# PAGE 3: GENERATED QUESTION PAPER, TEST SCHEDULER & QR CODE
# ----------------------------------------------------------
@app.route('/teacher/question-paper')
def question_paper():
    if session.get('role') != 'teacher':
        flash('Please log in as an educator to access this page.', 'error')
        return redirect(url_for('teacher_login'))

    user_id = session.get('user_id')
    paper = QuestionPaper.query.filter_by(user_id=user_id).order_by(QuestionPaper.created_at.desc()).first()
    if not paper:
        paper = QuestionPaper.query.order_by(QuestionPaper.created_at.desc()).first()

    scheduled = ScheduledTest.query.filter_by(teacher_id=user_id).first() if paper else None
    if not scheduled:
        scheduled = ScheduledTest.query.first()

    window_info = parse_test_window(scheduled)

    if not scheduled:
        test_data = {
            'title': paper.title if paper else 'AI Assessment Test',
            'date': datetime.datetime.now().strftime('%Y-%m-%d'),
            'time': '10:00 AM',
            'duration_mins': 30,
            'passcode': 'AI-2026'
        }
    else:
        test_data = {
            'title': scheduled.test_title,
            'date': scheduled.test_date,
            'time': scheduled.test_time,
            'duration_mins': scheduled.duration_mins,
            'passcode': scheduled.passcode
        }

    student_test_url = request.host_url + 'student/login?code=' + test_data['passcode']
    qr_code_url = generate_qr_code(student_test_url)

    paper_dict = None
    if paper:
        paper_dict = {
            'id': paper.id,
            'title': paper.title,
            'subject': paper.subject,
            'difficulty': paper.difficulty,
            'total_marks': paper.total_marks,
            'duration_mins': paper.duration_mins,
            'created_at': paper.created_at,
            'questions': paper.questions
        }

    return render_template(
        'question_paper.html',
        paper=paper_dict,
        test=test_data,
        test_url=student_test_url,
        qr_code_url=qr_code_url,
        window_info=window_info
    )

@app.route('/teacher/download-pdf-paper')
def download_pdf_paper():
    if session.get('role') != 'teacher':
        return redirect(url_for('teacher_login'))

    user_id = session.get('user_id')
    paper = QuestionPaper.query.filter_by(user_id=user_id).order_by(QuestionPaper.created_at.desc()).first()
    if not paper:
        paper = QuestionPaper.query.order_by(QuestionPaper.created_at.desc()).first()

    if not paper:
        flash('No generated paper available to download.', 'error')
        return redirect(url_for('question_paper'))

    if REPORTLAB_AVAILABLE:
        pdf_buffer = create_pdf_question_paper(paper)
        filename = f"Question_Paper_{paper.title.replace(' ', '_')}.pdf"
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
    else:
        flash('ReportLab library is not installed.', 'error')
        return redirect(url_for('question_paper'))

@app.route('/teacher/schedule-test', methods=['POST'])
def schedule_test():
    if session.get('role') != 'teacher':
        return redirect(url_for('teacher_login'))

    user_id = session.get('user_id')
    scheduled = ScheduledTest.query.filter_by(teacher_id=user_id).first()
    if not scheduled:
        scheduled = ScheduledTest(teacher_id=user_id)
        db.session.add(scheduled)

    scheduled.test_title = request.form.get('test_title', 'AI Assessment Test')
    scheduled.test_date = request.form.get('test_date', datetime.datetime.now().strftime('%Y-%m-%d'))
    scheduled.test_time = request.form.get('test_time', '10:00 AM')
    scheduled.duration_mins = int(request.form.get('duration_mins', 30))
    scheduled.passcode = request.form.get('passcode', 'AI-2026').strip().upper()

    db.session.commit()
    flash('Test schedule updated successfully! Student start & end window configured.', 'success')
    return redirect(url_for('question_paper'))

# ------------------------------------------------------------------------------
# PAGE 4: STUDENT LOGIN & SIGN UP
# ------------------------------------------------------------------------------
@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    code_param = request.args.get('code', '')

    scheduled = ScheduledTest.query.first()
    test_info = {
        'passcode': scheduled.passcode if scheduled else (code_param or 'AI-2026'),
        'title': scheduled.test_title if scheduled else 'AI Assessment Test',
        'date': scheduled.test_date if scheduled else datetime.datetime.now().strftime('%Y-%m-%d'),
        'time': scheduled.test_time if scheduled else '10:00 AM',
        'duration_mins': scheduled.duration_mins if scheduled else 30
    }

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        passcode = request.form.get('passcode', '').strip().upper()
        password = request.form.get('password', '').strip()

        if scheduled and scheduled.passcode and passcode != scheduled.passcode.strip().upper():
            flash('Invalid class access passcode. Please check passcode and try again.', 'error')
            return render_template('student_login.html', code_param=code_param, scheduled_test=test_info)

        user = User.query.filter_by(email=email, role='student').first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = 'student'
            session['student_email'] = email
            session['student_name'] = user.name
            session['student_roll'] = user.roll_no or 'STU-2026'
            session['test_passcode'] = passcode
            flash(f'Welcome, {user.name}! Accessing your test portal.', 'success')
            return redirect(url_for('student_test'))
        else:
            flash('Invalid student credentials. Please check details or Sign Up.', 'error')

    return render_template('student_login.html', code_param=code_param, scheduled_test=test_info)

@app.route('/student/register', methods=['POST'])
def student_register():
    name = request.form.get('name', '').strip()
    roll_no = request.form.get('roll_no', '').strip().upper()
    email = request.form.get('email', '').strip().lower()
    passcode = request.form.get('passcode', '').strip().upper()
    password = request.form.get('password', '').strip()

    if not name or not email or not password or not passcode:
        flash('Please complete all fields to sign up.', 'error')
        return redirect(url_for('student_login'))

    existing = User.query.filter_by(email=email).first()
    if existing:
        flash('An account with this email already exists. Please log in.', 'error')
        return redirect(url_for('student_login'))

    formatted_roll = roll_no if roll_no else f"STU-2026-{uuid.uuid4().hex[:4].upper()}"

    new_student = User(
        name=name,
        roll_no=formatted_roll,
        email=email,
        password_hash=generate_password_hash(password),
        role='student'
    )
    db.session.add(new_student)
    db.session.commit()

    session['user_id'] = new_student.id
    session['role'] = 'student'
    session['student_email'] = email
    session['student_name'] = name
    session['student_roll'] = formatted_roll
    session['test_passcode'] = passcode

    flash('Student account registered successfully! Ready for your test.', 'success')
    return redirect(url_for('student_test'))

# ------------------------------------------------------------------------------
# PAGE 5: STUDENT TEST & INSTANT RESULTS
# ------------------------------------------------------------------------------
@app.route('/student/test', methods=['GET', 'POST'])
def student_test():
    if session.get('role') != 'student':
        flash('Please log in as a student to access the test portal.', 'error')
        return redirect(url_for('student_login'))

    paper = QuestionPaper.query.order_by(QuestionPaper.created_at.desc()).first()
    scheduled = ScheduledTest.query.first()
    window_info = parse_test_window(scheduled)

    if not paper:
        return render_template('student_test.html', paper=None, attempt=None, submitted=False, window_info=window_info)

    paper_dict = {
        'id': paper.id,
        'title': paper.title,
        'subject': paper.subject,
        'total_marks': paper.total_marks,
        'duration_mins': paper.duration_mins,
        'questions': paper.questions
    }

    student_email = session.get('student_email')
    existing_attempt = StudentAttempt.query.filter_by(student_email=student_email, status='Attempted').first()

    attempt_dict = None
    if existing_attempt:
        attempt_dict = {
            'id': existing_attempt.id,
            'student_name': existing_attempt.student_name,
            'student_email': existing_attempt.student_email,
            'roll_no': existing_attempt.roll_no,
            'score': existing_attempt.score,
            'total_marks': existing_attempt.total_marks,
            'percentage': existing_attempt.percentage,
            'grade': existing_attempt.grade,
            'submitted_at': existing_attempt.submitted_at,
            'answers': existing_attempt.answers,
            'feedback': existing_attempt.feedback
        }

    if request.method == 'POST':
        # Verify test time window
        if window_info['status'] == 'UPCOMING':
            flash('Test has not started yet. Early submissions are not permitted.', 'error')
            return redirect(url_for('student_test'))

        if window_info['status'] == 'ENDED' and not existing_attempt:
            flash('Test time window has closed. Late submissions are not accepted.', 'error')
            return redirect(url_for('student_test'))

        score = 0
        total_possible = paper.total_marks
        user_answers = {}

        for q in paper.questions:
            q_id = q['id']
            user_val = request.form.get(f"q_{q_id}", '').strip()
            user_answers[q_id] = user_val

            if q['type'] == 'mcq':
                if user_val.lower() == q['answer'].lower():
                    score += q['marks']
            elif q['type'] == 'descriptive':
                match_count = 0
                for kw in q.get('keywords', []):
                    if kw.lower() in user_val.lower():
                        match_count += 1
                if match_count >= 2:
                    score += q['marks']
                elif match_count >= 1:
                    score += int(q['marks'] * 0.6)
                elif len(user_val) > 15:
                    score += int(q['marks'] * 0.4)

        percentage = round((score / total_possible) * 100, 1) if total_possible > 0 else 0
        grade = 'A+' if percentage >= 85 else 'A' if percentage >= 70 else 'B' if percentage >= 55 else 'C' if percentage >= 40 else 'F'
        feedback = f"Automated Evaluation Complete. Score: {score}/{total_possible} ({percentage}%)."

        if existing_attempt:
            existing_attempt.score = score
            existing_attempt.percentage = percentage
            existing_attempt.grade = grade
            existing_attempt.answers_json = json.dumps(user_answers)
            existing_attempt.submitted_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            existing_attempt.feedback = feedback
            db.session.commit()
            attempt_record = existing_attempt
        else:
            new_attempt = StudentAttempt(
                student_id=session.get('user_id'),
                student_name=session.get('student_name', 'Student'),
                student_email=student_email,
                roll_no=session.get('student_roll', 'STU-2026'),
                paper_id=paper.id,
                status='Attempted',
                score=score,
                total_marks=total_possible,
                percentage=percentage,
                grade=grade,
                submitted_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
                answers_json=json.dumps(user_answers),
                feedback=feedback
            )
            db.session.add(new_attempt)
            db.session.commit()
            attempt_record = new_attempt

        attempt_dict = {
            'id': attempt_record.id,
            'student_name': attempt_record.student_name,
            'student_email': attempt_record.student_email,
            'roll_no': attempt_record.roll_no,
            'score': attempt_record.score,
            'total_marks': attempt_record.total_marks,
            'percentage': attempt_record.percentage,
            'grade': attempt_record.grade,
            'submitted_at': attempt_record.submitted_at,
            'answers': attempt_record.answers,
            'feedback': attempt_record.feedback
        }

        flash('Test submitted successfully!', 'success')
        return render_template('student_test.html', paper=paper_dict, attempt=attempt_dict, submitted=True, window_info=window_info)

    return render_template('student_test.html', paper=paper_dict, attempt=attempt_dict, submitted=(attempt_dict is not None), window_info=window_info)

# ------------------------------------------------------------------------------
# PAGE 6: TEACHER ANALYTICS & STUDENT PROGRESS TRACKING
# ------------------------------------------------------------------------------
@app.route('/teacher/analytics')
def teacher_analytics():
    if session.get('role') != 'teacher':
        flash('Please log in as an educator to access analytics.', 'error')
        return redirect(url_for('teacher_login'))

    attempts = StudentAttempt.query.order_by(StudentAttempt.submitted_at.desc()).all()
    student_users = User.query.filter_by(role='student').all()

    total_students = len(student_users) if len(student_users) > len(attempts) else len(attempts)
    attempted_students = [a for a in attempts if a.status == 'Attempted']
    attempted_count = len(attempted_students)
    pending_count = max(0, total_students - attempted_count)

    avg_score = round(sum(a.percentage for a in attempted_students) / attempted_count, 1) if attempted_count > 0 else 0.0

    paper = QuestionPaper.query.order_by(QuestionPaper.created_at.desc()).first()
    paper_title = paper.title if paper else 'No Active Question Paper'

    formatted_attempts = [
        {
            'id': a.id,
            'student_name': a.student_name,
            'student_email': a.student_email,
            'roll_no': a.roll_no,
            'status': a.status,
            'score': a.score,
            'total_marks': a.total_marks,
            'percentage': a.percentage,
            'grade': a.grade,
            'submitted_at': a.submitted_at,
            'feedback': a.feedback
        } for a in attempts
    ]

    return render_template(
        'teacher_analytics.html',
        attempts=formatted_attempts,
        total_students=total_students,
        attempted_count=attempted_count,
        pending_count=pending_count,
        avg_score=avg_score,
        paper_title=paper_title
    )

# ------------------------------------------------------------------------------
# LOGOUT
# ------------------------------------------------------------------------------
@app.route('/logout')
def logout():
    role = session.get('role')
    session.clear()
    flash('Logged out successfully.', 'info')
    if role == 'student':
        return redirect(url_for('student_login'))
    return redirect(url_for('teacher_login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
