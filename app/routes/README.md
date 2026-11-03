# HTTP Routing & API (`app/routes`)

## Overview
Defines Flask web routes, RESTful JSON API endpoints, and CSV export services for the Athar platform. Coordinates user actions, project lifecycle management, community onboarding, and client-side data queries.

## Interface
- `[api.py:api_bp]` Blueprint providing JSON API and data export endpoints under `/api`
- `[api.py:check_user]` Endpoint (`/api/check_user/<username>`) validating user existence via local database or Meta-Wiki CentralAuth
- `[api.py:create_projetct]` Endpoint (`/api/<community_slug>/projects`) creating a project within a community
- `[api.py:export_project_csv]` Endpoint (`/api/projects/<int:project_id>/export`) streaming participant and organizer roster CSV
- `[api.py:export_user_projects_csv]` Endpoint (`/api/users/<string:username>/export`) streaming contributor project history CSV
- `[api.py:exp_community_projects]` Endpoint (`/api/<community_slug>/export`) streaming filtered community project data as CSV
- `[api.py:export_csv]` Endpoint (`/api/export_csv`) exporting project records for a specified or first available community
- `[api.py:get_communities]` Endpoint (`/api/communities`) returning JSON list of all registered communities
- `[api.py:get_project]` Endpoint (`/api/<community_slug>/projects/<int:project_id>`) returning project details
- `[api.py:get_request_data]` Utility parsing JSON payloads or multipart/form data from request
- `[api.py:get_stats]` Endpoint (`/api/stats`) returning aggregate KPI counts across all communities
- `[api.py:list_members]` Endpoint (`/api/<community_slug>/members`) returning member roster and edit statistics
- `[api.py:list_projects]` Endpoint (`/api/projects`) listing all projects across the platform
- `[api.py:list_slug_project]` Endpoint (`/api/<community_slug>/projects`) returning filtered projects for a community
- `[api.py:slug_Stat]` Endpoint (`/api/<community_slug>/stats`) returning aggregate metrics for a single community
- `[api.py:update_project]` Endpoint (`/api/<community_slug>/projects/<int:project_id>`) updating an existing project
- `[web.py:web_bp]` Blueprint providing server-rendered HTML views and forms
- `[web.py:index]` View (`/`) rendering landing page or redirecting to active community dashboard
- `[web.py:dashboard]` View (`/<slug>/`) rendering affiliate community dashboard
- `[web.py:community_activities]` View (`/<slug>/activities`) rendering activity listing and filter panel
- `[web.py:community_users]` View (`/<slug>/users`) rendering member roster table
- `[web.py:add_community]` Form handler (`/add-community`) registering a new affiliate and initiating background sync
- `[web.py:create_project]` Form handler (`/project/new`) for creating affiliate projects
- `[web.py:edit_project]` Form handler (`/project/<int:project_id>/edit`) for updating projects
- `[web.py:view_project]` View (`/project/<int:project_id>`) rendering detailed project page
- `[web.py:user_profile]` View (`/user/<string:username>`) rendering contributor profile with CentralAuth metrics and project history
- `[web.py:project_report]` Printable view (`/project/<int:project_id>/report`) rendering single-project dossier
- `[web.py:community_report]` Printable view (`/<slug>/report`) rendering affiliate executive annual/monthly report
- `[web.py:user_report]` Printable view (`/user/<string:username>/report`) rendering contributor portfolio
- `[web.py:export_view]` View (`/export`) rendering CSV and printable report export configuration UI
- `[web.py:manual_sync]` Action route (`/<slug>/sync`) triggering on-demand Meta-Wiki member sync
- `[web.py:slugify]` Utility converting arbitrary title strings into URL-safe slugs
- `[web.py:RESERVED_SLUGS]`, `[web.py:is_reserved_slug]` Reserved slug set protecting core application namespaces

## Invariants
- `[api.py:get_request_data]` Returns JSON dictionary if request `is_json` is True, otherwise returns form dictionary.
- `[api.py:export_csv]` Returns HTTP 400 error if community is not specified and no communities exist in database.
- `[api.py:slug_Stat]`, `[api.py:list_members]`, `[api.py:list_slug_project]` Return HTTP 404 error if community slug is not found.
- `[api.py:create_projetct]` Requires authenticated membership via `@member_required`; returns HTTP 404 if community slug is missing; returns HTTP 400 if title is empty or `target_wiki` fails normalization; sanitizes description HTML with `bleach`; parses `participants` and `results` JSON; sets `jury_members` to empty list if `is_contest` is False.
- `[api.py:get_project]` Returns HTTP 404 error if project id is not found or does not belong to specified community slug.
- `[api.py:update_project]` Requires authorization via `@project_editor_required`; returns HTTP 404 if project id or slug is invalid; returns HTTP 400 if title empty or `target_wiki` invalid; sanitizes HTML with `bleach`; updates `participants` and `results`.
- `[api.py:export_project_csv]`, `[api.py:export_user_projects_csv]`, `[api.py:exp_community_projects]` Stream CSV data with UTF-8 BOM, sanitized cells against formula injection via `sanitize_csv_cell`, and return HTTP 400 for non-csv format.
- `[api.py:check_user]` Returns HTTP 400 if `username` query parameter is missing or empty.
- `[web.py:slugify]` Converts string to lowercase, strips punctuation, and replaces whitespace/underscores with hyphens.
- `[web.py:add_community]` Requires authenticated session username; rejects reserved slugs; appends numeric counters to ensure slug uniqueness.
- `[web.py:dashboard]`, `[web.py:community_activities]`, `[web.py:community_users]`, `[web.py:manual_sync]`, `[web.py:community_report]` Return HTTP 404 if slug belongs to `RESERVED_SLUGS` or community is not found.
- `[web.py:user_profile]`, `[web.py:user_report]` Uphold Zero-External-Network Invariant: return HTTP 404 if username has no local record in User or Project without issuing outbound network requests.
- `[web.py:create_project]`, `[web.py:edit_project]` Parse `participants` line-by-line / commas and deserialize `results` subfields with Bleach sanitization.
- `[web.py:view_project]` Returns HTTP 404 if project id not found; sets `can_edit` to True only if current user is lead organizer, in co-organizers, or MOCK_AUTH is enabled.

## Side Effects
- `[api.py:create_projetct]` Inserts new `Project` record into database via `db.session.add()` and `db.session.commit()`.
- `[api.py:update_project]` Modifies `Project` attributes and commits changes to database via `db.session.commit()`.
- `[api.py:exp_community_projects]` Streams CSV data with UTF-8 BOM byte marker and `Content-Disposition` attachment headers.
- `[api.py:check_user]` Dispatches outbound HTTP GET request to Wikimedia CentralAuth API (`meta.wikimedia.org`) if user is not cached locally.
- `[web.py:add_community]` Creates and commits new `Community` record; spawns daemon background thread executing `_async_sync_community` to synchronize members; flashes UI status notifications.
- `[web.py:dashboard]`, `[web.py:community_activities]`, `[web.py:community_users]` Mutate session state by recording active community slug in `session['community_slug']`.
- `[web.py:manual_sync]` Runs synchronous `sync_community` updating database and sets flash messages.
- `[web.py:create_project]`, `[web.py:edit_project]` Persist `Project` entities to database via `db.session.commit()` and flash status notifications.

## Verification
- Run: `pytest`

