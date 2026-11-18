# Goldfish Review Report — Stage 8: Intermediate Zoom Out Review

**Target:** `docs/designs/platform_redesign_i18n_and_admin_governance.md` (`1-635`)
**Standard:** `/home/bonnjalal/.gemini/config/plugins/egm/resources/document_standards/zoom-out-standard.md`
**Prior Reports Context:** `zoom_out_report.md`, `comprehension_report.md`, `critic_report.md`

## Reviewer Status

| Reviewer | Status |
| :--- | :--- |
| `egm-zoom-out` | completed |

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. Over-Engineering Risks in Proposed Stage 6 & 7 Mitigations - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 210-228, 247-256, 284-286, 379, 490, 498` (Stage 7 mitigations in `critic_report.md`)
* **Discrepancy Description:** Several proposed remediations from Stages 6 and 7 add operational complexity beyond Athar's scale (`gunicorn -w 4`, single 4-hour cron in `jobs.yaml`, 12 Python dependencies):
  * Moving community/manual roster syncs off Gunicorn onto a custom DB job queue or Celery/Redis broker over-engineers a rare Admin/manual action; running only the single Meta-Wiki roster parse synchronously (`timeout=15` in `scripts/parse_members.py`) and letting `jobs.yaml` handle bulk CentralAuth metrics—plus removing `force=True` on `manual_sync`—eliminates Gunicorn daemon threads without new worker infrastructure.
  * Adding Redis/Memcached, a sliding-window rate-limit table, or custom 64 KB serialized byte accounting for `Project.translations` over-engineers an authenticated authoring helper; coalescing the 4 fields into one MinT request per click, capping per-field character lengths + 20 languages, and using a minimal per-user cooldown suffices.
  * Adding a separate `LOCKED_ADMINS` config tier alongside `Config.ADMIN_USERS` creates unnecessary two-tier precedence; keeping `Config.ADMIN_USERS` seed-only (`migrate_v3.py`, `seed_test.py`) with DB `User.is_admin` as sole runtime authority avoids split-brain rules.
  * Mandating pagination across `/activities` and `/api/projects` conflicts with `tests/test_api.py` and `export.js` expectations for flat arrays; drop `?paginated=1` on `/api/projects` and use a simple SQL `LIMIT` or standard SSR `?page=` if needed on HTML pages.
* **Rationale & Recommendation:** Include a concise `## Risks & Mitigations` table to satisfy `feature-spec-standard.md`, while keeping all mitigations minimal and free of unrequested worker/cache infrastructure.

### 2. Dual SSR + CSR Activity Pipeline on `/activities` Creates Template Drift & HTML Rendering Paradox - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 247-257`, `Lines 535-584`
* **Discrepancy Description:** `GET /activities` and `GET /<slug>/activities` already filter via `filter_projects()` and render Jinja cards in `app/templates/activities.html`, while `/` submits a standard `GET /activities?...` query. Preserving a second client-side rendering pipeline in `app/static/js/filters.js` duplicates card HTML, duplicates status/type/wiki maps, forces `can_edit`/`lang` into `Project.to_dict()`, and creates the HTML-description rendering conflict without `.innerHTML`.
* **Rationale & Recommendation:** Submit `<form method="GET">` directly to server-rendered `/activities` and `/<slug>/activities` and link cards to `/project/<id>` (matching `dashboard.html`), deleting the redundant JS card/modal renderer.

### 3. Ambiguous Dual Soft-Delete Boundary & Split Admin Ownership - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 216-232`, `Lines 470-514`
* **Discrepancy Description:** Mixing explicit `active_projects_query()` calls across ~19 sites with an *"optional"* global `do_orm_execute` listener (`line 231`) while `GET /admin` relies on `execution_options(include_deleted=True)` (`line 474`) and `@project_editor_required` calls `Project.query.get_or_404()` directly is redundant and error-prone. Separately, `POST /add-community` is listed in the `admin_bp` table (`line 222`) yet modified inside `web.py` (`line 484`), while `POST /project/translate` is added to the 871-line `web.py`.
* **Rationale & Recommendation:** Commit exclusively to explicit `active_projects_query()` + `get_active_project_or_404()` across `web.py`, `api.py`, `oauth.py`, and `sync_data.py` (transparent for contributors, no ORM listener magic), and consolidate Admin routes inside `admin_bp`.

### 4. Over-Engineered `banana-i18n` Domain Split, Bespoke Plural Parser, & 4-Layer `*_ar` Wrappers - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 261-272`, `Lines 432-468`, `Lines 596-600`
* **Discrepancy Description:** Splitting ~60–100 static strings into `i18n/ui/*.json` and `i18n/reports/*.json` duplicates shared types, statuses, roles, and date labels while breaking `_(key, *args)` (`line 271`) vs. `get_message(domain, key, ...)` (`line 467`). Hand-rolling a Python plural parser leaves JS dynamic counts un-evaluated unless a client runtime is added. Furthermore, retaining 4 wrapper layers (`models.py` `*_ar` -> `__init__.py` filters -> `wiki_utils.py` -> `i18n.py`) breaks `?lang=en` report overrides because `p.status_ar` takes no `lang` parameter.
* **Rationale & Recommendation:** Merge into one `i18n/{en,ar,qqq}.json` bundle per locale, reuse `@wikimedia/banana-i18n` (or minimal `Intl.PluralRules`) on the client, lock `DEFAULT_LOCALE = "ar"`, and invoke `i18n.py` localization directly with `report_lang` rather than 4-layer `*_ar` properties.

### 5. Speculative `GET /healthz`, Unused `?paginated=1`, & Unnecessary `migrate_sqlite_to_mariadb.py` Work - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 237, 256, 483, 490, 498, 510-515`
* **Discrepancy Description:** `Procfile` and `jobs.yaml` configure no `/healthz` endpoint, and running cross-phase schema + `i18n` checks on an unauthenticated HTTP route fails in Phase 1 before `i18n/` exists. In addition, `scripts/migrate_sqlite_to_mariadb.py` already iterates `db.metadata.sorted_tables` and `db.metadata.create_all(dst_engine)` dynamically—requiring zero code changes (only tests).
* **Rationale & Recommendation:** Drop `GET /healthz`, drop `?paginated=1`, and remove `scripts/migrate_sqlite_to_mariadb.py` from code-modification items.

### 6. Missed Codebase Reuse Opportunities - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 227, 447-515, 522, 561`
* **Discrepancy Description:** Direct codebase inspection revealed five existing helpers/patterns to reuse rather than reimplementing:
  1. `community_report()` (`web.py:718-731`) already implements a single SQL `latest_snapshots` subquery—extract it into `query_utils.py` to fix N+1 loops in `dashboard()`, `community_users()`, `slug_Stat()` (which also queries member/project counts twice), and `list_members()`.
  2. `web.py` and `api.py` duplicate `project_type` `"Other"`, `bleach.clean`, date parsing, `results`, and status calculation—unify into one shared project-input parser/validator calling `determine_project_status()`.
  3. Parameterize `is_allowed_wikimedia_host(hostname, allowed_domains=...)` in `app/wiki_utils.py` instead of duplicating domain-suffix logic in `validate_activity_wiki_url()`.
  4. Extract CentralAuth `globaluserinfo` lookup (`api.py:check_user` and `scripts/sync_data.py:fetch_global_stats`) into a single utility using `Config.USER_AGENT` for `/admin/admins/grant`, and reuse `scripts/parse_members.py:normalize_meta_page_title()` for `meta_roster_page` normalization.
  5. `dashboard.html:116` already loads Chart.js; only remove the duplicate `<script>` in `base.html:11`.
* **Rationale & Recommendation:** Reuse and consolidate existing repository utilities instead of adding parallel logic.

### 7. Layering Leaks (`Project.to_dict`) and Altitude Drops / Cross-Section Repetition - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 44-65`, `Lines 170-293`, `Lines 370-383`, `Lines 408-615`
* **Discrepancy Description:** Adding `current_user=None, lang=None` to `Project.to_dict()` couples `app/models.py` to HTTP authorization and UI locale state while triggering lazy queries on lists. High-altitude sections (`Goals`, `NFRs`) also repeat code-level regexes, DDL strings, `bleach` kwargs, and template line numbers 3–4 times across sections.
* **Rationale & Recommendation:** Keep `models.py` persistence-only (evaluate permissions in `app/oauth.py`) and keep `Goals`/`NFRs` at contract altitude while consolidating specifics once in the technical/implementation plan.
