from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from app.oauth import init_oauth
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
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

    # Import models and create local database tables inside app context
    with app.app_context():
        from app.models import Project, User, StatSnapshot  # Import models here safely
        db.create_all()

    # Register Blueprints
    from app.routes.web import web_bp
    from app.routes.api import api_bp
    from app.oauth import oauth_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(oauth_bp)

    return app