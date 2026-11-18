# Goldfish Review Report — Stage 9: Implementation Readiness Test

**Target:** `docs/designs/platform_redesign_i18n_and_admin_governance.md` (`402-635`)
**Standard:** `/home/bonnjalal/.gemini/config/plugins/egm/resources/document_standards/implementation-readiness-standard.md`

## Reviewer Status

| Reviewer | Status |
| :--- | :--- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. Missing Incremental Phase Partitioning and Phase-Boundary Checkpoints - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** `Lines 404-631` (`Target Files to Create/Modify`, Item 9 line 490, Item 24, `Verification Plan`)
* **Discrepancy Description:** `implementation-readiness-standard.md` requires partitioning work into incremental phases where each phase leaves the codebase buildable and testable. Lines 404–616 instead present a single file-by-file list mixing Phase 1, Phase 2, and Phase 3 changes inside shared files (Items 1, 2, 3, 5, 9, 10, 13–21, 24–25) with only one end-of-plan `Verification Plan`. Furthermore, Item 9 (`line 490`) places `GET /healthz` checking `i18n` JSON validity in Phase 1 before `i18n/` files are created in Phase 2.
* **Rationale & Recommendation:** Split `Detailed Implementation Plan` into explicit Phase 1, Phase 2, and Phase 3 execution sections, each with phase-scoped file edits and a concrete verification checkpoint (`pytest` command + schema/asset assertions) before advancing.

### 2. `MOCK_AUTH` Startup Guard Conflicts with `.env.example`, `config.py`, `run.py`, and Existing Tests - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `Line 419`, `Lines 439-441`, `config.py:29-52`, `run.py:1-6`, `.env.example:1-15`, `tests/test_routes.py:12-90`
* **Discrepancy Description:**
  * Line 419 instructs `create_app()` to raise `RuntimeError` if `MOCK_AUTH=True` while `FLASK_DEBUG` is false or `OAUTH_CLIENT_ID` is set (unless `TESTING=True`). In the codebase, `config.py` has no `FLASK_DEBUG`/`DEBUG` attribute; `.env.example` sets `DEBUG=True` (not `FLASK_DEBUG`), `MOCK_AUTH=True`, and a placeholder `OAUTH_CLIENT_ID=your-meta-client-id-here`; and `run.py` runs `app = create_app()` before `app.run(debug=True)`. Consequently, this guard crashes `run.py`, `seed_test.py`, and `migrate_v3.py` locally.
  * Additionally, `TestConfig` in `tests/test_routes.py` (and sibling test files) inherits `MOCK_AUTH` from `.env`, lines 439–441 leave unclear whether `@member_required` and `@project_editor_required` still bypass checks when `MOCK_AUTH=True`, and removing session cookie trust (`session["is_member"] = True`) breaks 7 existing `tests/test_routes.py` tests unless `User` DB rows are seeded and `MOCK_AUTH = False` is set in `TestConfig`.
* **Rationale & Recommendation:** Support `DEBUG`/`FLASK_DEBUG` explicitly in `config.py`, treat placeholder `OAUTH_CLIENT_ID` values as unset (or clear the placeholder in `.env.example`), specify decorator behavior under `MOCK_AUTH=True` consistently with `get_current_user()`, set `MOCK_AUTH = False` in `TestConfig`, and list required `tests/test_routes.py` fixture updates.

### 3. Contradictory RBAC Precedence for `Config.ADMIN_USERS`, DB Revocation, & Non-Member Admin Lockout - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** `Lines 412, 439-441, 477, 490` (vs. context `Lines 188, 213, 228`)
* **Discrepancy Description:**
  * Line 441 evaluates `is_admin` *"against fresh DB state (plus `Config.ADMIN_USERS`)"*, overriding database revocation in `POST /admin/admins/revoke` (`line 477`) for any user listed in `ADMIN_USERS` and leaving unclear how `Bonnjalal00` or self-revocation is governed. Line 439 calls for *"a User-compatible object/record"* under `MOCK_AUTH` without defining whether it is a persisted row or in-memory object, refers to undefined `bootstrap_admins` (`line 440`), and uses `"upsert missing User rows"` instead of `"insert missing User rows"`.
  * Line 490 guards `POST /project/translate` with `@member_required` even though non-rostered Admins are provisioned with `is_member=False` (`line 440`) and `@member_required` (`line 441`) is never updated to allow `is_admin`.
* **Rationale & Recommendation:** Use `Config.ADMIN_USERS` strictly for initial seed/migration (or define an explicit `LOCKED_ADMINS` list), allow `is_admin` pass-through in `@member_required`, specify exact `MOCK_AUTH` user representation, and document `ADMIN_USERS` comma-separated parsing.

### 4. Contradictory Soft-Delete Enforcement (`do_orm_execute` vs. `active_projects_query()` vs. Raw `db.session.query`) - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `Lines 415-433, 457, 474, 488, 498, 514`, `app/oauth.py:116`, `app/routes/api.py:178-192, 522`
* **Discrepancy Description:** Line 474 assumes `execution_options(include_deleted=True)` (which requires registering a SQLAlchemy `do_orm_execute` listener), yet Items 2 and 3 (`lines 415-433`) never specify registering `do_orm_execute`. Without it, `app/oauth.py:116` (`Project.query.get_or_404`), `api.py:178-192` (`slug_Stat` raw `db.session.query`), and `api.py:522` (`db.session.get`) bypass `active_projects_query()`. Moreover, `line 488` applies `active_projects_query()` to `view_project` and `edit_project` while simultaneously stating Admins can still view/edit soft-deleted projects (`"returning 404 to non-admins"`).
* **Rationale & Recommendation:** Either specify registering `do_orm_execute` in `app/__init__.py` (converting `get_or_404` / `db.session.get` to SQLAlchemy 2.0 `select()` queries so criteria apply) or drop `execution_options(include_deleted=True)` and update every query site including `slug_Stat` and `@project_editor_required`. Explicitly state Admin visibility on soft-deleted detail/edit/report routes.

### 5. Broken Date-Overlap Formula, Missing `target_wiki`/`"Other"` Filters, & Unspecified `filter_projects()` Contract - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `Lines 459-460, 497` (context `Lines 248-255`), `app/query_utils.py:14-114`, `app/routes/api.py:111-136, 246-278`, `tests/test_api.py:67-78, 146-152, 252-262`
* **Discrepancy Description:**
  * Overlap formula `(start_date IS NULL OR start_date <= period_end) AND (end_date IS NULL OR end_date >= period_start)` (`line 255`) drops `query_utils.py`'s `created_at` fallback when `start_date`/`end_date` are `NULL`, causing `tests/test_api.py:259-261` (`year=1999`) to falsely return `self.p2` (`start_date=None, end_date=None`) and matching 2025 projects with `end_date=None` in 2026.
  * Unifying `/api/projects` and `/api/<slug>/projects` onto `filter_projects()` (`line 459, 497`) omits `target_wiki` normalization filtering (breaking `tests/test_api.py:147-151`) and omits `"Other"` custom-type / `"Contest"` / `"Education Program"` matching (`filters.js:502-511`) plus `filter_projects_by_status()` inclusion flags (`include_planned`, etc.).
  * Month-without-year `extract('month', ...)` column target, `filter_projects()` return value (`query` vs. `(query, start_date, end_date)`), `q` search scope, `campaign` match mode (exact vs. substring), and multi-`tags` logic (`IN`/OR vs. `AND`) are left undecided.
* **Rationale & Recommendation:** Use coalesced effective bounds (`coalesce(start_date, date(created_at))` and `coalesce(end_date, start_date, date(created_at))`), preserve `target_wiki`, `"Other"` type, and `filter_projects_by_status()` flags, and lock the exact SQL expressions, return signature, and boolean modes.

### 6. Unspecified Phase 3 Wikimedia MinT Protocol, `POST /project/translate` Contract, & `Project.localized_field()` Signature - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** `Lines 413, 432-433, 490, 570, 593, 609`
* **Discrepancy Description:**
  * Neither the upstream MinT translation endpoint (`POST {MINT_API_URL}/translate/{src}/{tgt}` and payload/response keys) nor the internal `POST /project/translate` request/response schema, single-batch vs. multi-field behavior, numeric rate-limit quota/window/store, HTTP `401`/`403`/`429`/`502`/`504` JSON responses (without `@member_required` `302` redirect), `<= 10 KB` scope (per-field vs. total), `<meta name="csrf-token">` in `base.html`, or hidden form field name (`line 593`) are specified.
  * `Project.localized_field(field_name, target_lang)` (`line 433`) states it returns translated text *"alongside source language metadata"* (tuple/dict), contradicting Jinja usage `project.localized_field(..., report_lang)` (`line 570`), omits `"results_summary"`/`"results_notes"` nested lookup mapping to `Project.results`, and leaves `Project.to_dict(lang=...)` JSON keys (`line 432`) undefined.
* **Rationale & Recommendation:** Specify exact upstream and internal JSON schemas, rate-limit numbers/store, non-redirect JSON error codes, CSRF meta tag injection, exact `localized_field()` string/metadata signatures, and `to_dict()` translation keys.

### 7. `determine_project_status()` Divergence Breaks `tests/test_routes.py` & Leaves `"Canceled"` Overwrite in `api.py` - Severity: Blocker
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** `Lines 449, 489, 499`, `app/wiki_utils.py:174-225`, `app/routes/web.py:381-391, 466-476`, `app/routes/api.py:488-495`, `tests/test_routes.py:213-238`
* **Discrepancy Description:** `web.py` recalculates non-Canceled statuses from dates (which `tests/test_routes.py:220-237` asserts by posting `status="In Progress"` with future dates and expecting `Planned`), whereas `determine_project_status()` honors manual statuses and returns un-normalized strings. Meanwhile, `api.py:492-494` (`update_project`) passes `"auto"` when dates change without `status`, overwriting `"Canceled"` projects—and line 499 omits fixing it.
* **Rationale & Recommendation:** Update `api.py:492-494` to skip `"auto"` recalculation when `project.status` is `"Canceled"`/`"Cancelled"`, normalize `"Canceled"`/`"Cancelled"` inside `determine_project_status()`, and explicitly specify `web.py`'s date-derived calculation rule for non-Canceled forms.

### 8. Unresolved Decisions in Detailed Plan (`DELETION_REQUEST_URL`, `wiki_link` Rules, `/lang` Route, Purge Input) - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** `Lines 412-413, 447, 450, 476-477, 483, 490, 548, 628`
* **Discrepancy Description:**
  * `Config.DELETION_REQUEST_URL` (`lines 412, 548`) has no default value or empty-state UI fallback in `project_detail.html`.
  * `Config.ADMIN_USERS` and `SUPPORTED_LOCALES` omit format, Python types, defaults, and precedence relative to runtime `i18n/` directory scanning (`line 466`).
  * `validate_activity_wiki_url()` (`line 447` vs. `line 193` vs. `line 628`) leaves `http://` upgrade vs. rejection, root-URL empty path allowance, and `None` vs. `ValueError` error signaling undecided.
  * `sanitize_project_text_fields()` (`line 450`) uses an ellipsis instead of exact `tags`/`attributes` lists (note existing `_parse_results` in `web.py:280-281` calls `bleach.clean` without `tags=[]`), signature, and empty-title HTTP 400 behavior.
  * `POST /lang (or ?set_lang=)` (`line 490`) is undecided and `"lang"` is omitted from `RESERVED_SLUGS` (`line 483`).
  * `POST /admin/project/<id>/purge` (`line 476`) omits confirmation field name/rule (`ID` vs. `title`) and audit log target/schema; `POST /admin/admins/revoke` (`line 477`) leaves self-revocation ambiguous when other admins exist and omits CentralAuth failure status in `check_user()`.
* **Rationale & Recommendation:** Resolve every undecided option and unspecified parameter before implementation so zero design choices remain.

### 9. Missing `@app.context_processor`, Form 400 Preservation Contract, & `activities.html`/`filters.js` Implementation Gaps - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `Lines 422, 487-491, 521, 539-547, 584, 592`
* **Discrepancy Description:**
  * `web.py` routes (`create_project`, `edit_project`, `view_project`, `export_view`) do not pass `current_user` to `render_template()`, which will break `base.html`'s global `/admin` check (`line 521`) unless `app/__init__.py` registers an `@app.context_processor` injecting `current_user`. Also, `view_project()` and `create_project()` (`web.py:393, 507-514`) still bypass `get_current_user()`.
  * `community_activities()` (`web.py:170-199`) is not updated alongside `global_activities()` (`line 487`) to apply `filter_projects()` on SSR, `activities.html` crashes on `community.slug`/`community.name` when `community=None`, its filter inputs lack `name` attributes, its `#reset-filters` (`type="reset"`) will not clear SSR-bound values, and its modal lacks `#modal-wiki-link`, `#modal-campaign`, and `#modal-tags`.
  * `project_form.html` (`line 547`) defines no `form_data` fallback contract for HTTP 400 value retention; using `<input type="url">` on `wiki_link` blocks schemeless inputs before backend normalization; `filters.js` (`line 584`) does not specify how clicking SSR cards populates the modal or how sanitized HTML `description` renders safely without escaping markup via `.textContent`; and `chip-input.js` (`line 592`) does not specify async submit handling for `wikimedia_user` mode.
* **Rationale & Recommendation:** Specify `@app.context_processor`, `community_activities()` SSR filter parity, `activities.html` null-safe rendering/DOM IDs/reset button behavior, `form_data` fallback and `type="text"` on `wiki_link`, safe modal HTML allowlist rendering in `filters.js`, and `chip-input.js` sync/async submit rules.

### 10. `scripts/migrate_v3.py`, `seed_test.py`, `migrate_sqlite_to_mariadb.py`, & Admin Community Edit Gaps - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** `Lines 421, 475, 503-515`, `scripts/migrate_v2.py`, `seed_test.py:10-16`, `scripts/migrate_sqlite_to_mariadb.py:52-58`, `app/models.py:10-12, 37`
* **Discrepancy Description:**
  * Calling `create_app()` inside `migrate_v3.py` (modeled on `migrate_v2.py`) risks triggering the `MOCK_AUTH` guard on dev `.env` before migration; checking `get_indexes("project_tags")` on a stale `inspector` before table creation raises `NoSuchTableError`; raw `INSERT INTO users` requires explicit `is_member=0` (`User.is_member` has no SQL `DEFAULT`); and step 4 admin seeding must avoid emitting duplicate `actions` on repeat runs to satisfy idempotency assertions.
  * `seed_test.py:11` calls `Project.query.delete()`, which bypasses ORM cascade and leaves orphan `project_tags` rows unless `ProjectTag.query.delete()` runs first; `migrate_sqlite_to_mariadb.py` bypasses `create_app()` and misses `ensure_ascii=False` serializer setup; `create_app()` must merge `json_serializer` into `SQLALCHEMY_ENGINE_OPTIONS` across SQLite/test configs; and `sync_active_project_statuses()`'s trigger inside `sync_data.py` is omitted.
  * `POST /admin/community/<id>/edit` (`line 475`) omits `Community.name` uniqueness checks (`unique=True`), non-empty `name`/`slugify(slug)`/`meta_roster_page` validation, and custom-slug behavior in `POST /add-community`.
* **Rationale & Recommendation:** Use pure-engine inspection/DDL (`ProjectTag.__table__.create(checkfirst=True)`) in `migrate_v3.py`, add `ProjectTag.query.delete()` to `seed_test.py`, wire `sync_active_project_statuses()` into `sync_data.py:run_sync()`, merge `json_serializer` in `create_app()`, and validate community `name`/`slug` uniqueness and non-empty values.

### 11. `api.py` Serialization, Tag Partial Updates, & Streaming CSV Localization Gaps - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** `Lines 430, 432, 458, 498-501`, `app/routes/api.py:136, 278, 407, 551-748`, `tests/test_exports_v2.py:81-137`
* **Discrepancy Description:**
  * `api.py` (`list_projects`, `list_slug_project`, `get_project`) is not instructed to pass `current_user=get_current_user()` and `lang` to `Project.to_dict()` (with eager `joinedload`/`selectinload`), `PUT /api/projects/<id>` does not clarify omitted `"tags"` vs. `"tags": []` or `>20` tag limit handling, and `?paginated=1` omits envelope JSON keys and max `per_page`.
  * Streaming CSV routes (`stream_with_context`) must resolve `?lang=` eagerly before yielding, and `line 501` must specify localizing raw `p.status` and `p.project_type` cells in CSVs while keeping default Arabic outputs passing `tests/test_exports_v2.py`.
  * Phase 3 `Project.translations` mutations require fresh dict copies or `flag_modified` (`MutableDict`) so SQLAlchemy persists updates.
* **Rationale & Recommendation:** Specify `to_dict(current_user, lang)` call sites and eager loading, `PUT` tag semantics, paginated envelope schema, eager CSV locale binding, and `MutableDict`/copy assignment for `translations`.

### 12. Phase 2 `i18n` & Phase 3 Theme/RTL Implementation Gaps - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** `Lines 422, 451, 466-468, 524, 562, 569-570, 577, 584-586`
* **Discrepancy Description:**
  * `app/i18n.py` leaves `get_message(domain, ...)` vs. `_(key)` domain selection undefined (`ui` vs. `reports`); report templates call parameterless `{{ p.status_ar }}` and raw `{{ p.project_type }}` without `?lang=` (`report_lang`) override support; and client JS (`export.js`, `index.html`, `users.html`, `filters.js`) receives `window.ATHAR_I18N` with no client `$1` / CLDR `{{PLURAL:...}}` evaluation helper specified.
  * `app/static/js/export.js:245-261` embeds inline `#fafafa`/`#54595d` and `text-align: right` (missed in Item 21); `codex.style.css:1113` has asymmetric physical padding (`10px 40px 10px 36px`); `index.html:52` (`←`) and `dashboard.html:61` (`&larr;`) hardcode RTL arrows; and `charts.js` must read theme CSS variables on initial load (not only on `athar:themechange`).
* **Rationale & Recommendation:** Add `g.request_locale` or explicit `lang` parameter to `ar_type`/`ar_status` and report templates, specify a JS `atharI18n.t(key, ...args)` plural helper, migrate inline styles in `export.js` and directional padding/arrows in CSS/templates, and initialize `charts.js` colors from CSS variables on load.

### 13. Unmeasurable Verification Claims (`100%` / `19+`), Missing Verification Commands, & Vague Qualifiers - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** `Lines 417, 491, 505, 515, 524, 532, 555, 584, 622-631`
* **Discrepancy Description:**
  * Verification Plan (`lines 622-631`) asserts `"100% branch verification"` across `"all 19+ Project query touchpoints"` without naming those touchpoints or specifying coverage tooling; omits `python3 -m compileall app scripts` and required env vars for `create_app()` boot; omits `margin-left`, `padding-right`, and `translateX(-4px)` from CSS checks; omits reverse/orphan key and placeholder checks on `i18n` JSON files; omits explicit commands for `MOCK_AUTH` guard and `404` asset checks; and leaves E2E browser harness and Phase 1/3 form/MinT flows unspecified.
  * Detailed items repeatedly substitute subjective qualifiers (`"serialize cleanly"`, `"safely"`, `"tiny"`, `"concise guidance"`, `"clean Python syntax"`) for concrete behaviors.
* **Rationale & Recommendation:** Enumerate exact query touchpoints or specify `pytest --cov`, add exact CLI commands for syntax/CSS/i18n checks, define concrete E2E assertions per phase, and replace filler modifiers with verifiable implementation mechanics.

### 14. Inaccurate `"dependency order"` Claim, `app/routes/__init__.py` Ambiguity, & Minor Editorial Nits - Severity: Nit
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** `Lines 406, 422, 470, 508, 514, 524, 548-549, 559, 561, 569, 577, 584, 606-615`, `app/routes/__init__.py:1-37`, `dashboard.html:116`, `docs/designs/SITEMAP.md:6`
* **Discrepancy Description:**
  * Line 406 states files are in `"dependency order"` despite Phase 2 `app/i18n.py` preceding Phase 1 `admin.py` and `i18n/*.json` trailing templates; Item 8 marks `app/routes/__init__.py` (`Modify if needed`, containing an unused duplicate `create_app()`) ambiguously; `dashboard.html:116` already loads Chart.js; and `SITEMAP.md:6` already includes this design doc.
  * Missing minor specifics: `try/catch` around `localStorage` in `base.html`, `#export-lang` DOM ID in `export.html`/`export.js`, `prefers-color-scheme: dark` fallback in `<head>`, `sync_active_project_statuses()` call site in `sync_data.py:run_sync()`, and explicit Phase 1/2/3 edge-case tests in Item 24 (`MOCK_AUTH` RuntimeError, `oauth_callback` `is_member=False`, 400 form retention, Phase 3 localized exports).
* **Rationale & Recommendation:** Organize Target Files cleanly by Phase 1 -> Phase 2 -> Phase 3, decide `app/routes/__init__.py` disposition, reflect existing `dashboard.html` Chart.js and `SITEMAP.md` entry accurately, and add the missing edge-case test items and minor UI details.
