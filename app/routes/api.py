import csv
import io
from datetime import datetime
from flask import Blueprint, jsonify, request, Response, session
from app.models import Community, Project, User, StatSnapshot, CommunityMember
from app.oauth import member_required, project_editor_required, get_current_user
from app import db
from sqlalchemy import func
import bleach

api_bp = Blueprint("api", __name__)

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
        query = query.filter_by(target_wiki=target_wiki)
        
    projects = query.order_by(Project.created_at.desc()).all()
    return jsonify([p.to_dict() for p in projects]), 200

@api_bp.route("/export", methods=["GET"])
def export_csv():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)

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
            p.created_at.strftime("%Y-%m-%d") if p.created_at else ""
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=athar_projects.csv"}
    )

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

    total_edits_member_comm = 0

    if member_ids:
        total_edits_member_comm = (
            db.session.query(
                func.coalesce(func.sum(StatSnapshot.total_edits), 0)
            )
            .filter(StatSnapshot.user_id.in_(member_ids))
            .scalar()
        )
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
        query = query.filter_by(target_wiki=target_wiki)

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
    project_type = data.get("project_type", "Workshop")
    target_wiki = data.get("target_wiki", community.default_wiki or "ar.wikipedia.org")
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

    if "project_type" in data:
        project.project_type = data["project_type"]
    if "target_wiki" in data:
        project.target_wiki = data["target_wiki"]
    if "status" in data:
        project.status = data["status"]

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

    projects = query.order_by(Project.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)

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
            p.created_at.strftime("%Y-%m-%d") if p.created_at else ""
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=athar_{community.slug}_projects.csv"}
    )