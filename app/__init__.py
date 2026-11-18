import json
from flask import Flask
from flask_wtf.csrf import CSRFProtect

from config import Config
from app.models import db
from app.oauth import get_current_user, init_oauth

csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Guard against accidental MOCK_AUTH in non-debug or live-OAuth environments
    if app.config.get("MOCK_AUTH") and not app.config.get("TESTING"):
        debug_active = bool(app.config.get("DEBUG") or app.debug)
        oauth_id = (app.config.get("OAUTH_CLIENT_ID") or "").strip()
        real_oauth = bool(oauth_id and oauth_id != "your-meta-client-id-here")
        if not debug_active or real_oauth:
            raise RuntimeError(
                "MOCK_AUTH cannot be enabled when DEBUG=False or real OAuth credentials are configured."
            )

    # Set default SQLite URI if not provided in config
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///dev.db"

    # Merge UTF-8 JSON serializer cleanly into engine options
    engine_options = dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS") or {})
    engine_options.setdefault("json_serializer", lambda obj: json.dumps(obj, ensure_ascii=False))
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    init_oauth(app)

    # Create local database tables automatically for development / tests
    with app.app_context():
        db.create_all()

    # Register Jinja template helpers and i18n localization filters/globals
    from app.i18n import (
        _,
        _r,
        current_locale,
        get_client_catalog,
        get_supported_locales,
        locale_dir,
        locale_label,
    )
    from app.wiki_utils import (
        build_xtools_user_url,
        translate_activity_type,
        translate_status,
    )

    app.jinja_env.globals["build_xtools_user_url"] = build_xtools_user_url
    app.jinja_env.globals["_"] = _
    app.jinja_env.globals["_r"] = _r
    app.jinja_env.globals["current_locale"] = current_locale
    app.jinja_env.globals["locale_dir"] = locale_dir
    app.jinja_env.globals["locale_label"] = locale_label
    app.jinja_env.globals["get_client_catalog"] = get_client_catalog

    @app.template_filter("ar_type")
    def arabic_type_filter(val, lang=None):
        return translate_activity_type(val, lang=lang)

    @app.template_filter("ar_status")
    def arabic_status_filter(val, lang=None):
        return translate_status(val, lang=lang)

    app.jinja_env.filters["t_type"] = arabic_type_filter
    app.jinja_env.filters["t_status"] = arabic_status_filter

    @app.context_processor
    def inject_global_template_context():
        return {
            "current_user": get_current_user(),
            "current_locale": current_locale,
            "locale_dir": locale_dir,
            "supported_locales": get_supported_locales(),
            "deletion_request_url": (app.config.get("DELETION_REQUEST_URL") or "").strip(),
        }

    # Register Blueprints
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp
    from app.routes.web import web_bp
    from app.oauth import oauth_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(oauth_bp)
    csrf.exempt(api_bp)

    return app
