#!/usr/bin/env python3
"""
Athar (أثر) - Wikimedia Community Dashboard
Repository Scaffolding & Initial Template Generator
====================================================
This script creates the entire project folder structure and writes production-ready
starter files for Day 0 of the hackathon.

Usage:
    cd /path/to/Athar
    python3 setup_repo.py
"""

import os
import sys

FILES = {}

# ==============================================================================
# 1. ROOT CONFIGURATION & TOOLFORGE SPECIFICATION FILES
# ==============================================================================

FILES[".gitignore"] = """# Python byte-code & virtual environments
__pycache__/
*.py[cod]
*$py.class
venv/
.venv/
env/

# Environment secrets & local SQLite databases
.env
dev.db
*.sqlite3

# Test caches & coverage
.pytest_cache/
.coverage
htmlcov/

# IDE / Operating System artifacts
.DS_Store
.vscode/
.idea/
"""

FILES[".env.example"] = """# Flask Application Settings
SECRET_KEY=change-this-to-a-secure-random-token-in-production
ENV=development
DEBUG=True

# Authentication Settings
# Set MOCK_AUTH=True to bypass Wikimedia OAuth during local development
MOCK_AUTH=True
MOCK_USERNAME=MoroccoVolunteer

# Live Wikimedia OAuth 2.0 Credentials (Provided by Supervisor on Day 2)
OAUTH_CLIENT_ID=your-meta-client-id-here
OAUTH_CLIENT_SECRET=your-meta-client-secret-here
OAUTH_REDIRECT_URI=http://127.0.0.1:5000/oauth/callback

# Community & Data Customization (Generalizable Settings)
COMMUNITY_NAME=Wikimedia Morocco
META_ROSTER_PAGE=Wikimedia_MA/Members
DEFAULT_TARGET_WIKI=ar.wikipedia.org
CONTACT_EMAIL=contact@wikimedia.ma

# Production Toolforge Database Credentials (Auto-injected on Toolforge)
TOOL_NAME=athar
TOOL_DB_USER=
TOOL_DB_PASS=
"""

FILES["requirements.txt"] = """Flask==3.0.3
Flask-SQLAlchemy==3.1.1
Flask-WTF==1.2.1
Authlib==1.3.1
requests==2.32.3
mwparserfromhell==0.6.6
bleach==6.1.0
PyMySQL==1.1.1
cryptography==42.0.8
python-dotenv==1.0.1
gunicorn==22.0.0
pytest==8.2.2
"""

FILES["Procfile"] = """web: gunicorn -w 4 -b 0.0.0.0:8000 run:app
"""

FILES["jobs.yaml"] = """# Toolforge Scheduled Kubernetes Job for automated metrics ingestion
- name: stats-sync
  command: python3 scripts/sync_data.py
  image: python3.11
  schedule: "0 */4 * * *"
  emails: none
"""

FILES["config.py"] = """import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-replace-in-production")
    ENV = os.getenv("ENV", "development")
    DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1")

    # Community Customization Variables
    COMMUNITY_NAME = os.getenv("COMMUNITY_NAME", "Wikimedia Morocco")
    META_ROSTER_PAGE = os.getenv("META_ROSTER_PAGE", "Wikimedia_MA/Members")
    DEFAULT_TARGET_WIKI = os.getenv("DEFAULT_TARGET_WIKI", "ar.wikipedia.org")
    CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "contact@wikimedia.ma")

    # Wikimedia API User-Agent Policy enforcement
    USER_AGENT = (
        f"AtharDashboard/1.0 (https://athar.toolforge.org; {CONTACT_EMAIL}) "
        "Python-Requests/Flask"
    )

    # Database URI: MariaDB (ToolsDB) on Toolforge; SQLite for local development
    TOOL_NAME = os.getenv("TOOL_NAME", "athar")
    TOOL_DB_USER = os.getenv("TOOL_DB_USER")
    TOOL_DB_PASS = os.getenv("TOOL_DB_PASS")

    if ENV == "production" and TOOL_DB_USER and TOOL_DB_PASS:
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{TOOL_DB_USER}:{TOOL_DB_PASS}"
            f"@tools.db.svc.wikimedia.cloud:3306/s{TOOL_NAME}__main?charset=utf8mb4"
        )
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///dev.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = (ENV == "production")
"""

FILES["run.py"] = """from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
"""

# ==============================================================================
# 2. CORE WEB APPLICATION PACKAGE (app/)
# ==============================================================================

FILES["app/__init__.py"] = """from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from config import Config

db = SQLAlchemy()
csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)

    # Register blueprints
    from app.routes.web import web_bp
    from app.routes.api import api_bp
    from app.oauth import oauth_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(oauth_bp)

    # Create tables locally if SQLite is used
    with app.app_context():
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
            db.create_all()

    return app
"""

FILES["app/models.py"] = """from datetime import datetime
from app import db

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(128), unique=True, nullable=False, index=True)
    is_member = db.Column(db.Boolean, default=True, nullable=False)
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_synced = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    snapshots = db.relationship("StatSnapshot", backref="user", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username} member={self.is_member}>"


class StatSnapshot(db.Model):
    __tablename__ = "stat_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    total_edits = db.Column(db.Integer, default=0, nullable=False)
    home_wiki = db.Column(db.String(64), default="ar.wikipedia.org")
    wiki_breakdown = db.Column(db.JSON, nullable=True)  # {"ar.wikipedia": 120, "commons": 45}
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<StatSnapshot user_id={self.user_id} edits={self.total_edits}>"


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)  # Bleach sanitized HTML
    project_type = db.Column(db.String(64), default="Workshop", nullable=False)
    target_wiki = db.Column(db.String(64), default="ar.wikipedia.org", nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(32), default="In Progress", nullable=False)  # Planned, In Progress, Completed

    # Ownership & Roles
    lead_organizer = db.Column(db.String(128), nullable=False)
    co_organizers = db.Column(db.JSON, nullable=True)  # ["UserA", "UserB"]
    is_contest = db.Column(db.Boolean, default=False, nullable=False)
    jury_members = db.Column(db.JSON, nullable=True)   # ["Jury1", "Jury2"]

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "project_type": self.project_type,
            "target_wiki": self.target_wiki,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status,
            "lead_organizer": self.lead_organizer,
            "co_organizers": self.co_organizers or [],
            "is_contest": self.is_contest,
            "jury_members": self.jury_members or [],
            "created_at": self.created_at.isoformat()
        }
"""

FILES["app/oauth.py"] = """import os
from functools import wraps
from flask import Blueprint, session, redirect, url_for, request, abort, current_app

oauth_bp = Blueprint("oauth", __name__)

def is_mock_enabled():
    return os.getenv("MOCK_AUTH", "False").lower() in ("true", "1", "yes")

def get_current_user():
    # Development bypass: Auto-inject test user if MOCK_AUTH is enabled
    if is_mock_enabled() and "username" not in session:
        session["username"] = os.getenv("MOCK_USERNAME", "MoroccoVolunteer")
        session["is_member"] = True
    return session.get("username")

def member_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = get_current_user()
        if not username:
            return redirect(url_for("oauth.login"))
        if not session.get("is_member", False):
            abort(403, description="Access restricted to verified community members.")
        return f(*args, **kwargs)
    return decorated_function

def project_editor_required(f):
    @wraps(f)
    def decorated_function(project_id, *args, **kwargs):
        from app.models import Project
        project = Project.query.get_or_404(project_id)
        current_user = get_current_user()
        if not current_user:
            return redirect(url_for("oauth.login"))

        co_orgs = project.co_organizers or []
        if current_user != project.lead_organizer and current_user not in co_orgs:
            abort(403, description="Only the lead organizer or co-organizers can edit this project.")
        return f(project_id, *args, **kwargs)
    return decorated_function

@oauth_bp.route("/login")
def login():
    if is_mock_enabled():
        session["username"] = os.getenv("MOCK_USERNAME", "MoroccoVolunteer")
        session["is_member"] = True
        return redirect(url_for("web.dashboard"))
    # In live mode (Student 2 will plug Authlib redirect here on Day 2)
    return redirect("https://meta.wikimedia.org/w/index.php?title=Special:OAuth/authorize")

@oauth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.dashboard"))

@oauth_bp.route("/oauth/callback")
def callback():
    # Placeholder for live Wikimedia token exchange (Day 2)
    session["username"] = "MoroccoVolunteer"
    session["is_member"] = True
    return redirect(url_for("web.dashboard"))
"""

FILES["app/routes/__init__.py"] = ""

FILES["app/routes/web.py"] = """from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models import Project, User, StatSnapshot
from app.oauth import member_required, project_editor_required, get_current_user
from app import db
import bleach

web_bp = Blueprint("web", __name__)

@web_bp.route("/")
def dashboard():
    user = get_current_user()
    projects = Project.query.order_by(Project.created_at.desc()).limit(10).all()
    total_members = User.query.filter_by(is_member=True).count()
    return render_template("dashboard.html", projects=projects, total_members=total_members, current_user=user)

@web_bp.route("/project/new", methods=["GET", "POST"])
@member_required
def create_project():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        raw_description = request.form.get("description", "").strip()
        project_type = request.form.get("project_type", "Workshop")
        target_wiki = request.form.get("target_wiki", "ar.wikipedia.org")
        status = request.form.get("status", "In Progress")
        co_orgs_raw = request.form.get("co_organizers", "")
        is_contest = bool(request.form.get("is_contest"))
        jury_raw = request.form.get("jury_members", "")

        # Sanitize HTML description against stored XSS
        safe_description = bleach.clean(
            raw_description,
            tags=["p", "b", "i", "strong", "em", "ul", "ol", "li", "a", "br"],
            attributes={"a": ["href", "title"]},
            strip=True
        )

        co_organizers = [u.strip() for u in co_orgs_raw.split(",") if u.strip()]
        jury_members = [j.strip() for j in jury_raw.split(",") if j.strip()] if is_contest else []

        new_project = Project(
            title=title,
            description=safe_description,
            project_type=project_type,
            target_wiki=target_wiki,
            status=status,
            lead_organizer=session.get("username"),
            co_organizers=co_organizers,
            is_contest=is_contest,
            jury_members=jury_members
        )
        db.session.add(new_project)
        db.session.commit()
        flash("Project activity created successfully!", "success")
        return redirect(url_for("web.dashboard"))

    return render_template("project_form.html", project=None)

@web_bp.route("/project/<int:project_id>/edit", methods=["GET", "POST"])
@project_editor_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    if request.method == "POST":
        project.title = request.form.get("title", "").strip()
        raw_description = request.form.get("description", "").strip()
        project.description = bleach.clean(
            raw_description,
            tags=["p", "b", "i", "strong", "em", "ul", "ol", "li", "a", "br"],
            attributes={"a": ["href", "title"]},
            strip=True
        )
        project.project_type = request.form.get("project_type", project.project_type)
        project.target_wiki = request.form.get("target_wiki", project.target_wiki)
        project.status = request.form.get("status", project.status)
        project.is_contest = bool(request.form.get("is_contest"))
        
        co_orgs_raw = request.form.get("co_organizers", "")
        project.co_organizers = [u.strip() for u in co_orgs_raw.split(",") if u.strip()]
        
        jury_raw = request.form.get("jury_members", "")
        project.jury_members = [j.strip() for j in jury_raw.split(",") if j.strip()] if project.is_contest else []

        db.session.commit()
        flash("Project updated successfully!", "success")
        return redirect(url_for("web.dashboard"))

    return render_template("project_form.html", project=project)

@web_bp.route("/export")
def export_view():
    return render_template("export.html")
"""

FILES["app/routes/api.py"] = """import csv
import io
from flask import Blueprint, jsonify, request, Response, session
from app.models import Project, User, StatSnapshot
from app.oauth import member_required, get_current_user
from app import db
import bleach

api_bp = Blueprint("api", __name__)

@api_bp.route("/stats")
def get_stats():
    total_members = User.query.filter_by(is_member=True).count()
    total_projects = Project.query.count()
    
    # Calculate aggregate edits across snapshots
    latest_snapshots = StatSnapshot.query.order_by(StatSnapshot.recorded_at.desc()).limit(100).all()
    total_edits = sum(s.total_edits for s in latest_snapshots)

    return jsonify({
        "total_members": total_members,
        "total_projects": total_projects,
        "total_edits": total_edits
    })

@api_bp.route("/projects", methods=["GET"])
def list_projects():
    status = request.args.get("status")
    project_type = request.args.get("type")
    
    query = Project.query
    if status:
        query = query.filter_by(status=status)
    if project_type:
        query = query.filter_by(project_type=project_type)
        
    projects = query.order_by(Project.created_at.desc()).all()
    return jsonify([p.to_dict() for p in projects])

@api_bp.route("/export")
def export_csv():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row formatted for Wikimedia reporting
    writer.writerow(["ID", "Title", "Type", "Target Wiki", "Status", "Lead Organizer", "Co-Organizers", "Is Contest", "Created At"])
    for p in projects:
        writer.writerow([
            p.id,
            p.title,
            p.project_type,
            p.target_wiki,
            p.status,
            p.lead_organizer,
            ", ".join(p.co_organizers or []),
            p.is_contest,
            p.created_at.strftime("%Y-%m-%d")
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=athar_projects.csv"}
    )
"""

# ==============================================================================
# 3. CODEX TEMPLATES & STATIC STYLES
# ==============================================================================

FILES["app/templates/base.html"] = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ config.COMMUNITY_NAME }} — أثر (Athar)</title>
    <!-- Wikimedia Codex CSS Distribution -->
    <link rel="stylesheet" href="https://tools-static.wmflabs.org/cdnjs/ajax/libs/codex/0.17.1/codex.style.min.css">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/codex.style.css') }}">
    <!-- Chart.js for data visualization -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="cdx-body">
    <header class="cdx-header">
        <div class="header-container">
            <a href="{{ url_for('web.dashboard') }}" class="brand-title">
                <span class="brand-badge">أثر</span> {{ config.COMMUNITY_NAME }}
            </a>
            <nav class="nav-links">
                <a href="{{ url_for('web.dashboard') }}" class="cdx-button cdx-button--quiet">لوحة القيادة (Dashboard)</a>
                <a href="{{ url_for('web.export_view') }}" class="cdx-button cdx-button--quiet">التقارير (Export)</a>
                {% if session.get('username') %}
                    <a href="{{ url_for('web.create_project') }}" class="cdx-button cdx-button--action cdx-button--weight-primary">+ إضافة نشاط</a>
                    <span class="user-greeting">مرحباً، <strong>{{ session.get('username') }}</strong></span>
                    <a href="{{ url_for('oauth.logout') }}" class="cdx-button cdx-button--quiet">خروج</a>
                {% else %}
                    <a href="{{ url_for('oauth.login') }}" class="cdx-button cdx-button--action cdx-button--weight-primary">تسجيل الدخول بـ Wikimedia</a>
                {% endif %}
            </nav>
        </div>
    </header>

    <main class="main-content">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="cdx-message cdx-message--{{ category }}">
                            <div class="cdx-message__content">{{ message }}</div>
                        </div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </main>

    <footer class="cdx-footer">
        <p>أثر (Athar) — أداة مجتمعية مفتوحة المصدر تستضيفها <a href="https://toolforge.org">Wikimedia Toolforge</a>.</p>
    </footer>

    {% block scripts %}{% endblock %}
</body>
</html>
"""

FILES["app/templates/dashboard.html"] = """{% extends "base.html" %}

{% block content %}
<section class="kpi-grid">
    <div class="kpi-card">
        <span class="kpi-title">أعضاء المجتمع المسجلون</span>
        <span class="kpi-value" id="kpi-members">{{ total_members }}</span>
    </div>
    <div class="kpi-card">
        <span class="kpi-title">المشاريع الموثقة</span>
        <span class="kpi-value" id="kpi-projects">{{ projects|length }}</span>
    </div>
    <div class="kpi-card">
        <span class="kpi-title">تحديث الإحصائيات التلقائي</span>
        <span class="kpi-value kpi-green">كل 4 ساعات</span>
    </div>
</section>

<section class="content-split">
    <div class="projects-list-container">
        <h2>أحدث الأنشطة والمشاريع المجتمعية</h2>
        {% if projects %}
            <div class="projects-grid">
                {% for p in projects %}
                    <article class="project-card">
                        <div class="project-header">
                            <span class="badge badge-type">{{ p.project_type }}</span>
                            <span class="badge badge-status">{{ p.status }}</span>
                        </div>
                        <h3>{{ p.title }}</h3>
                        <div class="project-body">{{ p.description|safe }}</div>
                        <div class="project-meta">
                            <span>المنظم: <strong>{{ p.lead_organizer }}</strong></span>
                            {% if p.is_contest %}<span class="badge badge-contest">مسابقة / تحكيم</span>{% endif %}
                        </div>
                    </article>
                {% endfor %}
            </div>
        {% else %}
            <div class="empty-state">
                <p>لا توجد أنشطة مسجلة حالياً. سجل دخولك لإضافة أول مشروع!</p>
            </div>
        {% endif %}
    </div>

    <aside class="charts-sidebar">
        <h2>توزيع الأنشطة</h2>
        <canvas id="projectsChart" width="300" height="300"></canvas>
    </aside>
</section>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/charts.js') }}"></script>
{% endblock %}
"""

FILES["app/templates/project_form.html"] = """{% extends "base.html" %}

{% block content %}
<div class="form-container">
    <h2>{% if project %}تعديل النشاط{% else %}تسجيل نشاط مجتمعي جديد{% endif %}</h2>
    <p class="form-subtitle">سجل فعاليات ورشات التحرير، مسابقات التصوير، أو مشاريع ويكي بيانات.</p>

    <form method="POST" class="cdx-form">
        <!-- Flask-WTF CSRF Token -->
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>

        <div class="form-group">
            <label for="title" class="cdx-label">عنوان النشاط / المشروع</label>
            <input type="text" id="title" name="title" required class="cdx-text-input" 
                   value="{{ project.title if project else '' }}" placeholder="مثال: ورشة تحرير ويكيبيديا بجامعة الرباط">
        </div>

        <div class="form-row">
            <div class="form-group flex-1">
                <label for="project_type" class="cdx-label">نوع النشاط</label>
                <select id="project_type" name="project_type" class="cdx-select">
                    <option value="Workshop" {% if project and project.project_type == 'Workshop' %}selected{% endif %}>ورشة تدريبية (Workshop)</option>
                    <option value="Edit-a-thon" {% if project and project.project_type == 'Edit-a-thon' %}selected{% endif %}>ماراثون تحرير (Edit-a-thon)</option>
                    <option value="Photo Walk" {% if project and project.project_type == 'Photo Walk' %}selected{% endif %}>جولة تصوير (Photo Walk)</option>
                    <option value="Outreach" {% if project and project.project_type == 'Outreach' %}selected{% endif %}>شراكة تعليمية (Outreach)</option>
                </select>
            </div>

            <div class="form-group flex-1">
                <label for="target_wiki" class="cdx-label">المشروع المستهدف</label>
                <input type="text" id="target_wiki" name="target_wiki" class="cdx-text-input"
                       value="{{ project.target_wiki if project else config.DEFAULT_TARGET_WIKI }}">
            </div>
        </div>

        <div class="form-group">
            <label for="description" class="cdx-label">تفاصيل النشاط (سيتم فحصها أمنياً بـ Bleach)</label>
            <textarea id="description" name="description" rows="5" required class="cdx-textarea"
                      placeholder="اذكر أهداف الورشة، النتائج المتوقعة، والروابط ذات الصلة...">{{ project.description if project else '' }}</textarea>
        </div>

        <div class="form-group">
            <label for="co_organizers" class="cdx-label">منظمون مشاركون (أسماء المستخدمين مفصولة بفاصلة)</label>
            <input type="text" id="co_organizers" name="co_organizers" class="cdx-text-input"
                   value="{{ (project.co_organizers|join(', ')) if project and project.co_organizers else '' }}"
                   placeholder="UserA, UserB">
        </div>

        <div class="form-checkbox-group">
            <input type="checkbox" id="is_contest" name="is_contest" value="1" 
                   {% if project and project.is_contest %}checked{% endif %}
                   onchange="toggleJuryField()">
            <label for="is_contest">هذا النشاط عبارة عن مسابقة أو منافسة (تتطلب لجنة تحكيم)</label>
        </div>

        <div class="form-group" id="jury-group" style="display: {% if project and project.is_contest %}block{% else %}none{% endif %};">
            <label for="jury_members" class="cdx-label">أعضاء لجنة التحكيم (أسماء مفصولة بفاصلة)</label>
            <input type="text" id="jury_members" name="jury_members" class="cdx-text-input"
                   value="{{ (project.jury_members|join(', ')) if project and project.jury_members else '' }}"
                   placeholder="JuryUser1, JuryUser2">
        </div>

        <button type="submit" class="cdx-button cdx-button--action cdx-button--weight-primary">
            {% if project %}حفظ التعديلات{% else %}نشر النشاط المجتمعي{% endif %}
        </button>
    </form>
</div>
{% endblock %}

{% block scripts %}
<script>
function toggleJuryField() {
    const isChecked = document.getElementById('is_contest').checked;
    document.getElementById('jury-group').style.display = isChecked ? 'block' : 'none';
}
</script>
{% endblock %}
"""

FILES["app/templates/export.html"] = """{% extends "base.html" %}

{% block content %}
<div class="export-container">
    <h2>تصدير تقارير الأنشطة المجتمعية (CSV Export)</h2>
    <p>خاص بمنسقي مجموعة المستخدمين لتقديم التقارير الربع سنوية إلى مؤسسة ويكيميديا.</p>

    <div class="export-card">
        <h3>تصدير كافة الأنشطة الحالية</h3>
        <p>تحميل ملف بصيغة CSV يتضمن المعرفات، العناوين، المنظمين، ولجان التحكيم.</p>
        <a href="/api/export" class="cdx-button cdx-button--action cdx-button--weight-primary">
            تحميل البيانات (Download CSV)
        </a>
    </div>
</div>
{% endblock %}
"""

FILES["app/static/css/codex.style.css"] = """/* Custom CSS overrides aligned with Wikimedia Codex tokens */
body {
    background-color: #f8f9fa;
    color: #202122;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Tajawal", sans-serif;
    margin: 0;
}

.header-container {
    max-width: 1100px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 20px;
    border-bottom: 1px solid #c8ccd1;
    background: #ffffff;
}

.brand-title {
    font-size: 1.25rem;
    font-weight: 700;
    text-decoration: none;
    color: #202122;
}

.brand-badge {
    background: #dc2626;
    color: #ffffff;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.9rem;
}

.main-content {
    max-width: 1100px;
    margin: 24px auto;
    padding: 0 20px;
}

.kpi-grid {
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
}

.kpi-card {
    background: #ffffff;
    border: 1px solid #c8ccd1;
    border-radius: 8px;
    padding: 16px 20px;
    flex: 1;
}

.kpi-title {
    display: block;
    font-size: 0.85rem;
    color: #72777d;
}

.kpi-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #202122;
}

.kpi-green {
    color: #16a34a;
}

.content-split {
    display: flex;
    gap: 24px;
}

.projects-list-container {
    flex: 2;
}

.charts-sidebar {
    flex: 1;
    background: #ffffff;
    border: 1px solid #c8ccd1;
    border-radius: 8px;
    padding: 20px;
    height: fit-content;
}

.project-card {
    background: #ffffff;
    border: 1px solid #c8ccd1;
    border-radius: 6px;
    padding: 16px;
    margin-bottom: 12px;
}

.badge {
    font-size: 0.75rem;
    padding: 2px 6px;
    border-radius: 4px;
    font-weight: 600;
}

.badge-type { background: #eaecf0; color: #202122; }
.badge-status { background: #dcfce7; color: #15803d; }
.badge-contest { background: #fee2e2; color: #b91c1c; }

.form-container {
    background: #ffffff;
    border: 1px solid #c8ccd1;
    border-radius: 8px;
    padding: 32px;
    max-width: 700px;
    margin: 0 auto;
}

.cdx-text-input, .cdx-textarea, .cdx-select {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid #a2a9b1;
    border-radius: 4px;
    box-sizing: border-box;
    margin-top: 4px;
    font-family: inherit;
}

.form-group {
    margin-bottom: 16px;
}

.cdx-button {
    padding: 8px 16px;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 600;
    text-decoration: none;
    border: 1px solid #a2a9b1;
}

.cdx-button--weight-primary {
    background: #36c;
    color: #ffffff;
    border-color: #36c;
}
"""

FILES["app/static/js/charts.js"] = """document.addEventListener("DOMContentLoaded", function() {
    const ctx = document.getElementById("projectsChart");
    if (ctx) {
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['ورشات (Workshops)', 'ماراثون تحرير (Edit-a-thons)', 'جولات تصوير (Photo Walks)'],
                datasets: [{
                    data: [12, 19, 7],
                    backgroundColor: ['#16a34a', '#3366cc', '#dc2626']
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        });
    }
});
"""

# ==============================================================================
# 4. INGESTION SCRIPTS & UNIT TESTS
# ==============================================================================

FILES["scripts/parse_members.py"] = """#!/usr/bin/env python3
\"\"\"
Member List Parser for Meta-Wiki
Extracts usernames using mwparserfromhell AST instead of fragile regex.
\"\"\"
import requests
import mwparserfromhell
from config import Config

def fetch_members_from_meta(page_title=None):
    if not page_title:
        page_title = Config.META_ROSTER_PAGE

    url = "https://meta.wikimedia.org/w/api.php"
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "wikitext",
        "format": "json"
    }
    headers = {"User-Agent": Config.USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        raw_wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception as e:
        print(f"[Error] Failed to fetch Meta page: {e}")
        return []

    wikicode = mwparserfromhell.parse(raw_wikitext)
    members = []

    # Extract all wikilinks formatted like [[User:Username|...]]
    for link in wikicode.filter_wikilinks():
        target = str(link.title).strip()
        if target.startswith("User:"):
            clean_user = target.replace("User:", "").split("/")[0].strip()
            if clean_user and clean_user not in members:
                members.append(clean_user)

    return members

if __name__ == "__main__":
    roster = fetch_members_from_meta()
    print(f"Extracted {len(roster)} members: {roster[:5]}...")
"""

FILES["scripts/sync_data.py"] = """#!/usr/bin/env python3
\"\"\"
Scheduled Background Worker for Toolforge
Runs every 4 hours to synchronize member roster and query CentralAuth global stats.
\"\"\"
import requests
from config import Config
from app import create_app, db
from app.models import User, StatSnapshot
from scripts.parse_members import fetch_members_from_meta

def fetch_global_stats(username):
    url = "https://meta.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "meta": "globaluserinfo",
        "guiuser": username,
        "guiprop": "editcount|merged",
        "format": "json"
    }
    headers = {"User-Agent": Config.USER_AGENT}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10).json()
        gui = resp.get("query", {}).get("globaluserinfo", {})
        
        breakdown = {}
        for item in gui.get("merged", []):
            if item.get("editcount", 0) > 0:
                breakdown[item.get("wiki")] = item.get("editcount")

        return {
            "total_edits": gui.get("editcount", 0),
            "home_wiki": gui.get("home", "ar.wikipedia.org"),
            "wiki_breakdown": breakdown
        }
    except Exception as e:
        print(f"[Warning] Could not fetch stats for {username}: {e}")
        return None

def run_sync():
    app = create_app()
    with app.app_context():
        print("[Sync] Fetching member list from Meta-Wiki...")
        usernames = fetch_members_from_meta()
        if not usernames:
            print("[Sync] Retaining existing database cache.")
            return

        for username in usernames:
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(username=username, is_member=True)
                db.session.add(user)
                db.session.flush()

            stats = fetch_global_stats(username)
            if stats:
                snapshot = StatSnapshot(
                    user_id=user.id,
                    total_edits=stats["total_edits"],
                    home_wiki=stats["home_wiki"],
                    wiki_breakdown=stats["wiki_breakdown"]
                )
                db.session.add(snapshot)

        db.session.commit()
        print(f"[Sync] Successfully synchronized {len(usernames)} members to database.")

if __name__ == "__main__":
    run_sync()
"""

FILES["tests/test_parser.py"] = """import unittest
import mwparserfromhell

class TestWikitextParser(unittest.TestCase):
    def test_link_extraction(self):
        sample_wikitext = \"\"\"
        == أعضاء المجموعة ==
        * [[User:RedaMorocco|رضا]]
        * [[User:FatimaWiki|فاطمة]]
        * [[User:TestUser/Sandbox|مسودة]]
        \"\"\"
        code = mwparserfromhell.parse(sample_wikitext)
        users = []
        for link in code.filter_wikilinks():
            target = str(link.title).strip()
            if target.startswith("User:"):
                user = target.replace("User:", "").split("/")[0].strip()
                users.append(user)

        self.assertIn("RedaMorocco", users)
        self.assertIn("FatimaWiki", users)
        self.assertIn("TestUser", users)
        self.assertEqual(len(users), 3)

if __name__ == "__main__":
    unittest.main()
"""

FILES["tests/test_routes.py"] = """import unittest
from app import create_app, db
from app.models import Project

class TestRoutesAndSecurity(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_dashboard_accessible(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Athar", response.data)

    def test_mock_auth_login(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "TestVolunteer"
            sess["is_member"] = True

        response = self.client.get("/project/new")
        self.assertEqual(response.status_code, 200)

if __name__ == "__main__":
    unittest.main()
"""

FILES[".github/PULL_REQUEST_TEMPLATE.md"] = """##  Task Reference
Closes Phabricator Ticket: `T...` (or Task #)

##  Summary of Changes
- Briefly describe what code was added or modified.

##  How to Test Locally
1. Ensure your local environment is synced with `upstream/dev`.
2. Run the application with `MOCK_AUTH=True`.
3. Provide test steps:
   - Step 1:
   - Step 2:

##  Checklist
- [ ] My code targets the `dev` branch (NOT `main`).
- [ ] I tested my feature locally without breaking existing routes.
- [ ] No hardcoded secrets were committed.
"""

FILES["README.md"] = """# أثر (Athar) — Wikimedia Community Dashboard

A lightweight, high-performance community analytics and activity dashboard hosted on **Wikimedia Toolforge**.

---

##  Quickstart for Students (Day 1)

### 1. Clone your Fork
```bash
git clone https://github.com/<your-username>/Athar.git
cd Athar
git remote add upstream https://github.com/<official-org>/Athar.git
git fetch upstream
```

### 2. Set Up Virtual Environment & Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Local Environment
```bash
cp .env.example .env
```
*(Notice that `MOCK_AUTH=True` is enabled by default so you can test project creation immediately!)*

### 4. Run the Application
```bash
python3 run.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

##  Contribution Workflow
Always create feature branches off `dev`:
```bash
git checkout dev
git pull upstream dev
git checkout -b task-<number>-<short-description>
```
Submit your Pull Request targeting `base: dev`.
"""

# ==============================================================================
# 5. EXECUTION & FILE WRITING ENGINE
# ==============================================================================

def build_repository():
    print(" Initializing Athar repository scaffold...")
    for filepath, content in FILES.items():
        dirname = os.path.dirname(filepath)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)
            print(f"   Created directory: {dirname}/")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"   Written file: {filepath}")

    print("\n All 25 repository files generated successfully!")
    print(" Run 'python3 run.py' to launch the local application.")

if __name__ == "__main__":
    build_repository()