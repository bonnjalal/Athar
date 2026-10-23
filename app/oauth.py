from flask import Blueprint, session, redirect, url_for, current_app, abort, request
from functools import wraps
from authlib.integrations.flask_client import OAuth
from app.models import User, Project

oauth = OAuth()
oauth_bp = Blueprint('oauth', __name__)

def init_oauth(app):
    """Initialize Authlib with Wikimedia OAuth 2.0 parameters."""
    oauth.init_app(app)
    oauth.register(
        name='wikimedia',
        client_id=app.config.get('OAUTH_CLIENT_ID'),
        client_secret=app.config.get('OAUTH_CLIENT_SECRET'),
        access_token_url='https://meta.wikimedia.org/w/rest.php/oauth2/access_token',
        authorize_url='https://meta.wikimedia.org/w/rest.php/oauth2/authorize',
        api_base_url='https://meta.wikimedia.org/w/rest.php/'
    )

def get_current_user():
    """Retrieve the currently authenticated user from session or MOCK_AUTH."""
    if session.get('logged_out'):
        return None

    if current_app.config.get('MOCK_AUTH', False):
        return {
            'username': 'MoroccoVolunteer',
            'is_member': True
        }
    
    username = session.get('username')
    if not username:
        return None
    return User.query.filter_by(username=username).first()

# --- OAuth Blueprint Routes ---

@oauth_bp.route('/login')
def login():
    if current_app.config.get('MOCK_AUTH', False):
        session.pop('logged_out', None)
        session['username'] = 'MoroccoVolunteer'
        session['is_member'] = True
        return redirect(url_for('web.dashboard'))
    
    redirect_uri = url_for('oauth.oauth_callback', _external=True)
    return oauth.wikimedia.authorize_redirect(redirect_uri)

@oauth_bp.route('/oauth/callback')
def oauth_callback():
    try:
        token = oauth.wikimedia.authorize_access_token()
        resp = oauth.wikimedia.get('oauth2/resource/profile', token=token)
        profile_data = resp.json()
        
        username = profile_data.get('username') or profile_data.get('sub')
        if username:
            session.pop('logged_out', None)
            session['username'] = username
            user = User.query.filter_by(username=username).first()
            session['is_member'] = user.is_member if user else False
            
    except Exception as e:
        current_app.logger.error(f"OAuth callback error: {e}")
        abort(400, description="Authentication failed.")
        
    return redirect(url_for('web.dashboard'))

@oauth_bp.route('/logout')
def logout():
    session.clear()
    session['logged_out'] = True
    return redirect(url_for('web.dashboard'))


# --- Security Decorators ---

def member_required(f):
    """Decorator to check if user is logged in and is an active Meta-Wiki group member."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_app.config.get('MOCK_AUTH', False):
            return f(*args, **kwargs)
            
        username = session.get('username')
        if not username:
            return redirect(url_for('oauth.login'))
            
        if not session.get('is_member'):
            user = User.query.filter_by(username=username).first()
            if not user or not user.is_member:
                abort(403, description="Access restricted: Active Meta-Wiki group membership required.")
            
        return f(*args, **kwargs)
    return decorated_function

def project_editor_required(f):
    """Decorator to check if logged-in user is the lead organizer or a co-organizer."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_app.config.get('MOCK_AUTH', False):
            return f(*args, **kwargs)
            
        username = session.get('username')
        if not username:
            return redirect(url_for('oauth.login'))
            
        project_id = kwargs.get('project_id') or kwargs.get('id') or request.view_args.get('id')
        project = Project.query.get_or_404(project_id)
        if project.lead_organizer != username and username not in (project.co_organizers or []):
            abort(403, description="Access restricted: Only the lead organizer or co-organizers can edit this project.")
            
        return f(*args, **kwargs)
    return decorated_function