"""
app/query_utils.py

Shared query filtering, string normalization, and CSV sanitization utilities.
"""
import calendar
from datetime import datetime, date
from typing import Any
from urllib.parse import unquote
from app import db
from app.models import Project


def filter_projects_by_date(query, args):
    """
    Filter Project query by year, month, or custom date range.
    Supports filter_type='year'|'month'|'custom', or explicit 'year', 'month',
    'start_date' / 'from_date', and 'end_date' / 'to_date'.
    Returns (filtered_query, start_date, end_date).
    """
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


def filter_projects_by_status(query, args):
    """
    Filter project query by status.
    Supports explicit 'status' query param, or status inclusion flags:
    'include_planned', 'include_in_progress', 'include_canceled'.
    When inclusion flags are present:
    'Completed' is included by default, and additional statuses are included
    if their corresponding inclusion flag is set to true/1.
    """
    explicit_status = args.get("status")
    if explicit_status:
        statuses = [s.strip() for s in explicit_status.split(",") if s.strip()]
        if statuses:
            return query.filter(Project.status.in_(statuses))

    has_inclusion_flag = any(k in args for k in ("include_planned", "include_in_progress", "include_canceled", "only_completed"))
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


def sanitize_csv_cell(value: Any) -> Any:
    """
    Sanitizes a single CSV cell value to neutralize spreadsheet formula injection.
    Strips leading whitespace before testing trigger characters: '=', '+', '-', '@', '|', '\t', '\r'.
    If triggered, prepends a single quote (').
    """
    if not isinstance(value, str):
        return value
    stripped = value.lstrip()
    if stripped and stripped[0] in ("=", "+", "-", "@", "|", "\t", "\r"):
        return "'" + value
    return value


def normalize_username(username: str) -> str:
    """
    Normalizes a MediaWiki username by decoding URL entities, replacing underscores
    with spaces, and stripping leading/trailing whitespace.
    Example:
        normalize_username("User%20Name_123%20") -> "User Name 123"
    """
    if not username:
        return ""
    decoded = unquote(str(username))
    return decoded.replace("_", " ").strip()

