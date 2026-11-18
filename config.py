import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


def resolve_database_uri(env=None):
    """Resolve database URI from DATABASE_URL, Toolforge ToolsDB envvars, or local SQLite."""
    environ = env if env is not None else os.environ
    database_url = environ.get('DATABASE_URL')
    if database_url:
        return database_url

    toolsdb_user = environ.get('TOOL_TOOLSDB_USER')
    toolsdb_password = environ.get('TOOL_TOOLSDB_PASSWORD')
    if toolsdb_user and toolsdb_password:
        toolsdb_host = environ.get('TOOLSDB_HOST', 'tools.db.svc.wikimedia.cloud')
        toolsdb_name = environ.get('TOOLSDB_NAME', f'{toolsdb_user}__athar')
        return (
            f"mysql+pymysql://{quote_plus(toolsdb_user)}:{quote_plus(toolsdb_password)}"
            f"@{toolsdb_host}/{toolsdb_name}?charset=utf8mb4"
        )

    return 'sqlite:///dev.db'


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    DEBUG = (os.environ.get('DEBUG') or os.environ.get('FLASK_DEBUG') or 'False').lower() == 'true'
    TESTING = (os.environ.get('TESTING') or 'False').lower() in ('1', 'true', 'yes')

    # Session Cookie Security Flags
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = not DEBUG

    # ToolsDB / Database Configuration
    SQLALCHEMY_DATABASE_URI = resolve_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"pool_pre_ping": True, "pool_recycle": 280}
        if SQLALCHEMY_DATABASE_URI.startswith("mysql")
        else {}
    )

    # Wikimedia User-Agent Policy
    USER_AGENT = os.environ.get('USER_AGENT', 'Athar/1.0 (https://athar.toolforge.org; bonnjalal@gmail.com)')

    # OAuth & Local Mock Authentication
    MOCK_AUTH = os.environ.get('MOCK_AUTH', 'False').lower() == 'true'
    MOCK_USERNAME = os.environ.get('MOCK_USERNAME', 'MoroccoVolunteer').strip() or 'MoroccoVolunteer'
    MOCK_IS_ADMIN = os.environ.get('MOCK_IS_ADMIN', 'False').lower() == 'true'
    OAUTH_CLIENT_ID = os.environ.get('OAUTH_CLIENT_ID')
    OAUTH_CLIENT_SECRET = os.environ.get('OAUTH_CLIENT_SECRET')

    # Governance & External Meta-Wiki Requests
    ADMIN_USERS = {
        u.replace('_', ' ').strip()
        for u in os.environ.get('ADMIN_USERS', 'Bonnjalal00').split(',')
        if u.strip()
    }
    DELETION_REQUEST_URL = os.environ.get('DELETION_REQUEST_URL', '').strip()

    # Localization & Wikimedia MinT Machine Translation
    DEFAULT_LOCALE = 'ar'
    MINT_API_URL = os.environ.get('MINT_API_URL', 'https://translate.wmcloud.org/api').rstrip('/')
    MINT_TIMEOUT_SECONDS = int(os.environ.get('MINT_TIMEOUT_SECONDS', '10'))