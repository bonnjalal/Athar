# Goldfish Annotated Review Report

**Status:** resolved
**Target:** `docs/designs/platform_redesign_i18n_and_admin_governance.md` (`1-635`)

## Prioritized Findings & AI Suggestions

### [B1 — Contradictory Soft-Delete Boundary (`do_orm_execute` vs. `active_projects_query()` vs. Raw Queries)] [`egm-zoom-out, egm-comprehension, egm-structural, egm-implementation-readiness, egm-codebase-details`] - Severity: Blocker
*   **Affected Scope:** [Lines 230-232, 415-433, 457, 474, 488, 498, 514](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L230-L514) (`Global Active-Project Query Boundary` & `Detailed Implementation Plan`)
*   **Discrepancy Description:** Line 231 marks SQLAlchemy `do_orm_execute` *"optional"*, yet Item 8 (`line 474`) uses `execution_options(include_deleted=True)` while Items 2–3 never register `do_orm_execute`. Without `do_orm_execute`, `Project.query.get_or_404()` in `@project_editor_required` (`app/oauth.py:116`), raw `db.session.query()` in `slug_Stat()` (`app/routes/api.py:178-192`), and `db.session.get()` in `export_project_csv()` (`app/routes/api.py:522`) leak soft-deleted rows. Furthermore, line 488 filters `view_project`/`edit_project` with `active_projects_query()` while stating only non-admins get HTTP 404.
*   **Rationale:** Dual optional ORM listeners and un-audited raw queries expose deleted activities in edits, KPIs, and exports while violating the Zero-Decision Rule.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Code inspection confirms `app/oauth.py:116`, `app/routes/api.py:178-192,522`, and `scripts/sync_data.py:194` query `Project` directly. Removing optional `do_orm_execute`/`execution_options` magic in favor of explicit `active_projects_query()` + `get_active_project_or_404()` across an enumerated list of all query sites makes soft-delete filtering uniform and inspectable.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §3` (`Line 231`) and `Detailed Implementation Plan` (`Items 3, 4, 6, 8, 9, 10, 12`)
    *   Change: Remove optional `do_orm_execute` / `execution_options(include_deleted=True)`. Standardize on `active_projects_query()` and `get_active_project_or_404(project_id)` across every public route, `api.py` (`slug_Stat`, `export_project_csv`, `list_*`, `get_project`, `update_project`), `@project_editor_required`, and `sync_data.py`. Specify that soft-deleted projects return HTTP 404 on public `view_project` / `edit_project` (requiring Admin restoration in `/admin` first), and guard `Community.projects` against accidental hard cascade deletion.

---

### [B2 — Contradictory Admin RBAC Precedence (`ADMIN_USERS` vs. DB Revocation) & Non-Member Admin Lockout] [`egm-zoom-out, egm-comprehension, egm-design, egm-structural, egm-implementation-readiness, egm-codebase-details, egm-style`] - Severity: Blocker
*   **Affected Scope:** [Lines 172, 188, 210-214, 228, 349, 412, 439-441, 477, 490](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L172-L490) (`OAuth & Role Resolution` & `Admin Console`)
*   **Discrepancy Description:** Line 213 asks `oauth_callback()` not to re-promote DB-demoted admins unless they are "locked bootstrap admins", while line 441 instructs decorators to evaluate `is_admin` *"against fresh DB state (plus `Config.ADMIN_USERS`)"* on every request—making env-listed admins impossible to revoke via `POST /admin/admins/revoke`. Additionally, `User` has only one `is_admin` boolean, `bootstrap_admins` is undefined, and non-rostered Admins provisioned with `is_member=False` hit HTTP 403 on `@member_required` endpoints (`POST /project/translate`, `POST /<slug>/sync`, `/project/new`).
*   **Rationale:** Runtime evaluation of `Config.ADMIN_USERS` overrides database revocation, and `@member_required` locks out non-rostered Admins.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Separating initial seeding (`Config.ADMIN_USERS` parsed as comma-separated `set[str]`, applied once in `migrate_v3.py`, `seed_test.py`, and initial `User` insert on first login) from runtime DB `User.is_admin` evaluation fixes the split-brain contradiction, while granting `is_admin` pass-through inside `@member_required` prevents Admin lockouts.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §3` (`Lines 210-214, 228`) and `Detailed Implementation Plan` (`Items 1, 4, 8, 9`)
    *   Change: Specify `Config.ADMIN_USERS` as a seed-only `set[str]` parsed from comma-separated env var (`{"Bonnjalal00"}` default), remove `"plus Config.ADMIN_USERS"` from runtime `@admin_required`, insert missing `User` rows on `oauth_callback()` with `is_member=False` and `is_admin=(username_lower in seeded_admins)` without re-promoting existing DB rows, grant `user.is_admin` pass-through inside `@member_required`, and document the complete RBAC permission table (`anonymous`, `non-member`, `member`, `organizer`, `admin`).

---

### [B3 — Missing Incremental Phase Partitioning & Unchecked Phase-Boundary Coupling (`/healthz`)] [`egm-zoom-out, egm-implementation-readiness`] - Severity: Blocker
*   **Affected Scope:** [Lines 237, 404-631](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L237-L631) (`Detailed Implementation Plan` & `Verification Plan`)
*   **Discrepancy Description:** Lines 404–616 present one mixed file-by-file list combining Phase 1, Phase 2, and Phase 3 changes inside shared files with only one end-of-plan verification section, and Item 9 (`line 490`) places `GET /healthz` checking `i18n/` JSON files in Phase 1 before `i18n/` exists in Phase 2.
*   **Rationale:** Each incremental phase must leave the repository buildable and testable with its own checkpoint, and no unrequested endpoint should couple Phase 1 to Phase 2 assets.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Reorganizing `Detailed Implementation Plan` into explicit `### Phase 1`, `### Phase 2`, and `### Phase 3` sections with phase-scoped file edits and verification checkpoints aligns with `implementation-readiness-standard.md`, and dropping speculative `GET /healthz` (verifying schema/i18n via startup/pytest instead) removes cross-phase failure modes.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §4` (`Line 237`) and `Detailed Implementation Plan` (`Lines 404-631`)
    *   Change: Split `Target Files to Create/Modify` into explicit Phase 1, Phase 2, and Phase 3 blocks, each ending with a runnable `pytest` + build verification checkpoint, and remove `GET /healthz` (`"healthz"` in `RESERVED_SLUGS` optional or removed).

---

### [B4 — `MOCK_AUTH` Startup Guard Conflicts with `.env.example`, `config.py`, `run.py`, & Existing Tests] [`egm-design, egm-implementation-readiness, egm-codebase-details`] - Severity: Blocker
*   **Affected Scope:** [Lines 211, 373, 419, 439-441](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L211-L441) (`config.py`, `run.py`, `.env.example`, `tests/test_routes.py`)
*   **Discrepancy Description:** Line 419 instructs `create_app()` to raise `RuntimeError` if `MOCK_AUTH=True` when `FLASK_DEBUG` is false or `OAUTH_CLIENT_ID` is set (and lines 211/373 omit `TESTING=True`). In the repo, `config.py` defines neither `FLASK_DEBUG` nor `DEBUG`, `.env.example` sets `DEBUG=True` alongside `MOCK_AUTH=True` and placeholder `OAUTH_CLIENT_ID=your-meta-client-id-here`, and `run.py` calls `create_app()` before `app.run(debug=True)`. Moreover, dropping cookie `session["is_member"]` trust breaks 7 existing `tests/test_routes.py` tests unless `User` DB rows are inserted and `TestConfig` sets `MOCK_AUTH = False`.
*   **Rationale:** As specified, the guard crashes local startup scripts (`run.py`, `seed_test.py`) and breaks existing route tests.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Defining `DEBUG` in `config.py` (reading `DEBUG` or `FLASK_DEBUG`), ignoring placeholder `OAUTH_CLIENT_ID` strings (and clearing the placeholder in `.env.example`), consistently exempting `TESTING=True`, and explicitly specifying `MOCK_AUTH = False` + `User` row fixtures in `tests/test_routes.py` resolves all startup and test failures.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §3` (`Lines 211-212`), `NFRs` (`Line 373`), and `Phase 1 Detailed Plan` (`config.py`, `app/__init__.py`, `app/oauth.py`, `.env.example`, `tests/test_routes.py`)
    *   Change: Add `Config.DEBUG` parsing (`DEBUG` or `FLASK_DEBUG`), exempt `TESTING=True` and unset/placeholder `OAUTH_CLIENT_ID` in the `MOCK_AUTH` startup check (updating `.env.example`), specify `get_current_user()` returning a `User` instance (or DB-backed mock user matching `MOCK_USERNAME`/`MOCK_IS_ADMIN`) used consistently by `@member_required`/`@project_editor_required`/`@admin_required`, and mandate `MOCK_AUTH = False` + DB `User` fixtures in `tests/test_routes.py`.

---

### [B5 — Cookie-Authenticated API Mutations Left Under `csrf.exempt(api_bp)`] [`egm-design`] - Severity: Blocker
*   **Affected Scope:** [Lines 373, 420](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L373-L420) (`app/__init__.py:47`, `app/routes/api.py:280-513`)
*   **Discrepancy Description:** Leaving `csrf.exempt(api_bp)` active while expanding `POST /api/<slug>/projects` and `PUT /api/projects/<id>` to accept `wiki_link`, `campaign`, `tags`, `translations`, and Admin cross-project writes exposes session-cookie-authenticated mutations to cross-site request forgery.
*   **Rationale:** `api_bp` authenticates via browser session cookies and `get_request_data()` accepts form data, so mutating routes require CSRF protection.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Enforcing Flask-WTF CSRF validation on session-cookie `POST`/`PUT` mutations (removing `csrf.exempt(api_bp)` or calling `csrf.protect()` on mutating `api_bp` endpoints and passing `X-CSRFToken` from client JS, while preserving/updating `WTF_CSRF_ENABLED` test hooks) closes the CSRF exposure cleanly.
*   ***Proposed Edit:***
    *   Location: `NFRs` (`Line 373`) and `Phase 1 Detailed Plan` (`app/__init__.py`, `app/routes/api.py`, `base.html`, `tests/test_api.py`)
    *   Change: Remove blanket `csrf.exempt(api_bp)` (or enforce `csrf.protect()` on all mutating `POST`/`PUT`/`DELETE` routes in `api_bp` while allowing read-only `GET` endpoints), inject `<meta name="csrf-token" content="{{ csrf_token() }}">` in `base.html` for JS `fetch()`, and cover CSRF validation in `test_api.py` / `test_admin_and_governance.py`.

---

### [B6 — Broken Date-Overlap Formula & Underspecified `filter_projects()` Contract] [`egm-comprehension, egm-design, egm-structural, egm-style, egm-implementation-readiness, egm-codebase-details`] - Severity: Blocker
*   **Affected Scope:** [Lines 248-255, 459-460, 497](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L248-L497) (`app/query_utils.py`, `app/routes/api.py`, `tests/test_api.py`)
*   **Discrepancy Description:** The overlap predicate `(start_date IS NULL OR start_date <= period_end) AND (end_date IS NULL OR end_date >= period_start)` drops `created_at` fallback when `start_date`/`end_date` are `NULL`, causing `tests/test_api.py:259-261` (`year=1999`) to return `self.p2` (`start_date=None, end_date=None`) and matching 2025 projects with `end_date=None` in 2026. Unifying `api.py` onto `filter_projects()` also drops existing `target_wiki` filtering (`tests/test_api.py:147-151`), `"Other"` custom-type filtering, and `filter_projects_by_status()` flags, while leaving `month`-only column targeting, return signature, `q` fields, `campaign` match mode, and multi-`tag` `AND` vs `OR` semantics undecided.
*   **Rationale:** The current predicate introduces test regressions and leaves core filter semantics ambiguous.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Using `effective_start = func.coalesce(Project.start_date, func.date(Project.created_at))` and `effective_end = func.coalesce(Project.end_date, Project.start_date, func.date(Project.created_at))` preserves `tests/test_api.py` compatibility while supporting multi-month overlap, and locking every parameter (`target_wiki`, `"Other"` type, `campaign` exact/substring, `tags` `AND`, `month`-only overlap) satisfies the Zero-Decision Rule.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §4` (`Lines 248-255`) and `Phase 1 Detailed Plan` (`app/query_utils.py`, `app/routes/api.py`)
    *   Change: Define `filter_projects(query, args) -> Query` (plus `filter_projects_by_date(query, args) -> tuple[Query, Optional[date], Optional[date]]` for `community_report`) using `eff_start = func.coalesce(Project.start_date, func.date(Project.created_at))` and `eff_end = func.coalesce(Project.end_date, Project.start_date, func.date(Project.created_at))` with `eff_start <= period_end` and `eff_end >= period_start`. For `month` without `year`, match `extract('month', eff_start) == m` OR `extract('month', eff_end) == m` (or span check across month). Preserve `target_wiki` normalization, `filter_projects_by_status()` inclusion flags + `"Canceled"`/`"Cancelled"`, and `"Other"` non-standard type exclusion; lock `q` (case-insensitive `title` + `campaign` + `description`), `campaign` (case-insensitive substring match), and comma-separated `tags` (`AND` matching requiring all specified normalized tags).

---

### [B7 — Phase 3 MinT API Protocol, Multi-Worker Rate Limiting & `Project.localized_field()` Contract Gaps] [`egm-zoom-out, egm-comprehension, egm-design, egm-structural, egm-style, egm-implementation-readiness`] - Severity: Blocker
*   **Affected Scope:** [Lines 64, 222-223, 280-287, 355-356, 379, 413, 432-433, 490, 549, 570, 593, 609](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L64-L609) (`Procfile:1`, `app/routes/web.py:102-103, 242-254`)
*   **Discrepancy Description:** Upstream MinT endpoint (`POST {MINT_API_URL}/translate/{src}/{tgt}`), HTML/plain-text handling, coalesced single-request schema on `POST /project/translate`, `<meta name="csrf-token">`, error codes, and `Project.localized_field()` / `Project.to_dict(lang=...)` return shapes (including `results_summary`/`results_notes` mapping) are unspecified. In addition, a cookie-backed Flask `session` rate limit is bypassable by cookie replay across 4 Gunicorn workers, and `POST /add-community` / `POST /<slug>/sync` risk worker starvation via `daemon=True` threads and synchronous CentralAuth loops.
*   **Rationale:** Implementers cannot build `POST /project/translate`, `translation-panel.js`, or `Project.localized_field()` without concrete schemas and worker-safe limits.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Specifying the exact MinT API contract (single coalesced JSON request on `POST /project/translate` returning sanitized fields, lightweight server-side per-user cooldown stored on `User` or DB rather than cookies/Redis), exact `localized_field()` string return + helper signature, and synchronous single-page roster parse (`timeout=15`) + scheduled `jobs.yaml` CentralAuth sync (dropping `force=True` on `manual_sync`) resolves both Phase 3 protocol ambiguity and Gunicorn worker risks without extra infrastructure.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §3, §6` (`Lines 222-223, 280-287, 379`) and `Detailed Implementation Plan` (`Phase 1` & `Phase 3` entries for `models.py`, `web.py`, `admin.py`, `translation-panel.js`)
    *   Change: Specify `POST {MINT_API_URL}/translate/{source_lang}/{target_lang}` (`format="html"` for `description` then `bleach.clean`, `format="text"` for `title`/`results_summary`/`results_notes`), coalesced JSON payload/response on `POST /project/translate`, server-side per-user cooldown (`10` translation calls per minute via lightweight DB timestamp/counter column on `User` or rate-limit table) returning HTTP `401`/`403`/`429`/`502`/`504` JSON payloads (decorating `POST /project/translate` to return JSON `401` rather than `302` redirect), exact `Project.localized_text(field_name, lang) -> str` + `Project.localized_source_lang(field_name, lang) -> str` helpers (mapping `"results_summary"`/`"results_notes"` to `self.results`), `to_dict()` keys, and running only `parse_members` synchronously (`timeout=15`) on community add/edit while leaving bulk CentralAuth stats to `jobs.yaml` (and removing `force=True` from `POST /<slug>/sync`).

---

### [B8 — `determine_project_status()` Divergence Breaks `tests/test_routes.py` & Leaves `"Canceled"` Overwrite in `api.py`] [`egm-zoom-out, egm-codebase-details, egm-implementation-readiness`] - Severity: Blocker
*   **Affected Scope:** [Lines 200, 449, 489, 499](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L200-L499) (`app/wiki_utils.py:174-225`, `app/routes/web.py:381-391`, `app/routes/api.py:488-495`, `tests/test_routes.py:213-238`)
*   **Discrepancy Description:** `web.py` recalculates non-`Canceled` statuses from dates (explicitly asserted in `tests/test_routes.py:220-237`), whereas `determine_project_status()` honors manual statuses and returns un-normalized strings, and `api.py:492-494` (`update_project`) still passes `"auto"` when dates change without `status`, overwriting `"Canceled"` projects.
*   **Rationale:** Routing `web.py` blindly through `determine_project_status(..., raw_status)` breaks `tests/test_routes.py`, while leaving `api.py:492-494` untouched preserves the `"Canceled"` overwrite bug.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Explicitly skipping `"auto"` recalculation in `api.py:492-494` when `project.status` is `"Canceled"`/`"Cancelled"`, normalizing `"Canceled"`/`"Cancelled"` inside `determine_project_status()`, and keeping `web.py` passing `"Canceled"` if canceled else `"auto"` into a shared project-payload helper preserves all existing tests while fixing the bug everywhere.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §2` (`Line 200`) and `Phase 1 Detailed Plan` (`app/wiki_utils.py`, `app/routes/web.py`, `app/routes/api.py`)
    *   Change: Update `determine_project_status()` to normalize `"Canceled"`/`"Cancelled"`/`"ملغي"` to `"Canceled"`, add `current_status=None` guard so `"auto"` never overrides existing `"Canceled"` projects, update `api.py:update_project()` to skip `"auto"` override when `project.status == "Canceled"`, and specify `web.py` passes `"Canceled"` when selected or `"auto"` otherwise (preserving `tests/test_routes.py:220-237`).

---

### [B9 — Missing `Risks & Mitigations` Section & Unresolved Zero-Decision Choices] [`egm-comprehension, egm-design, egm-structural, egm-style, egm-implementation-readiness, egm-codebase-details`] - Severity: Blocker
*   **Affected Scope:** [Lines 47, 78, 193-194, 210, 232, 269, 368-400, 412-413, 447, 450, 476-477, 483, 490, 548, 628](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L47-L628)
*   **Discrepancy Description:** `FeatureRange` omits the mandatory `## Risks & Mitigations` section; `Config.DELETION_REQUEST_URL` default/empty UI behavior is unresolved; `wiki_link` validation contradicts between normalizing vs. rejecting `http://`, rejects empty root paths (`eventmetrics.wmcloud.org`), and omits `ValueError` vs. `None` signaling; `sanitize_project_text_fields()` uses an ellipsis instead of exact `tags=[], attributes={}`; `POST /lang (or ?set_lang=)` is undecided and `"lang"` is missing from `RESERVED_SLUGS`; purge confirmation (`ID` vs. `title`) and audit log destination (`app.logger` schema) are undefined; and self-revocation / CentralAuth error responses in `check_user()` are ambiguous.
*   **Rationale:** Every open choice violates `implementation-readiness-standard.md` (Zero-Decision Rule) and `feature-spec-standard.md` (`Risks & Mitigations`).
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Resolving each minor parameter deterministically and adding a concise `## Risks & Mitigations` table completes all required standards without leaving decisions to implementers.
*   ***Proposed Edit:***
    *   Location: `FeatureRange` (`after NFRs, ~Line 384`) and `Detailed Implementation Plan` (`config.py`, `wiki_utils.py`, `admin.py`, `web.py`, `api.py`)
    *   Change:
        1. Add `## Risks & Mitigations` (`Risk | Impact | Mitigation Strategy` table) covering 4-worker concurrency, MinT unavailability/stale translation drift, MariaDB vs SQLite collation/DDL limits, and Phase 1 rollback.
        2. Lock `Config.DELETION_REQUEST_URL` default (`""` / `None`, hiding the link on `project_detail.html` when unset).
        3. Lock `validate_activity_wiki_url(raw_url) -> Optional[str]`: blank -> `None`; scheme-less valid host or `http://` -> upgrade to `https://` (`urlparse` rejects non-`http`/`https` such as `javascript:`, embedded userinfo `@`, ports, backslashes, whitespace, length `> 1024`, and disallowed hosts by raising `ValueError`; empty `path == ""` is permitted).
        4. Lock `sanitize_project_text_fields()` exact parameters (`tags=[]`, `attributes={}`, `strip=True` for plain text; `tags=["p","b","i","strong","em","ul","ol","li","a","br"]`, `attributes={"a":["href","title"]}`, `protocols=["http","https"]`, `strip=True` + `rel="noopener noreferrer"` for `description`; reject blank post-sanitization `title` with HTTP 400).
        5. Lock `POST /lang` (plus `"lang"` in `RESERVED_SLUGS`) with CSRF token and safe relative `next` URL validation.
        6. Lock `POST /admin/project/<id>/purge` confirmation field (`confirm_project_id` matching `str(project.id)`), `current_app.logger.info(...)` structured audit fields (`actor`, `action`, `target_type`, `target_id`, `details`), blocking self-revocation on `/admin/admins/revoke`, and `check_user()` returning HTTP `503` JSON `{"exists": False, "error": "..."}` (or logging warning + `200` for form badge) on CentralAuth failure.

---

### [M1 — Dual SSR + CSR Activity Pipeline on `/activities` & Form/Modal Gaps] [`egm-zoom-out, egm-comprehension, egm-structural, egm-implementation-readiness, egm-codebase-details`] - Severity: Major
*   **Affected Scope:** [Lines 247-257, 283, 371, 487, 535-547, 584, 592](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L247-L592) (`activities.html`, `filters.js`, `project_form.html`)
*   **Discrepancy Description:** Maintaining both server-rendered cards (`activities.html`) and JS-rebuilt cards/modals (`filters.js`) causes template drift, breaks SSR `GET` parity on `community_activities()`, fails when `community=None` (`activities.html:3,6`), lacks `name` attributes and reset semantics on `#reset-filters`, and creates a conflict between banning `.innerHTML` vs. rendering Bleach-sanitized HTML descriptions in `#modal-project-description`. Separately, `project_form.html` needs a `form_data` fallback for HTTP 400 retention, `type="text"` on `wiki_link`, and async/sync submit behavior in `chip-input.js`.
*   **Rationale:** Consolidating `/activities` onto server-rendered `GET` filtering (linking cards directly to `/project/<id>` like `dashboard.html`) removes the entire dual-pipeline conflict, while specifying `form_data` and `chip-input.js` prevents form regressions.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Dropping the redundant JS card/modal builder in `filters.js` (keeping optional lightweight client enhancements or pure `<form method="GET">` submission onto `/activities` / `/<slug>/activities`) eliminates `.innerHTML` vs HTML-description conflicts, `Project.to_dict(can_edit=...)` coupling, and SSR/CSR divergence while keeping bookmarks shareable.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §4` (`Lines 247-257`) and `Phase 1 Detailed Plan` (`web.py`, `activities.html`, `filters.js`, `project_form.html`, `chip-input.js`)
    *   Change: Have both `GET /activities` and `GET /<slug>/activities` filter server-side via `filter_projects()` and render cards via a shared Jinja partial linking directly to `/project/<id>`, replacing `filters.js`'s duplicate card/modal DOM builder with clean `<form method="GET">` submission and working Reset link (`href` to clean route). Guard `community` checks in `activities.html` when `community=None`, add `form_data` dict fallback and `type="text"` (`inputmode="url"`) on `wiki_link` in `project_form.html`, and specify synchronous tag commit vs. blocking form submit until pending `wikimedia_user` `/api/check-user` verification resolves in `chip-input.js`.

---

### [M2 — Over-Engineered `banana-i18n` Domain Split, Plural Rules & `?lang=` Template Overrides] [`egm-zoom-out, egm-comprehension, egm-design, egm-structural, egm-style, egm-implementation-readiness, egm-codebase-details`] - Severity: Major
*   **Affected Scope:** [Lines 261-272, 413, 422, 432-433, 451, 462-468, 569-570, 584-586, 596-600](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L261-L600)
*   **Discrepancy Description:** Having both `_(key)` and `get_message(domain, ...)` creates ambiguity between `i18n/ui/` and `i18n/reports/` for shared activity types/statuses/roles; `DEFAULT_LOCALE` is stated ambiguously at line 269; `qqq` exclusion is omitted from FeatureRange; report templates call parameterless `{{ p.status_ar }}` (ignoring `?lang=en`); and dynamic JS counts receive raw `{{PLURAL:$1|...}}` strings with no JS runtime specified.
*   **Rationale:** Keeping the user's requested two Translatewiki message groups (`i18n/ui/` and `i18n/reports/`), the engine must unambiguously route shared keys, pass `report_lang` through report filters, and evaluate plurals in client JS.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Honoring the user's explicit request for two Translatewiki subprojects (`i18n/ui/` and `i18n/reports/`), we resolve every implementation ambiguity cleanly by defining `_()` (`ui`) and `_r()` (`reports`), storing shared type/status/role terms in `i18n/ui/` (or resolving `_r()` with `reports` -> `ui` fallback), updating report templates to pass `report_lang`, locking `DEFAULT_LOCALE = "ar"`, excluding `qqq` from locales, and adding `atharI18n.t(key, ...args)` using `Intl.PluralRules` for client JS.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §5` (`Lines 261-272`) and `Phase 2 Detailed Plan` (`config.py`, `app/i18n.py`, `app/models.py`, `app/templates/reports/*.html`, `app/static/js/`)
    *   Change: Lock `Config.DEFAULT_LOCALE = "ar"`, derive `SUPPORTED_LOCALES` by scanning `i18n/ui/*.json` (excluding `qqq.json`), expose `_()` (`ui`) and `_r()` (`reports` with fallback to `ui`) to Jinja/routes, update `ar_type`/`ar_status` (and new `t_type`/`t_status` filters) to accept optional `lang` (defaulting to `g.report_lang` or `current_locale()`), update `reports/*.html` to invoke localized filters with `report_lang` instead of `p.status_ar`, map CLDR plural rule lookup by locale code, and add a small `atharI18n.t(key, ...args)` helper using `Intl.PluralRules` in `base.html`/`i18n.js`.

---

### [M3 — Blueprint Ownership Split, ORM/RBAC Coupling & Missed Codebase Reuse] [`egm-zoom-out, egm-comprehension, egm-structural, egm-style, egm-implementation-readiness, egm-codebase-details`] - Severity: Major
*   **Affected Scope:** [Lines 116-166, 216-227, 256, 422, 432, 470, 484, 490, 498, 510-515, 521](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L116-L521)
*   **Discrepancy Description:** `POST /add-community` is placed in `admin_bp` (`line 222`) yet modified in `web.py` (`line 484`); `?paginated=1` on `/api/projects` has no UI caller; `Project.to_dict(current_user=...)` couples `models.py` to RBAC; `@app.context_processor` for `current_user` is missing (`base.html` fails on `create_project`/`view_project`); `migrate_sqlite_to_mariadb.py` already handles dynamic tables via `db.metadata`; the Mermaid diagram mislabels `/report/*` and omits edges; and 5 existing helpers (`latest_snapshots` subquery in `community_report`, shared project payload parser across `web.py`/`api.py`, `is_allowed_wikimedia_host()`, `check_user` CentralAuth lookup with `Config.USER_AGENT`, `normalize_meta_page_title()`) were missed.
*   **Rationale:** Consolidating routes, removing unused API modes, registering context processors, and reusing existing helpers prevents duplication and bugs.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Every item is directly verified against `app/routes/web.py`, `app/routes/api.py`, `scripts/parse_members.py`, and `scripts/migrate_sqlite_to_mariadb.py`.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §1, §3, §4` and `Detailed Implementation Plan` (`Items 2, 3, 4, 5, 6, 8, 9, 10, 12`)
    *   Change: Keep `POST /add-community` cleanly on `admin_bp` (updating `url_for` targets) or `web_bp` (specified once); drop unused `?paginated=1` on `/api/projects`; register `@app.context_processor` injecting `current_user`, `current_locale`, `locale_dir` in `app/__init__.py`; remove `can_edit` from `Project.to_dict()` (evaluate in `app/oauth.py` helpers when needed); drop `scripts/migrate_sqlite_to_mariadb.py` edits; extract `get_latest_snapshots_total()`, `verify_wikimedia_username()` (using `Config.USER_AGENT`), and shared project payload parser/validator; parameterize `is_allowed_wikimedia_host()`; reuse `normalize_meta_page_title()`; and update the Mermaid diagram with accurate `/project/<id>/report`, `/<slug>/report`, `/user/<username>/report`, `AdminBP`, `SyncCron`, and edges.

---

### [M4 — Unbounded Queries, Missing Eager Loading & Uncapped `Project.translations` Serialization] [`egm-design, egm-implementation-readiness, egm-codebase-details`] - Severity: Major
*   **Affected Scope:** [Lines 241-256, 280-281, 377-378, 430, 432, 458, 498-501](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L241-L501)
*   **Discrepancy Description:** List endpoints lack `selectinload(Project.tags_rel)` + `joinedload(Project.community)` + `defer(Project.translations)`, `export_view` scans `Project.query.all()` for years, `Project.translations` lacks per-field size bounds (Phase 3), `sync_project_tags()` leaves `PUT` partial-update and `>20` tag handling undefined, `translations` mutations need `MutableDict`/copy assignment, and CSV `stream_with_context` generators must bind `?lang=` eagerly and localize raw `p.status`/`p.project_type`.
*   **Rationale:** Unbounded eager/lazy loading and unguarded JSON updates cause N+1 latency spikes, silent lost writes, and inconsistent CSV output.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Specifying `joinedload`/`selectinload` + `defer(Project.translations)` on list queries, `SELECT DISTINCT` years in `export_view`, per-field limits (`title <= 255`, `description <= 10 KB`, `results_summary/notes <= 4 KB`) on `translations`, copy/assignment semantics (`MutableDict`), `sync_project_tags()` rejecting `>20` tags with HTTP `400` and leaving omitted `"tags"` untouched on `PUT`, and eager CSV locale resolution solves all scalability and correctness gaps.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §4, §6` and `Detailed Implementation Plan` (`models.py`, `query_utils.py`, `web.py`, `api.py`)
    *   Change: Add `selectinload(Project.tags_rel)` + `joinedload(Project.community)` + `defer(Project.translations)` on list queries; bound `GET /activities` (e.g. `LIMIT 100` or standard `?page=` HTML pagination); replace `export_view` full scan with distinct year SQL query; add per-field max character caps on `Project.translations`; specify `MutableDict` / fresh `dict` assignment; reject `>20` tags with HTTP `400` and keep omitted `tags` unchanged in `PUT /api/projects/<id>`; and localize `status`/`project_type` cells in CSV exports using eagerly captured `?lang=`.

---

### [M5 — Non-Transactional MariaDB DDL, `migrate_v3.py` / `seed_test.py` Traps & Community Edit Validation] [`egm-design, egm-structural, egm-implementation-readiness, egm-codebase-details`] - Severity: Major
*   **Affected Scope:** [Lines 184-188, 222-223, 421, 475, 503-515](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L184-L515) (`scripts/migrate_v2.py`, `seed_test.py`, `scripts/sync_data.py`)
*   **Discrepancy Description:** MariaDB DDL commits implicitly (ignoring `engine.begin()` rollback); calling `create_app()` in `migrate_v3.py` risks premature startup hook failures; raw SQL table/admin inserts risk `NoSuchTableError` on stale `inspector`, missing `InnoDB`/`utf8mb4` parity, missing `is_member=0`, or duplicate idempotency `actions`; `seed_test.py:11` bulk `Project.query.delete()` leaves orphan `project_tags`; `create_app()` must merge `json_serializer` into `SQLALCHEMY_ENGINE_OPTIONS`; `sync_active_project_statuses()`'s trigger inside `sync_data.py` is unstated; and community add/edit lacks `Community.name` uniqueness, `[a-z0-9-]` non-empty `slug`, and `meta_roster_page` URL validation.
*   **Rationale:** These SQLite/MariaDB DDL and ORM cascade traps will cause runtime errors during migration and community editing.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Directly verified against `scripts/migrate_v2.py`, `seed_test.py:11`, `app/models.py:10-12,37`, and `config.py:40`.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §2, §3` and `Phase 1 Detailed Plan` (`app/__init__.py`, `admin.py`, `scripts/migrate_v3.py`, `scripts/sync_data.py`, `seed_test.py`)
    *   Change: Run `migrate_v3.py` directly on `resolve_database_uri()` engine (without `create_app()`), use `ProjectTag.__table__.create(bind=conn, checkfirst=True)` and explicit `is_member=0` on missing admin inserts while recording `actions` only on actual mutations, delete `ProjectTag` rows before `Project.query.delete()` in `seed_test.py`, merge `json_serializer` into `SQLALCHEMY_ENGINE_OPTIONS` in `create_app()`, invoke `sync_active_project_statuses()` inside `sync_data.py:run_sync()`, validate `Community.name` uniqueness + non-empty ASCII `[a-z0-9-]` `slug` + Wikimedia `meta_roster_page` validation in `POST /add-community` and `POST /admin/community/<id>/edit`, and document MariaDB implicit DDL commits.

---

### [M6 — Phase 3 Inline Style / RTL / Chart.js Initial Theme & H2/H3 Hierarchy Violations] [`egm-structural, egm-codebase-details`] - Severity: Major
*   **Affected Scope:** [Lines 385-400, 561-586](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L385-L586) (`app/static/js/export.js:245-261`, `codex.style.css:1113`, `index.html:52`, `dashboard.html:61`)
*   **Discrepancy Description:** `### Additional Resources` and `### Future Improvements` (`lines 387, 394`) are H3 headings nested under `## Non-Functional Requirements` instead of H2. Additionally, `export.js:245-261` embeds inline `#fafafa` / `text-align: right` styles, `codex.style.css:1113` uses asymmetric physical padding, `index.html:52` (`←`) and `dashboard.html:61` (`&larr;`) hardcode RTL arrows, and `charts.js` must read theme CSS variables on initial load (not only on `athar:themechange`).
*   **Rationale:** Incomplete CSS/JS cleanup leaves broken dark mode surfaces and inverted arrows in LTR mode, and mismatched H2/H3 headers break document hierarchy.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Promoting the two H3 headings to H2 and enumerating the observed inline styles/arrows/initial Chart.js paint guarantees complete theme and LTR/RTL parity.
*   ***Proposed Edit:***
    *   Location: `Lines 387, 394` and `Phase 2 / Phase 3 Detailed Plan` (`templates`, `codex.style.css`, `export.js`, `charts.js`)
    *   Change: Promote `### Additional Resources` and `### Future Improvements` to `##`; add `export.js:245-261` inline hex/alignment removal, `codex.style.css:1113` `padding-inline-start`/`padding-inline-end` conversion, directional arrow mirroring in `index.html:52` and `dashboard.html:61`, and reading CSS custom properties on initial `charts.js` chart render.

---

### [M7 — Terminology Precision ("Stewards", "Tool Admin", "Commons-style") & Unexplained Legacy Symbols] [`egm-comprehension, egm-style`] - Severity: Major
*   **Affected Scope:** [Lines 13, 15, 31, 39, 49, 55-57, 64, 72, 85, 106, 196, 205, 221-226, 284, 484, 499](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L13-L499)
*   **Discrepancy Description:** Uses `"stewards"` (`line 31`) instead of `"administrators"`, leaves `"Tool Admin"` and `"Commons-style"` undefined relative to Wikimedia Toolforge terminology, blurs browser `@media print` PDF saving vs. server PDF rendering, references `pending_community_*`, `create_projetct`, `target_wiki_url`, and `/api/check-user` without brief explanations, and uses open-ended scope phrasing (`"full community editing"`, `"load cleanly"`).
*   **Rationale:** Misleading Wikimedia terms and unexplained legacy code artifacts confuse fresh readers and implementers.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Defining terms inline on first use and naming exact legacy symbols (`create_projetct` `[sic]` in `api.py`, existing `pending_community_*` session stash, browser print-to-PDF HTML) makes the spec self-contained.
*   ***Proposed Edit:***
    *   Location: `Overview`, `Problem`, `Goals`, `Technical Plan`, and `Detailed Implementation Plan`
    *   Change: Replace `"stewards"` with `"administrators"`; define `"Tool Admin"` (`"in-app database administrators, distinct from Toolforge UNIX maintainers"`); replace `"Commons-style"` with `"expandable per-language panel"`; clarify browser `@media print` PDF export; briefly explain `pending_community_*`, `target_wiki_url`, `/api/check-user` user chips, and `create_projetct` `[sic]`; and specify exact moderation actions and observable asset assertions.

---

### [M8 — Unmeasurable Verification Claims (`100%` / `19+`) & Missing Verification Commands] [`egm-style`] - Severity: Major
*   **Affected Scope:** [Lines 355-356, 377, 417, 491, 505, 515, 524, 532, 555, 584, 622-631](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L355-L631)
*   **Discrepancy Description:** `Verification Plan` claims `"100% branch verification"` across `"19+ Project query touchpoints"` without listing touchpoints or coverage commands, omits `python3 -m compileall app scripts`, omits required env vars for `create_app()` boot verification, omits `margin-left`/`padding-right`/`translateX(-4px)` in CSS grep checks and reverse-key/placeholder checks in `i18n` validation, lacks explicit E2E assertions across Phases 1–3, and uses subjective modifiers (`"cleanly"`, `"safely"`, `"tiny"`, `"sub-second"` without dataset scale).
*   **Rationale:** Unbounded claims and missing commands cannot be audited deterministically during verification.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Replacing subjective qualifiers with exact behaviors and listing explicit CLI verification commands per phase makes verification objective.
*   ***Proposed Edit:***
    *   Location: `Verification Plan` and `Detailed Implementation Plan` items (`Lines 417-631`)
    *   Change: Replace `"100% branch verification"` across `"19+ touchpoints"` with enumerated query site verification + `./venv/bin/pytest --cov=app`; add `python3 -m compileall app scripts` and explicit `TESTING=1` / `FLASK_DEBUG=1` boot checks; expand CSS and JSON parity/placeholder grep/Python checks; specify Phase 1/2/3 E2E test assertions (including MinT and pre-paint `data-theme`); and delete filler qualifiers (`"cleanly"`, `"safely"`, `"tiny"`).

---

### [N1 — Security & Schema Polish (`rel="noopener noreferrer"`, Composite Index, `"Cancelled"` Filter Normalization)] [`egm-comprehension, egm-design`] - Severity: Nit
*   **Affected Scope:** [Lines 200, 241, 254, 283](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L200-L283)
*   **Discrepancy Description:** `bleach.clean` on `description` strips `rel` rather than setting `rel="noopener noreferrer"` on `<a>` tags; `projects` lacks composite index `(is_deleted, status, start_date)` for `GET /`; and `"Cancelled"` spelling is normalized in status saving (`L200`) but omitted in `filter_projects()` (`L254`).
*   **Rationale:** Adding link attributes, the composite index, and `"Cancelled"` query normalization closes minor security and query polish gaps.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Small, deterministic additions with clear security/query benefits.
*   ***Proposed Edit:***
    *   Location: `Technical Plan §2, §4, §6` and `Phase 1 Detailed Plan` (`wiki_utils.py`, `query_utils.py`, `migrate_v3.py`)
    *   Change: Add `bleach` link callback setting `rel="noopener noreferrer"`, add `ix_projects_active_status_start (is_deleted, status, start_date)` in `migrate_v3.py`, and normalize `"Canceled"`/`"Cancelled"` in `filter_projects()`.

---

### [N2 — Missed Existing Reuse (`is_allowed_wikimedia_host()`, `dashboard.html` Chart.js, Already-Registered `SITEMAP.md`)] [`egm-zoom-out, egm-codebase-details`] - Severity: Nit
*   **Affected Scope:** [Lines 447, 522, 561, 615](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L447-L615) (`app/wiki_utils.py:60-65`, `app/templates/dashboard.html:116`, `docs/designs/SITEMAP.md:6`)
*   **Discrepancy Description:** `is_allowed_wikimedia_host()` already checks suffix domains; `dashboard.html:116` already includes `chart.js` (so only `base.html:11` needs removal); and `docs/designs/SITEMAP.md:6` already registers this design document.
*   **Rationale:** Keeping file instructions accurate prevents redundant edits.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Verified directly in repository files.
*   ***Proposed Edit:***
    *   Location: `Phase 1 Detailed Plan` (`wiki_utils.py`, `base.html`, `dashboard.html`, `SITEMAP.md`)
    *   Change: Parameterize `is_allowed_wikimedia_host(hostname, allowed_domains=...)`; remove duplicate Chart.js only from `base.html:11`; and note `SITEMAP.md` row update covers final post-resolution metadata only.

---

### [N3 — Dead Duplicate Factory in `app/routes/__init__.py` & Target File Ordering] [`egm-codebase-details, egm-implementation-readiness, egm-style`] - Severity: Nit
*   **Affected Scope:** [Lines 406, 470](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L406-L470) (`app/routes/__init__.py:1-37`)
*   **Discrepancy Description:** Line 406 claims files are in `"dependency order"` even though Phase 2 `app/i18n.py` precedes Phase 1 `admin.py`, and Item 8 (`line 470`) marks `app/routes/__init__.py` `(Modify if needed)` despite containing an unused duplicate `create_app()`.
*   **Rationale:** Deciding `app/routes/__init__.py` explicitly and fixing ordering removes minor ambiguity.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Reorganizing by Phase 1 -> Phase 2 -> Phase 3 (`B3`) fixes ordering; explicitly leaving `app/routes/__init__.py` untouched (blueprints register in `app/__init__.py`) avoids unnecessary churn.
*   ***Proposed Edit:***
    *   Location: `Detailed Implementation Plan` (`Lines 406, 470`)
    *   Change: Remove `(Modify if needed)` on `app/routes/__init__.py` (keep registration in `app/__init__.py`) and group all file steps strictly by Phase 1 -> Phase 2 -> Phase 3 in dependency order.

---

### [N4 — Altitude Drops (Weeds), Cross-Section Repetition, & Markdown Formatting / Portable Links] [`egm-zoom-out, egm-structural`] - Severity: Nit
*   **Affected Scope:** [Lines 35, 44-65, 170-293, 370-392, 408-615](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L35-L615)
*   **Discrepancy Description:** `Goals` and `NFRs` repeat regexes, DDL strings, and `bleach` kwargs from `Technical Plan`; `lines 171-292` use 1-space list markers / 2-space indents vs. 3-space / 4-space elsewhere; `lines 389-392` use machine-local `file://` links; and `line 35` refers to `"four JavaScript files"` instead of three standalone JS files plus inline template scripts.
*   **Rationale:** Keeping `Goals`/`NFRs` concise, using portable relative links, and standardizing list formatting improves readability.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Trimming redundant syntax details in `Goals`/`NFRs` and fixing portable Markdown formatting matches repository conventions.
*   ***Proposed Edit:***
    *   Location: `Lines 35, 44-65, 171-292, 370-392`
    *   Change: Move low-level DDL/regex specifics out of `Goals`/`NFRs`, fix `"three standalone JS files and inline template scripts"` (`line 35`), standardize `*   ` 4-space indentation (`lines 171-292`), and convert `Additional Resources` URLs (`lines 389-392`) to relative paths (`../../concepts_brief.md`, `./multi_level_export_and_user_intelligence.md`, `../../app/models.py`, `../../scripts/migrate_v2.py`).

---

### [N5 — Open Questions vs. Plan Alignment & Minor UI/Test Edge Cases] [`egm-comprehension, egm-implementation-readiness, egm-style`] - Severity: Nit
*   **Affected Scope:** [Lines 78-79, 226, 396, 422, 524, 548-555, 569, 606-609](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L78-L609)
*   **Discrepancy Description:** Open Question #2 (`line 79`) asks whether old slugs 404 or redirect while `line 555` already picks warning + no redirect; `line 524` omits `try/catch` around `localStorage` and `prefers-color-scheme: dark` fallback; `#export-lang` DOM ID and `ar_type`/`ar_status` signatures are omitted; and Item 24 omits explicit tests for `MOCK_AUTH` `RuntimeError`, `oauth_callback` `is_member=False`, 400 form retention, `sync_active_project_statuses()`, and Phase 3 localized exports.
*   **Rationale:** Syncing Open Questions and listing edge-case tests prevents minor implementation omissions.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Quick textual alignment across existing document sections.
*   ***Proposed Edit:***
    *   Location: `Open Questions` (`Lines 78-79`), `Phase 1–3 Detailed Plan` (`base.html`, `export.html`, `tests/`)
    *   Change: Remove resolved Open Questions (moving `DELETION_REQUEST_URL` default and 404 + warning slug rename rule into Technical Plan), add `localStorage` `try/catch` + OS fallback note, specify `#export-lang` selector ID, and add the missing edge-case test items to Phase 1/2/3 test checkpoints.

---

### [N6 — Plain-English Style & Minor Terminology Nits] [`egm-style`] - Severity: Nit
*   **Affected Scope:** [Lines 27, 35, 40, 49, 53, 55, 61, 65, 91, 95, 101, 204, 244, 257, 335, 371](./docs/designs/platform_redesign_i18n_and_admin_governance.md#L27-L371)
*   **Discrepancy Description:** Contains MediaWiki/SPA/marketing jargon (`"lego strings"`, `"SSR"`, `"CTA"`, `"FOUC"`, `"Patchwork"`, `"Hygiene"`), filler adverbs (`"strictly"`, `"cleanly"`, `"harmlessly"`, `"tiny"`, `"safely"`), internal schema phrasing inside CUJs (`lines 91, 95`), `"separated"` instead of `"separate"`, and inconsistent `project_type` lists.
*   **Rationale:** Plain-English wording improves clarity across contributors and future translators.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Low-cost copy edits that align with the plain-English document standard.
*   ***Proposed Edit:***
    *   Location: `Lines 27-371`
    *   Change: Replace `"lego strings"` -> `"concatenated sentence fragments"`, `"SSR"` -> `"server-rendered"`, `"CTA"` -> `"button/link"`, `"FOUC"` -> `"pre-paint theme flash"`, strip filler adverbs (`"strictly"`, `"cleanly"`, `"harmlessly"`), keep CUJs user-observable, and align `project_type` lists.
