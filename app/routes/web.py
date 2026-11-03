import re
import bleach
import threading
from sqlalchemy import func
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, abort
from app import db
from datetime import datetime
from app.models import Project, User, StatSnapshot, Community, CommunityMember
from app.oauth import member_required, project_editor_required, get_current_user
from app.wiki_utils import normalize_wiki_target

web_bp = Blueprint("web", __name__)

RESERVED_SLUGS = {"user", "project", "export", "api", "auth", "static", "admin"}


def is_reserved_slug(slug: str) -> bool:
    """Check if a slug collides with core system routes."""
    return (slug or "").lower().strip() in RESERVED_SLUGS


def _async_sync_community(app, community_id):
    with app.app_context():
        try:
            comm = db.session.get(Community, community_id)
            if comm:
                from scripts.sync_data import sync_community
                sync_community(comm)
        except Exception as e:
            app.logger.error(f"Error in background sync for community {community_id}: {e}")


def slugify(text):
    """Generate a clean URL slug from string input."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text).strip('-')
    return text


@web_bp.route("/")
def index():
    """Landing page with logo, description, community selection, and community add form."""
    user = get_current_user()
    communities = Community.query.order_by(Community.name.asc()).all()
    return render_template(
        "index.html",
        current_user=user,
        communities=communities,
        pending_name=session.get('pending_community_name', ''),
        pending_link=session.get('pending_community_link', '')
    )


@web_bp.route("/add-community", methods=["POST"])
def add_community():
    """Handle new community addition requests (persisting to database)."""
    if not session.get('username'):
        # Save form fields temporarily in session so user doesn't lose data after login redirect
        session['pending_community_name'] = request.form.get("community_name", "").strip()
        session['pending_community_link'] = request.form.get("community_link", "").strip()
        
        flash("يجب تسجيل الدخول بحساب ويكيميديا الخاص بك قبل إضافة مجتمع جديد.", "error")
        return redirect(url_for("oauth.login"))

    name = request.form.get("community_name", "").strip()
    link = request.form.get("community_link", "").strip()
    contact_email = request.form.get("contact_email", "").strip() or None

    if not name or not link:
        flash("يرجى إدخال كل من اسم المجتمع ورابط صفحة ويكيميديا الصالح.", "error")
        return redirect(url_for("web.index"))

    base_slug = slugify(name)
    if not base_slug:
        base_slug = f"comm-{int(datetime.utcnow().timestamp())}"

    # Check if community with same name already exists
    existing = Community.query.filter_by(name=name).first()
    if existing:
        flash(f"المجتمع '{name}' مسجل مسبقاً في قاعدة البيانات.", "info")
        return redirect(url_for("web.dashboard", slug=existing.slug))

    # Ensure unique and unreserved slug
    slug = base_slug
    counter = 1
    while is_reserved_slug(slug) or Community.query.filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    try:
        new_community = Community(
            name=name,
            slug=slug,
            meta_roster_page=link,
            contact_email=contact_email
        )
        db.session.add(new_community)
        db.session.commit()

        # Trigger background roster ingestion immediately
        app = current_app._get_current_object()
        threading.Thread(target=_async_sync_community, args=(app, new_community.id), daemon=True).start()

        session.pop('pending_community_name', None)
        session.pop('pending_community_link', None)

        flash(f"تمت إضافة المجتمع '{name}' بنجاح إلى قاعدة البيانات! جاري مزامنة قائمة الأعضاء...", "success")
        return redirect(url_for("web.dashboard", slug=new_community.slug))
    except Exception as e:
        db.session.rollback()
        flash(f"حدث خطأ أثناء إضافة المجتمع: {str(e)}", "error")
        return redirect(url_for("web.index"))


@web_bp.route("/<slug>/")
def dashboard(slug):
    """Community-specific dashboard view querying database records."""
    if is_reserved_slug(slug):
        abort(404)
    user = get_current_user()

    community = Community.query.filter_by(slug=slug).first()
    if not community:
        flash(f"المجتمع '{slug}' غير موجود.", "error")
        return redirect(url_for("web.index"))

    # Save active community slug in session for oauth redirects
    session['community_slug'] = community.slug

    # Sync project statuses with current date
    all_comm_projects = Project.query.filter_by(community_id=community.id).all()
    status_changed = False
    for p in all_comm_projects:
        old_st = p.status
        if p.sync_status_with_dates() != old_st:
            status_changed = True
    if status_changed:
        db.session.commit()

    # Keep only in-progress activities on the main overview page
    in_progress_projects = Project.query.filter_by(
        community_id=community.id,
        status="In Progress"
    ).order_by(Project.created_at.desc()).all()

    total_projects = Project.query.filter_by(community_id=community.id).count()
    total_members = CommunityMember.query.filter_by(community_id=community.id).count()

    member_user_ids = [cm.user_id for cm in community.members]
    total_edits = 0
    if member_user_ids:
        for uid in member_user_ids:
            latest = StatSnapshot.query.filter_by(user_id=uid).order_by(StatSnapshot.recorded_at.desc()).first()
            if latest:
                total_edits += latest.total_edits

    return render_template(
        "dashboard.html",
        community=community,
        in_progress_projects=in_progress_projects,
        total_projects=total_projects,
        total_members=total_members,
        total_edits=total_edits,
        active_tab="overview",
        current_user=user
    )


@web_bp.route("/<slug>/activities")
def community_activities(slug):
    """Dedicated activities page with full filtering and search."""
    if is_reserved_slug(slug):
        abort(404)
    user = get_current_user()
    community = Community.query.filter_by(slug=slug).first_or_404()
    session['community_slug'] = community.slug

    projects = Project.query.filter_by(community_id=community.id).order_by(Project.created_at.desc()).all()
    status_changed = False
    for p in projects:
        old_st = p.status
        if p.sync_status_with_dates() != old_st:
            status_changed = True
    if status_changed:
        db.session.commit()

    total_projects = len(projects)
    total_members = CommunityMember.query.filter_by(community_id=community.id).count()

    return render_template(
        "activities.html",
        community=community,
        projects=projects,
        total_projects=total_projects,
        total_members=total_members,
        active_tab="activities",
        current_user=user
    )


@web_bp.route("/<slug>/users")
def community_users(slug):
    """Dedicated members page with real-time search, roles and metrics."""
    if is_reserved_slug(slug):
        abort(404)
    user = get_current_user()
    community = Community.query.filter_by(slug=slug).first_or_404()
    session['community_slug'] = community.slug

    members_data = []
    total_edits = 0
    for cm in community.members:
        user_rec = cm.user
        latest_snap = StatSnapshot.query.filter_by(user_id=cm.user_id).order_by(StatSnapshot.recorded_at.desc()).first()
        edits = latest_snap.total_edits if latest_snap else 0
        total_edits += edits
        members_data.append({
            "username": user_rec.username if user_rec else "Unknown",
            "role": cm.role or "Member",
            "total_edits": edits,
            "home_wiki": latest_snap.home_wiki if latest_snap else "ar.wikipedia.org",
            "added_at": cm.added_at,
            "last_synced": user_rec.last_synced if user_rec else None
        })

    members_data.sort(key=lambda m: m["total_edits"], reverse=True)
    total_projects = Project.query.filter_by(community_id=community.id).count()

    return render_template(
        "users.html",
        community=community,
        members=members_data,
        total_members=len(members_data),
        total_edits=total_edits,
        total_projects=total_projects,
        active_tab="users",
        current_user=user
    )


@web_bp.route("/<slug>/sync", methods=["POST"])
def manual_sync(slug):
    """Trigger manual member synchronization for a community from Meta-Wiki."""
    if is_reserved_slug(slug):
        abort(404)
    community = Community.query.filter_by(slug=slug).first_or_404()
    from scripts.sync_data import sync_community
    try:
        synced_count = sync_community(community)
        flash(f"تم بنجاح تحديث وتزامن {synced_count} عضواً لمجتمع '{community.name}'.", "success")
    except Exception as e:
        flash(f"خطأ أثناء تحديث بيانات المجتمع: {str(e)}", "error")
    return redirect(url_for("web.dashboard", slug=community.slug))

def _parse_date(date_str):
    """Safely parse YYYY-MM-DD date string into a datetime.date object."""
    if not date_str or not str(date_str).strip():
        return None
    try:
        return datetime.strptime(str(date_str).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _parse_participants(raw_text):
    """Parse line-by-line or comma-separated usernames into a deduplicated list."""
    if not raw_text:
        return []
    result = []
    for line in re.split(r'[\r\n,]+', str(raw_text)):
        cleaned = line.strip().replace("_", " ")
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _parse_results(form):
    """Extract structured results dictionary from form inputs with Bleach sanitization."""
    summary = bleach.clean(form.get("results_summary", "").strip(), strip=True)
    notes = bleach.clean(form.get("results_notes", "").strip(), strip=True)

    winners_raw = form.get("results_winners", "")
    winners = []
    for line in re.split(r'[\r\n,]+', str(winners_raw)):
        w = line.strip().replace("_", " ")
        if w and w not in winners:
            winners.append(w)

    def _safe_int(key):
        try:
            return max(0, int(form.get(key) or 0))
        except (ValueError, TypeError):
            return 0

    articles_created = _safe_int("results_articles_created")
    articles_improved = _safe_int("results_articles_improved")
    files_uploaded = _safe_int("results_files_uploaded")

    has_content = bool(summary or winners or articles_created or articles_improved or files_uploaded or notes)
    if not has_content:
        return None

    return {
        "summary": summary,
        "winners": winners,
        "metrics": {
            "articles_created": articles_created,
            "articles_improved": articles_improved,
            "files_uploaded": files_uploaded
        },
        "notes": notes
    }


@web_bp.route("/project/new", methods=["GET", "POST"])
@member_required
def create_project():
    communities = Community.query.all()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        raw_description = request.form.get("description", "").strip()
        raw_type = request.form.get("project_type", "Workshop").strip()
        custom_type = request.form.get("custom_project_type", "").strip()
        if raw_type == "Other" and custom_type:
            project_type = custom_type
        elif raw_type == "Other":
            project_type = "Other"
        else:
            project_type = raw_type or "Workshop"

        raw_target_wiki = request.form.get("target_wiki", "arwiki").strip()
        try:
            target_wiki, _ = normalize_wiki_target(raw_target_wiki)
        except ValueError as err:
            flash(str(err), "error")
            return render_template("project_form.html", project=None, communities=communities, selected_community_slug=session.get("community_slug")), 400

        co_orgs_raw = request.form.get("co_organizers", "")
        is_contest = bool(request.form.get("is_contest"))
        jury_raw = request.form.get("jury_members", "")

        # Community association
        community_id = request.form.get("community_id")
        if community_id:
            try:
                community_id = int(community_id)
            except ValueError:
                community_id = None
        if not community_id:
            active_slug = session.get("community_slug")
            if active_slug:
                active_comm = Community.query.filter_by(slug=active_slug).first()
                if active_comm:
                    community_id = active_comm.id
            if not community_id and communities:
                community_id = communities[0].id

        # Sanitize HTML description against stored XSS
        safe_description = bleach.clean(
            raw_description,
            tags=["p", "b", "i", "strong", "em", "ul", "ol", "li", "a", "br"],
            attributes={"a": ["href", "title"]},
            strip=True
        )

        co_organizers = [u.strip() for u in co_orgs_raw.split(",") if u.strip()]
        jury_members = [j.strip() for j in jury_raw.split(",") if j.strip()] if is_contest else []
        participants = _parse_participants(request.form.get("participants", ""))
        results = _parse_results(request.form)
        start_date = _parse_date(request.form.get("start_date"))
        end_date = _parse_date(request.form.get("end_date"))
        if not start_date or not end_date:
            flash("تاريخ بدء النشاط وتاريخ انتهائه إلزاميان لتسجيل النشاط.", "error")
            return render_template("project_form.html", project=None, communities=communities, selected_community_slug=session.get("community_slug")), 400

        if end_date < start_date:
            flash("تاريخ انتهاء النشاط لا يمكن أن يكون قبل تاريخ البدء.", "error")
            return render_template("project_form.html", project=None, communities=communities, selected_community_slug=session.get("community_slug")), 400

        raw_status = request.form.get("status", "").strip()
        if raw_status.lower() in ("canceled", "cancelled", "ملغي"):
            status = "Canceled"
        else:
            today = datetime.utcnow().date()
            if today < start_date:
                status = "Planned"
            elif today > end_date:
                status = "Completed"
            else:
                status = "In Progress"

        username = session.get("username")
        if not username and current_app.config.get("MOCK_AUTH", False):
            username = "MoroccoVolunteer"

        new_project = Project(
            community_id=community_id,
            title=title,
            description=safe_description,
            project_type=project_type,
            target_wiki=target_wiki,
            start_date=start_date,
            end_date=end_date,
            status=status,
            lead_organizer=username or "MoroccoVolunteer",
            co_organizers=co_organizers,
            is_contest=is_contest,
            jury_members=jury_members,
            participants=participants,
            results=results
        )
        db.session.add(new_project)
        db.session.commit()
        flash("تم إنشاء وحفظ النشاط المجتمعي بنجاح!", "success")

        target_comm = db.session.get(Community, community_id) if community_id else None
        if target_comm:
            return redirect(url_for("web.dashboard", slug=target_comm.slug))
        return redirect(url_for("web.index"))

    return render_template("project_form.html", project=None, communities=communities, selected_community_slug=session.get("community_slug"))


@web_bp.route("/project/<int:project_id>/edit", methods=["GET", "POST"])
@project_editor_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    communities = Community.query.all()
    if request.method == "POST":
        project.title = request.form.get("title", "").strip()
        raw_description = request.form.get("description", "").strip()
        project.description = bleach.clean(
            raw_description,
            tags=["p", "b", "i", "strong", "em", "ul", "ol", "li", "a", "br"],
            attributes={"a": ["href", "title"]},
            strip=True
        )
        raw_type = request.form.get("project_type", project.project_type).strip()
        custom_type = request.form.get("custom_project_type", "").strip()
        if raw_type == "Other" and custom_type:
            project.project_type = custom_type
        else:
            project.project_type = raw_type or project.project_type

        raw_target_wiki = request.form.get("target_wiki", project.target_wiki).strip()
        try:
            target_wiki, _ = normalize_wiki_target(raw_target_wiki)
            project.target_wiki = target_wiki
        except ValueError as err:
            flash(str(err), "error")
            return render_template("project_form.html", project=project, communities=communities, selected_community_slug=project.community.slug if project.community else session.get("community_slug")), 400
        start_date = _parse_date(request.form.get("start_date"))
        end_date = _parse_date(request.form.get("end_date"))
        if not start_date or not end_date:
            flash("تاريخ بدء النشاط وتاريخ انتهائه إلزاميان.", "error")
            return render_template("project_form.html", project=project, communities=communities, selected_community_slug=project.community.slug if project.community else session.get("community_slug")), 400

        if end_date < start_date:
            flash("تاريخ انتهاء النشاط لا يمكن أن يكون قبل تاريخ البدء.", "error")
            return render_template("project_form.html", project=project, communities=communities, selected_community_slug=project.community.slug if project.community else session.get("community_slug")), 400

        project.start_date = start_date
        project.end_date = end_date

        raw_status = request.form.get("status", "").strip()
        if raw_status.lower() in ("canceled", "cancelled", "ملغي"):
            project.status = "Canceled"
        else:
            today = datetime.utcnow().date()
            if today < start_date:
                project.status = "Planned"
            elif today > end_date:
                project.status = "Completed"
            else:
                project.status = "In Progress"
        project.is_contest = bool(request.form.get("is_contest"))

        community_id = request.form.get("community_id")
        if community_id:
            try:
                project.community_id = int(community_id)
            except ValueError:
                pass

        co_orgs_raw = request.form.get("co_organizers", "")
        project.co_organizers = [u.strip() for u in co_orgs_raw.split(",") if u.strip()]

        jury_raw = request.form.get("jury_members", "")
        project.jury_members = [j.strip() for j in jury_raw.split(",") if j.strip()] if project.is_contest else []
        project.participants = _parse_participants(request.form.get("participants", ""))
        project.results = _parse_results(request.form)

        db.session.commit()
        flash("تم تحديث بيانات النشاط بنجاح!", "success")

        if project.community:
            return redirect(url_for("web.dashboard", slug=project.community.slug))
        return redirect(url_for("web.index"))

    return render_template("project_form.html", project=project, communities=communities, selected_community_slug=project.community.slug if project.community else session.get("community_slug"))


@web_bp.route("/project/<int:project_id>", methods=["GET"])
def view_project(project_id):
    project = Project.query.get_or_404(project_id)
    username = session.get("username")
    can_edit = bool(
        username and (
            username == project.lead_organizer or
            (project.co_organizers and username in project.co_organizers) or
            current_app.config.get("MOCK_AUTH", False)
        )
    )
    return render_template(
        "project_detail.html",
        project=project,
        community=project.community,
        can_edit=can_edit
    )


def format_relative_time(dt):
    """Formats a datetime into human-friendly relative Arabic time."""
    if not dt:
        return "غير متوفر"
    diff = datetime.utcnow() - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "الآن"
    minutes = seconds // 60
    if minutes < 60:
        return f"قبل {minutes} دقيقة"
    hours = minutes // 60
    if hours < 24:
        return f"قبل {hours} ساعة"
    days = hours // 24
    if days == 1:
        return "أمس"
    if days < 30:
        return f"قبل {days} يوماً"
    months = days // 30
    return f"قبل {months} شهراً"


@web_bp.route("/user/<string:username>")
def user_profile(username):
    """
    Global contributor profile view.
    Zero-External-Network Invariant: Reads strictly from local relational storage.
    If the username has no local record in User or Project, returns HTTP 404 immediately.
    """
    from app.query_utils import normalize_username
    clean_username = normalize_username(username)
    if not clean_username:
        abort(404)

    # 1. Local User lookup
    user = User.query.filter(func.lower(User.username) == clean_username.lower()).first()

    # 2. In-memory Python role filtering on candidate projects (cross-dialect safe)
    candidate_projects = Project.query.order_by(Project.start_date.desc(), Project.created_at.desc()).all()
    norm_lower = clean_username.lower()

    lead_projects = []
    co_projects = []
    jury_projects = []
    participant_projects = []

    for p in candidate_projects:
        is_lead = bool(p.lead_organizer and p.lead_organizer.strip().lower() == norm_lower)
        is_co = any(co and co.strip().lower() == norm_lower for co in (p.co_organizers or []))
        is_jury = any(j and j.strip().lower() == norm_lower for j in (p.jury_members or []))
        is_part = any(part and part.strip().lower() == norm_lower for part in (p.participants or []))

        if is_lead:
            lead_projects.append(p)
        if is_co:
            co_projects.append(p)
        if is_jury:
            jury_projects.append(p)
        if is_part:
            participant_projects.append(p)

    all_user_projects = list({p.id: p for p in (lead_projects + co_projects + jury_projects + participant_projects)}.values())

    # If completely absent from both User and Project tables -> 404
    if not user and not all_user_projects:
        abort(404)

    # If user is not yet in User table but participated in projects, construct display object
    if not user:
        user = User(
            username=clean_username,
            is_member=False,
            first_seen=None,
            last_synced=None
        )

    # 3. Metrics aggregation from StatSnapshot
    snapshot = None
    top_wikis = []
    top_wikis_data = []
    total_top_edits = 0
    if user.id:
        snapshot = StatSnapshot.query.filter_by(user_id=user.id).order_by(StatSnapshot.recorded_at.desc()).first()
        if snapshot and snapshot.wiki_breakdown:
            top_wikis = sorted(snapshot.wiki_breakdown.items(), key=lambda x: x[1], reverse=True)[:5]
            total_top_edits = sum(count for _, count in top_wikis) or 1
            max_count = top_wikis[0][1] if top_wikis else 1
            min_count = top_wikis[-1][1] if top_wikis else 1
            use_scaled = (max_count / max(min_count, 1)) > 50

            palette = [
                {"color": "#0ea5e9", "tint": "rgba(14, 165, 233, 0.12)", "border": "rgba(14, 165, 233, 0.3)"},
                {"color": "#10b981", "tint": "rgba(16, 185, 129, 0.12)", "border": "rgba(16, 185, 129, 0.3)"},
                {"color": "#f59e0b", "tint": "rgba(245, 158, 11, 0.12)", "border": "rgba(245, 158, 11, 0.3)"},
                {"color": "#8b5cf6", "tint": "rgba(139, 92, 246, 0.12)", "border": "rgba(139, 92, 246, 0.3)"},
                {"color": "#ec4899", "tint": "rgba(236, 72, 153, 0.12)", "border": "rgba(236, 72, 153, 0.3)"},
            ]

            for idx, (wiki, count) in enumerate(top_wikis):
                c_info = palette[idx % len(palette)]
                raw_pct = (count / total_top_edits) * 100
                if raw_pct >= 1.0:
                    pct_str = f"{raw_pct:.1f}%"
                elif raw_pct >= 0.1:
                    pct_str = f"{raw_pct:.1f}%"
                elif raw_pct > 0:
                    pct_str = "<0.1%"
                else:
                    pct_str = "0%"

                ratio = count / max_count if max_count else 0
                if use_scaled:
                    bar_width = max(2.5, round((ratio ** 0.4) * 100, 1))
                else:
                    bar_width = max(3.0, round(ratio * 100, 1))

                top_wikis_data.append({
                    "rank": idx + 1,
                    "wiki": wiki,
                    "count": count,
                    "pct": raw_pct,
                    "pct_str": pct_str,
                    "bar_width": bar_width,
                    "color": c_info["color"],
                    "tint": c_info["tint"],
                    "border": c_info["border"],
                })

    sync_dt = snapshot.recorded_at if snapshot else user.last_synced
    last_synced_relative = format_relative_time(sync_dt)

    # 4. Multi-affiliate memberships
    communities = [m.community for m in user.memberships if m.community] if user.id else []

    organized_projects = list({p.id: p for p in (lead_projects + co_projects)}.values())

    projects_by_role = {
        "lead": lead_projects,
        "co": co_projects,
        "organized": organized_projects,
        "jury": jury_projects,
        "participant": participant_projects,
        "all": all_user_projects
    }

    return render_template(
        "user_profile.html",
        user=user,
        snapshot=snapshot,
        top_wikis=top_wikis,
        top_wikis_data=top_wikis_data,
        total_top_edits=total_top_edits,
        projects_by_role=projects_by_role,
        total_user_projects=len(all_user_projects),
        communities=communities,
        last_synced_relative=last_synced_relative,
        current_user=get_current_user()
    )


@web_bp.route("/project/<int:project_id>/report")
def project_report(project_id):
    """Printable Single-Project Dossier."""
    project = Project.query.get_or_404(project_id)
    auto_print = request.args.get("print") == "1"
    return render_template(
        "reports/project_report.html",
        project=project,
        community=project.community,
        auto_print=auto_print,
        generated_at=datetime.utcnow()
    )


@web_bp.route("/<slug>/report")
def community_report(slug):
    """Printable Affiliate Executive Report."""
    if is_reserved_slug(slug):
        abort(404)
    community = Community.query.filter_by(slug=slug).first_or_404()

    from app.query_utils import filter_projects_by_date, filter_projects_by_status
    query = Project.query.filter_by(community_id=community.id)
    query, start_date, end_date = filter_projects_by_date(query, request.args)
    query = filter_projects_by_status(query, request.args)
    projects = query.order_by(Project.start_date.desc(), Project.created_at.desc()).all()

    total_projects = len(projects)
    completed_projects = sum(1 for p in projects if p.status == "Completed")
    contests_count = sum(1 for p in projects if p.is_contest)

    members = CommunityMember.query.filter_by(community_id=community.id).all()
    user_ids = [m.user_id for m in members]
    total_edits = 0
    if user_ids:
        latest_snapshots = db.session.query(
            StatSnapshot.user_id,
            func.max(StatSnapshot.recorded_at).label("max_recorded")
        ).filter(StatSnapshot.user_id.in_(user_ids)).group_by(StatSnapshot.user_id).subquery()

        snaps = db.session.query(StatSnapshot).join(
            latest_snapshots,
            db.and_(
                StatSnapshot.user_id == latest_snapshots.c.user_id,
                StatSnapshot.recorded_at == latest_snapshots.c.max_recorded
            )
        ).all()
        total_edits = sum(s.total_edits for s in snaps)

    filter_label = "تقرير شامل"
    if start_date and end_date:
        filter_label = f"الفترة من {start_date.strftime('%Y-%m-%d')} إلى {end_date.strftime('%Y-%m-%d')}"
    elif request.args.get("year"):
        filter_label = f"سنة {request.args.get('year')}"
    elif request.args.get("month"):
        filter_label = f"شهر {request.args.get('month')}"

    stats = {
        "total_projects": total_projects,
        "completed_projects": completed_projects,
        "contests_count": contests_count,
        "total_members": len(members),
        "total_edits": total_edits
    }

    auto_print = request.args.get("print") == "1"
    detailed = request.args.get("detailed") in ("1", "true", "yes")
    return render_template(
        "reports/community_report.html",
        community=community,
        projects=projects,
        stats=stats,
        filter_label=filter_label,
        auto_print=auto_print,
        detailed=detailed,
        generated_at=datetime.utcnow()
    )


@web_bp.route("/user/<string:username>/report")
def user_report(username):
    """Printable Contributor Portfolio Report."""
    from app.query_utils import normalize_username, filter_projects_by_status
    clean_username = normalize_username(username)
    if not clean_username:
        abort(404)

    user = User.query.filter(func.lower(User.username) == clean_username.lower()).first()

    query = Project.query
    query = filter_projects_by_status(query, request.args)
    candidate_projects = query.order_by(Project.start_date.desc(), Project.created_at.desc()).all()
    norm_lower = clean_username.lower()

    lead_projects = []
    co_projects = []
    jury_projects = []
    participant_projects = []

    for p in candidate_projects:
        is_lead = bool(p.lead_organizer and p.lead_organizer.strip().lower() == norm_lower)
        is_co = any(co and co.strip().lower() == norm_lower for co in (p.co_organizers or []))
        is_jury = any(j and j.strip().lower() == norm_lower for j in (p.jury_members or []))
        is_part = any(part and part.strip().lower() == norm_lower for part in (p.participants or []))

        if is_lead:
            lead_projects.append(p)
        if is_co:
            co_projects.append(p)
        if is_jury:
            jury_projects.append(p)
        if is_part:
            participant_projects.append(p)

    all_user_projects = list({p.id: p for p in (lead_projects + co_projects + jury_projects + participant_projects)}.values())

    if not user and not all_user_projects:
        abort(404)

    if not user:
        user = User(
            username=clean_username,
            is_member=False,
            first_seen=None,
            last_synced=None
        )

    snapshot = None
    top_wikis = []
    if user.id:
        snapshot = StatSnapshot.query.filter_by(user_id=user.id).order_by(StatSnapshot.recorded_at.desc()).first()
        if snapshot and snapshot.wiki_breakdown:
            top_wikis = sorted(snapshot.wiki_breakdown.items(), key=lambda x: x[1], reverse=True)[:5]

    organized_projects = list({p.id: p for p in (lead_projects + co_projects)}.values())

    projects_by_role = {
        "lead": lead_projects,
        "co": co_projects,
        "organized": organized_projects,
        "jury": jury_projects,
        "participant": participant_projects,
        "all": all_user_projects
    }

    auto_print = request.args.get("print") == "1"
    detailed = request.args.get("detailed") in ("1", "true", "yes")
    return render_template(
        "reports/user_report.html",
        user=user,
        snapshot=snapshot,
        top_wikis=top_wikis,
        projects_by_role=projects_by_role,
        auto_print=auto_print,
        detailed=detailed,
        generated_at=datetime.utcnow()
    )


@web_bp.route("/export")
def export_view():
    communities = Community.query.order_by(Community.name.asc()).all()
    selected_slug = request.args.get("community") or session.get("community_slug")
    if not selected_slug and communities:
        selected_slug = communities[0].slug

    selected_community = Community.query.filter_by(slug=selected_slug).first() if selected_slug else None

    current_year = datetime.utcnow().year
    years_set = {current_year, current_year - 1}
    all_projects = Project.query.all()
    for p in all_projects:
        if p.start_date:
            years_set.add(p.start_date.year)
        if p.created_at:
            years_set.add(p.created_at.year)

    available_years = sorted(list(years_set), reverse=True)

    return render_template(
        "export.html",
        communities=communities,
        selected_slug=selected_slug or "",
        selected_community=selected_community,
        available_years=available_years,
        current_year=current_year,
        current_month=datetime.utcnow().month
    )