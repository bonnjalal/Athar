import re
import bleach
import threading
from sqlalchemy import func
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app import db
from datetime import datetime
from app.models import Project, User, StatSnapshot, Community, CommunityMember
from app.oauth import member_required, project_editor_required, get_current_user
from app.wiki_utils import normalize_wiki_target

web_bp = Blueprint("web", __name__)


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
        
        flash("You must log in with your Wikimedia account before adding a community.", "error")
        return redirect(url_for("oauth.login"))

    name = request.form.get("community_name", "").strip()
    link = request.form.get("community_link", "").strip()
    contact_email = request.form.get("contact_email", "").strip() or None

    if not name or not link:
        flash("Please provide both a community name and a valid Wikimedia link.", "error")
        return redirect(url_for("web.index"))

    base_slug = slugify(name)
    if not base_slug:
        base_slug = f"comm-{int(datetime.utcnow().timestamp())}"

    # Check if community with same name already exists
    existing = Community.query.filter_by(name=name).first()
    if existing:
        flash(f"Community '{name}' already exists in the database.", "info")
        return redirect(url_for("web.dashboard", slug=existing.slug))

    # Ensure unique slug
    slug = base_slug
    counter = 1
    while Community.query.filter_by(slug=slug).first():
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

        flash(f"Community '{name}' added successfully to the database! Syncing member roster...", "success")
        return redirect(url_for("web.dashboard", slug=new_community.slug))
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding community: {str(e)}", "error")
        return redirect(url_for("web.index"))


@web_bp.route("/<slug>/")
def dashboard(slug):
    """Community-specific dashboard view querying database records."""
    user = get_current_user()

    community = Community.query.filter_by(slug=slug).first()
    if not community:
        flash(f"Community '{slug}' not found.", "error")
        return redirect(url_for("web.index"))

    # Save active community slug in session for oauth redirects
    session['community_slug'] = community.slug

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
    user = get_current_user()
    community = Community.query.filter_by(slug=slug).first_or_404()
    session['community_slug'] = community.slug

    projects = Project.query.filter_by(community_id=community.id).order_by(Project.created_at.desc()).all()
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
    community = Community.query.filter_by(slug=slug).first_or_404()
    from scripts.sync_data import sync_community
    try:
        synced_count = sync_community(community)
        flash(f"تم بنجاح تحديث وتزامن {synced_count} عضواً لمجتمع '{community.name}'.", "success")
    except Exception as e:
        flash(f"خطأ أثناء تحديث بيانات المجتمع: {str(e)}", "error")
    return redirect(url_for("web.dashboard", slug=community.slug))

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

        status = request.form.get("status", "In Progress")
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

        username = session.get("username")
        if not username and current_app.config.get("MOCK_AUTH", False):
            username = "MoroccoVolunteer"

        new_project = Project(
            community_id=community_id,
            title=title,
            description=safe_description,
            project_type=project_type,
            target_wiki=target_wiki,
            status=status,
            lead_organizer=username or "MoroccoVolunteer",
            co_organizers=co_organizers,
            is_contest=is_contest,
            jury_members=jury_members
        )
        db.session.add(new_project)
        db.session.commit()
        flash("Project activity created successfully!", "success")

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
        project.status = request.form.get("status", project.status)
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

        db.session.commit()
        flash("Project updated successfully!", "success")

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


@web_bp.route("/export")
def export_view():
    return render_template("export.html")