from datetime import datetime
import json
import re
import time
from urllib.parse import urlparse
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
import requests
from sqlalchemy import func
from sqlalchemy.orm import defer, joinedload, selectinload

from app.i18n import (
    _,
    _r,
    activate_report_lang_from_request,
    format_relative_time,
    get_supported_locales,
    is_supported_locale,
    locale_dir,
)
from app.models import Community, CommunityMember, Project, StatSnapshot, User, db
from app.oauth import can_user_edit_project, get_current_user, member_required, project_editor_required
from app.query_utils import (
    active_projects_query,
    filter_projects,
    filter_projects_by_date,
    filter_projects_by_status,
    get_active_project_or_404,
    get_latest_snapshots_map,
    get_latest_snapshots_total,
    normalize_username,
    sync_project_tags,
)
from app.wiki_utils import (
    PRESET_CAMPAIGNS,
    RESERVED_SLUGS,
    STANDARD_ACTIVITY_TYPES,
    is_reserved_slug,
    parse_and_validate_project_payload,
    sanitize_project_text_fields,
    validate_lang_code,
)

web_bp = Blueprint("web", __name__)


def _get_filter_facets(community_id=None):
    """Collect distinct years and campaigns from non-deleted projects cleanly without loading blobs."""
    q_dates = db.session.query(Project.start_date, Project.created_at).filter(Project.is_deleted.is_(False))
    q_campaigns = db.session.query(Project.campaign).filter(
        Project.is_deleted.is_(False),
        Project.campaign.isnot(None),
        Project.campaign != "",
    )
    if community_id is not None:
        q_dates = q_dates.filter(Project.community_id == community_id)
        q_campaigns = q_campaigns.filter(Project.community_id == community_id)

    current_year = datetime.utcnow().year
    years = {current_year}
    for s_date, c_date in q_dates.all():
        if s_date:
            years.add(s_date.year)
        if c_date:
            years.add(c_date.year)

    db_campaigns = [row[0] for row in q_campaigns.distinct().all() if row[0]]
    seen = set()
    campaigns = []
    for c in list(PRESET_CAMPAIGNS) + sorted(db_campaigns):
        if c and c.lower() not in seen:
            seen.add(c.lower())
            campaigns.append(c)

    return sorted(years, reverse=True), campaigns


def _build_form_data(form):
    """Capture submitted form values so validation errors retain organizer inputs."""
    return {key: form.get(key, "") for key in form.keys()}


@web_bp.route("/lang", methods=["POST"])
def set_language():
    """Persist selected UI locale in session and redirect safely to relative next target."""
    lang = (request.form.get("lang") or "").strip().lower()
    if not is_supported_locale(lang):
        abort(400, description=_("athar-error-invalid-lang"))

    session["lang"] = lang
    raw_next = (request.form.get("next") or "").strip()
    if raw_next and re.match(r"^/(?![/\\])", raw_next):
        parsed = urlparse(raw_next)
        if not parsed.scheme and not parsed.netloc and "\\" not in raw_next:
            return redirect(raw_next)
    return redirect(url_for("web.index"))


@web_bp.route("/")
def index():
    """Global landing page with up to 6 running activities and community directory."""
    user = get_current_user()
    communities = Community.query.order_by(Community.name.asc()).all()
    running_activities = (
        active_projects_query()
        .filter(Project.status == "In Progress")
        .options(
            joinedload(Project.community),
            selectinload(Project.tags_rel),
            defer(Project.description),
        )
        .order_by(Project.start_date.desc(), Project.created_at.desc())
        .limit(6)
        .all()
    )
    return render_template(
        "index.html",
        current_user=user,
        communities=communities,
        running_activities=running_activities,
    )


@web_bp.route("/activities")
def global_activities():
    """Global searchable activity directory across all communities."""
    user = get_current_user()
    communities = Community.query.order_by(Community.name.asc()).all()

    query = active_projects_query().options(
        joinedload(Project.community),
        selectinload(Project.tags_rel),
        defer(Project.description),
    )
    query = filter_projects(query, request.args)
    projects = query.order_by(Project.start_date.desc(), Project.created_at.desc()).limit(100).all()

    available_years, available_campaigns = _get_filter_facets()
    return render_template(
        "activities.html",
        community=None,
        communities=communities,
        projects=projects,
        total_projects=len(projects),
        total_members=0,
        available_years=available_years,
        available_campaigns=available_campaigns,
        standard_types=STANDARD_ACTIVITY_TYPES,
        filter_args=request.args,
        active_tab="activities",
        current_user=user,
    )


@web_bp.route("/<slug>/")
def dashboard(slug):
    """Community-specific dashboard view reading cleanly from database records."""
    if is_reserved_slug(slug):
        abort(404)
    user = get_current_user()

    community = Community.query.filter_by(slug=slug).first()
    if not community:
        flash(_("athar-flash-community-not-found", slug), "error")
        return redirect(url_for("web.index"))

    session["community_slug"] = community.slug

    in_progress_projects = (
        active_projects_query()
        .filter(Project.community_id == community.id, Project.status == "In Progress")
        .options(selectinload(Project.tags_rel), defer(Project.description))
        .order_by(Project.created_at.desc())
        .all()
    )

    total_projects = active_projects_query().filter(Project.community_id == community.id).count()
    total_members = CommunityMember.query.filter_by(community_id=community.id).count()
    member_user_ids = [cm.user_id for cm in community.members]
    total_edits = get_latest_snapshots_total(member_user_ids)

    return render_template(
        "dashboard.html",
        community=community,
        in_progress_projects=in_progress_projects,
        total_projects=total_projects,
        total_members=total_members,
        total_edits=total_edits,
        active_tab="overview",
        current_user=user,
    )


@web_bp.route("/<slug>/activities")
def community_activities(slug):
    """Dedicated community activities page using shared server-side filtering."""
    if is_reserved_slug(slug):
        abort(404)
    user = get_current_user()
    community = Community.query.filter_by(slug=slug).first_or_404()
    session["community_slug"] = community.slug

    scoped_args = request.args.to_dict(flat=False)
    scoped_args.pop("community", None)
    from werkzeug.datastructures import MultiDict

    query = (
        active_projects_query()
        .filter(Project.community_id == community.id)
        .options(selectinload(Project.tags_rel), defer(Project.description))
    )
    query = filter_projects(query, MultiDict(scoped_args))
    projects = query.order_by(Project.start_date.desc(), Project.created_at.desc()).limit(100).all()

    total_projects = active_projects_query().filter(Project.community_id == community.id).count()
    total_members = CommunityMember.query.filter_by(community_id=community.id).count()
    available_years, available_campaigns = _get_filter_facets(community_id=community.id)

    return render_template(
        "activities.html",
        community=community,
        communities=[],
        projects=projects,
        total_projects=total_projects,
        total_members=total_members,
        available_years=available_years,
        available_campaigns=available_campaigns,
        standard_types=STANDARD_ACTIVITY_TYPES,
        filter_args=request.args,
        active_tab="activities",
        current_user=user,
    )


@web_bp.route("/<slug>/users")
def community_users(slug):
    """Dedicated members page with single-query snapshot batch loading."""
    if is_reserved_slug(slug):
        abort(404)
    user = get_current_user()
    community = Community.query.filter_by(slug=slug).first_or_404()
    session["community_slug"] = community.slug

    member_user_ids = [cm.user_id for cm in community.members if cm.user_id]
    snapshots_map = get_latest_snapshots_map(member_user_ids)

    members_data = []
    total_edits = 0
    for cm in community.members:
        user_rec = cm.user
        latest_snap = snapshots_map.get(cm.user_id)
        edits = latest_snap.total_edits if latest_snap else 0
        total_edits += edits
        members_data.append(
            {
                "username": user_rec.username if user_rec else "Unknown",
                "role": cm.role or "Member",
                "total_edits": edits,
                "home_wiki": latest_snap.home_wiki if latest_snap else "ar.wikipedia.org",
                "added_at": cm.added_at,
                "last_synced": user_rec.last_synced if user_rec else None,
            }
        )

    members_data.sort(key=lambda m: m["total_edits"], reverse=True)
    total_projects = active_projects_query().filter(Project.community_id == community.id).count()

    return render_template(
        "users.html",
        community=community,
        members=members_data,
        total_members=len(members_data),
        total_edits=total_edits,
        total_projects=total_projects,
        active_tab="users",
        current_user=user,
    )


@web_bp.route("/<slug>/sync", methods=["POST"])
@member_required
def manual_sync(slug):
    """Trigger manual member synchronization for a community (respecting freshness TTL)."""
    if is_reserved_slug(slug):
        abort(404)
    community = Community.query.filter_by(slug=slug).first_or_404()
    from scripts.sync_data import sync_community

    try:
        synced_count = sync_community(community)
        flash(_("athar-flash-sync-success", synced_count, community.name), "success")
    except Exception as e:
        flash(_("athar-flash-sync-error", str(e)), "error")
    return redirect(url_for("web.dashboard", slug=community.slug))


@web_bp.route("/project/new", methods=["GET", "POST"])
@member_required
def create_project():
    communities = Community.query.order_by(Community.name.asc()).all()
    if request.method == "POST":
        try:
            parsed = parse_and_validate_project_payload(
                request.form,
                existing_project=None,
                require_dates=True,
                date_calc_when_not_canceled=True,
                partial=False,
            )
        except ValueError as err:
            flash(str(err), "error")
            return (
                render_template(
                    "project_form.html",
                    project=None,
                    communities=communities,
                    selected_community_slug=session.get("community_slug"),
                    preset_campaigns=PRESET_CAMPAIGNS,
                    form_data=_build_form_data(request.form),
                ),
                400,
            )

        community_id = None
        raw_comm_id = request.form.get("community_id")
        if raw_comm_id:
            try:
                cid = int(raw_comm_id)
                if db.session.get(Community, cid):
                    community_id = cid
            except (ValueError, TypeError):
                pass
        if not community_id:
            active_slug = session.get("community_slug")
            if active_slug:
                active_comm = Community.query.filter_by(slug=active_slug).first()
                if active_comm:
                    community_id = active_comm.id
            if not community_id and communities:
                community_id = communities[0].id

        curr = get_current_user()
        lead_organizer = (curr.username if curr else session.get("username")) or "MoroccoVolunteer"

        new_project = Project(
            community_id=community_id,
            title=parsed["title"],
            description=parsed["description"],
            project_type=parsed["project_type"],
            target_wiki=parsed["target_wiki"],
            wiki_link=parsed["wiki_link"],
            campaign=parsed["campaign"],
            primary_lang=parsed["primary_lang"],
            translations=parsed["translations"],
            start_date=parsed["start_date"],
            end_date=parsed["end_date"],
            status=parsed["status"],
            lead_organizer=lead_organizer,
            co_organizers=parsed["co_organizers"],
            is_contest=parsed["is_contest"],
            jury_members=parsed["jury_members"],
            participants=parsed["participants"],
            results=parsed["results"],
        )
        db.session.add(new_project)
        db.session.flush()
        sync_project_tags(new_project, parsed["tags"], replace=True)
        db.session.commit()

        flash(_("athar-flash-project-created"), "success")
        target_comm = db.session.get(Community, community_id) if community_id else None
        if target_comm:
            return redirect(url_for("web.dashboard", slug=target_comm.slug))
        return redirect(url_for("web.index"))

    return render_template(
        "project_form.html",
        project=None,
        communities=communities,
        selected_community_slug=session.get("community_slug"),
        preset_campaigns=PRESET_CAMPAIGNS,
        form_data=None,
    )


@web_bp.route("/project/<int:project_id>/edit", methods=["GET", "POST"])
@project_editor_required
def edit_project(project_id):
    project = get_active_project_or_404(project_id)
    communities = Community.query.order_by(Community.name.asc()).all()

    if request.method == "POST":
        try:
            parsed = parse_and_validate_project_payload(
                request.form,
                existing_project=project,
                require_dates=True,
                date_calc_when_not_canceled=True,
                partial=False,
            )
        except ValueError as err:
            flash(str(err), "error")
            return (
                render_template(
                    "project_form.html",
                    project=project,
                    communities=communities,
                    selected_community_slug=project.community.slug if project.community else session.get("community_slug"),
                    preset_campaigns=PRESET_CAMPAIGNS,
                    form_data=_build_form_data(request.form),
                ),
                400,
            )

        project.title = parsed["title"]
        project.description = parsed["description"]
        project.project_type = parsed["project_type"]
        project.target_wiki = parsed["target_wiki"]
        project.wiki_link = parsed["wiki_link"]
        project.campaign = parsed["campaign"]
        project.primary_lang = parsed["primary_lang"]
        project.translations = parsed["translations"]
        project.start_date = parsed["start_date"]
        project.end_date = parsed["end_date"]
        project.status = parsed["status"]
        project.is_contest = parsed["is_contest"]
        project.co_organizers = parsed["co_organizers"]
        project.jury_members = parsed["jury_members"]
        project.participants = parsed["participants"]
        project.results = parsed["results"]

        raw_comm_id = request.form.get("community_id")
        if raw_comm_id:
            try:
                cid = int(raw_comm_id)
                if db.session.get(Community, cid):
                    project.community_id = cid
            except (ValueError, TypeError):
                pass

        sync_project_tags(project, parsed["tags"], replace=True)
        db.session.commit()
        flash(_("athar-flash-project-updated"), "success")

        if project.community:
            return redirect(url_for("web.dashboard", slug=project.community.slug))
        return redirect(url_for("web.index"))

    return render_template(
        "project_form.html",
        project=project,
        communities=communities,
        selected_community_slug=project.community.slug if project.community else session.get("community_slug"),
        preset_campaigns=PRESET_CAMPAIGNS,
        form_data=None,
    )


@web_bp.route("/project/<int:project_id>", methods=["GET"])
def view_project(project_id):
    project = get_active_project_or_404(project_id)
    user = get_current_user()
    can_edit = can_user_edit_project(user, project)
    return render_template(
        "project_detail.html",
        project=project,
        community=project.community,
        can_edit=can_edit,
    )


def _collect_user_projects(clean_username, query):
    candidate_projects = query.order_by(Project.start_date.desc(), Project.created_at.desc()).all()
    norm_lower = clean_username.lower()

    lead_projects = []
    co_projects = []
    jury_projects = []
    participant_projects = []

    for p in candidate_projects:
        is_lead = bool(p.lead_organizer and normalize_username(p.lead_organizer).lower() == norm_lower)
        is_co = any(co and normalize_username(co).lower() == norm_lower for co in (p.co_organizers or []))
        is_jury = any(j and normalize_username(j).lower() == norm_lower for j in (p.jury_members or []))
        is_part = any(part and normalize_username(part).lower() == norm_lower for part in (p.participants or []))

        if is_lead:
            lead_projects.append(p)
        if is_co:
            co_projects.append(p)
        if is_jury:
            jury_projects.append(p)
        if is_part:
            participant_projects.append(p)

    all_user_projects = list(
        {p.id: p for p in (lead_projects + co_projects + jury_projects + participant_projects)}.values()
    )
    organized_projects = list({p.id: p for p in (lead_projects + co_projects)}.values())

    projects_by_role = {
        "lead": lead_projects,
        "co": co_projects,
        "organized": organized_projects,
        "jury": jury_projects,
        "participant": participant_projects,
        "all": all_user_projects,
    }
    return projects_by_role, all_user_projects


@web_bp.route("/user/<string:username>")
def user_profile(username):
    """Global contributor profile view reading strictly from local relational storage."""
    clean_username = normalize_username(username)
    if not clean_username:
        abort(404)

    user = User.query.filter(func.lower(User.username) == clean_username.lower()).first()
    projects_by_role, all_user_projects = _collect_user_projects(
        clean_username,
        active_projects_query().options(joinedload(Project.community), defer(Project.description)),
    )

    if not user and not all_user_projects:
        abort(404)

    if not user:
        user = User(username=clean_username, is_member=False, first_seen=None, last_synced=None)

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
                if raw_pct >= 0.1:
                    pct_str = f"{raw_pct:.1f}%"
                elif raw_pct > 0:
                    pct_str = "<0.1%"
                else:
                    pct_str = "0%"

                ratio = count / max_count if max_count else 0
                bar_width = max(2.5, round((ratio ** 0.4) * 100, 1)) if use_scaled else max(3.0, round(ratio * 100, 1))

                top_wikis_data.append(
                    {
                        "rank": idx + 1,
                        "wiki": wiki,
                        "count": count,
                        "pct": raw_pct,
                        "pct_str": pct_str,
                        "bar_width": bar_width,
                        "color": c_info["color"],
                        "tint": c_info["tint"],
                        "border": c_info["border"],
                    }
                )

    sync_dt = snapshot.recorded_at if snapshot else user.last_synced
    last_synced_relative = format_relative_time(sync_dt)
    communities = [m.community for m in user.memberships if m.community] if user.id else []

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
        current_user=get_current_user(),
    )


@web_bp.route("/project/<int:project_id>/report")
def project_report(project_id):
    """Printable Single-Project Dossier."""
    try:
        report_lang = activate_report_lang_from_request()
    except ValueError as err:
        abort(400, description=str(err))

    project = get_active_project_or_404(project_id)
    auto_print = request.args.get("print") == "1"
    return render_template(
        "reports/project_report.html",
        project=project,
        community=project.community,
        auto_print=auto_print,
        report_lang=report_lang,
        report_dir=locale_dir(report_lang),
        report_locales=get_supported_locales(),
        generated_at=datetime.utcnow(),
    )


@web_bp.route("/<slug>/report")
def community_report(slug):
    """Printable Affiliate Executive Report."""
    if is_reserved_slug(slug):
        abort(404)
    try:
        report_lang = activate_report_lang_from_request()
    except ValueError as err:
        abort(400, description=str(err))

    community = Community.query.filter_by(slug=slug).first_or_404()

    query = active_projects_query().filter(Project.community_id == community.id)
    query, start_date, end_date = filter_projects_by_date(query, request.args)
    query = filter_projects_by_status(query, request.args)
    projects = query.order_by(Project.start_date.desc(), Project.created_at.desc()).all()

    total_projects = len(projects)
    completed_projects = sum(1 for p in projects if p.status == "Completed")
    contests_count = sum(1 for p in projects if p.is_contest)

    members = CommunityMember.query.filter_by(community_id=community.id).all()
    user_ids = [m.user_id for m in members]
    total_edits = get_latest_snapshots_total(user_ids)

    filter_label = _r("athar-report-period-all", lang=report_lang)
    if start_date and end_date:
        filter_label = _r(
            "athar-report-period-range",
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            lang=report_lang,
        )
    elif request.args.get("year"):
        filter_label = _r("athar-report-period-year", request.args.get("year"), lang=report_lang)
    elif request.args.get("month"):
        filter_label = _r("athar-report-period-month", request.args.get("month"), lang=report_lang)

    stats = {
        "total_projects": total_projects,
        "completed_projects": completed_projects,
        "contests_count": contests_count,
        "total_members": len(members),
        "total_edits": total_edits,
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
        report_lang=report_lang,
        report_dir=locale_dir(report_lang),
        report_locales=get_supported_locales(),
        generated_at=datetime.utcnow(),
    )


@web_bp.route("/user/<string:username>/report")
def user_report(username):
    """Printable Contributor Portfolio Report."""
    try:
        report_lang = activate_report_lang_from_request()
    except ValueError as err:
        abort(400, description=str(err))

    clean_username = normalize_username(username)
    if not clean_username:
        abort(404)

    user = User.query.filter(func.lower(User.username) == clean_username.lower()).first()

    query = filter_projects_by_status(
        active_projects_query().options(joinedload(Project.community)),
        request.args,
    )
    projects_by_role, all_user_projects = _collect_user_projects(clean_username, query)

    if not user and not all_user_projects:
        abort(404)

    if not user:
        user = User(username=clean_username, is_member=False, first_seen=None, last_synced=None)

    snapshot = None
    top_wikis = []
    if user.id:
        snapshot = StatSnapshot.query.filter_by(user_id=user.id).order_by(StatSnapshot.recorded_at.desc()).first()
        if snapshot and snapshot.wiki_breakdown:
            top_wikis = sorted(snapshot.wiki_breakdown.items(), key=lambda x: x[1], reverse=True)[:5]

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
        report_lang=report_lang,
        report_dir=locale_dir(report_lang),
        report_locales=get_supported_locales(),
        generated_at=datetime.utcnow(),
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
    rows = db.session.query(Project.start_date, Project.created_at).filter(Project.is_deleted.is_(False)).all()
    for start_d, created_d in rows:
        if start_d:
            years_set.add(start_d.year)
        if created_d:
            years_set.add(created_d.year)

    available_years = sorted(years_set, reverse=True)

    return render_template(
        "export.html",
        communities=communities,
        selected_slug=selected_slug or "",
        selected_community=selected_community,
        available_years=available_years,
        current_year=current_year,
        current_month=datetime.utcnow().month,
    )


_MINT_LANGUAGES_CACHE = {}
_MINT_CACHE_TTL_SECONDS = 6 * 3600
_MINT_RATE_LIMIT_MAX = 10
_MINT_RATE_LIMIT_WINDOW_SECONDS = 60
_MINT_MAX_BODY_BYTES = 12288  # 12 KB
_MINT_ALLOWED_FIELDS = ("title", "description", "results_summary", "results_notes")


def _get_mint_languages(mint_base: str, timeout_s: float, headers: dict):
    """Fetch and cache MinT /languages map in memory with a 6-hour TTL."""
    now_ts = time.time()
    cached = _MINT_LANGUAGES_CACHE.get(mint_base)
    if cached and (now_ts - cached["fetched_at"]) < _MINT_CACHE_TTL_SECONDS:
        return cached["data"]

    try:
        resp = requests.get(f"{mint_base}/languages", headers=headers, timeout=timeout_s)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                _MINT_LANGUAGES_CACHE[mint_base] = {"fetched_at": now_ts, "data": data}
                return data
    except (requests.RequestException, ValueError, TypeError):
        pass
    return cached["data"] if cached else None


def _is_mint_pair_supported(langs_data: dict, source_lang: str, target_lang: str) -> bool:
    """Check whether MinT /languages map includes source_lang -> target_lang."""
    if not isinstance(langs_data, dict):
        return True
    targets = langs_data.get(source_lang)
    if targets is None:
        return False
    if isinstance(targets, list):
        return target_lang in targets
    if isinstance(targets, dict):
        if target_lang in targets:
            return True
        nested = targets.get("targets")
        if isinstance(nested, list):
            return target_lang in nested
    return False


@web_bp.route("/project/translate", methods=["POST"])
@member_required
def translate_project_fields():
    """
    CSRF-protected, rate-limited proxy to Wikimedia MinT translating activity fields.
    Always sanitizes upstream HTML/text output before returning JSON.
    """
    raw_body = request.get_data(cache=True) or b""
    if (request.content_length and request.content_length > _MINT_MAX_BODY_BYTES) or len(raw_body) > _MINT_MAX_BODY_BYTES:
        return jsonify({"error": "Translation payload exceeds 12 KB limit."}), 400

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON translation payload."}), 400

    try:
        source_lang = validate_lang_code(payload.get("source_lang", ""))
        target_lang = validate_lang_code(payload.get("target_lang", ""))
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    if source_lang == target_lang:
        return jsonify({"error": "Source and target languages must differ."}), 400

    fields_in = payload.get("fields")
    if not isinstance(fields_in, dict):
        return jsonify({"error": "Missing or invalid 'fields' dictionary."}), 400

    non_empty = {}
    for key in _MINT_ALLOWED_FIELDS:
        val = fields_in.get(key)
        if isinstance(val, str) and val.strip():
            non_empty[key] = val.strip()

    if not non_empty:
        return jsonify({"error": "No translatable fields provided."}), 400

    # DB-persisted per-user sliding window cooldown (10 req / 60s across all workers)
    user = get_current_user()
    now_dt = datetime.utcnow()
    if (
        user.mint_window_start is None
        or (now_dt - user.mint_window_start).total_seconds() >= _MINT_RATE_LIMIT_WINDOW_SECONDS
    ):
        user.mint_window_start = now_dt
        user.mint_window_count = 1
    elif (user.mint_window_count or 0) >= _MINT_RATE_LIMIT_MAX:
        db.session.commit()
        return jsonify({"error": "Rate limit exceeded (max 10 requests per minute). Please wait before retrying."}), 429
    else:
        user.mint_window_count = (user.mint_window_count or 0) + 1
    db.session.commit()

    mint_base = (current_app.config.get("MINT_API_URL") or "https://translate.wmcloud.org/api").rstrip("/")
    timeout_s = float(current_app.config.get("MINT_TIMEOUT_SECONDS", 10))
    headers = {"User-Agent": current_app.config.get("USER_AGENT", "AtharTool/1.0")}

    langs_map = _get_mint_languages(mint_base, timeout_s, headers)
    if langs_map is not None and not _is_mint_pair_supported(langs_map, source_lang, target_lang):
        return (
            jsonify(
                {
                    "error": f"MinT does not support {source_lang} -> {target_lang}.",
                    "manual_only": True,
                }
            ),
            400,
        )

    raw_out = {}
    endpoint = f"{mint_base}/translate"
    for key, text_val in non_empty.items():
        fmt = "html" if key == "description" else "text"
        try:
            resp = requests.post(
                endpoint,
                json={
                    "format": fmt,
                    "content": text_val,
                    "source_language": source_lang,
                    "target_language": target_lang,
                },
                headers=headers,
                timeout=timeout_s,
            )
        except requests.Timeout:
            return jsonify({"error": "MinT translation service timed out."}), 504
        except requests.RequestException:
            return jsonify({"error": "MinT translation service unreachable."}), 502

        if resp.status_code == 400:
            return (
                jsonify(
                    {
                        "error": f"MinT does not support {source_lang} -> {target_lang}.",
                        "manual_only": True,
                    }
                ),
                400,
            )
        if resp.status_code != 200:
            return jsonify({"error": f"MinT upstream returned HTTP {resp.status_code}."}), 502

        try:
            resp_data = resp.json()
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid JSON returned by MinT upstream."}), 502

        if not isinstance(resp_data, dict) or "translation" not in resp_data:
            return jsonify({"error": "Unexpected response format from MinT upstream."}), 502

        raw_out[key] = str(resp_data.get("translation") or "")

    sanitized = sanitize_project_text_fields(
        title=raw_out.get("title", ""),
        description=raw_out.get("description", ""),
        results_summary=raw_out.get("results_summary", ""),
        results_notes=raw_out.get("results_notes", ""),
        primary_lang=target_lang,
        require_title=False,
    )
    out_fields = {k: sanitized[k] for k in non_empty.keys()}
    return jsonify({"target_lang": target_lang, "fields": out_fields}), 200
