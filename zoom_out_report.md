# Goldfish Review Report — Stage 5: Initial Zoom Out Review

**Target:** `docs/designs/platform_redesign_i18n_and_admin_governance.md` (`1-635`)
**Standard:** `/home/bonnjalal/.gemini/config/plugins/egm/resources/document_standards/zoom-out-standard.md`

## Reviewer Status

| Reviewer | Status |
| :--- | :--- |
| `egm-zoom-out` | completed |

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. Conflicting Dual Soft-Delete Boundary (`active_projects_query()` vs. Optional `do_orm_execute`) - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 230-232`, `Lines 457-514`
* **Discrepancy Description:** Line 231 proposes adding `active_projects_query()` in `app/query_utils.py` *"—and optionally register a SQLAlchemy `do_orm_execute` filter over `Project` bypassed solely via `execution_options(include_deleted=True)` in `/admin`"*, while Item 8 (`GET /admin`, line 474) explicitly relies on `execution_options(include_deleted=True)` and Items 6, 9, 10, and 12 simultaneously tell every route to call `active_projects_query()`. Having both an explicit query helper at ~19 callsites and an "optional" global ORM interceptor creates an ambiguous dual mechanism. Additionally, `app/oauth.py` (`@project_editor_required`) queries `Project.query.get_or_404(project_id)` directly and is omitted from the explicit `active_projects_query()` callsite list; if `do_orm_execute` were skipped as optional, soft-deleted projects would remain editable.
* **Rationale & Recommendation:** Pick one mechanism—either explicit `active_projects_query()` everywhere (including `@project_editor_required`) with no ORM event hook, or a mandatory `do_orm_execute` filter everywhere except `/admin`.

### 2. Dual SSR + CSR Rendering Pipeline on `/activities` (`filters.js` vs. Server-Side `filter_projects()`) - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 247-257`, `Lines 535-584`
* **Discrepancy Description:** `GET /activities` and `GET /<slug>/activities` already filter on the server via `app/query_utils.py:filter_projects()` and render project cards via Jinja in `app/templates/activities.html`, and `/` submits standard `GET /activities?...` query parameters. Yet the design preserves a second, parallel client-side rendering pipeline in `app/static/js/filters.js` that re-queries `/api/projects` or `/api/<slug>/projects`, rebuilds all DOM cards in JavaScript, duplicates localized dictionaries via `window.ATHAR_I18N`, manually synchronizes `history.replaceState`, and checks `project.can_edit` for a modal edit button. Keeping both server-rendered and client-rendered card/modal paths for the same page guarantees template/JS drift.
* **Rationale & Recommendation:** Use standard `GET` form submission onto the server-rendered `/activities` and `/<slug>/activities` controllers (linking cards directly to `/project/<id>` as `activities.html` already does), eliminating the duplicated JS card builder, `innerHTML` surface, and `can_edit` API coupling.

### 3. Bespoke `{{PLURAL:$1|...}}` Parser, Split `ui`/`reports` Bundles, and Unresolved JS Pluralization - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 261-272`, `Lines 462-600`
* **Discrepancy Description:**
  * Splitting Translatewiki JSON files into `i18n/ui/*.json` and `i18n/reports/*.json` duplicates shared terms (activity types, statuses, roles, `"General"`, date labels) across two message domains for a small Flask app.
  * The design hand-rolls a custom `banana-i18n` `{{PLURAL:$1|...}}` + Arabic 6-form CLDR parser in Python (`app/i18n.py`) and injects `window.ATHAR_I18N` JSON into templates for JS scripts. However, dynamic count messages formatted directly in JS (`index.html`, `users.html`, `export.js`) receive raw `{{PLURAL:$1|...}}` strings with no JS runtime specified to evaluate them.
  * Line 269 leaves `session['lang']` default undecided (*"default `'ar'` initially or `'en'` per config"*), whereas line 413 sets `Config.DEFAULT_LOCALE = "ar"` (and `tests/test_routes.py` asserts Arabic defaults).
* **Rationale & Recommendation:** Consolidate onto a single `i18n/{en,ar,qqq}.json` bundle per locale, reuse `@wikimedia/banana-i18n` or specify a single JS pluralization helper, and lock `DEFAULT_LOCALE = "ar"`.

### 4. Contradictory Dual Source of Truth for `User.is_admin` vs. `Config.ADMIN_USERS` - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 210-228`, `Lines 439-477`
* **Discrepancy Description:** Line 213 instructs `oauth_callback()` to promote `ADMIN_USERS` *"without re-promoting admins explicitly demoted via DB flags unless configured as locked bootstrap admins"*, while line 441 instructs `@admin_required` to evaluate `is_admin` *"against fresh DB state (plus `Config.ADMIN_USERS`)"*. `User` has only one boolean `is_admin` column—no schema flag distinguishes "never promoted" from "explicitly demoted" or "locked bootstrap admins"—and honoring `Config.ADMIN_USERS` at runtime makes `POST /admin/admins/revoke` unable to revoke any env-listed admin (including `Bonnjalal00`).
* **Rationale & Recommendation:** Use `Config.ADMIN_USERS` strictly as an initial seed during migration/first bootstrap, and treat `User.is_admin` in the database as the sole runtime source of truth.

### 5. YAGNI Speculative Endpoints & Unconsumed API Contracts (`?paginated=1`, `/healthz`) - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 237-256`, `Lines 490-498`
* **Discrepancy Description:**
  * Unused `?paginated=1&page=1&per_page=24` on `/api/projects` (lines 256, 498): Neither `GET /activities`, `activities.html`, `filters.js`, nor `export.js` implements pagination UI or consumes a paginated wrapper.
  * Speculative `GET /healthz` (lines 237, 490): `Procfile` and `jobs.yaml` configure no `/healthz` health check, and validating `i18n` JSON files and DB schema columns on an unauthenticated HTTP route duplicates startup/CI verification while exposing internal schema status.
* **Rationale & Recommendation:** Remove `?paginated=1` until a caller needs pagination, and move schema/`i18n` verification to startup/CI checks instead of an unauthenticated `/healthz` endpoint.

### 6. Layering Leaks (`Project.to_dict(current_user=...)`), Fragmented Governance Placement, and Bypassable Cookie Rate Limiting - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 222-286`, `Lines 432-499`
* **Discrepancy Description:**
  * Adding `current_user=None, lang=None` to `Project.to_dict()` (line 432) leaks HTTP/authorization policy into `app/models.py`, and accessing `community` and `tags` inside `to_dict()` triggers 2N lazy queries on `/api/projects` and `/api/<slug>/projects`.
  * Placing `/admin/...` in `admin_bp` (`app/routes/admin.py`) while leaving Admin-only `POST /add-community` in `app/routes/web.py` splits community admin actions across two blueprints, while `POST /project/translate` is added to the 871-line `web.py` and `web.py` duplicates `determine_project_status()` inline instead of sharing one helper with `api.py`.
  * Flask's default `session` is a client-side signed cookie, so a "per-session rate limit" on `POST /project/translate` can be bypassed by replaying a pre-request cookie across 4 Gunicorn workers, and lines 284–286 do not clarify whether translating 4 fields runs in 1 batched call or 4 sequential `timeout=10` requests.
* **Rationale & Recommendation:** Move `can_edit` computation to a policy helper in `app/oauth.py`, mandate eager loading on list queries, consolidate admin routes under `admin_bp` and shared project-input parsing across `web.py`/`api.py`, and specify batched MinT translation with server-side rate-limit state.

### 7. Missed Existing Reuse (`is_allowed_wikimedia_host()`, `dashboard.html` Chart.js, and `/api/check-user`) - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 447-561`
* **Discrepancy Description:**
  * `app/wiki_utils.py` already provides `is_allowed_wikimedia_host(hostname)`; parameterizing its `allowed_domains` tuple avoids reimplementing domain-suffix checks inside `validate_activity_wiki_url()`.
  * `app/templates/dashboard.html` already loads Chart.js; only the duplicate tag in `app/templates/base.html` needs removal.
  * `app/routes/api.py` (`check_user()`) already checks local `User` and Meta-Wiki CentralAuth; extracting that lookup into a shared utility using `Config.USER_AGENT` lets `/admin/admins/grant` reuse it without calling a route handler.
* **Rationale & Recommendation:** Reuse and parameterize existing helpers rather than creating parallel wrappers.

### 8. Altitude Drops (Weeds) & Cross-Section Repetition - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 44-65`, `Lines 170-293`, `Lines 370-383`, `Lines 408-615`
* **Discrepancy Description:** High-altitude sections (`Goals`, `Technical Plan`, `NFRs`) drop into code-level specifics—exact DDL strings (`BOOLEAN NOT NULL DEFAULT 0`, `VARCHAR(1024)`), exact regexes (`^[a-z]{2,12}(-[a-z0-9]{2,12})*$`), exact `bleach.clean(...)` argument lists, exact `localStorage.getItem("athar-theme")` calls, and existing template line numbers—and repeat the same details 3–4 times across `Goals`, `Technical Plan`, `NFRs`, and `Detailed Implementation Plan`.
* **Rationale & Recommendation:** Keep `Goals` and `NFRs` at the behavior/contract level and state implementation specifics once in the Technical or Detailed Implementation sections.
