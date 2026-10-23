import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    
    # Session Cookie Security Flags
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_DEBUG', 'False').lower() != 'true'
    
    # ToolsDB / Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///dev.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Wikimedia User-Agent Policy
    USER_AGENT = os.environ.get('USER_AGENT', 'Athar/1.0 (https://athar.toolforge.org; bonnjalal@gmail.com)')
    
    # Your Task 2 Additions
    MOCK_AUTH = os.environ.get('MOCK_AUTH', 'False').lower() == 'true'
    OAUTH_CLIENT_ID = os.environ.get('OAUTH_CLIENT_ID')
    OAUTH_CLIENT_SECRET = os.environ.get('OAUTH_CLIENT_SECRET')