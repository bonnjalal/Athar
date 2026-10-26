from flask import Flask
from config import Config
from app.models import db
from app.oauth import init_oauth
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Set default SQLite URI if not provided in config
    if not app.config.get('SQLALCHEMY_DATABASE_URI'):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dev.db'

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    init_oauth(app)

    # Create local database tables automatically for development
    with app.app_context():
        db.create_all()

    # Register Jinja template filters for Arabic localization
    from app.wiki_utils import translate_activity_type, translate_status

    @app.template_filter('ar_type')
    def arabic_type_filter(val):
        return translate_activity_type(val)

    @app.template_filter('ar_status')
    def arabic_status_filter(val):
        return translate_status(val)

    # Register Blueprints
    from app.routes.web import web_bp
    from app.routes.api import api_bp
    from app.oauth import oauth_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(oauth_bp)
    csrf.exempt(api_bp)

    return app