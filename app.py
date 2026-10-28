import os, datetime, functools, re, io, json
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, abort, send_from_directory, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import pdfplumber

BASE = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config["SECRET_KEY"] = "epetals-secret-key-2024"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE, "crm.db")

db = SQLAlchemy(app)

PROFIT_MARGIN = 0.40 
DEPTS = ["Speech", "BT", "OT", "Physiotherapy", "Special Ed"]
STATUSES = ["New", "Contacted", "Assessment Scheduled", "Assessment Completed",
            "Therapy Started", "Follow-up Required", "Converted", "Lost"]

# ================= SERVE LOGO =================
@app.route('/logo.png')
def serve_logo():
    return send_from_directory(BASE, 'logo.png')

# ================= MODELS =================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False)
    full_name = db.Column(db.String(120))
    department = db.Column(db.String(60))
    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class Child(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parent_name = db.Column(db.String(120))
    child_name = db.Column(db.String(120), nullable=False)
    dob = db.Column(db.String(30))
    contact = db.Column(db.String(40))
    primary_concern = db.Column(db.Text)
    required_dept = db.Column(db.String(60))
    source = db.Column(db.String(60))
    enquiry_date = db.Column(db.Date, default=datetime.date.today)
    status = db.Column(db.String(40), default="New")
    follow_up_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    parent_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    questionnaire_sent = db.Column(db.Boolean, default=False)
    questionnaire_submitted = db.Column(db.Boolean, default=False)
    questionnaire_answers = db.Column(db.Text)

class Assessment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"))
    therapist_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    department = db.Column(db.String(60))
    findings = db.Column(db.Text)
    concerns = db.Column(db.Text)
    strengths = db.Column(db.Text)
    recommendations = db.Column(db.Text)
    required_depts = db.Column(db.String(200))
    recommended_sessions = db.Column(db.Integer, default=0)
    additional_assessments = db.Column(db.Text)
    date = db.Column(db.Date, default=datetime.date.today)

class Referral(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"))
    from_dept = db.Column(db.String(60))
    to_dept = db.Column(db.String(60))
    notes = db.Column(db.Text)
    status = db.Column(db.String(30), default="Open")
    created = db.Column(db.Date, default=datetime.date.today)

class Discussion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"))
    notes = db.Column(db.Text)
    participants = db.Column(db.String(200))
    date = db.Column(db.Date, default=datetime.date.today)

class GoalSheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"))
    department = db.Column(db.String(60))
    goal = db.Column(db.Text)
    target_skill = db.Column(db.String(200))
    baseline = db.Column(db.String(200))
    expected_outcome = db.Column(db.String(200))
    measurement = db.Column(db.String(200))
    review_status = db.Column(db.String(60), default="Pending")
    created = db.Column(db.Date, default=datetime.date.today)
    parent_signed = db.Column(db.Boolean, default=False)
    parent_signed_at = db.Column(db.DateTime)

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"))
    department = db.Column(db.String(60))
    therapist_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    date = db.Column(db.Date)
    time = db.Column(db.String(20))
    session_type = db.Column(db.String(40), default="Regular")
    status = db.Column(db.String(40), default="Scheduled")

class SessionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"))
    department = db.Column(db.String(60))
    therapist_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    date = db.Column(db.Date, default=datetime.date.today)
    scheduled_time = db.Column(db.String(20))
    status = db.Column(db.String(40), default="Completed")
    rate = db.Column(db.Float, default=0)
    cancellation_reason = db.Column(db.String(200))
    additional = db.Column(db.Boolean, default=False)
    payment_status = db.Column(db.String(30), default="Unpaid")
    notes = db.Column(db.Text)

class MonthlyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"))
    month = db.Column(db.String(7))
    department = db.Column(db.String(60))
    planned_sessions = db.Column(db.Integer, default=0)
    carry_forward = db.Column(db.Integer, default=0)
    rate = db.Column(db.Float, default=0)
    planned_amount = db.Column(db.Float, default=0)
    paid_amount = db.Column(db.Float, default=0)

class ProgressNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"))
    department = db.Column(db.String(60))
    therapist_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    week_start = db.Column(db.Date)
    goals = db.Column(db.Text)
    progress = db.Column(db.Text)
    concerns = db.Column(db.Text)
    difficulties = db.Column(db.Text)
    recommendations = db.Column(db.Text)
    other = db.Column(db.Text)
    status = db.Column(db.String(30), default="Submitted")
    manager_comment = db.Column(db.Text)
    clinical_comment = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class GoalReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("goal_sheet.id"))
    month = db.Column(db.String(7))
    current_progress = db.Column(db.Text)
    improving = db.Column(db.Boolean, default=False)
    not_improving = db.Column(db.Boolean, default=False)
    achieved = db.Column(db.Boolean, default=False)
    needs_modification = db.Column(db.Boolean, default=False)
    new_recommendations = db.Column(db.Text)
    date = db.Column(db.Date, default=datetime.date.today)

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(60))
    message = db.Column(db.Text)
    child_id = db.Column(db.Integer)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

# ================= HELPERS =================
def page(body): return render_template_string(BASE_HTML, body=body)

def login_required(*roles):
    def deco(f):
        @functools.wraps(f)
        def w(*a, **k):
            if "uid" not in session: return redirect(url_for("login"))
            if roles and session["role"] not in roles: abort(403)
            return f(*a, **k)
        return w
    return deco

def cu(): return db.session.get(User, session["uid"]) if "uid" in session else None
def add_alert(t, m, cid=None): db.session.add(Alert(type=t, message=m, child_id=cid))

def clean_text(t):
    if not t: return ""
    return re.sub(r'\s+', ' ', str(t)).strip()

def find_or_create_child(name_str):
    name_str = clean_text(name_str)
    if not name_str: return None
    c = Child.query.filter(func.lower(Child.child_name) == func.lower(name_str)).first()
    if c: return c
    base_name = name_str.split('(')[0].split('/')[0].strip()
    c = Child.query.filter(func.lower(Child.child_name) == func.lower(base_name)).first()
    if c: return c
    new_child = Child(child_name=base_name, status="New")
    db.session.add(new_child)
    db.session.flush()
    return new_child

def find_or_create_therapist(name_str, dept):
    name_str = clean_text(name_str)
    if not name_str: return None
    
    t = User.query.filter((func.lower(User.full_name) == func.lower(name_str)) | (func.lower(User.username) == func.lower(name_str))).filter_by(role="therapist").first()
    if t:
        if not t.department or t.department != dept:
            t.department = dept
        return t
    
    safe_username = re.sub(r'[^a-z0-9]', '', name_str.lower())
    existing_user = User.query.filter_by(username=safe_username).first()
    if existing_user:
         safe_username = safe_username + str(int(datetime.datetime.now().timestamp()))
    
    new_therapist = User(username=safe_username, role="therapist", full_name=name_str, department=dept)
    new_therapist.set_password("password123")
    db.session.add(new_therapist)
    db.session.flush()
    return new_therapist

# ================= ALERTS API (For Popup/Sound) =================
@app.route("/api/alerts/unread")
@login_required()
def api_alerts_unread():
    unread = Alert.query.filter_by(read=False).order_by(Alert.id.desc()).all()
    return jsonify({
        "count": len(unread),
        "latest": unread[0].message if unread else None,
        "latest_type": unread[0].type if unread else None
    })

# ================= TEMPLATE =================
BASE_HTML = """<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ePetals</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
:root {
  --bg: #f5f5f7; --surface: #ffffff; --surface-2: #fafafa;
  --text: #1d1d1f; --text-2: #6e6e73; --text-3: #86868b;
  --accent: #6a3b9b; --accent-hover: #5a2f87; --accent-soft: #f4ebf9;
  --secondary: #00b2a9; --secondary-soft: #e0f7f6;
  --border: #d2d2d7; --border-soft: #e8e8ed;
  --success: #34c759; --success-soft: #e8f9ee; --warning: #ff9500; --warning-soft: #fff4e0;
  --danger: #ff3b30; --danger-soft: #ffe9e7;
  --r: 12px; --r-sm: 8px; --r-lg: 16px;
  --sh-sm: 0 1px 2px rgba(0,0,0,.04), 0 1px 3px rgba(0,0,0,.04);
  --sh: 0 4px 12px rgba(0,0,0,.05), 0 1px 3px rgba(0,0,0,.04);
  --sh-lg: 0 12px 32px rgba(0,0,0,.08), 0 4px 8px rgba(0,0,0,.04);
}
[data-theme="dark"] {
  --bg: #121212; --surface: #1c1c1e; --surface-2: #2c2c2e;
  --text: #f5f5f7; --text-2: #a1a1a6; --text-3: #8e8e93;
  --accent: #9d6ce6; --accent-hover: #b085ec; --accent-soft: #3a264f;
  --secondary: #00d2c8; --secondary-soft: #1a4745;
  --border: #38383a; --border-soft: #2c2c2e;
  --success: #30d158; --success-soft: #1c3823; --warning: #ffd60a; --warning-soft: #3a320e;
  --danger: #ff453a; --danger-soft: #4a1c1a;
  --sh-sm: 0 1px 3px rgba(0,0,0,.4); --sh: 0 4px 12px rgba(0,0,0,.5); --sh-lg: 0 12px 32px rgba(0,0,0,.6);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);
font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;letter-spacing:-.01em;transition:background 0.3s,color 0.3s}
h1{font-size:30px;font-weight:700;letter-spacing:-.02em;margin:0 0 8px}
h2{font-size:21px;font-weight:600;letter-spacing:-.01em;margin:0 0 12px}
h3{font-size:16px;font-weight:600;margin:0 0 12px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.app{display:flex;min-height:100vh}
.sidebar{width:240px;background:var(--surface);border-right:1px solid var(--border-soft);
padding:20px 12px;display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;overflow-y:auto;z-index:10}
.brand{display:flex;align-items:center;gap:10px;padding:8px 12px 20px}
.brand-logo{height:36px;width:auto;object-fit:contain}
.brand-text{font-weight:700;font-size:18px;color:var(--accent);letter-spacing:-0.5px}
.nav{display:flex;flex-direction:column;gap:2px}
.nav a{padding:8px 12px;border-radius:8px;color:var(--text);font-size:14px;font-weight:500;
transition:background .15s;display:flex;justify-content:space-between;align-items:center}
.nav a:hover{background:var(--surface-2);text-decoration:none}
.nav a.active{background:var(--accent-soft);color:var(--accent)}
.nav .badge{background:var(--danger);color:#fff;font-size:11px;font-weight:600;
padding:1px 7px;border-radius:99px;min-width:18px;text-align:center;display:none;}
.user-card{margin-top:auto;padding:10px;border-radius:10px;background:var(--surface-2);
display:flex;align-items:center;gap:10px;font-size:13px}
.user-avatar{width:28px;height:28px;border-radius:50%;background:var(--accent);color:#fff;
display:flex;align-items:center;justify-content:center;font-weight:600;font-size:12px;flex-shrink:0}
.user-meta{flex:1;overflow:hidden}
.user-name{font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.user-role{color:var(--text-3);font-size:11px;text-transform:capitalize}
.user-card a{padding:6px;font-size:16px;color:var(--text-3)}
.theme-toggle{background:transparent;border:0;color:var(--text-2);font-size:18px;cursor:pointer;padding:8px 12px;border-radius:8px;display:flex;align-items:center;gap:8px;width:100%;font-family:inherit;margin-bottom:12px}
.theme-toggle:hover{background:var(--surface-2);color:var(--text)}
.main{flex:1;margin-left:240px;padding:32px 40px;min-height:100vh}
.main>*{max-width:1100px}
.card{background:var(--surface);border:1px solid var(--border-soft);border-radius:var(--r);
padding:24px;margin-bottom:20px;box-shadow:var(--sh-sm);animation:fadeIn .3s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
label{display:block;font-size:13px;font-weight:500;color:var(--text-2);margin-bottom:6px}
input,select,textarea{width:100%;padding:10px 12px;border:1px solid var(--border);
border-radius:var(--r-sm);background:var(--surface);font-size:14px;font-family:inherit;
color:var(--text);transition:border .15s,box-shadow .15s}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent);
box-shadow:0 0 0 3px var(--accent-soft)}
textarea{min-height:72px;resize:vertical}
input[type=checkbox]{width:auto;accent-color:var(--accent)}
.row{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px}
.row>div{flex:1;min-width:180px}
button,.btn{display:inline-flex;align-items:center;justify-content:center;padding:9px 16px;
background:var(--accent);color:#fff;border:0;border-radius:var(--r-sm);font-size:14px;
font-weight:500;font-family:inherit;cursor:pointer;text-decoration:none;
transition:background .15s,transform .05s}
button:hover,.btn:hover{background:var(--accent-hover);text-decoration:none}
button:active,.btn:active{transform:scale(.98)}
.btn.sm{padding:5px 11px;font-size:13px}
.btn.green{background:var(--success)}.btn.green:hover{background:#2eb750}
.btn.gray{background:var(--surface-2);color:var(--text);border:1px solid var(--border)}
.btn.gray:hover{background:var(--border-soft)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-weight:600;font-size:12px;text-transform:uppercase;
letter-spacing:.04em;color:var(--text-3);padding:10px 12px;
border-bottom:1px solid var(--border-soft);background:transparent}
td{padding:12px;border-bottom:1px solid var(--border-soft);color:var(--text);vertical-align:top}
tr:last-child td{border-bottom:0}
tbody tr:hover td{background:var(--surface-2)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:20px}
.stat{background:var(--surface);border:1px solid var(--border-soft);border-radius:var(--r);padding:20px;box-shadow:var(--sh-sm)}
.stat .label{font-size:12px;color:var(--text-3);text-transform:uppercase;letter-spacing:.04em;font-weight:500;margin-bottom:6px}
.stat b{display:block;font-size:26px;font-weight:600;color:var(--text);letter-spacing:-.02em}
.tag{display:inline-block;font-size:12px;font-weight:500;padding:3px 10px;border-radius:99px;background:var(--accent-soft);color:var(--accent)}
.tag.g{background:var(--success-soft);color:var(--success)}
.tag.r{background:var(--danger-soft);color:var(--danger)}
.tag.y{background:var(--warning-soft);color:var(--warning)}
.muted{color:var(--text-3);font-size:13px}
.flash{background:var(--warning-soft);border:1px solid var(--warning);color:var(--text);
padding:12px 16px;border-radius:var(--r-sm);margin-bottom:16px;font-size:14px}
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;
background:var(--bg);padding:20px}
.login-card{background:var(--surface);border-radius:var(--r-lg);padding:40px;
width:100%;max-width:400px;box-shadow:var(--sh-lg);border:1px solid var(--border-soft)}
.login-card h1{font-size:26px;margin-bottom:4px;text-align:center;color:var(--accent)}
.login-card .sub{text-align:center;color:var(--text-3);font-size:14px;margin:0 0 28px}
.gb-fab{position:fixed;bottom:24px;right:24px;width:56px;height:56px;border-radius:50%;
background:var(--accent);color:#fff;border:0;cursor:pointer;
box-shadow:0 8px 24px rgba(106,59,155,.35);font-size:24px;z-index:1000;
transition:transform .2s,box-shadow .2s;display:flex;align-items:center;justify-content:center}
.gb-fab:hover{transform:scale(1.05);box-shadow:0 12px 32px rgba(106,59,155,.45)}
.gb-panel{position:fixed;bottom:96px;right:24px;width:380px;max-width:calc(100vw - 32px);
height:560px;max-height:calc(100vh - 120px);background:var(--surface);
border-radius:var(--r-lg);box-shadow:var(--sh-lg);display:none;
flex-direction:column;z-index:1001;overflow:hidden;border:1px solid var(--border-soft)}
.gb-panel.open{display:flex}
.gb-header{padding:16px 20px;background:linear-gradient(135deg, var(--accent), var(--secondary));
color:#fff;display:flex;align-items:center;justify-content:space-between}
.gb-header h3{margin:0;color:#fff;font-size:15px}
.gb-close{background:transparent;border:0;color:#fff;font-size:24px;cursor:pointer;padding:0;line-height:1;width:auto}
.gb-messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.gb-msg{max-width:85%;padding:10px 14px;border-radius:16px;font-size:14px;line-height:1.45;animation:popIn .2s ease-out}
@keyframes popIn{from{opacity:0;transform:scale(0.95)}to{opacity:1;transform:scale(1)}}
.gb-msg.bot{background:var(--surface-2);align-self:flex-start;border-bottom-left-radius:4px}
.gb-msg.user{background:var(--accent);color:#fff;align-self:flex-end;border-bottom-right-radius:4px}
.gb-typing{display:flex;gap:4px;padding:14px 18px;align-items:center}
.gb-typing span{width:6px;height:6px;border-radius:50%;background:var(--text-3);animation:typing 1.2s infinite}
.gb-typing span:nth-child(2){animation-delay:.2s}.gb-typing span:nth-child(3){animation-delay:.4s}
@keyframes typing{0%,60%,100%{opacity:.3;transform:translateY(0)}30%{opacity:1;transform:translateY(-4px)}}
.gb-actions{padding:0 16px 8px;display:flex;flex-wrap:wrap;gap:6px}
.gb-action{background:var(--accent-soft);color:var(--accent);border:0;padding:6px 12px;
border-radius:99px;font-size:12px;font-weight:500;cursor:pointer;font-family:inherit;transition:background .15s}
.gb-action:hover{filter:brightness(0.95)}
.gb-action.primary{background:var(--accent);color:#fff}
.gb-action.primary:hover{background:var(--accent-hover)}
.gb-form{display:flex;gap:8px;padding:12px 16px 16px;border-top:1px solid var(--border-soft)}
.gb-form input{flex:1;padding:10px 14px;border-radius:99px;font-size:14px}
.gb-form button{padding:10px 16px;border-radius:99px;width:auto}
.toast{position:fixed;top:24px;right:24px;background:var(--surface);color:var(--text);
border-left:4px solid var(--accent);padding:16px 24px;border-radius:var(--r-sm);
box-shadow:var(--sh-lg);z-index:9999;transform:translateX(120%);transition:transform 0.3s ease;
font-weight:500;display:flex;align-items:center;gap:12px;border:1px solid var(--border);}
.toast.show{transform:translateX(0);}
@media (max-width:768px){
.sidebar{width:100%;position:relative;height:auto}
.main{margin-left:0;padding:20px}
.gb-panel{width:calc(100vw - 32px);right:16px}
}
</style>
<script>
  const savedTheme = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', savedTheme);
  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
  }
</script>
</head>
<body data-role="{{ session.get('role','guest') }}">
{% if session.get('uid') %}
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <img src="/logo.png" alt="ePetals" class="brand-logo" onerror="this.style.display='none'">
      <div class="brand-text">ePetals</div>
    </div>
    {% set ep = request.endpoint %}
    <nav class="nav">
      <a href="{{url_for('dashboard')}}" class="{{ 'active' if ep == 'dashboard' else '' }}">Dashboard</a>
      {% if session.role in ['admin','manager','frontoffice','clinical'] %}
      <a href="{{url_for('enquiries')}}" class="{{ 'active' if ep in ['enquiries'] else '' }}">Enquiries</a>
      {% endif %}
      {% if session.role != 'parent' %}
      <a href="{{url_for('clients')}}" class="{{ 'active' if ep in ['clients','client_detail'] else '' }}">Clients</a>
      <a href="{{url_for('schedule')}}" class="{{ 'active' if ep == 'schedule' else '' }}">Schedule</a>
      <a href="{{url_for('session_log')}}" class="{{ 'active' if ep == 'session_log' else '' }}">Session Log</a>
      {% endif %}
      {% if session.role in ['admin','manager','frontoffice'] %}
      <a href="{{url_for('plans')}}" class="{{ 'active' if ep == 'plans' else '' }}">Plans</a>
      {% endif %}
      {% if session.role in ['admin', 'manager'] %}
      <a href="{{url_for('financials')}}" class="{{ 'active' if ep == 'financials' else '' }}">Financials</a>
      {% endif %}
      {% if session.role == 'therapist' %}
      <a href="{{url_for('progress_notes')}}" class="{{ 'active' if ep == 'progress_notes' else '' }}">My Notes</a>
      {% endif %}
      {% if session.role in ['admin','manager','clinical'] %}
      <a href="{{url_for('weekly_review')}}" class="{{ 'active' if ep == 'weekly_review' else '' }}">Weekly Review</a>
      <a href="{{url_for('goal_reviews')}}" class="{{ 'active' if ep == 'goal_reviews' else '' }}">Goal Reviews</a>
      {% endif %}
      {% if session.role != 'parent' %}
      <a href="{{url_for('alerts')}}" class="{{ 'active' if ep == 'alerts' else '' }}">
          Alerts <span id="alert-badge" class="badge">0</span>
      </a>
      {% endif %}
      {% if session.role == 'parent' %}
      <a href="{{url_for('parent_portal')}}" class="{{ 'active' if ep == 'parent_portal' else '' }}">My Child</a>
      {% endif %}
    </nav>
    <div style="margin-top:auto">
      <button class="theme-toggle" onclick="toggleTheme()">
        <span id="theme-icon">🌙</span> <span id="theme-text">Dark Mode</span>
      </button>
    </div>
    <div class="user-card">
      <div class="user-avatar">{{ (session.get('name') or 'U')[0]|upper }}</div>
      <div class="user-meta">
        <div class="user-name">{{ session.get('name') }}</div>
        <div class="user-role">{{ session.get('role') }}</div>
      </div>
      <a href="{{url_for('logout')}}" title="Logout">↩</a>
    </div>
  </aside>
  <main class="main">
    {% with msgs = get_flashed_messages() %}{% for m in msgs %}<div class="flash">{{m}}</div>{% endfor %}{% endwith %}
    {{body|safe}}
  </main>
</div>

<button class="gb-fab" aria-label="Open guide">💬</button>
<div class="gb-panel">
  <div class="gb-header">
    <h3>ePetals Guide</h3>
    <button class="gb-close" aria-label="Close">×</button>
  </div>
  <div class="gb-messages"></div>
  <div class="gb-actions"></div>
  <form class="gb-form">
    <input placeholder="Ask me anything…" autocomplete="off">
    <button type="submit">Send</button>
  </form>
</div>
<script>
const ROLE = {{ session.get('role','guest')|tojson }};
document.addEventListener("DOMContentLoaded", () => {
  const icon = document.getElementById('theme-icon');
  const text = document.getElementById('theme-text');
  if(document.documentElement.getAttribute('data-theme') === 'dark') {
    icon.textContent = '☀️'; text.textContent = 'Light Mode';
  }
});

let lastAlertCount = -1;
function playAlertSound() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.1);
        gain.gain.setValueAtTime(0.5, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.3);
    } catch(e) { }
}

function showToast(msg) {
    const t = document.createElement('div');
    t.className = 'toast';
    t.innerHTML = `<span style="margin-right:10px; font-size:18px;">🔔</span> <span>${msg}</span>`;
    document.body.appendChild(t);
    setTimeout(() => { t.classList.add('show'); }, 10);
    setTimeout(() => {
        t.classList.remove('show');
        setTimeout(() => t.remove(), 300);
    }, 5000);
}

function checkAlerts() {
    if (ROLE === 'guest') return;
    fetch('/api/alerts/unread')
        .then(r => r.json())
        .then(data => {
            const badge = document.getElementById('alert-badge');
            if (badge) {
                if (data.count > 0) {
                    badge.style.display = 'inline-block';
                    badge.textContent = data.count;
                } else {
                    badge.style.display = 'none';
                }
            }
            if (lastAlertCount !== -1 && data.count > lastAlertCount) {
                playAlertSound();
                if (data.latest) showToast(data.latest);
            }
            lastAlertCount = data.count;
        }).catch(() => {});
}
setInterval(checkAlerts, 10000);
setTimeout(checkAlerts, 1000);

const GREETINGS = {
  admin:"Hi Admin 👋 I'm the ePetals guide. I can help you run the centre. Would you like a quick tutorial on how the software works?",
  manager:"Hi Manager 👋 I'm here to help you manage operations. Would you like a quick tour of the system?",
  clinical:"Hi Clinical Director 👋 I can guide you through assessments and clinical reviews. Would you like a quick tour?",
  therapist:"Hi 👋 I'll help you with your schedule and notes. Would you like a quick tour of your dashboard?",
  frontoffice:"Hi 👋 I can help with enquiries and scheduling. Would you like a quick tour?",
  parent:"Hi 👋 I'm here to help you understand your child's progress. Would you like a quick tour?",
  guest:"Hi 👋 Please sign in to get personalized help."
};
const TUTORIALS = {
  admin: [
    { text: "Welcome to ePetals! Let's start with the <b>Dashboard</b>. This is your bird's-eye view. You can see today's sessions, revenue, and unread alerts all in one place.", next: "Next" },
    { text: "Next, check <b>Enquiries</b>. When a parent calls or messages, you log it here. Once they schedule an assessment, you move them to the <b>Clients</b> list.", next: "Next" },
    { text: "In <b>Clients</b>, you can click 'Open' on any child to see their assessments, goal sheets, and therapy progress.", next: "Next" },
    { text: "Every day, use the <b>Schedule</b> page to book tomorrow's therapy sessions. You can also import schedules directly from PDF files here!", next: "Next" },
    { text: "After a session happens, go to <b>Session Log</b> to record it. If a child does an extra session, check 'Additional'. This automatically updates their billing balance!", next: "Next" },
    { text: "Finally, manage monthly payments in <b>Plans</b>. This page calculates exactly how many sessions are remaining based on what the parent paid for.", next: "Finish Tour" }
  ],
  manager: [
    { text: "Welcome! Let's look at the <b>Dashboard</b> first. You can monitor daily operations, cancellations, and revenue at a glance.", next: "Next" },
    { text: "Use the <b>Schedule</b> and <b>Session Log</b> to ensure therapists are on track and sessions are being completed.", next: "Next" },
    { text: "As a Manager, you'll need to review therapist notes in <b>Weekly Review</b>. You can add comments and flag any concerns.", next: "Next" },
    { text: "Check <b>Goal Reviews</b> to monitor clinical progress and see which children need more attention.", next: "Finish Tour" }
  ],
  clinical: [
    { text: "Welcome, Clinical Director. Your main workspace is the <b>Clients</b> page. Click 'Open' on a child to view or add <b>Assessments</b> and <b>Goal Sheets</b>.", next: "Next" },
    { text: "When a child needs multiple departments, use the <b>Referrals</b> section inside the client profile to alert other therapists.", next: "Next" },
    { text: "Use <b>Weekly Review</b> to oversee the therapists' progress notes and add your clinical guidance.", next: "Next" },
    { text: "Don't forget to check <b>Goal Reviews</b> monthly to update progress and adjust targets.", next: "Finish Tour" }
  ],
  therapist: [
    { text: "Welcome! Your day starts on the <b>Dashboard</b>, where you can see exactly who you are seeing today.", next: "Next" },
    { text: "After each session, go to <b>Session Log</b> to mark it as 'Completed' or 'No-show'. This updates the centre's billing immediately.", next: "Next" },
    { text: "Every Monday, go to <b>My Notes</b> to submit your weekly progress notes for each child.", next: "Next" },
    { text: "Need to check a child's clinical goals? Just go to <b>Clients</b> and open their profile.", next: "Finish Tour" }
  ],
  frontoffice: [
    { text: "Welcome! Let's start with <b>Enquiries</b>. When a new parent contacts the centre, fill out the form here to create their profile.", next: "Next" },
    { text: "When it's time to book them, go to <b>Schedule</b> and add the child, therapist, and time. You can even upload a PDF of the schedule to import it all at once!", next: "Next" },
    { text: "If a parent calls to pay or check their balance, you can view their live numbers in <b>Plans</b>.", next: "Finish Tour" }
  ],
  parent: [
    { text: "Welcome to ePetals! Click on <b>My Child</b> in the menu to see your child's profile.", next: "Next" },
    { text: "At the top, you'll see <b>Today's Sessions</b> so you know exactly what time to arrive.", next: "Next" },
    { text: "Below that is the <b>Session Balances</b> table. This shows you how many sessions you paid for, how many are done, and how many are <i>remaining</i>.", next: "Finish Tour" }
  ]
};
const BASE_ANSWERS = [
  { keywords:["help","confused","don't know","stuck","guide"], text:"I'm here to help! You can ask me questions, or click the 'Start Tutorial' button to get a quick tour." },
  { keywords:["login","password","sign in","account"], text:"Use the username and password given to you by the centre." },
  { keywords:["logout","sign out"], text:"Click the ↩ icon at the bottom of the left sidebar to log out." },
  { keywords:["change","edit","update"], text:"Open the item (client, plan, note), change the fields, and click Save. Updates appear immediately across the system." }
];
const ROLE_ANSWERS = {
  admin: [
    { keywords:["enquiry","new client","add client","register"], text:"Enquiries page → fill the 'New Enquiry' form at the top → click 'Create Enquiry'. A client profile is created and an alert is raised." },
    { keywords:["schedule","appointment","book"], text:"Schedule page → date defaults to tomorrow → select Child, Department, Therapist, Time → click 'Add to Schedule'. The parent is alerted." },
    { keywords:["pdf","import schedule","file"], text:"On the Schedule page, there is an upload box. Upload a PDF containing the schedule text, and the system will try to pull in the sessions automatically." },
    { keywords:["plan","monthly","advance","payment plan"], text:"Plans page → set month → enter planned sessions, rate, planned amount, paid amount per department → Save. This drives all monthly reconciliation." },
    { keywords:["session log","record session","log session"], text:"Session Log page → select child, dept, therapist, status, rate → Save. Check 'Additional Session' when a session is beyond the plan — it creates an extra charge." },
    { keywords:["balance","remaining","carry forward","carry-forward"], text:"The Plans page shows Planned / Carry / Done / Remaining / Extra per department. Remaining = Planned + Carry − Done." },
    { keywords:["dashboard","metrics","revenue","utilization"], text:"Dashboard shows sessions today, cancellations, revenue (today + month), active clients, new enquiries, and revenue by department." },
    { keywords:["alert","notification"], text:"Alerts page lists all system events. Sidebar shows a badge, and you get a popup with a sound when new alerts arrive." },
    { keywords:["weekly review","progress note","therapist note"], text:"Weekly Review page shows every therapist's note. Add a comment, set status to Reviewed or Requires Attention, save." },
    { keywords:["goal review","monthly goal","goal progress"], text:"Goal Reviews page → pick the goal, month, current progress, mark Improving / Achieved / Needs Modification → Save." },
    { keywords:["assessment","referral","cross department","questionnaire"], text:"Open any client → Questionnaire, Assessment, Referrals, Discussion, and Goal Sheet all live on that one page." },
    { keywords:["dark mode","light mode","theme"], text:"You can toggle between Light and Dark mode using the button at the bottom of the sidebar." }
  ],
  manager: [
    { keywords:["schedule","appointment"], text:"Schedule page shows tomorrow by default. Add sessions for any date by changing the date field." },
    { keywords:["pdf","import schedule","file"], text:"You can import an entire day's schedule by uploading a PDF! Go to Schedule, upload your file, and the system will extract it." },
    { keywords:["session log","log"], text:"Session Log records what actually happened. Use 'Cancelled by parent' / 'No-show' — never delete a session." },
    { keywords:["dashboard","metrics","revenue"], text:"Dashboard: sessions today, cancellations, revenue (today + month), active clients, revenue by department." },
    { keywords:["weekly review","progress","note"], text:"Weekly Review → read each note → add comment → set status. Flag concerns as 'Requires Attention'." },
    { keywords:["goal review","goal progress"], text:"Goal Reviews → record monthly progress per goal with improving / achieved / needs modification flags." },
    { keywords:["plan","balance","reconcil"], text:"Plans page shows all monthly plans with Done and Remaining per department. That IS the reconciliation view." },
    { keywords:["dark mode","light mode","theme"], text:"Toggle between Light and Dark mode using the button at the bottom of the sidebar." }
  ],
  clinical: [
    { keywords:["assessment","clinical"], text:"Open a client → Assessment section → record findings, strengths, concerns, recommendations, required departments." },
    { keywords:["referral","cross department"], text:"On the client page, Referrals section → fill From, To, Notes → Create. Also auto-created from any assessment listing multiple required depts." },
    { keywords:["discussion","case discussion"], text:"Client page → Interdepartmental Discussion section → add participants and notes." },
    { keywords:["weekly review","progress"], text:"Weekly Review → add your clinical comment and set status. You see every therapist's notes." },
    { keywords:["goal","sheet"], text:"Client page → Goal Sheet section → add goals with target skill, baseline, expected outcome, measurement." }
  ],
  therapist: [
    { keywords:["schedule","my schedule","today"], text:"Your dashboard shows today's schedule. The Schedule page shows tomorrow by default — change the date to see other days." },
    { keywords:["session log","record","completed"], text:"Session Log → pick the child, dept, status ('Completed' for a normal session, 'Additional' for extra) → Save." },
    { keywords:["progress note","weekly","submit note"], text:"My Notes → fill the form → Submit. Do this by Monday for every assigned child. Include goals, progress, concerns, recommendations." },
    { keywords:["assessment","findings"], text:"Open the client → Assessment section → record findings, strengths, concerns, recommendations." },
    { keywords:["goal","goals","target"], text:"Client page shows the goal sheet. Goals are set by management or during assessment review." }
  ],
  frontoffice: [
    { keywords:["enquiry","new","register"], text:"Enquiries page → fill the New Enquiry form → Create. Status defaults to New; update to Contacted, Assessment Scheduled, etc. as you progress." },
    { keywords:["schedule","book"], text:"Schedule → select child, dept, therapist, date, time → Add. Parent gets an alert." },
    { keywords:["pdf","import schedule","file"], text:"On the Schedule page, you can upload a PDF to bulk-import the day's schedule. The system will scan the PDF for Dates, Child Names, and Therapist Names." },
    { keywords:["plan","payment"], text:"Plans page → add or update monthly plan per client and department." },
    { keywords:["client","open","details"], text:"Clients page → click 'Open' on any row to see the full client profile." }
  ],
  parent: [
    { keywords:["session","today","schedule"], text:"Open 'My Child' in the sidebar. Today's sessions are at the top with dept, time and status." },
    { keywords:["remaining","balance","how many"], text:"Remaining = Planned + Carry-forward − Done. It's how many sessions you still have this month before extra charges apply." },
    { keywords:["document","report","goal sheet"], text:"Approved reports and goal sheets appear on the My Child page once the centre releases them." },
    { keywords:["contact","call","centre"], text:"Please contact the centre directly for anything not shown here — I can only explain what's already on your page." }
  ]
};
const QUICK_ACTIONS = {
  admin:["How do I create an enquiry?","How do I schedule a session?","How does PDF import work?","How do monthly plans work?","How do I log a session?"],
  manager:["How do I see today's sessions?","How do weekly reviews work?","How does PDF import work?","How do monthly plans work?"],
  clinical:["How do assessments work?","How do referrals work?","How do weekly reviews work?"],
  therapist:["How do I log a session?","How do I submit weekly notes?"],
  frontoffice:["How do I add an enquiry?","How do I schedule a session?","How does PDF import work?"],
  parent:["How do I see today's sessions?","What does 'remaining' mean?"],
  guest:["How do I log in?"]
};
let tutorialStep = -1;
let isTutorialActive = false;
function answersFor(role){
  const roleAnswers = ROLE_ANSWERS[role] || ROLE_ANSWERS.admin;
  return [...BASE_ANSWERS, ...roleAnswers];
}
function matchAnswer(query){
  const q = query.toLowerCase();
  const all = answersFor(ROLE);
  let best = null, bestScore = 0;
  for (const a of all){
    for (const kw of a.keywords){
      if (q.includes(kw) && kw.length > bestScore){
        bestScore = kw.length;
        best = a.text;
      }
    }
  }
  return best || "I'm not sure about that yet. Try a quick action below, or ask about: enquiry, schedule, plan, session, review, or goal.";
}
const fab = document.querySelector('.gb-fab');
const panel = document.querySelector('.gb-panel');
const closeBtn = document.querySelector('.gb-close');
const form = document.querySelector('.gb-form');
const input = form ? form.querySelector('input') : null;
const messagesEl = document.querySelector('.gb-messages');
const actionsEl = document.querySelector('.gb-actions');
let initialized = false;
function addMessage(text, who){
  const el = document.createElement('div');
  el.className = 'gb-msg ' + who;
  el.innerHTML = text;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
function addTyping(){
  const el = document.createElement('div');
  el.className = 'gb-msg bot gb-typing';
  el.id = 'gb-typing';
  el.innerHTML = '<span></span><span></span><span></span>';
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
function removeTyping(){
  const el = document.getElementById('gb-typing');
  if (el) el.remove();
}
function setActions(list){
  actionsEl.innerHTML = '';
  list.forEach(item => {
    const b = document.createElement('button');
    b.className = 'gb-action ' + (item.primary ? 'primary' : '');
    b.textContent = item.label;
    b.type = 'button';
    b.onclick = item.action;
    actionsEl.appendChild(b);
  });
}
function showDefaultActions(){
  const actions = [];
  if (TUTORIALS[ROLE]) {
    actions.push({ label: "▶ Start Tutorial", primary: true, action: startTutorial });
  }
  const quick = QUICK_ACTIONS[ROLE] || QUICK_ACTIONS.guest;
  quick.forEach(q => {
    actions.push({ label: q, action: () => handleQuery(q) });
  });
  setActions(actions);
}
function startTutorial(){
  if (!TUTORIALS[ROLE]) return;
  isTutorialActive = true;
  tutorialStep = 0;
  addMessage("Let's begin!", "user");
  setActions([]);
  addTyping();
  setTimeout(() => {
    removeTyping();
    showTutorialStep();
  }, 400);
}
function showTutorialStep(){
  const steps = TUTORIALS[ROLE];
  if (!steps || tutorialStep >= steps.length){
    endTutorial();
    return;
  }
  const step = steps[tutorialStep];
  addMessage(step.text, 'bot');
  const actions = [
    { label: step.next || "Next", primary: true, action: () => {
      addMessage(step.next || "Next", "user");
      tutorialStep++;
      addTyping();
      setTimeout(() => {
        removeTyping();
        showTutorialStep();
      }, 400);
    }},
    { label: "Exit Tutorial", action: () => {
      addMessage("Exit Tutorial", "user");
      endTutorial();
    }}
  ];
  setActions(actions);
}
function endTutorial(){
  isTutorialActive = false;
  tutorialStep = -1;
  addMessage("Tutorial complete! If you ever need a refresher, just click 'Start Tutorial' again, or ask me any question.", 'bot');
  showDefaultActions();
}
function initBot(){
  addMessage(GREETINGS[ROLE] || GREETINGS.guest, 'bot');
  showDefaultActions();
  initialized = true;
}
function handleQuery(text){
  addMessage(text, 'user');
  setActions([]);
  input.value = '';
  addTyping();
  setTimeout(() => {
    removeTyping();
    if (isTutorialActive) {
      isTutorialActive = false;
      addMessage(matchAnswer(text), 'bot');
      addMessage("(Tutorial paused. Click 'Start Tutorial' to resume the tour.)", 'bot');
    } else {
      addMessage(matchAnswer(text), 'bot');
    }
    showDefaultActions();
  }, 400);
}
if (fab && panel){
  fab.onclick = () => {
    panel.classList.toggle('open');
    if (panel.classList.contains('open')){
      if (!initialized) initBot();
      setTimeout(() => input.focus(), 120);
    }
  };
  closeBtn.onclick = () => panel.classList.remove('open');
  form.onsubmit = e => {
    e.preventDefault();
    const v = input.value.trim();
    if (v) handleQuery(v);
  };
}
</script>
{% else %}
<div class="login-wrap">{{body|safe}}</div>
{% endif %}
</body>
</html>"""

def page(body): return render_template_string(BASE_HTML, body=body)

def login_required(*roles):
    def deco(f):
        @functools.wraps(f)
        def w(*a, **k):
            if "uid" not in session: return redirect(url_for("login"))
            if roles and session["role"] not in roles: abort(403)
            return f(*a, **k)
        return w
    return deco

def cu(): return db.session.get(User, session["uid"]) if "uid" in session else None
def add_alert(t, m, cid=None): db.session.add(Alert(type=t, message=m, child_id=cid))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form["username"]).first()
        if u and u.check_password(request.form["password"]):
            session.update(uid=u.id, role=u.role, name=u.full_name or u.username, dept=u.department)
            return redirect(url_for("dashboard"))
        flash("Invalid credentials")
    return page("""<div class="login-card">
    <img src="/logo.png" alt="ePetals" style="height:80px;display:block;margin:0 auto 16px;" onerror="this.style.display='none'">
    <h1>ePetals</h1>
    <p class="sub">Sign in to continue</p>
    <form method="post">
      <div style="margin-bottom:16px"><label>Username</label>
      <input name="username" placeholder="Enter username" required autofocus></div>
      <div style="margin-bottom:24px"><label>Password</label>
      <input name="password" type="password" placeholder="Enter password" required></div>
      <button style="width:100%">Sign In</button>
    </form>
    </div>""")

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/")
@login_required()
def dashboard():
    today = datetime.date.today(); month = today.strftime("%Y-%m")
    if session["role"] == "parent": return redirect(url_for("parent_portal"))
    
    if session["role"] == "therapist":
        uid = session["uid"]
        dept = session.get("dept")
        
        sch = Schedule.query.filter_by(department=dept, date=today).all()
        logs = SessionLog.query.filter_by(department=dept, date=today).all()
        
        return page(f"""<h1>Welcome, {session['name']}</h1>
        <div class="grid"><div class="stat"><div class="label">Today's Schedule ({dept})</div><b>{len(sch)}</b></div>
        <div class="stat"><div class="label">Completed Today</div><b>{sum(1 for l in logs if l.status == 'Completed')}</b></div></div>
        <div class="card"><h3>Today's Schedule</h3><table><tr><th>Child</th><th>Dept</th><th>Time</th><th>Status</th></tr>
        {''.join(f'<tr><td>{db.session.get(Child, s.child_id).child_name}</td><td>{s.department}</td><td>{s.time}</td><td>{s.status}</td></tr>' for s in sch) or '<tr><td colspan=4 class="muted">No sessions today</td></tr>'}</table></div>""")
    
    if session["role"] in ['admin', 'manager']:
        rev_t = db.session.query(func.coalesce(func.sum(SessionLog.rate), 0)).filter(SessionLog.date == today, SessionLog.status == "Completed").scalar() or 0
        rev_m = db.session.query(func.coalesce(func.sum(SessionLog.rate), 0)).filter(func.strftime("%Y-%m", SessionLog.date) == month, SessionLog.status == "Completed").scalar() or 0
        fin_html = f"""<h3 style="margin-top:24px">Financial</h3><div class="grid">
        <div class="stat"><div class="label">Revenue Today</div><b>{rev_t:.0f}</b></div>
        <div class="stat"><div class="label">Revenue This Month</div><b>{rev_m:.0f}</b></div>
        <div class="stat"><div class="label">Active Clients</div><b>{Child.query.filter(Child.status.in_(["Therapy Started", "Converted", "Assessment Completed"])).count()}</b></div>
        <div class="stat"><div class="label">New Enquiries</div><b>{Child.query.filter_by(status="New").count()}</b></div>
        </div>"""
    else:
        fin_html = f"""<h3 style="margin-top:24px">Overview</h3><div class="grid">
        <div class="stat"><div class="label">Active Clients</div><b>{Child.query.filter(Child.status.in_(["Therapy Started", "Converted", "Assessment Completed"])).count()}</b></div>
        <div class="stat"><div class="label">New Enquiries</div><b>{Child.query.filter_by(status="New").count()}</b></div>
        </div>"""

    total = SessionLog.query.filter_by(date=today).count()
    comp = SessionLog.query.filter_by(date=today, status="Completed").count()
    canc = SessionLog.query.filter(SessionLog.date == today, SessionLog.status.like("%Cancel%")).count()
    ns = SessionLog.query.filter_by(date=today, status="No-show").count()
    rs = SessionLog.query.filter_by(date=today, status="Rescheduled").count()
    unread = Alert.query.filter_by(read=False).count()
    return page(f"""<h1>Dashboard</h1>
    <p class="muted" style="margin:0 0 24px">Overview of today and this month</p>
    <h3>Operations</h3><div class="grid">
    <div class="stat"><div class="label">Sessions Today</div><b>{total}</b></div>
    <div class="stat"><div class="label">Completed</div><b>{comp}</b></div>
    <div class="stat"><div class="label">Cancellations</div><b>{canc}</b></div>
    <div class="stat"><div class="label">No-shows</div><b>{ns}</b></div>
    <div class="stat"><div class="label">Rescheduled</div><b>{rs}</b></div>
    <div class="stat"><div class="label">Unread Alerts</div><b>{unread}</b></div></div>
    {fin_html}""")

@app.route("/financials", methods=["GET"])
@login_required("admin", "manager")
def financials():
    selected_date_str = request.args.get("date") or datetime.date.today().isoformat()
    try:
        selected_date = datetime.date.fromisoformat(selected_date_str)
    except:
        selected_date = datetime.date.today()

    import calendar
    _, num_days = calendar.monthrange(selected_date.year, selected_date.month)
    
    daily_rev = []
    daily_profit = []
    days_x = []
    
    for day in range(1, num_days + 1):
        d = datetime.date(selected_date.year, selected_date.month, day)
        days_x.append(d.strftime("%d-%m"))
        
        rev = db.session.query(func.coalesce(func.sum(SessionLog.rate), 0)).filter(
            SessionLog.date == d, SessionLog.status == "Completed"
        ).scalar() or 0
        daily_rev.append(float(rev))
        daily_profit.append(float(rev) * PROFIT_MARGIN)

    total_month_rev = sum(daily_rev)
    total_month_profit = sum(daily_profit)
    total_month_sessions = SessionLog.query.filter(
        func.strftime("%Y-%m", SessionLog.date) == selected_date.strftime("%Y-%m"),
        SessionLog.status == "Completed"
    ).count()

    day_logs = SessionLog.query.filter(
        SessionLog.date == selected_date, SessionLog.status == "Completed"
    ).all()
    
    hourly_rev = {}
    for log in day_logs:
        hour = "Unknown"
        if log.scheduled_time:
            match = re.search(r'(\d+)', log.scheduled_time)
            if match:
                hour = f"{match.group(1)}:00"
        hourly_rev[hour] = hourly_rev.get(hour, 0) + log.rate
        
    hourly_x = sorted([k for k in hourly_rev.keys() if k != "Unknown"])
    hourly_y = [hourly_rev[k] for k in hourly_x]

    dept_revs = []
    for d in DEPTS:
        rev = db.session.query(func.coalesce(func.sum(SessionLog.rate), 0)).filter(
            SessionLog.department == d,
            SessionLog.status == "Completed",
            func.strftime("%Y-%m", SessionLog.date) == selected_date.strftime("%Y-%m")
        ).scalar() or 0
        dept_revs.append(float(rev))

    top_dept = "N/A"
    if max(dept_revs) > 0:
        top_dept = DEPTS[dept_revs.index(max(dept_revs))]

    rev_color = "#0071e3" 
    profit_color = "#34c759" if total_month_profit >= 0 else "#ff3b30" 

    dept_colors = {
        "Speech": "#ff99cc", "OT": "#34c759", "BT": "#ffcc00", "Physiotherapy": "#ff9500", "Special Ed": "#ff3b30"
    }
    bar_colors = [dept_colors.get(d, "#6a3b9b") for d in DEPTS]

    body = f"""
    <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:24px;">
        <div>
            <h1>Financial Analytics</h1>
            <p class="muted" style="margin:0">Revenue and Profit breakdown</p>
        </div>
        <form method="get" style="display:flex; gap:8px; align-items:center;">
            <label style="margin:0;">Select Day:</label>
            <input type="date" name="date" value="{selected_date.isoformat()}" style="max-width:200px;">
            <button class="btn sm">View</button>
        </form>
    </div>

    <div class="grid">
        <div class="stat" style="border-left: 4px solid {rev_color};">
            <div class="label">Total Month Revenue</div>
            <b style="color: {rev_color};">₹{total_month_rev:,.2f}</b>
        </div>
        <div class="stat" style="border-left: 4px solid {profit_color};">
            <div class="label">Total Month Profit</div>
            <b style="color: {profit_color};">₹{total_month_profit:,.2f}</b>
        </div>
        <div class="stat">
            <div class="label">Sessions This Month</div>
            <b>{total_month_sessions}</b>
        </div>
        <div class="stat">
            <div class="label">Top Department</div>
            <b>{top_dept}</b>
        </div>
    </div>

    <div class="card" style="padding:20px;">
        <h3 style="margin-bottom: 4px;">Monthly Growth</h3>
        <p class="muted" style="margin-top:0; margin-bottom: 16px; font-size: 13px;">Solid blue line is money in. Dashed line is your profit.</p>
        <div id="monthly-graph" style="width:100%; height:350px;"></div>
    </div>

    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
        <div class="card" style="padding:20px;">
            <h3 style="margin-bottom: 4px;">Day View: {selected_date.strftime('%d %b %Y')}</h3>
            <p class="muted" style="margin-top:0; margin-bottom: 16px; font-size: 13px;">Revenue grouped by hour of the day.</p>
            <div id="daily-graph" style="width:100%; height:300px;"></div>
        </div>

        <div class="card" style="padding:20px;">
            <h3 style="margin-bottom: 4px;">Revenue by Department</h3>
            <p class="muted" style="margin-top:0; margin-bottom: 16px; font-size: 13px;">Total revenue generated by each department this month.</p>
            <div id="dept-graph" style="width:100%; height:300px;"></div>
        </div>
    </div>

    <script>
        function getLayout(title, yLabel, isBar = false) {{
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            return {{
                margin: {{ l: 60, r: 20, t: 20, b: 40 }},
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                hovermode: 'x unified', 
                xaxis: {{ 
                    type: isBar ? 'category' : '-',
                    color: isDark ? '#a1a1a6' : '#6e6e73', 
                    gridcolor: isDark ? '#38383a' : '#e8e8ed',
                    showgrid: false 
                }},
                yaxis: {{ 
                    color: isDark ? '#a1a1a6' : '#6e6e73', 
                    gridcolor: isDark ? '#38383a' : '#e8e8ed',
                    title: {{ text: yLabel, font: {{ size: 12 }} }},
                    tickprefix: '₹'
                }},
                showlegend: true,
                legend: {{ orientation: 'h', y: 1.1, x: 0, font: {{ size: 12 }} }}
            }};
        }}

        var traceRev = {{
            x: {json.dumps(days_x)}, y: {json.dumps(daily_rev)}, type: 'scatter', mode: 'lines+markers',
            name: 'Revenue (Money In)', line: {{ color: '{rev_color}', width: 3 }}, marker: {{ size: 6, color: '{rev_color}' }},
            hovertemplate: '<b>₹%{{y:,.2f}}</b><extra></extra>'
        }};
        var traceProfit = {{
            x: {json.dumps(days_x)}, y: {json.dumps(daily_profit)}, type: 'scatter', mode: 'lines',
            name: 'Profit (After Costs)', line: {{ color: '{profit_color}', width: 3, dash: 'dot' }},
            hovertemplate: '<b>₹%{{y:,.2f}}</b><extra></extra>'
        }};
        Plotly.newPlot('monthly-graph', [traceRev, traceProfit], getLayout('', 'Amount (₹)'));

        var traceDaily = {{
            x: {json.dumps(hourly_x)}, y: {json.dumps(hourly_y)}, type: 'scatter', mode: 'lines+markers', fill: 'tozeroy',
            line: {{ color: '{rev_color}', width: 3, shape: 'spline' }}, marker: {{ size: 8, color: '{rev_color}' }},
            fillcolor: 'rgba(0, 113, 227, 0.1)', name: 'Revenue', hovertemplate: '<b>₹%{{y:,.2f}}</b><extra></extra>'
        }};
        Plotly.newPlot('daily-graph', [traceDaily], getLayout('', 'Revenue (₹)'));

        var traceDept = {{
            x: {json.dumps(DEPTS)}, y: {json.dumps(dept_revs)}, type: 'bar',
            marker: {{ color: {json.dumps(bar_colors)} }}, name: 'Revenue by Department',
            hovertemplate: '<b>₹%{{y:,.2f}}</b><extra></extra>'
        }};
        Plotly.newPlot('dept-graph', [traceDept], getLayout('', 'Total Revenue (₹)', true));
    </script>
    """
    return page(body)

@app.route("/enquiries", methods=["GET", "POST"])
@login_required("admin", "manager", "frontoffice", "clinical")
def enquiries():
    if request.method == "POST":
        c = Child(parent_name=request.form.get("parent_name"), child_name=request.form["child_name"],
                  dob=request.form.get("dob"), contact=request.form.get("contact"),
                  primary_concern=request.form.get("primary_concern"),
                  required_dept=request.form.get("required_dept"),
                  source=request.form.get("source"), status=request.form.get("status", "New"),
                  notes=request.form.get("notes"))
        if request.form.get("follow_up_date"):
            c.follow_up_date = datetime.date.fromisoformat(request.form["follow_up_date"])
        db.session.add(c); add_alert("New Enquiry", f"New enquiry: {c.child_name}"); db.session.commit()
        flash("Enquiry created"); return redirect(url_for("enquiries"))
    q = Child.query.order_by(Child.id.desc()).all()
    rows = "".join(f'<tr><td>{c.id}</td><td>{c.child_name}</td><td>{c.parent_name or ""}</td><td>{c.contact or ""}</td><td>{c.required_dept or ""}</td><td><span class="tag">{c.status}</span></td><td>{c.enquiry_date}</td><td><a class="btn sm" href="{url_for("client_detail", cid=c.id)}">Open</a></td></tr>' for c in q)
    dept = "".join(f"<option>{d}</option>" for d in DEPTS)
    st = "".join(f"<option>{s}</option>" for s in STATUSES)
    return page(f"""<h1>Enquiries</h1><p class="muted" style="margin:0 0 24px">Create and manage all new enquiries</p>
    <div class="card"><h3>New Enquiry</h3><form method="post">
    <div class="row"><div><label>Parent Name</label><input name="parent_name"></div>
    <div><label>Child Name *</label><input name="child_name" required></div>
    <div><label>DOB</label><input name="dob" placeholder="YYYY-MM-DD"></div>
    <div><label>Contact</label><input name="contact"></div></div>
    <div class="row"><div><label>Primary Concern</label><textarea name="primary_concern"></textarea></div>
    <div><label>Required Dept</label><select name="required_dept">{dept}</select></div>
    <div><label>Source</label><input name="source" placeholder="WhatsApp, phone…"></div>
    <div><label>Status</label><select name="status">{st}</select></div>
    <div><label>Follow-up Date</label><input type="date" name="follow_up_date"></div></div>
    <p><label>Notes</label><textarea name="notes"></textarea></p>
    <button>Create Enquiry</button></form></div>
    <div class="card"><h3>All Clients</h3><table>
    <tr><th>ID</th><th>Child</th><th>Parent</th><th>Contact</th><th>Dept</th><th>Status</th><th>Date</th><th></th></tr>{rows or '<tr><td colspan=8 class="muted">No clients yet</td></tr>'}</table></div>""")

@app.route("/clients")
@login_required("admin", "manager", "frontoffice", "clinical", "therapist")
def clients():
    q = Child.query.order_by(Child.id.desc()).all()
    rows = "".join(f'<tr><td>{c.id}</td><td>{c.child_name}</td><td>{c.parent_name or ""}</td><td>{c.required_dept or ""}</td><td><span class="tag">{c.status}</span></td><td><a class="btn sm" href="{url_for("client_detail", cid=c.id)}">Open</a></td></tr>' for c in q)
    return page(f"<h1>Clients</h1><p class='muted' style='margin:0 0 24px'>All registered clients</p><div class='card'><table><tr><th>ID</th><th>Child</th><th>Parent</th><th>Dept</th><th>Status</th><th></th></tr>{rows or '<tr><td colspan=6 class=muted>None</td></tr>'}</table></div>")

@app.route("/client/<int:cid>", methods=["GET", "POST"])
@login_required("admin", "manager", "frontoffice", "clinical", "therapist")
def client_detail(cid):
    c = db.session.get(Child, cid) or abort(404)
    if request.method == "POST":
        a = request.form.get("action")
        if a == "q_sent":
            c.questionnaire_sent = True; add_alert("Questionnaire Pending", f"Sent to {c.child_name}", c.id)
        elif a == "q_submit":
            c.questionnaire_submitted = True; c.questionnaire_answers = request.form.get("answers", "")
            add_alert("Questionnaire Completed", f"{c.child_name} submitted", c.id)
        elif a == "assessment":
            ass = Assessment(child_id=c.id, therapist_id=session["uid"],
                department=request.form["department"], findings=request.form.get("findings"),
                concerns=request.form.get("concerns"), strengths=request.form.get("strengths"),
                recommendations=request.form.get("recommendations"),
                required_depts=request.form.get("required_depts"),
                recommended_sessions=int(request.form.get("recommended_sessions") or 0),
                additional_assessments=request.form.get("additional_assessments"))
            db.session.add(ass)
            for d in [x.strip() for x in (ass.required_depts or "").split(",") if x.strip()]:
                db.session.add(Referral(child_id=c.id, from_dept=ass.department, to_dept=d, notes="From assessment"))
            c.status = "Assessment Completed"
            add_alert("Assessment Completed", f"Assessment done: {c.child_name}", c.id)
        elif a == "referral":
            db.session.add(Referral(child_id=c.id, from_dept=request.form.get("from_dept", ""),
                                    to_dept=request.form["to_dept"], notes=request.form.get("notes")))
        elif a == "discussion":
            db.session.add(Discussion(child_id=c.id, notes=request.form.get("notes"),
                                      participants=request.form.get("participants")))
        elif a == "goal":
            db.session.add(GoalSheet(child_id=c.id, department=request.form["department"],
                goal=request.form["goal"], target_skill=request.form.get("target_skill"),
                baseline=request.form.get("baseline"), expected_outcome=request.form.get("expected_outcome"),
                measurement=request.form.get("measurement")))
            c.status = "Therapy Started"
        elif a == "sign":
            for g in GoalSheet.query.filter_by(child_id=c.id).all():
                g.parent_signed = True; g.parent_signed_at = datetime.datetime.utcnow()
        elif a == "status":
            c.status = request.form["status"]
        db.session.commit(); flash("Saved"); return redirect(url_for("client_detail", cid=c.id))
    ass_list = Assessment.query.filter_by(child_id=c.id).all()
    ref_list = Referral.query.filter_by(child_id=c.id).all()
    disc_list = Discussion.query.filter_by(child_id=c.id).all()
    goals = GoalSheet.query.filter_by(child_id=c.id).all()
    dept = "".join(f"<option>{d}</option>" for d in DEPTS)
    st = "".join(f"<option>{s}</option>" for s in STATUSES)
    return page(f"""<h1>{c.child_name} <span class="tag">{c.status}</span></h1>
    <p class="muted" style="margin:0 0 24px">Parent: {c.parent_name or "-"} · DOB: {c.dob or "-"} · Contact: {c.contact or "-"} · Concern: {c.primary_concern or "-"}</p>
    <div class="card"><h3>Status</h3><form method="post" style="display:flex;gap:8px">
    <input type="hidden" name="action" value="status">
    <select name="status" style="max-width:250px">{st}</select><button>Update</button></form></div>
    <div class="card"><h3>Questionnaire</h3>
    <p class="muted">Sent: {'✓' if c.questionnaire_sent else '✗'} · Submitted: {'✓' if c.questionnaire_submitted else '✗'}</p>
    <form method="post" style="margin-bottom:8px"><input type="hidden" name="action" value="q_sent"><button class="btn gray">Mark Sent</button></form>
    <form method="post"><input type="hidden" name="action" value="q_submit">
    <textarea name="answers">{c.questionnaire_answers or ''}</textarea>
    <button style="margin-top:8px">Save Answers</button></form></div>
    <div class="card"><h3>Assessment</h3><form method="post"><input type="hidden" name="action" value="assessment">
    <div class="row"><div><label>Department</label><select name="department">{dept}</select></div>
    <div><label>Recommended Sessions</label><input name="recommended_sessions" type="number" value="12"></div>
    <div><label>Refer to (comma separated)</label><input name="required_depts" placeholder="Speech, OT"></div></div>
    <p><label>Findings</label><textarea name="findings"></textarea></p>
    <p><label>Concerns</label><textarea name="concerns"></textarea></p>
    <p><label>Strengths</label><textarea name="strengths"></textarea></p>
    <p><label>Recommendations</label><textarea name="recommendations"></textarea></p>
    <p><label>Additional Assessments</label><textarea name="additional_assessments"></textarea></p>
    <button>Save Assessment</button></form>
    <table style="margin-top:16px"><tr><th>Date</th><th>Dept</th><th>Findings</th><th>Sessions</th></tr>
    {''.join(f'<tr><td>{x.date}</td><td>{x.department}</td><td>{(x.findings or "")[:80]}</td><td>{x.recommended_sessions}</td></tr>' for x in ass_list) or '<tr><td colspan=4 class="muted">None</td></tr>'}</table></div>
    <div class="card"><h3>Referrals</h3>
    <form method="post" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px"><input type="hidden" name="action" value="referral">
    <input name="from_dept" placeholder="From" style="max-width:150px">
    <select name="to_dept" style="max-width:150px">{dept}</select>
    <input name="notes" placeholder="Notes" style="max-width:300px"><button>Create</button></form>
    <table><tr><th>Date</th><th>From</th><th>To</th><th>Notes</th></tr>
    {''.join(f'<tr><td>{r.created}</td><td>{r.from_dept or ""}</td><td>{r.to_dept}</td><td>{r.notes or ""}</td></tr>' for r in ref_list) or '<tr><td colspan=4 class="muted">None</td></tr>'}</table></div>
    <div class="card"><h3>Interdepartmental Discussion</h3>
    <form method="post" style="margin-bottom:12px"><input type="hidden" name="action" value="discussion">
    <p><input name="participants" placeholder="Participants"></p>
    <p><textarea name="notes" placeholder="Discussion notes"></textarea></p><button>Add</button></form>
    {''.join(f'<p class="muted">{d.date}: <b>{d.participants or ""}</b> — {d.notes or ""}</p>' for d in disc_list)}</div>
    <div class="card"><h3>Goal Sheet (3-Month)</h3><form method="post"><input type="hidden" name="action" value="goal">
    <div class="row"><div><label>Department</label><select name="department">{dept}</select></div>
    <div><label>Goal</label><input name="goal" required></div>
    <div><label>Target Skill</label><input name="target_skill"></div></div>
    <div class="row"><div><label>Baseline</label><input name="baseline"></div>
    <div><label>Expected Outcome</label><input name="expected_outcome"></div>
    <div><label>Measurement</label><input name="measurement"></div></div>
    <button>Add Goal</button></form>
    <table style="margin-top:16px"><tr><th>Dept</th><th>Goal</th><th>Target</th><th>Baseline</th><th>Signed</th></tr>
    {''.join(f'<tr><td>{g.department}</td><td>{g.goal}</td><td>{g.target_skill or ""}</td><td>{g.baseline or ""}</td><td>{"✓" if g.parent_signed else "✗"}</td></tr>' for g in goals) or '<tr><td colspan=5 class="muted">None</td></tr>'}</table>
    <form method="post" style="margin-top:12px"><input type="hidden" name="action" value="sign"><button class="btn green">Parent Digital Signature</button></form></div>""")

@app.route("/schedule", methods=["GET", "POST"])
@login_required("admin", "manager", "frontoffice", "therapist")
def schedule():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "import_pdf":
            file = request.files.get("pdf_file")
            schedule_date_str = request.form.get("schedule_date")
            
            if not file or not file.filename.endswith('.pdf'):
                flash("Please upload a valid .pdf file.")
                return redirect(url_for("schedule"))
            if not schedule_date_str:
                flash("Please select the Date for this schedule.")
                return redirect(url_for("schedule"))
                
            try:
                target_date = datetime.date.fromisoformat(schedule_date_str)
                count = 0
                new_children = 0
                new_therapists = 0
                
                with pdfplumber.open(io.BytesIO(file.read())) as pdf:
                    for pdf_page in pdf.pages:
                        tables = pdf_page.extract_tables()
                        if not tables: continue
                        for table in tables:
                            if not table or len(table) < 2: continue
                            
                            header_idx = 0
                            for i, row in enumerate(table):
                                if row and any(cell and "time" in str(cell).lower() for cell in row):
                                    header_idx = i
                                    break
                                    
                            headers = table[header_idx]
                            therapists = [clean_text(h) for h in headers[1:]]
                            
                            for row in table[header_idx+1:]:
                                if not row or not row[0]: continue
                                
                                time_raw = clean_text(row[0]).replace('.', ':').replace(' ', '').upper()
                                ampm = ""
                                if time_raw.endswith("AM") or time_raw.endswith("PM"):
                                    ampm = time_raw[-2:]
                                    time_part = time_raw[:-2]
                                    if ':' not in time_part: time_part += ':00'
                                    parts = time_part.split(':')
                                    time_clean = f"{parts[0].zfill(2)}:{parts[1]} {ampm}"
                                else:
                                    time_clean = time_raw
                                    
                                for col_idx, child_cell in enumerate(row[1:]):
                                    if col_idx >= len(therapists): break
                                    t_name = therapists[col_idx]
                                    if not t_name or not child_cell: continue
                                    
                                    t_name_lower = t_name.lower()
                                    dept = "Speech"
                                    if "shana" in t_name_lower: dept = "Speech"
                                    elif "nilufer" in t_name_lower: dept = "Speech"
                                    elif "alveena" in t_name_lower: dept = "OT"
                                    elif "afnan" in t_name_lower: dept = "BT"
                                    elif "meghna" in t_name_lower: dept = "BT"
                                    elif "teena" in t_name_lower: dept = "Special Ed"
                                    elif "jenifer" in t_name_lower: dept = "Physiotherapy"
                                    
                                    existing_child = Child.query.filter(func.lower(Child.child_name) == func.lower(clean_text(child_cell).split('(')[0].split('/')[0].strip())).first()
                                    child = find_or_create_child(child_cell)
                                    if not existing_child and child: new_children += 1
                                    
                                    existing_therapist = User.query.filter((func.lower(User.full_name) == func.lower(t_name)) | (func.lower(User.username) == func.lower(t_name))).filter_by(role="therapist").first()
                                    therapist = find_or_create_therapist(t_name, dept)
                                    if not existing_therapist and therapist: new_therapists += 1
                                    
                                    if child and therapist:
                                        sch = Schedule(
                                            child_id=child.id,
                                            department=dept,
                                            therapist_id=therapist.id,
                                            date=target_date,
                                            time=time_clean,
                                            session_type="Imported"
                                        )
                                        db.session.add(sch)
                                        count += 1
                                        
                db.session.commit()
                
                msg = f"Successfully imported {count} sessions for {target_date.strftime('%b %d, %Y')}."
                if new_children > 0 or new_therapists > 0:
                    msg += f" (Auto-created {new_children} clients and {new_therapists} therapists!)"
                flash(msg)
                
            except Exception as e:
                flash(f"Error parsing PDF: {str(e)}")
            return redirect(url_for("schedule", date=schedule_date_str))
        
        sch = Schedule(child_id=int(request.form["child_id"]),
                       department=request.form["department"],
                       therapist_id=int(request.form["therapist_id"]),
                       date=datetime.date.fromisoformat(request.form["date"]),
                       time=request.form["time"], session_type=request.form.get("session_type", "Regular"))
        db.session.add(sch)
        add_alert("Session Scheduled", f"Session for {db.session.get(Child, sch.child_id).child_name} on {sch.date}", sch.child_id)
        db.session.commit(); flash("Scheduled"); return redirect(url_for("schedule"))
        
    target = request.args.get("date") or (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    
    if session["role"] == "therapist":
        dept = session.get("dept")
        schs = Schedule.query.filter_by(date=datetime.date.fromisoformat(target), department=dept).all()
    else:
        schs = Schedule.query.filter_by(date=datetime.date.fromisoformat(target)).all()
    
    def sort_key(s):
        t = s.time or ""
        t = t.strip().upper().replace('.', ':').replace(' ', '')
        minutes = 9999
        for fmt in ("%I:%M%p", "%H:%M", "%I:%M", "%H"):
            try:
                dt = datetime.datetime.strptime(t, fmt)
                minutes = dt.hour * 60 + dt.minute
                break
            except ValueError:
                pass
        if minutes == 9999:
            match = re.search(r'(\d{1,2})[:.:](\d{2})', t)
            if match:
                h, m = int(match.group(1)), int(match.group(2))
                if 'PM' in t and h < 12: h += 12
                if 'AM' in t and h == 12: h = 0
                minutes = h * 60 + m
        child_name = db.session.get(Child, s.child_id).child_name if db.session.get(Child, s.child_id) else ""
        return (minutes, child_name)
        
    schs.sort(key=sort_key)

    kids = Child.query.order_by(Child.child_name).all()
    ths = User.query.filter_by(role="therapist").all()
    dept = "".join(f"<option>{d}</option>" for d in DEPTS)
    kid_opts = "".join(f'<option value="{k.id}">{k.child_name}</option>' for k in kids)
    th_opts = "".join(f'<option value="{t.id}">{t.full_name or t.username}</option>' for t in ths)
    rows = "".join(f'<tr><td>{db.session.get(Child, s.child_id).child_name}</td><td>{s.department}</td><td>{db.session.get(User, s.therapist_id).full_name or ""}</td><td>{s.time}</td><td>{s.status}</td></tr>' for s in schs)
    
    admin_controls = ""
    if session["role"] in ["admin", "manager", "frontoffice"]:
        admin_controls = f"""
        <div class="card" style="border-left: 4px solid var(--secondary);">
          <h3>Import Table from PDF</h3>
          <p class="muted">Upload your schedule PDF. The system reads the grid layout exactly as shown in your spreadsheet. <b>Missing clients and therapists are created automatically.</b></p>
          <form method="post" enctype="multipart/form-data" style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end">
            <input type="hidden" name="action" value="import_pdf">
            <div style="flex:0 0 200px"><label>Schedule Date</label><input type="date" name="schedule_date" value="{datetime.date.today().isoformat()}" required></div>
            <div style="flex:1"><label>PDF File</label><input type="file" name="pdf_file" accept=".pdf" required style="padding:8px;"></div>
            <button class="btn" style="background:var(--secondary);height:42px;">Upload & Sync</button>
          </form>
        </div>

        <div class="card"><h3>Create Schedule (Manual)</h3><form method="post">
        <div class="row"><div><label>Child</label><select name="child_id">{kid_opts}</select></div>
        <div><label>Department</label><select name="department">{dept}</select></div>
        <div><label>Therapist</label><select name="therapist_id">{th_opts}</select></div>
        <div><label>Date</label><input type="date" name="date" value="{target}" required></div>
        <div><label>Time</label><input name="time" placeholder="10:00" required></div>
        <div><label>Type</label><input name="session_type" value="Regular"></div></div>
        <button>Add to Schedule</button></form></div>
        """
    
    return page(f"""<h1>Schedule</h1><p class="muted" style="margin:0 0 24px">Plan sessions in advance (defaults to tomorrow)</p>
    {admin_controls}
    <div class="card"><h3>Schedule for {target}</h3>
    <form method="get" style="margin-bottom:16px"><input type="date" name="date" value="{target}" style="max-width:200px"><button style="margin-left:8px">View</button></form>
    <table><tr><th>Child</th><th>Dept</th><th>Therapist</th><th>Time</th><th>Status</th></tr>{rows or '<tr><td colspan=5 class="muted">No sessions scheduled</td></tr>'}</table></div>""")

@app.route("/session_log", methods=["GET", "POST"])
@login_required("admin", "manager", "frontoffice", "therapist")
def session_log():
    if request.method == "POST":
        log = SessionLog(child_id=int(request.form["child_id"]),
                         department=request.form["department"],
                         therapist_id=int(request.form["therapist_id"]),
                         date=datetime.date.fromisoformat(request.form.get("date") or datetime.date.today().isoformat()),
                         scheduled_time=request.form.get("scheduled_time"),
                         status=request.form["status"],
                         rate=float(request.form.get("rate") or 0),
                         cancellation_reason=request.form.get("cancellation_reason"),
                         additional=request.form.get("additional") == "on",
                         payment_status=request.form.get("payment_status", "Unpaid"),
                         notes=request.form.get("notes"))
        db.session.add(log)
        if log.status == "Completed" and log.additional:
            add_alert("Additional Sessions", f"Additional session for {db.session.get(Child, log.child_id).child_name}", log.child_id)
        if log.status and "Cancel" in log.status:
            add_alert("Cancellation", f"Cancellation: {db.session.get(Child, log.child_id).child_name}", log.child_id)
        db.session.commit(); flash("Session logged"); return redirect(url_for("session_log"))
    
    if session["role"] == "therapist":
        dept = session.get("dept")
        logs = SessionLog.query.filter_by(department=dept).order_by(SessionLog.date.desc(), SessionLog.id.desc()).limit(100).all()
    else:
        logs = SessionLog.query.order_by(SessionLog.date.desc(), SessionLog.id.desc()).limit(100).all()
        
    kids = Child.query.order_by(Child.child_name).all()
    ths = User.query.filter_by(role="therapist").all()
    dept = "".join(f"<option>{d}</option>" for d in DEPTS)
    kid_opts = "".join(f'<option value="{k.id}">{k.child_name}</option>' for k in kids)
    th_opts = "".join(f'<option value="{t.id}">{t.full_name or t.username}</option>' for t in ths)
    st_opts = "".join(f"<option>{s}</option>" for s in ["Completed", "Cancelled by parent", "Cancelled by centre", "No-show", "Rescheduled", "Leave", "Additional"])
    
    show_finance = session["role"] in ['admin', 'manager']
    form_finance = ""
    th_finance = ""
    
    if show_finance:
        form_finance = f"""
        <div><label>Rate</label><input name="rate" type="number" step="0.01" value="0"></div>
        <div><label>Payment Status</label><select name="payment_status"><option>Unpaid</option><option>Paid</option><option>Partial</option></select></div>"""
        th_finance = "<th>Rate</th><th>Payment</th>"
        
    rows = ""
    for l in logs:
        td_finance = ""
        if show_finance:
            td_finance = f"<td>{(l.rate or 0):.0f}</td><td>{l.payment_status}</td>"
            
        rows += f'<tr><td>{l.date}</td><td>{db.session.get(Child, l.child_id).child_name}</td><td>{l.department}</td><td>{l.status}</td>{td_finance}<td>{"Yes" if l.additional else "No"}</td></tr>'

    return page(f"""<h1>Session Log</h1><p class="muted" style="margin:0 0 24px">Record what actually happened for every session</p>
    <div class="card"><h3>Log a Session</h3><form method="post">
    <div class="row"><div><label>Child</label><select name="child_id">{kid_opts}</select></div>
    <div><label>Department</label><select name="department">{dept}</select></div>
    <div><label>Therapist</label><select name="therapist_id">{th_opts}</select></div>
    <div><label>Date</label><input type="date" name="date" value="{datetime.date.today().isoformat()}"></div>
    <div><label>Time</label><input name="scheduled_time" placeholder="10:00"></div>
    <div><label>Status</label><select name="status">{st_opts}</select></div>
    {form_finance}</div>
    <div class="row"><div><label>Cancellation Reason</label><input name="cancellation_reason"></div>
    <div><label>Additional Session?</label><div style="padding-top:10px"><input type="checkbox" name="additional"></div></div></div>
    <p><label>Notes</label><textarea name="notes"></textarea></p>
    <button>Log Session</button></form></div>
    <div class="card"><h3>Recent Sessions</h3><table>
    <tr><th>Date</th><th>Child</th><th>Dept</th><th>Status</th>{th_finance}<th>Additional</th></tr>{rows or '<tr><td colspan=6 class="muted">No sessions yet</td></tr>'}</table></div>""")

@app.route("/plans", methods=["GET", "POST"])
@login_required("admin", "manager", "frontoffice")
def plans():
    month = request.args.get("month") or datetime.date.today().strftime("%Y-%m")
    if request.method == "POST":
        p = MonthlyPlan(child_id=int(request.form["child_id"]),
                        month=request.form["month"],
                        department=request.form["department"],
                        planned_sessions=int(request.form.get("planned_sessions") or 0),
                        carry_forward=int(request.form.get("carry_forward") or 0),
                        rate=float(request.form.get("rate") or 0),
                        planned_amount=float(request.form.get("planned_amount") or 0),
                        paid_amount=float(request.form.get("paid_amount") or 0))
        db.session.add(p); db.session.commit(); flash("Plan saved"); return redirect(url_for("plans", month=month))
    ps = MonthlyPlan.query.filter_by(month=month).all()
    kids = Child.query.order_by(Child.child_name).all()
    kid_opts = "".join(f'<option value="{k.id}">{k.child_name}</option>' for k in kids)
    dept = "".join(f"<option>{d}</option>" for d in DEPTS)
    
    show_finance = session["role"] in ['admin', 'manager']
    form_finance = ""
    th_finance = ""
    if show_finance:
        form_finance = f"""
        <div><label>Rate</label><input name="rate" type="number" step="0.01" value="0"></div>
        <div><label>Planned Amount</label><input name="planned_amount" type="number" step="0.01" value="0"></div>
        <div><label>Paid Amount</label><input name="paid_amount" type="number" step="0.01" value="0"></div>"""
        th_finance = "<th>Rate</th><th>Paid</th>"

    rows = ""
    for p in ps:
        done = SessionLog.query.filter(SessionLog.child_id == p.child_id, SessionLog.department == p.department,
            func.strftime("%Y-%m", SessionLog.date) == p.month, SessionLog.status == "Completed",
            SessionLog.additional == False).count()
        total = p.planned_sessions + p.carry_forward
        remaining = max(total - done, 0)
        extra = SessionLog.query.filter(SessionLog.child_id == p.child_id, SessionLog.department == p.department,
            func.strftime("%Y-%m", SessionLog.date) == p.month, SessionLog.status == "Completed",
            SessionLog.additional == True).count()
            
        td_finance = ""
        if show_finance:
            td_finance = f"<td>{(p.rate or 0):.0f}</td><td>{(p.paid_amount or 0):.0f}</td>"
            
        rows += f'<tr><td>{db.session.get(Child, p.child_id).child_name}</td><td>{p.department}</td><td>{p.planned_sessions}</td><td>{p.carry_forward}</td><td>{total}</td><td>{done}</td><td>{remaining}</td><td>{extra}</td>{td_finance}</tr>'
        
    return page(f"""<h1>Monthly Plans</h1><p class="muted" style="margin:0 0 24px">Advance payment plans and live session balances</p>
    <div class="card"><h3>Add / Update Plan</h3><form method="post">
    <div class="row"><div><label>Child</label><select name="child_id">{kid_opts}</select></div>
    <div><label>Month</label><input name="month" value="{month}" placeholder="YYYY-MM"></div>
    <div><label>Department</label><select name="department">{dept}</select></div>
    <div><label>Planned Sessions</label><input name="planned_sessions" type="number" value="0"></div>
    <div><label>Carry Forward</label><input name="carry_forward" type="number" value="0"></div>
    {form_finance}</div>
    <button>Save Plan</button></form></div>
    <div class="card"><h3>Plans for {month}</h3>
    <form method="get" style="margin-bottom:16px"><input name="month" value="{month}" style="max-width:200px"><button style="margin-left:8px">View</button></form>
    <table><tr><th>Child</th><th>Dept</th><th>Planned</th><th>Carry</th><th>Total</th><th>Done</th><th>Remaining</th><th>Extra</th>{th_finance}</tr>{rows or '<tr><td colspan=10 class="muted">No plans for this month</td></tr>'}</table></div>""")

@app.route("/progress_notes", methods=["GET", "POST"])
@login_required("therapist", "admin", "manager")
def progress_notes():
    if request.method == "POST":
        n = ProgressNote(child_id=int(request.form["child_id"]),
                         department=request.form["department"],
                         therapist_id=session["uid"],
                         week_start=datetime.date.fromisoformat(request.form.get("week_start") or datetime.date.today().isoformat()),
                         goals=request.form.get("goals"), progress=request.form.get("progress"),
                         concerns=request.form.get("concerns"), difficulties=request.form.get("difficulties"),
                         recommendations=request.form.get("recommendations"), other=request.form.get("other"))
        db.session.add(n); db.session.commit(); flash("Note submitted"); return redirect(url_for("progress_notes"))
    
    if session["role"] == "therapist":
        dept = session.get("dept")
        q = ProgressNote.query.filter_by(department=dept).order_by(ProgressNote.id.desc()).all()
    else:
        q = ProgressNote.query.order_by(ProgressNote.id.desc()).all()
        
    kids = Child.query.order_by(Child.child_name).all()
    kid_opts = "".join(f'<option value="{k.id}">{k.child_name}</option>' for k in kids)
    dept = "".join(f"<option>{d}</option>" for d in DEPTS)
    rows = "".join(f'<tr><td>{db.session.get(Child, n.child_id).child_name}</td><td>{n.department}</td><td>{n.week_start}</td><td>{n.status}</td></tr>' for n in q)
    return page(f"""<h1>Weekly Progress Notes</h1><p class="muted" style="margin:0 0 24px">Submit by Monday for each assigned child</p>
    <div class="card"><h3>Submit Note</h3><form method="post">
    <div class="row"><div><label>Child</label><select name="child_id">{kid_opts}</select></div>
    <div><label>Department</label><select name="department">{dept}</select></div>
    <div><label>Week Starting</label><input type="date" name="week_start" value="{datetime.date.today().isoformat()}"></div></div>
    <p><label>Goals Addressed</label><textarea name="goals"></textarea></p>
    <p><label>Progress</label><textarea name="progress"></textarea></p>
    <p><label>Concerns</label><textarea name="concerns"></textarea></p>
    <p><label>Difficulties</label><textarea name="difficulties"></textarea></p>
    <p><label>Recommendations</label><textarea name="recommendations"></textarea></p>
    <p><label>Other</label><textarea name="other"></textarea></p>
    <button>Submit Note</button></form></div>
    <div class="card"><h3>Recent Notes</h3><table><tr><th>Child</th><th>Dept</th><th>Week</th><th>Status</th></tr>{rows or '<tr><td colspan=4 class="muted">None yet</td></tr>'}</table></div>""")

@app.route("/weekly_review", methods=["GET", "POST"])
@login_required("admin", "manager", "clinical")
def weekly_review():
    if request.method == "POST":
        n = db.session.get(ProgressNote, int(request.form["note_id"]))
        if session["role"] == "clinical": n.clinical_comment = request.form["comment"]
        else: n.manager_comment = request.form["comment"]
        n.status = request.form["status"]
        db.session.commit(); flash("Reviewed"); return redirect(url_for("weekly_review"))
    q = ProgressNote.query.order_by(ProgressNote.id.desc()).all()
    rows = ""
    for n in q:
        rows += f"""<tr><td>{db.session.get(Child, n.child_id).child_name}</td><td>{n.department}</td><td>{n.week_start}</td>
        <td>{(n.progress or "")[:120]}</td><td>{n.status}</td>
        <td><form method="post"><input type="hidden" name="note_id" value="{n.id}">
        <textarea name="comment" placeholder="Comment">{n.manager_comment or n.clinical_comment or ""}</textarea>
        <select name="status" style="margin-top:6px"><option>Reviewed</option><option>Requires Attention</option><option>Pending</option></select>
        <button style="margin-top:6px">Save</button></form></td></tr>"""
    return page(f"""<h1>Weekly Review</h1><p class="muted" style="margin:0 0 24px">Review therapist notes and flag concerns</p>
    <div class="card"><table>
    <tr><th>Child</th><th>Dept</th><th>Week</th><th>Progress</th><th>Status</th><th>Review</th></tr>{rows or '<tr><td colspan=6 class="muted">No notes yet</td></tr>'}</table></div>""")

@app.route("/goal_reviews", methods=["GET", "POST"])
@login_required("admin", "manager", "clinical")
def goal_reviews():
    if request.method == "POST":
        gr = GoalReview(goal_id=int(request.form["goal_id"]),
                        month=request.form.get("month") or datetime.date.today().strftime("%Y-%m"),
                        current_progress=request.form.get("current_progress"),
                        improving=request.form.get("improving") == "on",
                        not_improving=request.form.get("not_improving") == "on",
                        achieved=request.form.get("achieved") == "on",
                        needs_modification=request.form.get("needs_modification") == "on",
                        new_recommendations=request.form.get("new_recommendations"))
        db.session.add(gr)
        g = db.session.get(GoalSheet, gr.goal_id); g.review_status = "Reviewed"
        db.session.commit(); flash("Review saved"); return redirect(url_for("goal_reviews"))
    goals = GoalSheet.query.all()
    goal_opts = "".join(f'<option value="{g.id}">{db.session.get(Child, g.child_id).child_name} — {g.goal[:40]}</option>' for g in goals)
    revs = GoalReview.query.order_by(GoalReview.id.desc()).all()
    rows = "".join(f'<tr><td>{db.session.get(Child, db.session.get(GoalSheet, r.goal_id).child_id).child_name}</td><td>{r.month}</td><td>{r.current_progress or ""}</td><td>{"Yes" if r.improving else ""}</td><td>{"Yes" if r.achieved else ""}</td></tr>' for r in revs)
    return page(f"""<h1>Goal Reviews</h1><p class="muted" style="margin:0 0 24px">Monthly progress review of 3-month goals</p>
    <div class="card"><h3>Add Review</h3><form method="post">
    <div class="row"><div><label>Goal</label><select name="goal_id">{goal_opts}</select></div>
    <div><label>Month</label><input name="month" value="{datetime.date.today().strftime('%Y-%m')}"></div></div>
    <p><label>Current Progress</label><textarea name="current_progress"></textarea></p>
    <div class="row" style="align-items:center;gap:24px;padding:8px 0">
      <label style="margin:0;display:flex;gap:6px;align-items:center;font-size:14px"><input type="checkbox" name="improving"> Improving</label>
      <label style="margin:0;display:flex;gap:6px;align-items:center;font-size:14px"><input type="checkbox" name="not_improving"> Not Improving</label>
      <label style="margin:0;display:flex;gap:6px;align-items:center;font-size:14px"><input type="checkbox" name="achieved"> Achieved</label>
      <label style="margin:0;display:flex;gap:6px;align-items:center;font-size:14px"><input type="checkbox" name="needs_modification"> Needs Modification</label>
    </div>
    <p><label>New Recommendations</label><textarea name="new_recommendations"></textarea></p>
    <button>Save Review</button></form></div>
    <div class="card"><h3>Past Reviews</h3><table><tr><th>Child</th><th>Month</th><th>Progress</th><th>Improving</th><th>Achieved</th></tr>{rows or '<tr><td colspan=5 class="muted">None yet</td></tr>'}</table></div>""")

@app.route("/alerts")
@login_required("admin", "manager", "clinical", "frontoffice")
def alerts():
    q = Alert.query.order_by(Alert.id.desc()).limit(200).all()
    for a in q: a.read = True
    db.session.commit()
    rows = "".join(f'<tr><td>{a.created.strftime("%Y-%m-%d %H:%M")}</td><td>{a.type}</td><td>{a.message}</td></tr>' for a in q)
    return page(f"<h1>Alerts</h1><p class='muted' style='margin:0 0 24px'>All recent system events</p><div class='card'><table><tr><th>When</th><th>Type</th><th>Message</th></tr>{rows or '<tr><td colspan=3 class=muted>None</td></tr>'}</table></div>")

@app.route("/parent")
@login_required("parent")
def parent_portal():
    u = cu()
    kids = Child.query.filter_by(parent_user_id=u.id).all()
    if not kids:
        return page("<div class='card'><p>No child linked to your account. Please contact the centre.</p></div>")
    html = "<h1>My Child</h1><p class='muted' style='margin:0 0 24px'>Sessions and balances at a glance</p>"
    for c in kids:
        sch = Schedule.query.filter_by(child_id=c.id, date=datetime.date.today()).all()
        plans = MonthlyPlan.query.filter_by(child_id=c.id).order_by(MonthlyPlan.month.desc()).all()
        html += f"""<div class="card"><h2>{c.child_name}</h2>
        <h3>Today's Sessions</h3><table><tr><th>Dept</th><th>Time</th><th>Status</th></tr>
        {''.join(f'<tr><td>{s.department}</td><td>{s.time}</td><td>{s.status}</td></tr>' for s in sch) or '<tr><td colspan=3 class="muted">No sessions today</td></tr>'}</table>
        <h3 style="margin-top:24px">Session Balances</h3><table>
        <tr><th>Dept</th><th>Planned</th><th>Carry</th><th>Total</th><th>Done</th><th>Remaining</th></tr>"""
        for p in plans:
            done = SessionLog.query.filter(SessionLog.child_id == c.id, SessionLog.department == p.department,
                func.strftime("%Y-%m", SessionLog.date) == p.month, SessionLog.status == "Completed",
                SessionLog.additional == False).count()
            rem = max(p.planned_sessions + p.carry_forward - done, 0)
            html += f"<tr><td>{p.department}</td><td>{p.planned_sessions}</td><td>{p.carry_forward}</td><td>{p.planned_sessions + p.carry_forward}</td><td>{done}</td><td>{rem}</td></tr>"
        html += "</table></div>"
    return page(html)

# ================= SEED & RUN =================
def seed():
    if User.query.count() > 0: return
    
    demo = [
        # ADMINS
        ("Rizwan naushad", "Chowaraferry@2956", "admin", "Rizwan Naushad", None),
        ("Reyan Naushad", "Chowaraferry@2956", "admin", "Reyan Naushad", None),
        ("Nilufer Naushad", "Chowaraferry@2956", "admin", "Nilufer Naushad", None),
        
        # MANAGER
        ("Manager", "Petals@683105", "manager", "Manager", None),
        
        # THERAPISTS (Department locked)
        ("occupational therapist", "OT@43376", "therapist", "Occupational Therapist", "OT"),
        ("behavioural therapist", "BT@43376", "therapist", "Behavioural Therapist", "BT"),
        ("Special Education", "SE@43376", "therapist", "Special Education", "Special Ed"),
        ("physiotherapy", "PT@43376", "therapist", "Physiotherapy", "Physiotherapy"),
        ("speech therapy", "ST@43376", "therapist", "Speech Therapy", "Speech"),
    ]
    
    users = {}
    for un, pw, role, name, dept in demo:
        u = User(username=un, role=role, full_name=name, department=dept)
        u.set_password(pw)
        db.session.add(u); users[un] = u
    db.session.flush()
    
    c = Child(parent_name="Mrs. Rao", child_name="Aarav", dob="2020-03-15", contact="9999999999",
              primary_concern="Speech delay", required_dept="Speech", source="WhatsApp",
              status="Therapy Started", parent_user_id=None,
              questionnaire_sent=True, questionnaire_submitted=True)
    db.session.add(c); db.session.flush()
    
    m = datetime.date.today().strftime("%Y-%m")
    db.session.add(MonthlyPlan(child_id=c.id, month=m, department="Speech", planned_sessions=14, rate=800, planned_amount=11200, paid_amount=11200))
    db.session.add(MonthlyPlan(child_id=c.id, month=m, department="BT", planned_sessions=13, rate=900, planned_amount=11700, paid_amount=11700))
    db.session.add(MonthlyPlan(child_id=c.id, month=m, department="OT", planned_sessions=12, rate=700, planned_amount=8400, paid_amount=8400))
    
    db.session.add(Schedule(child_id=c.id, department="Speech", therapist_id=users["speech therapy"].id, date=datetime.date.today(), time="10:00"))
    db.session.add(Schedule(child_id=c.id, department="OT", therapist_id=users["occupational therapist"].id, date=datetime.date.today(), time="11:00"))
    db.session.commit()

# ================= DATABASE INITIALIZATION (Runs on import) =================
# This runs when Gunicorn imports the app, ensuring tables exist.
with app.app_context():
    db.create_all()
    seed()

# ================= RUN LOCALLY =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)