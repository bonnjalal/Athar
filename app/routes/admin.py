from datetime import datetime
import json
import re
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.models import Community, CommunityMember, Project, User, db
from app.oauth import admin_required, get_current_user
from app.query_utils import active_projects_query, normalize_username
from app.wiki_utils import (
    is_allowed_wikimedia_host,
    is_reserved_slug,
    verify_wikimedia_username,
)
from scripts.parse_members import fetch_members_from_meta, normalize_meta_page_title

admin_bp = Blueprint("admin", __name__)

ASCII_SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _log_audit(actor_username, action, target_type, target_id, details=None):
    current_app.logger.info(
        json.dumps(
            {
                "actor": actor_username,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "details": details or {},
            },
            ensure_ascii=False,
        )
    )


def _generate_ascii_slug(name: str) -> str:
    lowered = (name or "").lower().strip()
    ascii_only = re.sub(r"[^a-z0-9\s-]", "", lowered)
    slug = re.sub(r"[\s-]+", "-", ascii_only).strip("-")[:64]
    if not slug:
        slug = f"comm-{int(datetime.utcnow().timestamp())}"
    return slug


def _validate_and_normalize_meta_page(raw_link: str) -> str:
    raw = (raw_link or "").strip()
    if not raw:
        raise ValueError("Meta-Wiki roster page or URL is required.")

    if "://" in raw or raw.startswith("//"):
        parsed = urlparse(raw if "://" in raw else f"https:{raw}")
        if not parsed.hostname or not is_allowed_wikimedia_host(parsed.hostname):
            raise ValueError("Roster URL must belong to an official Wikimedia domain.")

    normalized = normalize_meta_page_title(raw)
    if not normalized:
        raise ValueError("Could not extract a valid MediaWiki page title from roster input.")
    if len(normalized) > 255:
        raise ValueError("Roster page title must not exceed 255 characters.")
    return normalized


def _sync_community_roster_only(community: Community) -> int:
    """
    Synchronously fetch a community's single Meta-Wiki roster page (timeout=15)
    and upsert User + CommunityMember rows without invoking per-user CentralAuth HTTP calls.
    """
    usernames = fetch_members_from_meta(community.meta_roster_page)
    if not usernames:
        return 0

    now = datetime.utcnow()
    added_count = 0
    for raw_name in usernames:
        clean_name = normalize_username(raw_name)
        if not clean_name:
            continue
        user = User.query.filter(func.lower(User.username) == clean_name.lower()).first()
        if not user:
            user = User(
                username=clean_name,
                is_member=True,
                first_seen=now,
                last_synced=None,
            )
            db.session.add(user)
            db.session.flush()
        else:
            user.is_member = True

        membership = CommunityMember.query.filter_by(
            community_id=community.id,
            user_id=user.id,
        ).first()
        if not membership:
            db.session.add(
                CommunityMember(
                    community_id=community.id,
                    user_id=user.id,
                    role="member",
                    verified=True,
                    added_at=now,
                )
            )
        else:
            membership.verified = True
        added_count += 1

    db.session.commit()
    return added_count


def _build_admin_context():
    communities = Community.query.order_by(Community.name.asc()).all()
    active_projects = (
        active_projects_query()
        .options(joinedload(Project.community))
        .order_by(Project.created_at.desc())
        .limit(200)
        .all()
    )
    deleted_projects = (
        Project.query.filter(Project.is_deleted.is_(True))
        .options(joinedload(Project.community))
        .order_by(Project.deleted_at.desc(), Project.id.desc())
        .all()
    )
    admins = User.query.filter(User.is_admin.is_(True)).order_by(User.username.asc()).all()
    return {
        "communities": communities,
        "active_projects": active_projects,
        "deleted_projects": deleted_projects,
        "admins": admins,
    }


def _render_admin_page(status_code=200):
    return render_template("admin.html", **_build_admin_context()), status_code


@admin_bp.route("/admin", methods=["GET"])
@admin_required
def admin_console():
    return _render_admin_page(200)


@admin_bp.route("/add-community", methods=["POST"])
@admin_required
def add_community():
    """Admin-only community creation endpoint."""
    actor = get_current_user()
    name = (request.form.get("community_name") or request.form.get("name") or "").strip()
    raw_link = (request.form.get("community_link") or request.form.get("meta_roster_page") or "").strip()
    raw_slug = (request.form.get("slug") or "").strip().lower()
    contact_email = (request.form.get("contact_email") or "").strip() or None
    redirect_to = (request.form.get("redirect_to") or "").strip()

    if not name or len(name) > 120:
        flash("اسم المجتمع مطلوب (بحد أقصى 120 حرفاً).", "error")
        return _render_admin_page(400)

    if contact_email and len(contact_email) > 128:
        flash("البريد الإلكتروني طويل جداً.", "error")
        return _render_admin_page(400)

    try:
        meta_roster_page = _validate_and_normalize_meta_page(raw_link)
    except ValueError as err:
        flash(str(err), "error")
        return _render_admin_page(400)

    existing_name = Community.query.filter(func.lower(Community.name) == name.lower()).first()
    if existing_name:
        flash(f"المجتمع '{name}' مسجل مسبقاً في قاعدة البيانات.", "info")
        return _render_admin_page(400)

    if raw_slug:
        if len(raw_slug) > 64 or not ASCII_SLUG_REGEX.match(raw_slug):
            flash("المعرّف (slug) يجب أن يتكون من أحرف إنجليزية صغيرة وأرقام وشرطات فقط.", "error")
            return _render_admin_page(400)
        if is_reserved_slug(raw_slug):
            flash(f"المعرّف '{raw_slug}' محجوز للنظام ولا يمكن استخدامه.", "error")
            return _render_admin_page(400)
        if Community.query.filter_by(slug=raw_slug).first():
            flash(f"المعرّف '{raw_slug}' مستخدم من قبل مجتمع آخر.", "error")
            return _render_admin_page(400)
        slug = raw_slug
    else:
        base_slug = _generate_ascii_slug(name)
        slug = base_slug
        counter = 1
        while is_reserved_slug(slug) or Community.query.filter_by(slug=slug).first():
            slug = f"{base_slug[:58]}-{counter}"
            counter += 1

    new_community = Community(
        name=name,
        slug=slug,
        meta_roster_page=meta_roster_page,
        contact_email=contact_email,
    )
    db.session.add(new_community)
    db.session.commit()

    synced_count = _sync_community_roster_only(new_community)
    _log_audit(
        actor.username,
        "community.create",
        "community",
        new_community.id,
        {"slug": new_community.slug, "roster_count": synced_count},
    )

    if synced_count:
        flash(f"تمت إضافة المجتمع '{name}' ومزامنة {synced_count} عضو.", "success")
    else:
        flash(f"تمت إضافة المجتمع '{name}' بنجاح (لم تُسحب أسماء أعضاء من الصفحة حالياً).", "info")

    if redirect_to == "admin":
        return redirect(url_for("admin.admin_console"))
    return redirect(url_for("web.dashboard", slug=new_community.slug))


@admin_bp.route("/admin/community/<int:community_id>/edit", methods=["POST"])
@admin_required
def edit_community(community_id):
    """Admin-only community metadata and slug editor."""
    actor = get_current_user()
    community = db.session.get(Community, community_id)
    if not community:
        abort(404)

    name = (request.form.get("name") or "").strip()
    new_slug = (request.form.get("slug") or "").strip().lower()
    raw_link = (request.form.get("meta_roster_page") or request.form.get("community_link") or "").strip()
    contact_email = (request.form.get("contact_email") or "").strip() or None

    if not name or len(name) > 120:
        flash("اسم المجتمع مطلوب (بحد أقصى 120 حرفاً).", "error")
        return _render_admin_page(400)

    if not new_slug or len(new_slug) > 64 or not ASCII_SLUG_REGEX.match(new_slug):
        flash("المعرّف (slug) يجب أن يتكون من أحرف إنجليزية صغيرة وأرقام وشرطات فقط (1-64 حرفاً).", "error")
        return _render_admin_page(400)

    if is_reserved_slug(new_slug):
        flash(f"المعرّف '{new_slug}' محجوز للنظام.", "error")
        return _render_admin_page(400)

    if contact_email and len(contact_email) > 128:
        flash("البريد الإلكتروني طويل جداً.", "error")
        return _render_admin_page(400)

    try:
        meta_roster_page = _validate_and_normalize_meta_page(raw_link)
    except ValueError as err:
        flash(str(err), "error")
        return _render_admin_page(400)

    dup_name = Community.query.filter(
        func.lower(Community.name) == name.lower(),
        Community.id != community.id,
    ).first()
    if dup_name:
        flash(f"اسم المجتمع '{name}' مستخدم بالفعل.", "error")
        return _render_admin_page(400)

    dup_slug = Community.query.filter(
        Community.slug == new_slug,
        Community.id != community.id,
    ).first()
    if dup_slug:
        flash(f"المعرّف '{new_slug}' مستخدم بالفعل.", "error")
        return _render_admin_page(400)

    old_slug = community.slug
    roster_changed = meta_roster_page != community.meta_roster_page

    community.name = name
    community.slug = new_slug
    community.meta_roster_page = meta_roster_page
    community.contact_email = contact_email
    db.session.commit()

    if session.get("community_slug") == old_slug:
        session["community_slug"] = new_slug

    synced_count = 0
    if roster_changed:
        synced_count = _sync_community_roster_only(community)

    _log_audit(
        actor.username,
        "community.edit",
        "community",
        community.id,
        {"old_slug": old_slug, "new_slug": new_slug, "roster_changed": roster_changed, "synced_count": synced_count},
    )
    flash(f"تم تحديث بيانات المجتمع '{community.name}' بنجاح.", "success")
    return redirect(url_for("admin.admin_console"))


@admin_bp.route("/admin/project/<int:project_id>/soft-delete", methods=["POST"])
@admin_required
def soft_delete_project(project_id):
    actor = get_current_user()
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)

    if not project.is_deleted:
        project.is_deleted = True
        project.deleted_at = datetime.utcnow()
        project.deleted_by = actor.username
        db.session.commit()
        _log_audit(actor.username, "project.soft_delete", "project", project.id, {"title": project.title})
        flash(f"تم حذف النشاط '{project.title}' مبدئياً (قابل للاستعادة من سجل المحذوفات).", "success")
    else:
        flash("هذا النشاط محذوف مبدئياً بالفعل.", "info")

    return redirect(url_for("admin.admin_console"))


@admin_bp.route("/admin/project/<int:project_id>/restore", methods=["POST"])
@admin_required
def restore_project(project_id):
    actor = get_current_user()
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)

    if project.is_deleted:
        project.is_deleted = False
        project.deleted_at = None
        project.deleted_by = None
        db.session.commit()
        _log_audit(actor.username, "project.restore", "project", project.id, {"title": project.title})
        flash(f"تمت استعادة النشاط '{project.title}' بنجاح.", "success")
    else:
        flash("هذا النشاط نشط بالفعل.", "info")

    return redirect(url_for("admin.admin_console"))


@admin_bp.route("/admin/project/<int:project_id>/purge", methods=["POST"])
@admin_required
def purge_project(project_id):
    actor = get_current_user()
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)

    if not project.is_deleted:
        flash("يجب حذف النشاط مبدئياً قبل تنفيذ الحذف النهائي.", "error")
        return _render_admin_page(400)

    confirm_id = (request.form.get("confirm_project_id") or "").strip()
    if confirm_id != str(project.id):
        flash("تأكيد المعرّف الرقمي للنشاط غير متطابق؛ لم يتم الحذف النهائي.", "error")
        return _render_admin_page(400)

    deleted_title = project.title
    db.session.delete(project)
    db.session.commit()
    _log_audit(actor.username, "project.purge", "project", project_id, {"title": deleted_title})
    flash(f"تم الحذف النهائي للنشاط '{deleted_title}' من قاعدة البيانات.", "success")
    return redirect(url_for("admin.admin_console"))


@admin_bp.route("/admin/admins/grant", methods=["POST"])
@admin_required
def grant_admin():
    actor = get_current_user()
    raw_username = (request.form.get("username") or "").strip()
    clean_username = normalize_username(raw_username)
    if not clean_username:
        flash("يرجى إدخال اسم مستخدم ويكيميديا صالح.", "error")
        return _render_admin_page(400)

    try:
        result = verify_wikimedia_username(clean_username)
    except RuntimeError:
        flash("تعذّر التحقق من اسم المستخدم عبر ويكيميديا CentralAuth حالياً.", "error")
        return _render_admin_page(503)

    if not result.get("exists"):
        flash(f"اسم المستخدم '{clean_username}' غير موجود في ويكيميديا.", "error")
        return _render_admin_page(400)

    canonical_name = normalize_username(result["username"])
    user = User.query.filter(func.lower(User.username) == canonical_name.lower()).first()
    if not user:
        user = User(
            username=canonical_name,
            is_member=False,
            is_admin=True,
        )
        db.session.add(user)
    else:
        user.is_admin = True
    db.session.commit()

    _log_audit(actor.username, "admin.grant", "user", user.id, {"target_username": user.username})
    flash(f"تم منح صلاحيات الإدارة للمستخدم '{user.username}'.", "success")
    return redirect(url_for("admin.admin_console"))


@admin_bp.route("/admin/admins/revoke", methods=["POST"])
@admin_required
def revoke_admin():
    actor = get_current_user()
    raw_user_id = request.form.get("user_id")
    raw_username = (request.form.get("username") or "").strip()

    target = None
    if raw_user_id:
        try:
            target = db.session.get(User, int(raw_user_id))
        except (ValueError, TypeError):
            target = None
    elif raw_username:
        norm = normalize_username(raw_username)
        target = User.query.filter(func.lower(User.username) == norm.lower()).first()

    if not target:
        flash("المستخدم المطلوب غير موجود.", "error")
        return _render_admin_page(400)

    if target.id == actor.id:
        flash("لا يمكنك سحب صلاحيات الإدارة من حسابك الشخصي.", "error")
        return _render_admin_page(400)

    admin_count = User.query.filter(User.is_admin.is_(True)).count()
    if target.is_admin and admin_count <= 1:
        flash("لا يمكن إزالة آخر مدير أداة نشط في النظام.", "error")
        return _render_admin_page(400)

    if target.is_admin:
        target.is_admin = False
        db.session.commit()
        _log_audit(actor.username, "admin.revoke", "user", target.id, {"target_username": target.username})
        flash(f"تم سحب صلاحيات الإدارة من '{target.username}'.", "success")
    else:
        flash(f"المستخدم '{target.username}' ليس مديراً حالياً.", "info")

    return redirect(url_for("admin.admin_console"))

