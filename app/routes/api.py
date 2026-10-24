import csv
import io
import calendar
from datetime import datetime, date
from flask import Blueprint, jsonify, request, Response, session
from app.models import Community, Project, User, StatSnapshot, CommunityMember
from app.oauth import member_required, project_editor_required, get_current_user
from app import db
from sqlalchemy import func
import bleach
from app.wiki_utils import normalize_wiki_target

api_bp = Blueprint("api", __name__)


def _filter_projects_by_date(query, args):
    """Filter Project query by year, month, or custom date range."""
    filter_type = args.get("filter_type")
    year_arg = args.get("year")
    month_arg = args.get("month")
    start_arg = args.get("start_date") or args.get("from_date")
    end_arg = args.get("end_date") or args.get("to_date")

    start_date = None
    end_date = None

    if filter_type == "year" or (year_arg and not month_arg and not start_arg and not filter_type):
        if year_arg:
            try:
                y = int(year_arg)
                start_date = date(y, 1, 1)
                end_date = date(y, 12, 31)
            except (ValueError, TypeError):
                pass
    elif filter_type == "month" or (month_arg and not start_arg and not filter_type):
        try:
            if month_arg and "-" in str(month_arg):
                parts = str(month_arg).split("-")
                y = int(parts[0])
                m = int(parts[1])
            else:
                y = int(year_arg) if year_arg else datetime.utcnow().year
                m = int(month_arg)
            if 1 <= m <= 12:
                _, last_day = calendar.monthrange(y, m)
                start_date = date(y, m, 1)
                end_date = date(y, m, last_day)
        except (ValueError, TypeError):
            pass
    elif filter_type == "custom" or start_arg or end_arg:
        if start_arg:
            try:
                start_date = datetime.strptime(start_arg.strip(), "%Y-%m-%d").date()
            except ValueError:
                pass
        if end_arg:
            try:
                end_date = datetime.strptime(end_arg.strip(), "%Y-%m-%d").date()
            except ValueError:
                pass

    if start_date:
        query = query.filter(
            db.or_(
                db.and_(Project.start_date.isnot(None), Project.start_date >= start_date),
                db.and_(Project.start_date.is_(None), Project.created_at >= datetime.combine(start_date, datetime.min.time()))
            )
        )
    if end_date:
        query = query.filter(
            db.or_(
                db.and_(Project.start_date.isnot(None), Project.start_date <= end_date),
                db.and_(Project.start_date.is_(None), Project.created_at <= datetime.combine(end_date, datetime.max.time()))
            )
        )

    return query, start_date, end_date

def get_request_data():
    """Extract request data supporting both JSON payloads and Form submissions."""
    if request.is_json:
        return request.get_json() or {}
    return request.form.to_dict()

# ----------------------------------------------------------------------
# Global Endpoints
# ----------------------------------------------------------------------

@api_bp.route("/communities", methods=["GET"])
def get_communities():
    communities = Community.query.all()
    return jsonify([community.to_dict() for community in communities]), 200

@api_bp.route("/stats", methods=["GET"])
def get_stats():
    total_members = User.query.filter_by(is_member=True).count()
    total_projects = Project.query.count()
    
    latest_snapshots = StatSnapshot.query.order_by(StatSnapshot.recorded_at.desc()).limit(100).all()
    total_edits = sum(s.total_edits for s in latest_snapshots)


    return jsonify({
        "total_members": total_members,
        "total_projects": total_projects,
        "total_edits": total_edits
    }), 200

@api_bp.route("/projects", methods=["GET"])
def list_projects():
    status = request.args.get("status")
    project_type = request.args.get("type") or request.args.get("project_type")
    target_wiki = request.args.get("target_wiki")
    
    query = Project.query
    if status:
        query = query.filter_by(status=status)
    if project_type:
        query = query.filter_by(project_type=project_type)
    if target_wiki:
        try:
            norm_code, norm_url = normalize_wiki_target(target_wiki)
            from urllib.parse import urlparse
            norm_domain = urlparse(norm_url).netloc
            query = query.filter(
                (Project.target_wiki == target_wiki) |
                (Project.target_wiki == norm_code) |
                (Project.target_wiki == norm_domain)
            )
        except ValueError:
            query = query.filter_by(target_wiki=target_wiki)
        
    projects = query.order_by(Project.created_at.desc()).all()
    return jsonify([p.to_dict() for p in projects]), 200

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
        
    count_community_member = CommunityMember.query.filter_by(community_id=community.id).count()
    count_project = Project.query.filter_by(community_id=community.id).count()
    
    # Calculate aggregate edits across community members' latest snapshots
    member_user_ids = [cm.user_id for cm in community.members]
    total_edits = 0
    if member_user_ids:
        for uid in member_user_ids:
            latest = StatSnapshot.query.filter_by(user_id=uid).order_by(StatSnapshot.recorded_at.desc()).first()
            if latest:
                total_edits += latest.total_edits
    

    count_community_member = (
        db.session.query(func.count(CommunityMember.user_id))
        .filter(CommunityMember.community_id == community.id)
        .scalar()
    )

    count_project = (
        db.session.query(func.count(Project.id))
        .filter(Project.community_id == community.id)
        .scalar()
    )

    activity_rows = (
        db.session.query(
            Project.project_type,
            func.count(Project.id).label("total")
        )
        .filter(Project.community_id == community.id)
        .group_by(Project.project_type)
        .all()
    )

    activities_by_type = {
        project_type: total
        for project_type, total in activity_rows
    }
    community_members = CommunityMember.query.filter_by(
        community_id=community.id
    ).all()

    member_ids = [cm.user_id for cm in community_members]

    total_edits_member_comm = total_edits
    return jsonify({
        "community": community.name,
        "slug": community.slug,
        "total_members": count_community_member,
        "total_projects": count_project,
        "total_edits": total_edits,
        # Backward-compatible keys for earlier code:
        "community_name": community.name,
        "total_community_member": count_community_member,
        "total_project_member": count_project,
        "total_edits_member_comm": total_edits_member_comm,
        "activities_by_type": activities_by_type
    }), 200

    
@api_bp.route("/<string:slug>/members", methods=["GET"])
def list_members(slug):
    community = Community.query.filter_by(slug=slug).first()
    if not community:
        return jsonify({"error": "Community not found"}), 404
        
    community_members = CommunityMember.query.filter_by(community_id=community.id).all()
    members = []
    for cm in community_members:
        member = cm.user
        if not member:
            continue
        last_snapshot = StatSnapshot.query.filter_by(user_id=member.id).order_by(StatSnapshot.recorded_at.desc()).first()
        members.append({
            "id": member.id,
            "username": member.username,
            "is_member": member.is_member,
            "role": cm.role,
            "verified": cm.verified,
            "added_at": cm.added_at.isoformat() if cm.added_at else None,
            "first_seen": member.first_seen.isoformat() if member.first_seen else None,
            "last_synced": member.last_synced.isoformat() if member.last_synced else None,
            "total_edits": last_snapshot.total_edits if last_snapshot else 0
        })
    return jsonify(members), 200

@api_bp.route("/<string:slug>/projects", methods=["GET"])
def list_slug_project(slug):
    community = Community.query.filter_by(slug=slug).first()
    if not community:
        return jsonify({"error": "Community not found"}), 404

    status = request.args.get("status")
    project_type = request.args.get("type") or request.args.get("project_type")
    target_wiki = request.args.get("target_wiki")

    query = Project.query.filter_by(community_id=community.id)
    if status:
        query = query.filter_by(status=status)
    if project_type:
        query = query.filter_by(project_type=project_type)
    if target_wiki:
        try:
            norm_code, norm_url = normalize_wiki_target(target_wiki)
            from urllib.parse import urlparse
            norm_domain = urlparse(norm_url).netloc
            query = query.filter(
                (Project.target_wiki == target_wiki) |
                (Project.target_wiki == norm_code) |
                (Project.target_wiki == norm_domain)
            )
        except ValueError:
            query = query.filter_by(target_wiki=target_wiki)

    query, _, _ = _filter_projects_by_date(query, request.args)

    projects = query.order_by(Project.created_at.desc()).all()
    return jsonify([p.to_dict() for p in projects]), 200

@api_bp.route("/<string:slug>/projects", methods=["POST"])
@api_bp.route("/<string:slug>/project", methods=["POST"])
@member_required
def create_projetct(slug):
    community = Community.query.filter_by(slug=slug).first()
    if not community:
        return jsonify({"error": "Community not found"}), 404
        
    data = get_request_data()
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Project title is required."}), 400

    raw_description = (data.get("description") or "").strip()
    raw_type = (data.get("project_type") or "Workshop").strip()
    custom_type = (data.get("custom_project_type") or "").strip()
    if raw_type == "Other" and custom_type:
        project_type = custom_type
    elif raw_type == "Other":
        project_type = "Other"
    else:
        project_type = raw_type or "Workshop"

    raw_target_wiki = data.get("target_wiki", "arwiki")
    try:
        target_wiki, _ = normalize_wiki_target(raw_target_wiki)
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    status = data.get("status", "In Progress")

    safe_description = bleach.clean(
        raw_description,
        tags=["p", "b", "i", "strong", "em", "ul", "ol", "li", "a", "br"],
        attributes={"a": ["href", "title"]},
        strip=True
    )

    co_orgs_raw = data.get("co_organizers", [])
    if isinstance(co_orgs_raw, str):
        co_organizers = [u.strip() for u in co_orgs_raw.split(",") if u.strip()]
    elif isinstance(co_orgs_raw, list):
        co_organizers = [str(u).strip() for u in co_orgs_raw if str(u).strip()]
    else:
        co_organizers = []

    is_contest = bool(data.get("is_contest", False))
    jury_raw = data.get("jury_members", [])
    if isinstance(jury_raw, str):
        jury_members = [j.strip() for j in jury_raw.split(",") if j.strip()] if is_contest else []
    elif isinstance(jury_raw, list):
        jury_members = [str(j).strip() for j in jury_raw if str(j).strip()] if is_contest else []
    else:
        jury_members = []

    # Current user identification (handles OAuth session and MOCK_AUTH)
    curr_user = get_current_user()
    if curr_user and isinstance(curr_user, dict):
        lead_user = curr_user.get("username", "MoroccoVolunteer")
    elif curr_user and hasattr(curr_user, "username"):
        lead_user = curr_user.username
    else:
        lead_user = session.get("username", "MoroccoVolunteer")

    start_date_val = None
    end_date_val = None
    if data.get("start_date"):
        try:
            start_date_val = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
        except ValueError:
            pass
    if data.get("end_date"):
        try:
            end_date_val = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    raw_status = data.get("status")
    from app.wiki_utils import determine_project_status
    status = determine_project_status(start_date_val, end_date_val, raw_status)
        
    new_project = Project(
        community_id=community.id,
        title=title,
        description=safe_description,
        project_type=project_type,
        target_wiki=target_wiki,
        status=status,
        start_date=start_date_val,
        end_date=end_date_val,
        lead_organizer=lead_user,
        co_organizers=co_organizers,
        is_contest=is_contest,
        jury_members=jury_members
    )
    db.session.add(new_project)
    db.session.commit()
    
    return jsonify({
        "message": "Project created successfully",
        "project": new_project.to_dict()
    }), 201

@api_bp.route("/<string:slug>/projects/<int:project_id>", methods=["GET"])
@api_bp.route("/projects/<int:project_id>", methods=["GET"])
def get_project(project_id, slug=None):
    if slug:
        community = Community.query.filter_by(slug=slug).first()
        if not community:
            return jsonify({"error": "Community not found"}), 404
        project = Project.query.filter_by(id=project_id, community_id=community.id).first_or_404()
    else:
        project = Project.query.get_or_404(project_id)
    return jsonify(project.to_dict()), 200

@api_bp.route("/<string:slug>/projects/<int:project_id>", methods=["PUT"])
@api_bp.route("/projects/<int:project_id>", methods=["PUT"])
@project_editor_required
def update_project(project_id, slug=None):
    if slug:
        community = Community.query.filter_by(slug=slug).first()
        if not community:
            return jsonify({"error": "Community not found"}), 404
        project = Project.query.filter_by(id=project_id, community_id=community.id).first_or_404()
    else:
        project = Project.query.get_or_404(project_id)

    data = get_request_data()

    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify({"error": "Title cannot be empty."}), 400
        project.title = title

    if "description" in data:
        project.description = bleach.clean(
            data["description"].strip(),
            tags=["p", "b", "i", "strong", "em", "ul", "ol", "li", "a", "br"],
            attributes={"a": ["href", "title"]},
            strip=True
        )

    if "project_type" in data or "custom_project_type" in data:
        raw_type = (data.get("project_type") or project.project_type).strip()
        custom_type = (data.get("custom_project_type") or "").strip()
        if raw_type == "Other" and custom_type:
            project.project_type = custom_type
        else:
            project.project_type = raw_type or project.project_type

    if "target_wiki" in data:
        raw_target_wiki = (data.get("target_wiki") or "").strip()
        try:
            target_wiki, _ = normalize_wiki_target(raw_target_wiki)
            project.target_wiki = target_wiki
        except ValueError as err:
            return jsonify({"error": str(err)}), 400

    if "is_contest" in data:
        project.is_contest = bool(data["is_contest"])

    if "co_organizers" in data:
        co_orgs_raw = data["co_organizers"]
        if isinstance(co_orgs_raw, str):
            project.co_organizers = [u.strip() for u in co_orgs_raw.split(",") if u.strip()]
        elif isinstance(co_orgs_raw, list):
            project.co_organizers = [str(u).strip() for u in co_orgs_raw if str(u).strip()]

    if "jury_members" in data:
        jury_raw = data["jury_members"]
        if isinstance(jury_raw, str):
            project.jury_members = [j.strip() for j in jury_raw.split(",") if j.strip()] if project.is_contest else []
        elif isinstance(jury_raw, list):
            project.jury_members = [str(j).strip() for j in jury_raw if str(j).strip()] if project.is_contest else []

    if "start_date" in data:
        if data["start_date"]:
            try:
                project.start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            project.start_date = None

    if "end_date" in data:
        if data["end_date"]:
            try:
                project.end_date = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            project.end_date = None

    if "status" in data:
        raw_status = data["status"]
        from app.wiki_utils import determine_project_status
        project.status = determine_project_status(project.start_date, project.end_date, raw_status)
    elif "start_date" in data or "end_date" in data:
        from app.wiki_utils import determine_project_status
        project.status = determine_project_status(project.start_date, project.end_date, "auto")

    db.session.commit()
    return jsonify({
        "message": "Project updated successfully",
        "project": project.to_dict()
    }), 200

@api_bp.route("/<string:slug>/export", methods=["GET"])
def exp_community_projects(slug):
    community = Community.query.filter_by(slug=slug).first()
    if not community:
        return jsonify({"error": "Community not found"}), 404

    export_format = request.args.get("format", "csv").lower()
    if export_format != "csv":
        return jsonify({"error": f"Unsupported format '{export_format}'. Only 'csv' is supported."}), 400

    status = request.args.get("status")
    project_type = request.args.get("type") or request.args.get("project_type")
    target_wiki = request.args.get("target_wiki")

    query = Project.query.filter_by(community_id=community.id)
    if status:
        query = query.filter_by(status=status)
    if project_type:
        query = query.filter_by(project_type=project_type)
    if target_wiki:
        query = query.filter_by(target_wiki=target_wiki)

    query, start_date, end_date = _filter_projects_by_date(query, request.args)

    projects = query.order_by(Project.created_at.desc()).all()
    
    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens Arabic text without corruption
    output.write('\ufeff')
    writer = csv.writer(output)

    writer.writerow([
        "المعرف",
        "عنوان النشاط",
        "نوع النشاط",
        "المشروع المستهدف",
        "رابط المشروع",
        "الحالة",
        "المنظم الرئيسي",
        "المنظمون المشاركون",
        "مسابقة",
        "لجنة التحكيم",
        "تاريخ البدء",
        "تاريخ الانتهاء",
        "تاريخ التسجيل"
    ])
    for p in projects:
        writer.writerow([
            p.id,
            p.title,
            p.project_type,
            p.target_wiki,
            p.target_wiki_url,
            p.status,
            p.lead_organizer,
            ", ".join(p.co_organizers or []),
            "نعم" if p.is_contest else "لا",
            ", ".join(p.jury_members or []),
            p.start_date.strftime("%Y-%m-%d") if p.start_date else "",
            p.end_date.strftime("%Y-%m-%d") if p.end_date else "",
            p.created_at.strftime("%Y-%m-%d") if p.created_at else ""
        ])

    filename = f"athar_{community.slug}_projects.csv"
    if request.args.get("year") and not request.args.get("month"):
        filename = f"athar_{community.slug}_projects_{request.args.get('year')}.csv"
    elif request.args.get("month"):
        m_str = str(request.args.get("month")).replace("-", "_")
        filename = f"athar_{community.slug}_projects_{m_str}.csv"
    elif request.args.get("start_date") or request.args.get("from_date"):
        filename = f"athar_{community.slug}_projects_custom.csv"

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )


@api_bp.route("/check-user", methods=["GET"])
def check_user():
    username = (request.args.get("username") or "").strip()
    if not username:
        return jsonify({"exists": False, "error": "Username is required."}), 400

    # Check local DB first
    local_user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if local_user:
        return jsonify({
            "exists": True,
            "username": local_user.username,
            "source": "local"
        }), 200

    # Check Wikimedia CentralAuth
    import requests
    url = "https://meta.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "meta": "globaluserinfo",
        "guiuser": username,
        "format": "json"
    }
    headers = {"User-Agent": "AtharTool/1.0 (https://toolforge.org/athar; contact@athar)"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=5)
        if r.status_code == 200:
            gui = r.json().get("query", {}).get("globaluserinfo", {})
            if "missing" in gui:
                return jsonify({"exists": False, "username": username}), 200
            canonical_name = gui.get("name", username)
            return jsonify({
                "exists": True,
                "username": canonical_name,
                "id": gui.get("id"),
                "home": gui.get("home", ""),
                "source": "wikimedia"
            }), 200
    except Exception:
        pass

    return jsonify({"exists": False, "username": username}), 200