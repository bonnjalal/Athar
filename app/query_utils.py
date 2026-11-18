"""
app/query_utils.py

Shared query boundaries, unified project filtering, batch snapshot lookups,
tag synchronization, and CSV/username normalization utilities.
"""
import calendar
from datetime import date, datetime
from typing import Any
from urllib.parse import unquote, urlparse

from flask import abort
from sqlalchemy import extract, func

from app import db
from app.models import Project, ProjectTag, StatSnapshot
from app.wiki_utils import (
    STANDARD_ACTIVITY_TYPES,
    normalize_tag,
    normalize_wiki_target,
    parse_tags_input,
)


def active_projects_query():
    """Canonical base query excluding soft-deleted projects across all public/organizer views."""
    return Project.query.filter(Project.is_deleted.is_(False))


def get_active_project_or_404(project_id):
    """Fetch a non-deleted project by ID or abort with HTTP 404."""
    project = active_projects_query().filter(Project.id == project_id).first()
    if not project:
        abort(404)
    return project


def sync_project_tags(project, raw_tags, replace=True):
    """
    Synchronize Project.tags_rel rows from a comma/newline string or iterable of tag strings.
    Enforces normalization and the 20-tag cap via parse_tags_input().
    """
    desired = parse_tags_input(raw_tags)

    if replace:
        existing_map = {t.tag: t for t in (project.tags_rel or [])}
        desired_set = set(desired)
        for existing in list(project.tags_rel or []):
            if existing.tag not in desired_set:
                project.tags_rel.remove(existing)
        for tag in desired:
            if tag not in existing_map:
                project.tags_rel.append(ProjectTag(tag=tag))
    else:
        existing_tags = {t.tag for t in (project.tags_rel or [])}
        merged = list(existing_tags) + [t for t in desired if t not in existing_tags]
        if len(merged) > 20:
            raise ValueError("Maximum of 20 tags allowed per activity.")
        for tag in desired:
            if tag not in existing_tags:
                project.tags_rel.append(ProjectTag(tag=tag))

    return desired


def get_latest_snapshots_map(user_ids) -> dict[int, StatSnapshot]:
    """Return {user_id: latest StatSnapshot} in a single grouped query (eliminates N+1 loops)."""
    clean_ids = [uid for uid in set(user_ids or []) if uid is not None]
    if not clean_ids:
        return {}

    latest_subq = (
        db.session.query(
            StatSnapshot.user_id,
            func.max(StatSnapshot.recorded_at).label("max_recorded"),
        )
        .filter(StatSnapshot.user_id.in_(clean_ids))
        .group_by(StatSnapshot.user_id)
        .subquery()
    )

    snaps = (
        db.session.query(StatSnapshot)
        .join(
            latest_subq,
            db.and_(
                StatSnapshot.user_id == latest_subq.c.user_id,
                StatSnapshot.recorded_at == latest_subq.c.max_recorded,
            ),
        )
        .order_by(StatSnapshot.id.desc())
        .all()
    )

    result = {}
    for snap in snaps:
        if snap.user_id not in result:
            result[snap.user_id] = snap
    return result


def get_latest_snapshots_total(user_ids) -> int:
    """Return aggregate total_edits across the latest StatSnapshot of each user_id."""
    return sum((s.total_edits or 0) for s in get_latest_snapshots_map(user_ids).values())


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def filter_projects_by_date(query, args):
    """
    Filter Project query by year, month (with or without year), or custom date range
    using coalesced effective dates and interval overlap semantics.
    Returns (filtered_query, start_date, end_date).
    """
    filter_type = args.get("filter_type")
    year_arg = (args.get("year") or "").strip() if args.get("year") is not None else ""
    month_arg = (args.get("month") or "").strip() if args.get("month") is not None else ""
    start_arg = args.get("start_date") or args.get("from_date")
    end_arg = args.get("end_date") or args.get("to_date")

    eff_start = func.coalesce(Project.start_date, func.date(Project.created_at), type_=db.Date)
    eff_end = func.coalesce(Project.end_date, Project.start_date, func.date(Project.created_at), type_=db.Date)

    start_date = None
    end_date = None

    # Month-only filter across any year when month is given without year or custom dates
    if (
        month_arg
        and not year_arg
        and "-" not in month_arg
        and not start_arg
        and not end_arg
        and filter_type != "month"
    ):
        try:
            m = int(month_arg)
            if 1 <= m <= 12:
                query = query.filter(
                    db.or_(
                        extract("month", eff_start) == m,
                        extract("month", eff_end) == m,
                        db.and_(
                            extract("year", eff_start) == extract("year", eff_end),
                            extract("month", eff_start) <= m,
                            extract("month", eff_end) >= m,
                        ),
                    )
                )
        except (ValueError, TypeError):
            pass
        return query, None, None

    if filter_type == "year" or (year_arg and not month_arg and not start_arg and not end_arg and not filter_type):
        if year_arg:
            try:
                y = int(year_arg)
                start_date = date(y, 1, 1)
                end_date = date(y, 12, 31)
            except (ValueError, TypeError):
                pass
    elif filter_type == "month" or (month_arg and not start_arg and not end_arg and not filter_type):
        try:
            if month_arg and "-" in month_arg:
                parts = month_arg.split("-", 1)
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
                start_date = datetime.strptime(str(start_arg).strip(), "%Y-%m-%d").date()
            except ValueError:
                pass
        if end_arg:
            try:
                end_date = datetime.strptime(str(end_arg).strip(), "%Y-%m-%d").date()
            except ValueError:
                pass

    if start_date:
        query = query.filter(eff_end >= start_date)
    if end_date:
        query = query.filter(eff_start <= end_date)

    return query, start_date, end_date


def filter_projects_by_status(query, args):
    """
    Filter project query by explicit 'status' or report inclusion flags.
    Normalizes 'Canceled' and 'Cancelled' equivalence.
    """
    explicit_status = args.get("status")
    if explicit_status:
        canonical_map = {
            "in progress": ["In Progress"],
            "planned": ["Planned"],
            "completed": ["Completed"],
            "canceled": ["Canceled", "Cancelled"],
            "cancelled": ["Canceled", "Cancelled"],
        }
        statuses = []
        for raw_s in str(explicit_status).split(","):
            s = raw_s.strip()
            if not s:
                continue
            statuses.extend(canonical_map.get(s.lower(), [s]))
        if statuses:
            return query.filter(Project.status.in_(statuses))

    has_inclusion_flag = any(
        k in args for k in ("include_planned", "include_in_progress", "include_canceled", "only_completed")
    )
    if has_inclusion_flag:
        allowed = ["Completed"]

        def _is_true(val):
            return str(val).lower() in ("1", "true", "yes", "on")

        if _is_true(args.get("include_planned")):
            allowed.append("Planned")
        if _is_true(args.get("include_in_progress")):
            allowed.append("In Progress")
        if _is_true(args.get("include_canceled")):
            allowed.extend(["Canceled", "Cancelled"])

        return query.filter(Project.status.in_(allowed))

    return query


def filter_projects(query, args):
    """
    Unified server-side filter across title/campaign/description ('q'),
    community slug, campaign, tags (AND), target_wiki, project_type, status, and dates.
    """
    from app.models import Community

    q = (args.get("q") or "").strip()
    if q:
        pattern = f"%{_escape_like(q)}%"
        query = query.filter(
            db.or_(
                Project.title.ilike(pattern, escape="\\"),
                Project.campaign.ilike(pattern, escape="\\"),
                Project.description.ilike(pattern, escape="\\"),
            )
        )

    community_slug = (args.get("community") or "").strip()
    if community_slug:
        query = query.join(Project.community).filter(Community.slug == community_slug)

    campaign = (args.get("campaign") or "").strip()
    if campaign:
        c_pattern = f"%{_escape_like(campaign)}%"
        query = query.filter(Project.campaign.ilike(c_pattern, escape="\\"))

    raw_tag_values = []
    if hasattr(args, "getlist"):
        raw_tag_values.extend(args.getlist("tag"))
        raw_tag_values.extend(args.getlist("tags"))
    else:
        if args.get("tag"):
            raw_tag_values.append(args.get("tag"))
        if args.get("tags"):
            raw_tag_values.append(args.get("tags"))

    parsed_tags = []
    seen_tags = set()
    for val in raw_tag_values:
        for piece in str(val).split(","):
            norm = normalize_tag(piece)
            if norm and norm not in seen_tags:
                seen_tags.add(norm)
                parsed_tags.append(norm)
    for t in parsed_tags:
        query = query.filter(Project.tags_rel.any(ProjectTag.tag == t))

    target_wiki = (args.get("target_wiki") or "").strip()
    if target_wiki:
        try:
            norm_code, norm_url = normalize_wiki_target(target_wiki)
            norm_domain = urlparse(norm_url).netloc
            candidates = list({target_wiki, norm_code, norm_domain})
            query = query.filter(Project.target_wiki.in_(candidates))
        except ValueError:
            query = query.filter(Project.target_wiki == target_wiki)

    raw_type = (args.get("type") or args.get("project_type") or "").strip()
    if raw_type:
        if raw_type == "Other":
            query = query.filter(
                db.or_(
                    Project.project_type == "Other",
                    ~Project.project_type.in_(STANDARD_ACTIVITY_TYPES),
                )
            )
        else:
            query = query.filter(Project.project_type == raw_type)

    query = filter_projects_by_status(query, args)
    query, _, _ = filter_projects_by_date(query, args)
    return query


def sanitize_csv_cell(value: Any) -> Any:
    """
    Sanitize a single CSV cell value to neutralize spreadsheet formula injection.
    """
    if not isinstance(value, str):
        return value
    stripped = value.lstrip()
    if stripped and stripped[0] in ("=", "+", "-", "@", "|", "\t", "\r"):
        return "'" + value
    return value


def normalize_username(username: str) -> str:
    """Decode URL entities, replace underscores with spaces, and strip whitespace."""
    if not username:
        return ""
    decoded = unquote(str(username))
    return decoded.replace("_", " ").strip()
