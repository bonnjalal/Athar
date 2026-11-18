from functools import wraps
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, abort, current_app, jsonify, redirect, request, session, url_for
from sqlalchemy import func

from app.models import User, db

oauth = OAuth()
oauth_bp = Blueprint("oauth", __name__)


def init_oauth(app):
    """Initialize Authlib with Wikimedia OAuth 2.0 parameters."""
    oauth.init_app(app)
    oauth.register(
        name="wikimedia",
        client_id=app.config.get("OAUTH_CLIENT_ID"),
        client_secret=app.config.get("OAUTH_CLIENT_SECRET"),
        access_token_url="https://meta.wikimedia.org/w/rest.php/oauth2/access_token",
        authorize_url="https://meta.wikimedia.org/w/rest.php/oauth2/authorize",
        api_base_url="https://meta.wikimedia.org/w/rest.php/",
    )


def _norm_user_key(username: str) -> str:
    from app.query_utils import normalize_username
    return normalize_username(username)


def _seeded_admin_keys() -> set[str]:
    admins = set(current_app.config.get("ADMIN_USERS", {"Bonnjalal00"}))
    keys = {_norm_user_key(u).lower() for u in admins if _norm_user_key(u)}
    keys.add("bonnjalal00")
    return keys


def _is_ajax_request() -> bool:
    return bool(
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.path == "/project/translate"
    )


def _ensure_mock_user() -> User:
    mock_name = _norm_user_key(current_app.config.get("MOCK_USERNAME", "MoroccoVolunteer")) or "MoroccoVolunteer"
    mock_is_admin = bool(current_app.config.get("MOCK_IS_ADMIN", False))

    user = User.query.filter(func.lower(User.username) == mock_name.lower()).first()
    if not user:
        user = User(
            username=mock_name,
            is_member=True,
            is_admin=mock_is_admin,
        )
        db.session.add(user)
        db.session.commit()
    session["username"] = user.username
    session["is_member"] = bool(user.is_member)
    session["is_admin"] = bool(user.is_admin)
    return user


def get_current_user():
    """Retrieve the currently authenticated User DB record from session or MOCK_AUTH."""
    if session.get("logged_out"):
        return None

    if current_app.config.get("MOCK_AUTH", False):
        return _ensure_mock_user()

    raw_username = session.get("username")
    clean_username = _norm_user_key(raw_username)
    if not clean_username:
        return None

    user = User.query.filter(func.lower(User.username) == clean_username.lower()).first()
    if user:
        session["is_member"] = bool(user.is_member)
        session["is_admin"] = bool(user.is_admin)
    return user


def can_user_edit_project(user, project) -> bool:
    """Return True if user is a Tool Admin or the lead/co-organizer of the project."""
    if not user or not project:
        return False
    if getattr(user, "is_admin", False):
        return True

    norm_user = _norm_user_key(getattr(user, "username", "")).lower()
    if not norm_user:
        return False

    if _norm_user_key(project.lead_organizer).lower() == norm_user:
        return True
    return any(_norm_user_key(co).lower() == norm_user for co in (project.co_organizers or []))


# --- OAuth Blueprint Routes ---


def _get_redirect_target():
    slug = session.get("community_slug")
    if slug:
        return url_for("web.dashboard", slug=slug)
    return url_for("web.index")


@oauth_bp.route("/login")
def login():
    if current_app.config.get("MOCK_AUTH", False):
        session.pop("logged_out", None)
        _ensure_mock_user()
        return redirect(_get_redirect_target())

    redirect_uri = url_for("oauth.oauth_callback", _external=True)
    return oauth.wikimedia.authorize_redirect(redirect_uri)


@oauth_bp.route("/oauth/callback")
def oauth_callback():
    try:
        token = oauth.wikimedia.authorize_access_token()
        resp = oauth.wikimedia.get("oauth2/resource/profile", token=token)
        profile_data = resp.json()

        raw_username = profile_data.get("username") or profile_data.get("sub")
        canonical = _norm_user_key(raw_username)
        if canonical:
            session.pop("logged_out", None)
            norm_lower = canonical.lower()
            seeded_admins = _seeded_admin_keys()

            user = User.query.filter(func.lower(User.username) == norm_lower).first()
            if not user:
                user = User(
                    username=canonical,
                    is_member=False,
                    is_admin=(norm_lower in seeded_admins),
                )
                db.session.add(user)
                db.session.commit()
            else:
                # Only bootstrap a seeded admin if zero admins exist anywhere in DB
                if norm_lower in seeded_admins and not user.is_admin:
                    if User.query.filter(User.is_admin.is_(True)).count() == 0:
                        user.is_admin = True
                        db.session.commit()

            session["username"] = user.username
            session["is_member"] = bool(user.is_member)
            session["is_admin"] = bool(user.is_admin)

    except Exception as e:
        current_app.logger.error(f"OAuth callback error: {e}")
        abort(400, description="Authentication failed.")

    return redirect(_get_redirect_target())


@oauth_bp.route("/logout")
def logout():
    session.clear()
    session["logged_out"] = True
    return redirect(url_for("web.index"))


# --- Security Decorators ---


def member_required(f):
    """Require an authenticated active community member (or Tool Admin)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if _is_ajax_request():
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("oauth.login"))

        if not (user.is_member or user.is_admin):
            if _is_ajax_request():
                return jsonify({"error": "Access restricted: Active Meta-Wiki group membership required."}), 403
            abort(403, description="Access restricted: Active Meta-Wiki group membership required.")

        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Require an authenticated Tool Admin (live User.is_admin check)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if _is_ajax_request():
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("oauth.login"))

        if not user.is_admin:
            if _is_ajax_request():
                return jsonify({"error": "Access restricted: Tool Administrator privileges required."}), 403
            abort(403, description="Access restricted: Tool Administrator privileges required.")

        return f(*args, **kwargs)
    return decorated_function


def project_editor_required(f):
    """Require lead organizer, co-organizer, or Tool Admin on an active (non-deleted) project."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.query_utils import get_active_project_or_404

        user = get_current_user()
        if not user:
            if _is_ajax_request():
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("oauth.login"))

        view_args = request.view_args or {}
        project_id = kwargs.get("project_id") or kwargs.get("id") or view_args.get("project_id") or view_args.get("id")
        project = get_active_project_or_404(project_id)

        if not can_user_edit_project(user, project):
            if _is_ajax_request():
                return jsonify({"error": "Access restricted: Insufficient permissions to edit this activity."}), 403
            abort(403, description="Access restricted: Only the lead organizer, co-organizers, or a Tool Admin can edit this project.")

        return f(*args, **kwargs)
    return decorated_function
