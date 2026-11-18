import csv
import io
import re
import time
from urllib.parse import urlparse

from flask import Blueprint, Response, current_app, jsonify, request, session, stream_with_context
import requests
from sqlalchemy import func
from sqlalchemy.orm import defer, joinedload, selectinload
from werkzeug.datastructures import MultiDict

from app import csrf, db
from app.i18n import _, _r, activate_report_lang_from_request
from app.models import Community, CommunityMember, Project, User
from app.oauth import get_current_user, member_required, project_editor_required
from app.query_utils import (
    active_projects_query,
    filter_projects,
    filter_projects_by_status,
    get_latest_snapshots_map,
    get_latest_snapshots_total,
    normalize_username,
    sanitize_csv_cell,
    sync_project_tags,
)
from app.wiki_utils import (
    LANG_CODE_REGEX,
    parse_and_validate_project_payload,
    verify_wikimedia_username,
)

api_bp = Blueprint("api", __name__)


def _enforce_csrf():
    if current_app.config.get("WTF_CSRF_ENABLED", True):
        csrf.protect()


def get_request_data():
    """Extract request data supporting both JSON payloads and Form submissions."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


# ----------------------------------------------------------------------
# Global Endpoints
# ----------------------------------------------------------------------


@api_bp.route("/communities", methods=["GET"])
def get_communities():
    communities = Community.query.order_by(Community.name.asc()).all()
    return jsonify([community.to_dict() for community in communities]), 200


@api_bp.route("/stats", methods=["GET"])
def get_stats():
    total_members = User.query.filter_by(is_member=True).count()
    total_projects = active_projects_query().count()
    all_user_ids = [uid for (uid,) in db.session.query(User.id).all()]
    total_edits = get_latest_snapshots_total(all_user_ids)

    return jsonify(
        {
            "total_members": total_members,
            "total_projects": total_projects,
            "total_edits": total_edits,
        }
    ), 200


@api_bp.route("/projects", methods=["GET"])
def list_projects():
    lang = (request.args.get("lang") or "").strip() or None
    query = active_projects_query().options(
        joinedload(Project.community),
        selectinload(Project.tags_rel),
        defer(Project.translations),
    )
    query = filter_projects(query, request.args)
    projects = query.order_by(Project.created_at.desc()).all()
    return jsonify([p.to_dict(lang=lang) for p in projects]), 200


@api_bp.route("/export", methods=["GET"])
def export_csv():
    slug = request.args.get("community") or request.args.get("slug")
    if slug:
        return exp_community_projects(slug)
    first_comm = Community.query.order_by(Community.name.asc()).first()
    if first_comm:
        return exp_community_projects(first_comm.slug)
    return jsonify({"error": "يرجى تحديد المجتمع لتصدير التقرير الخاص به."}), 400


# ----------------------------------------------------------------------
# Scoped Community Endpoints
# ----------------------------------------------------------------------


@api_bp.route("/<string:slug>/stats", methods=["GET"])
def slug_Stat(slug):
    community = Community.query.filter_by(slug=slug).first()
    if not community:
        return jsonify({"error": "Community not found"}), 404

    count_community_member = (
        db.session.query(func.count(CommunityMember.user_id))
        .filter(CommunityMember.community_id == community.id)
        .scalar()
        or 0
    )

    count_project = (
        db.session.query(func.count(Project.id))
        .filter(Project.community_id == community.id, Project.is_deleted.is_(False))
        .scalar()
        or 0
    )

    member_user_ids = [
        uid
        for (uid,) in db.session.query(CommunityMember.user_id)
        .filter(CommunityMember.community_id == community.id)
        .all()
    ]
    total_edits = get_latest_snapshots_total(member_user_ids)

    activity_rows = (
        db.session.query(
            Project.project_type,
            func.count(Project.id).label("total"),
        )
        .filter(Project.community_id == community.id, Project.is_deleted.is_(False))
        .group_by(Project.project_type)
        .all()
    )
    activities_by_type = {project_type: total for project_type, total in activity_rows}

    return jsonify(
        {
            "community": community.name,
            "slug": community.slug,
            "total_members": count_community_member,
            "total_projects": count_project,
            "total_edits": total_edits,
            # Backward-compatible keys
            "community_name": community.name,
            "total_community_member": count_community_member,
            "total_project_member": count_project,
            "total_edits_member_comm": total_edits,
            "activities_by_type": activities_by_type,
        }
    ), 200


@api_bp.route("/<string:slug>/members", methods=["GET"])
def list_members(slug):
    community = Community.query.filter_by(slug=slug).first()
    if not community:
        return jsonify({"error": "Community not found"}), 404

    community_members = (
        CommunityMember.query.options(joinedload(CommunityMember.user))
        .filter_by(community_id=community.id)
        .all()
    )
    user_ids = [cm.user_id for cm in community_members if cm.user_id]
    snapshots_map = get_latest_snapshots_map(user_ids)

    members = []
    for cm in community_members:
        member = cm.user
        if not member:
            continue
        last_snapshot = snapshots_map.get(member.id)
        members.append(
            {
                "id": member.id,
                "username": member.username,
                "is_member": member.is_member,
                "role": cm.role,
                "verified": cm.verified,
                "added_at": cm.added_at.isoformat() if cm.added_at else None,
                "first_seen": member.first_seen.isoformat() if member.first_seen else None,
                "last_synced": member.last_synced.isoformat() if member.last_synced else None,
                "total_edits": last_snapshot.total_edits if last_snapshot else 0,
            }
        )
    return jsonify(members), 200


@api_bp.route("/<string:slug>/projects", methods=["GET"])
def list_slug_project(slug):
    community = Community.query.filter_by(slug=slug).first()
    if not community:
        return jsonify({"error": "Community not found"}), 404

    lang = (request.args.get("lang") or "").strip() or None
    scoped_args = request.args.to_dict(flat=False)
    scoped_args.pop("community", None)

    query = (
        active_projects_query()
        .filter(Project.community_id == community.id)
        .options(
            joinedload(Project.community),
            selectinload(Project.tags_rel),
            defer(Project.translations),
        )
    )
    query = filter_projects(query, MultiDict(scoped_args))
    projects = query.order_by(Project.created_at.desc()).all()
    return jsonify([p.to_dict(lang=lang) for p in projects]), 200


@api_bp.route("/<string:slug>/projects", methods=["POST"])
@api_bp.route("/<string:slug>/project", methods=["POST"])
@member_required
def create_projetct(slug):
    _enforce_csrf()
    community = Community.query.filter_by(slug=slug).first()
    if not community:
        return jsonify({"error": "Community not found"}), 404

    data = get_request_data()
    try:
        parsed = parse_and_validate_project_payload(
            data,
            existing_project=None,
            require_dates=False,
            date_calc_when_not_canceled=False,
            partial=False,
        )
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    curr_user = get_current_user()
    if curr_user and isinstance(curr_user, dict):
        lead_user = curr_user.get("username", "MoroccoVolunteer")
    elif curr_user and hasattr(curr_user, "username"):
        lead_user = curr_user.username
    else:
        lead_user = session.get("username", "MoroccoVolunteer")

    new_project = Project(
        community_id=community.id,
        title=parsed["title"],
        description=parsed["description"],
        project_type=parsed["project_type"],
        target_wiki=parsed["target_wiki"],
        wiki_link=parsed["wiki_link"],
        campaign=parsed["campaign"],
        primary_lang=parsed["primary_lang"],
        translations=parsed["translations"],
        status=parsed["status"],
        start_date=parsed["start_date"],
        end_date=parsed["end_date"],
        lead_organizer=lead_user,
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

    return jsonify(
        {
            "message": "Project created successfully",
            "project": new_project.to_dict(),
        }
    ), 201


@api_bp.route("/<string:slug>/projects/<int:project_id>", methods=["GET"])
@api_bp.route("/projects/<int:project_id>", methods=["GET"])
def get_project(project_id, slug=None):
    lang = (request.args.get("lang") or "").strip() or None
    q = active_projects_query().filter(Project.id == project_id)
    if slug:
        community = Community.query.filter_by(slug=slug).first()
        if not community:
            return jsonify({"error": "Community not found"}), 404
        q = q.filter(Project.community_id == community.id)

    project = q.first_or_404()
    return jsonify(project.to_dict(lang=lang)), 200


@api_bp.route("/<string:slug>/projects/<int:project_id>", methods=["PUT"])
@api_bp.route("/projects/<int:project_id>", methods=["PUT"])
@project_editor_required
def update_project(project_id, slug=None):
    _enforce_csrf()
    q = active_projects_query().filter(Project.id == project_id)
    if slug:
        community = Community.query.filter_by(slug=slug).first()
        if not community:
            return jsonify({"error": "Community not found"}), 404
        q = q.filter(Project.community_id == community.id)

    project = q.first_or_404()
    data = get_request_data()

    try:
        parsed = parse_and_validate_project_payload(
            data,
            existing_project=project,
            require_dates=False,
            date_calc_when_not_canceled=False,
            partial=True,
        )
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    for attr in (
        "title",
        "description",
        "project_type",
        "target_wiki",
        "wiki_link",
        "campaign",
        "primary_lang",
        "translations",
        "start_date",
        "end_date",
        "status",
        "is_contest",
        "co_organizers",
        "jury_members",
        "participants",
        "results",
    ):
        if attr in parsed:
            setattr(project, attr, parsed[attr])

    if "tags" in parsed:
        sync_project_tags(project, parsed["tags"], replace=True)

    db.session.commit()
    return jsonify(
        {
            "message": "Project updated successfully",
            "project": project.to_dict(),
        }
    ), 200


@api_bp.route("/projects/<int:project_id>/export", methods=["GET"])
def export_project_csv(project_id):
    """Level 1 CSV Export: Streams participant and organizer roster for a single active project."""
    try:
        export_lang = activate_report_lang_from_request()
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    project = active_projects_query().filter(Project.id == project_id).first()
    if not project:
        return jsonify({"error": "Project not found"}), 404

    export_format = request.args.get("format", "csv").lower()
    if export_format != "csv":
        return jsonify({"error": f"Unsupported format '{export_format}'. Only 'csv' is supported."}), 400

    role_lead = _r("athar-report-role-lead", lang=export_lang)
    role_co = _r("athar-report-role-co", lang=export_lang)
    role_jury = _r("athar-report-role-jury", lang=export_lang)
    role_part = _r("athar-report-role-participant", lang=export_lang)

    rows = []
    if project.lead_organizer:
        rows.append((project.lead_organizer, role_lead))
    for co in (project.co_organizers or []):
        if co:
            rows.append((co, role_co))
    if project.is_contest:
        for j in (project.jury_members or []):
            if j:
                rows.append((j, role_jury))
    for part in (project.participants or []):
        if part:
            rows.append((part, role_part))

    title = project.localized_text("title", export_lang)
    target_wiki = project.target_wiki
    start_str = project.start_date.strftime("%Y-%m-%d") if project.start_date else ""
    end_str = project.end_date.strftime("%Y-%m-%d") if project.end_date else ""
    proj_id = project.id
    headers = [
        _r("athar-csv-l1-col-username", lang=export_lang),
        _r("athar-csv-l1-col-role", lang=export_lang),
        _r("athar-csv-l1-col-title", lang=export_lang),
        _r("athar-csv-l1-col-wiki", lang=export_lang),
        _r("athar-csv-l1-col-start", lang=export_lang),
        _r("athar-csv-l1-col-end", lang=export_lang),
    ]

    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        yield "\ufeff"

        writer.writerow(headers)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for username, role in rows:
            clean_row = [
                sanitize_csv_cell(username),
                sanitize_csv_cell(role),
                sanitize_csv_cell(title),
                sanitize_csv_cell(target_wiki),
                sanitize_csv_cell(start_str),
                sanitize_csv_cell(end_str),
            ]
            writer.writerow(clean_row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    filename = f"athar_project_{proj_id}_roster.csv"
    return Response(
        stream_with_context(generate_csv()),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_bp.route("/users/<string:username>/export", methods=["GET"])
@api_bp.route("/user/<string:username>/export", methods=["GET"])
def export_user_projects_csv(username):
    """Level 3 CSV Export: Streams contributor activity history across active projects."""
    try:
        export_lang = activate_report_lang_from_request()
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    clean_username = normalize_username(username)
    if not clean_username:
        return jsonify({"error": "Username is required"}), 400

    export_format = request.args.get("format", "csv").lower()
    if export_format != "csv":
        return jsonify({"error": f"Unsupported format '{export_format}'. Only 'csv' is supported."}), 400

    role_org = _r("athar-report-role-organizer", lang=export_lang)
    role_jury = _r("athar-report-role-jury", lang=export_lang)
    role_part = _r("athar-report-role-participant", lang=export_lang)
    general_label = _("athar-field-general", lang=export_lang)

    norm_lower = clean_username.lower()
    query = filter_projects_by_status(
        active_projects_query().options(joinedload(Project.community)),
        request.args,
    )
    candidate_projects = query.order_by(Project.start_date.desc(), Project.created_at.desc()).all()

    user_rows = []
    for p in candidate_projects:
        role = None
        if (p.lead_organizer and normalize_username(p.lead_organizer).lower() == norm_lower) or any(
            co and normalize_username(co).lower() == norm_lower for co in (p.co_organizers or [])
        ):
            role = role_org
        elif any(j and normalize_username(j).lower() == norm_lower for j in (p.jury_members or [])):
            role = role_jury
        elif any(part and normalize_username(part).lower() == norm_lower for part in (p.participants or [])):
            role = role_part

        if role:
            comm_name = p.community.name if p.community else general_label
            start_str = p.start_date.strftime("%Y-%m-%d") if p.start_date else ""
            end_str = p.end_date.strftime("%Y-%m-%d") if p.end_date else ""
            user_rows.append(
                [
                    sanitize_csv_cell(p.id),
                    sanitize_csv_cell(p.localized_text("title", export_lang)),
                    sanitize_csv_cell(comm_name),
                    sanitize_csv_cell(role),
                    sanitize_csv_cell(p.t_status(export_lang)),
                    sanitize_csv_cell(p.target_wiki),
                    sanitize_csv_cell(start_str),
                    sanitize_csv_cell(end_str),
                ]
            )

    headers = [
        _r("athar-csv-l3-col-id", lang=export_lang),
        _r("athar-csv-l3-col-title", lang=export_lang),
        _r("athar-csv-l3-col-community", lang=export_lang),
        _r("athar-csv-l3-col-role", lang=export_lang),
        _r("athar-csv-l3-col-status", lang=export_lang),
        _r("athar-csv-l3-col-wiki", lang=export_lang),
        _r("athar-csv-l3-col-start", lang=export_lang),
        _r("athar-csv-l3-col-end", lang=export_lang),
    ]

    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        yield "\ufeff"

        writer.writerow(headers)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for row in user_rows:
            writer.writerow(row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    filename = f"athar_user_{clean_username.replace(' ', '_')}_projects.csv"
    return Response(
        stream_with_context(generate_csv()),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_bp.route("/<string:slug>/export", methods=["GET"])
def exp_community_projects(slug):
    """Level 2 CSV Export: Streams filtered active community projects with formula protection."""
    try:
        export_lang = activate_report_lang_from_request()
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    community = Community.query.filter_by(slug=slug).first()
    if not community:
        return jsonify({"error": "Community not found"}), 404

    export_format = request.args.get("format", "csv").lower()
    if export_format != "csv":
        return jsonify({"error": f"Unsupported format '{export_format}'. Only 'csv' is supported."}), 400

    scoped_args = request.args.to_dict(flat=False)
    scoped_args.pop("community", None)

    query = (
        active_projects_query()
        .filter(Project.community_id == community.id)
        .options(selectinload(Project.tags_rel))
    )
    query = filter_projects(query, MultiDict(scoped_args))
    projects = query.order_by(Project.created_at.desc()).all()

    yes_label = _("athar-bool-yes", lang=export_lang)
    no_label = _("athar-bool-no", lang=export_lang)

    project_rows = []
    for p in projects:
        project_rows.append(
            [
                sanitize_csv_cell(p.id),
                sanitize_csv_cell(p.localized_text("title", export_lang)),
                sanitize_csv_cell(p.t_type(export_lang)),
                sanitize_csv_cell(p.target_wiki),
                sanitize_csv_cell(p.target_wiki_url),
                sanitize_csv_cell(p.t_status(export_lang)),
                sanitize_csv_cell(", ".join(p.all_organizers)),
                sanitize_csv_cell(yes_label if p.is_contest else no_label),
                sanitize_csv_cell(", ".join(p.jury_members or [])),
                sanitize_csv_cell(p.start_date.strftime("%Y-%m-%d") if p.start_date else ""),
                sanitize_csv_cell(p.end_date.strftime("%Y-%m-%d") if p.end_date else ""),
                sanitize_csv_cell(p.created_at.strftime("%Y-%m-%d") if p.created_at else ""),
                sanitize_csv_cell(p.campaign or ""),
                sanitize_csv_cell(", ".join(p.tags)),
                sanitize_csv_cell(p.wiki_link or ""),
            ]
        )

    headers = [
        _r("athar-csv-l2-col-id", lang=export_lang),
        _r("athar-csv-l2-col-title", lang=export_lang),
        _r("athar-csv-l2-col-type", lang=export_lang),
        _r("athar-csv-l2-col-wiki", lang=export_lang),
        _r("athar-csv-l2-col-wiki-url", lang=export_lang),
        _r("athar-csv-l2-col-status", lang=export_lang),
        _r("athar-csv-l2-col-organizers", lang=export_lang),
        _r("athar-csv-l2-col-contest", lang=export_lang),
        _r("athar-csv-l2-col-jury", lang=export_lang),
        _r("athar-csv-l2-col-start", lang=export_lang),
        _r("athar-csv-l2-col-end", lang=export_lang),
        _r("athar-csv-l2-col-created", lang=export_lang),
        _r("athar-csv-l2-col-campaign", lang=export_lang),
        _r("athar-csv-l2-col-tags", lang=export_lang),
        _r("athar-csv-l2-col-wiki-link", lang=export_lang),
    ]

    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        yield "\ufeff"

        writer.writerow(headers)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for row in project_rows:
            writer.writerow(row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    filename = f"athar_{community.slug}_projects.csv"
    if request.args.get("year") and not request.args.get("month"):
        filename = f"athar_{community.slug}_projects_{request.args.get('year')}.csv"
    elif request.args.get("month"):
        m_str = str(request.args.get("month")).replace("-", "_")
        filename = f"athar_{community.slug}_projects_{m_str}.csv"
    elif request.args.get("start_date") or request.args.get("from_date"):
        filename = f"athar_{community.slug}_projects_custom.csv"

    return Response(
        stream_with_context(generate_csv()),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_bp.route("/check-user", methods=["GET"])
def check_user():
    username = (request.args.get("username") or "").strip()
    if not username:
        return jsonify({"exists": False, "error": "Username is required."}), 400

    try:
        result = verify_wikimedia_username(username)
    except ValueError as err:
        return jsonify({"exists": False, "error": str(err)}), 400
    except RuntimeError as err:
        return jsonify({"exists": False, "error": str(err)}), 503

    return jsonify(result), 200


_WIKI_LANGUAGES_CACHE = {"fetched_at": 0.0, "data": None}
_WIKI_LANGUAGES_TTL = 24 * 3600


@api_bp.route("/languages", methods=["GET"])
def list_wikimedia_languages():
    """Return cached Wikimedia + MinT supported language matrix [[code, name, ...], ...]."""
    now_ts = time.time()
    cached = _WIKI_LANGUAGES_CACHE.get("data")
    if cached is not None and (now_ts - _WIKI_LANGUAGES_CACHE["fetched_at"]) < _WIKI_LANGUAGES_TTL:
        return jsonify(cached), 200

    headers = {"User-Agent": current_app.config.get("USER_AGENT", "AtharTool/1.0")}
    mint_base = (current_app.config.get("MINT_API_URL") or "https://translate.wmcloud.org/api").rstrip("/")
    merged = {}
    en_names = {}

    try:
        r_mw = requests.get(
            "https://meta.wikimedia.org/w/api.php",
            params={"action": "query", "meta": "siteinfo", "siprop": "languages", "format": "json"},
            headers=headers,
            timeout=8,
        )
        if r_mw.status_code == 200:
            for item in r_mw.json().get("query", {}).get("languages", []):
                code = str(item.get("code") or "").strip().lower()
                name = str(item.get("*") or "").strip()
                if LANG_CODE_REGEX.match(code):
                    merged[code] = name or code
    except (requests.RequestException, ValueError, TypeError):
        pass

    try:
        r_en = requests.get(
            "https://meta.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "meta": "siteinfo",
                "siprop": "languages",
                "siinlanguagecode": "en",
                "format": "json",
            },
            headers=headers,
            timeout=8,
        )
        if r_en.status_code == 200:
            for item in r_en.json().get("query", {}).get("languages", []):
                c = str(item.get("code") or "").strip().lower()
                n = str(item.get("*") or "").strip()
                if c and n:
                    en_names[c] = n
    except (requests.RequestException, ValueError, TypeError):
        pass

    try:
        r_mint = requests.get(f"{mint_base}/languages", headers=headers, timeout=8)
        if r_mint.status_code == 200:
            mint_data = r_mint.json()
            if isinstance(mint_data, dict):
                for src, tgts in mint_data.items():
                    c = str(src).strip().lower()
                    if LANG_CODE_REGEX.match(c) and c not in merged:
                        merged[c] = en_names.get(c, c)
                    if isinstance(tgts, (dict, list)):
                        for t in tgts:
                            tc = str(t).strip().lower()
                            if LANG_CODE_REGEX.match(tc) and tc not in merged:
                                merged[tc] = en_names.get(tc, tc)
    except (requests.RequestException, ValueError, TypeError):
        pass

    if merged:
        result = []
        for c in sorted(merged.keys()):
            autonym = merged[c]
            en_n = en_names.get(c, "")
            if en_n and en_n.lower() != autonym.lower():
                result.append([c, autonym, en_n])
            else:
                result.append([c, autonym])
        _WIKI_LANGUAGES_CACHE["fetched_at"] = now_ts
        _WIKI_LANGUAGES_CACHE["data"] = result
        return jsonify(result), 200

    return jsonify(cached or []), 200
