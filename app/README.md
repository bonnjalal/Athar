# Application Core (`app`)

## Overview
Core application package for Athar, containing the Flask application factory, database domain models, Wikimedia OAuth 2.0 authentication integration, and MediaWiki domain utility handlers.

## Interface
- `[__init__.py:create_app]` Application factory function configuring extensions, blueprints, and database tables
- `[__init__.py:csrf]` Flask-WTF CSRF protection extension instance
- `[models.py:db]` SQLAlchemy database instance
- `[models.py:Community]` Domain entity representing a Wikimedia affiliate user group
- `[models.py:Community.to_dict]` Serializes community model instance to a dictionary
- `[models.py:User]` Domain entity representing a community contributor
- `[models.py:User.to_dict]` Serializes user model instance to a dictionary
- `[models.py:CommunityMember]` Association entity tracking user membership in a community
- `[models.py:CommunityMember.to_dict]` Serializes membership record to a dictionary
- `[models.py:StatSnapshot]` Periodic CentralAuth metrics snapshot for a contributor
- `[models.py:Project]` Domain entity representing an affiliate activity, workshop, contest, or event
- `[models.py:Project.target_wiki_url]` Resolves target wiki domain to a fully-qualified HTTPS URL
- `[models.py:Project.project_type_ar]` Returns Arabic translation of activity type
- `[models.py:Project.status_ar]` Returns Arabic translation of project status
- `[models.py:Project.to_dict]` Serializes project entity to a dictionary
- `[oauth.py:oauth]` Authlib OAuth registry instance
- `[oauth.py:oauth_bp]` Blueprint registering OAuth login, callback, and logout endpoints
- `[oauth.py:init_oauth]` Configures Wikimedia OAuth provider on the Flask application
- `[oauth.py:get_current_user]` Retrieves active session user with support for `MOCK_AUTH`
- `[oauth.py:login]` Initiates OAuth redirect flow or simulates mock authentication
- `[oauth.py:oauth_callback]` Exchanges OAuth authorization code for access tokens and user profile
- `[oauth.py:logout]` Clears session state and flags user as logged out
- `[oauth.py:member_required]` Route decorator restricting access to verified community members
- `[oauth.py:project_editor_required]` Route decorator restricting modifications to project organizers
- `[query_utils.py:filter_projects_by_date]` Filters Project queries by year, month, or custom date range
- `[query_utils.py:sanitize_csv_cell]` Prepends apostrophe to formula trigger characters to prevent spreadsheet injection
- `[query_utils.py:normalize_username]` Decodes URL entities, replaces underscores with spaces, and strips whitespace
- `[wiki_utils.py:ALLOWED_WIKIMEDIA_DOMAINS]` Whitelist of recognized Wikimedia host domains
- `[wiki_utils.py:SPECIAL_WIKI_MAP]` Mapping table converting informal wiki aliases to hostnames
- `[wiki_utils.py:DBNAME_REGEX]` Regular expression parsing wiki database names (e.g. `arwiki`)
- `[wiki_utils.py:is_allowed_wikimedia_host]` Validates hostnames against Wikimedia whitelist
- `[wiki_utils.py:normalize_wiki_target]` Normalizes domain names, aliases, and database names
- `[wiki_utils.py:resolve_wiki_url]` Converts target wiki identifier to canonical HTTPS URL
- `[wiki_utils.py:build_xtools_user_url]` Constructs outbound URL to XTools edit counter for a user and wiki
- `[wiki_utils.py:ACTIVITY_TYPE_ARABIC]` Dictionary mapping activity types to Arabic display strings
- `[wiki_utils.py:STATUS_ARABIC]` Dictionary mapping project statuses to Arabic display strings
- `[wiki_utils.py:translate_activity_type]` Formats localized activity type with fallback
- `[wiki_utils.py:translate_status]` Formats localized project status with fallback
- [routes](./routes/README.md): Subdirectory contract for HTTP web routes and REST API endpoints
- [static](./static/README.md): Subdirectory contract for client-side JavaScript, styles, and assets

## Invariants
- `[__init__.py:create_app]` Sets `SQLALCHEMY_DATABASE_URI` default to `'sqlite:///dev.db'` if not provided in configuration.
- `[models.py:Community.name]` Must be unique and non-nullable.
- `[models.py:Community.slug]` Must be unique, non-nullable, and indexed.
- `[models.py:Community.meta_roster_page]` Must be non-nullable.
- `[models.py:Community.created_at]` Non-nullable with default `datetime.utcnow`.
- `[models.py:User.username]` Must be unique, non-nullable, and indexed.
- `[models.py:User.is_member]` Non-nullable boolean with default True.
- `[models.py:CommunityMember.community_id]` Composite primary key referencing `communities.id`.
- `[models.py:CommunityMember.user_id]` Composite primary key referencing `users.id`.
- `[models.py:StatSnapshot.user_id]` Non-nullable foreign key referencing `users.id`.
- `[models.py:StatSnapshot.total_edits]` Non-nullable integer with default 0.
- `[models.py:StatSnapshot]` Enforces composite index `ix_stat_snapshots_user_recorded` on `(user_id, recorded_at DESC)`.
- `[models.py:Project.title]`, `[models.py:Project.description]` Must be non-nullable.
- `[models.py:Project.lead_organizer]` Non-nullable string with index (`index=True`).
- `[models.py:Project.participants]`, `[models.py:Project.results]` Nullable JSON columns.
- `[models.py:Project.project_type]` Non-nullable string with default `'Workshop'`.
- `[models.py:Project.target_wiki]` Non-nullable string with default `'ar.wikipedia.org'`.
- `[models.py:Project.status]` Non-nullable string with default `'In Progress'`.
- `[models.py:Project.is_contest]` Non-nullable boolean with default False.
- `[query_utils.py:sanitize_csv_cell]` Prepends `'` if stripped string starts with `=`, `+`, `-`, `@`, `|`, `\t`, `\r`.
- `[query_utils.py:normalize_username]` Decodes URL encodings and replaces underscores with spaces.
- `[oauth.py:get_current_user]` Returns None if `session['logged_out']` is True; returns mock dict `{'username': 'MoroccoVolunteer', 'is_member': True}` when `MOCK_AUTH` is enabled; returns None if `session['username']` is missing.
- `[oauth.py:member_required]` Bypasses check if `MOCK_AUTH` is True; redirects to `oauth.login` if session lacks username; aborts with HTTP 403 if user is not an active member (`user.is_member` is False).
- `[oauth.py:project_editor_required]` Bypasses check if `MOCK_AUTH` is True; redirects to `oauth.login` if unauthenticated; aborts with HTTP 404 if project does not exist; aborts with HTTP 403 if username does not match `project.lead_organizer` and is not in `project.co_organizers`.
- `[wiki_utils.py:is_allowed_wikimedia_host]` Returns False if hostname is empty or falsy; returns True only if hostname matches or ends with an allowed domain in `ALLOWED_WIKIMEDIA_DOMAINS`.
- `[wiki_utils.py:normalize_wiki_target]` Raises ValueError if input does not match `SPECIAL_WIKI_MAP`, `is_allowed_wikimedia_host`, or `DBNAME_REGEX`.
- `[wiki_utils.py:resolve_wiki_url]` Catches ValueError from `normalize_wiki_target` and falls back to `'https://ar.wikipedia.org'`.
- `[wiki_utils.py:translate_activity_type]` Falls back to `'نشاط مجتمعي'` if input is falsy.
- `[wiki_utils.py:translate_status]` Falls back to `'جارية'` if input is falsy.

## Side Effects
- `[__init__.py:create_app]` Sets default database URI; initializes `db`, `csrf`, and `oauth` extensions; executes `db.create_all()` within application context creating database tables; registers template filters `ar_type` and `ar_status`; registers blueprints `web_bp`, `api_bp` (exempt from CSRF), and `oauth_bp`.
- `[models.py:Community.members]`, `[models.py:Community.projects]` Deletes child records on Community deletion via `cascade='all, delete-orphan'`.
- `[models.py:User.memberships]`, `[models.py:User.snapshots]` Deletes child records on User deletion via `cascade='all, delete-orphan'`.
- `[models.py:Project.updated_at]` Automatically updates timestamp column on row updates via `onupdate=datetime.utcnow`.
- `[oauth.py:init_oauth]` Registers Wikimedia OAuth client provider with Authlib on application.
- `[oauth.py:login]` Modifies session state under mock mode by popping `logged_out` and injecting mock user credentials.
- `[oauth.py:oauth_callback]` Sends external network requests to Wikimedia OAuth token and profile endpoints; modifies session state (`username`, `is_member`).
- `[oauth.py:logout]` Clears session via `session.clear()` and records `session['logged_out'] = True`.

## Verification
- Run: `pytest`

