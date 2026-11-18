# Consolidated EGM Design Review Report

**Target Document:** [`docs/designs/platform_redesign_i18n_and_admin_governance.md`](file:///home/bonnjalal/Documents/Athar/docs/designs/platform_redesign_i18n_and_admin_governance.md) (`Lines 1-635`; `FeatureRange: 1-401`, `DetailedRange: 402-635`)
**Date:** 2026-11-16
**Review Mode:** Uninterrupted Full Flow (`Stages 5 -> 6 -> 7 -> 8 -> 9`)

## Stage & Reviewer Execution Status

| Stage | Rubric / Standard | Reviewers | Status | Report File |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 5** | Initial Zoom Out (`zoom-out-standard.md`) | `egm-zoom-out` | completed | [zoom_out_report.md](file:///home/bonnjalal/Documents/Athar/zoom_out_report.md) |
| **Stage 6** | Comprehension Test (Paraphrase + Self-Containment) | `egm-comprehension` | completed | [comprehension_report.md](file:///home/bonnjalal/Documents/Athar/comprehension_report.md) |
| **Stage 7** | Critic Review (`feature-spec-standard.md`) | `egm-design`, `egm-structural`, `egm-style` | completed | [critic_report.md](file:///home/bonnjalal/Documents/Athar/critic_report.md) |
| **Stage 8** | Intermediate Zoom Out (`zoom-out-standard.md`) | `egm-zoom-out` | completed | [intermediate_zoom_out_report.md](file:///home/bonnjalal/Documents/Athar/intermediate_zoom_out_report.md) |
| **Stage 9** | Implementation Readiness (`implementation-readiness-standard.md`) | `egm-implementation-readiness`, `egm-codebase-details`, `egm-style` | completed | [implementation_readiness_report.md](file:///home/bonnjalal/Documents/Athar/implementation_readiness_report.md) |

---

## Consolidated Action Items (Prioritized by Severity)

### 🔴 Blockers (Must Resolve Before Implementation)

#### `B1` — Contradictory Soft-Delete Boundary (`do_orm_execute` vs. `active_projects_query()` vs. Raw Queries)
* **Stages / Lenses:** Stage 5 (`egm-zoom-out`), Stage 6 (`egm-comprehension`), Stage 7 (`egm-structural`), Stage 8 (`egm-zoom-out`), Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`)
* **Affected Scope:** `Lines 230-232, 415-433, 457, 474, 488, 498, 514` (`app/oauth.py:116`, `app/routes/api.py:178-192, 522`, `app/models.py:19`)
* **Discrepancy:** Line 231 marks SQLAlchemy `do_orm_execute` *"optional"*, yet Item 8 (`line 474`) uses `execution_options(include_deleted=True)` while Items 2–3 never register `do_orm_execute`. Without `do_orm_execute`, `Project.query.get_or_404()` in `@project_editor_required` (`app/oauth.py:116`), raw `db.session.query()` in `slug_Stat()` (`api.py:178-192`), and `db.session.get()` in `export_project_csv()` (`api.py:522`) leak soft-deleted rows. Furthermore, line 488 filters `view_project`/`edit_project` with `active_projects_query()` while saying only non-admins get 404.
* **Actionable Remediation:** Remove the optional `do_orm_execute` / `execution_options` dual mechanism and commit to explicit `active_projects_query()` + `get_active_project_or_404()` across every route, API endpoint, `@project_editor_required`, `slug_Stat()`, CSV export, report, and `sync_data.py` (enumerating all query sites); clarify explicitly whether Admins can view/edit soft-deleted projects prior to restoring them; and guard `Community.projects` (`cascade="all, delete-orphan"`) against unintended cascade deletion.

#### `B2` — Contradictory Admin RBAC Precedence (`ADMIN_USERS` vs. DB Revocation) & Non-Member Admin Lockout
* **Stages / Lenses:** Stage 5 (`egm-zoom-out`), Stage 6 (`egm-comprehension`), Stage 7 (`egm-design`, `egm-structural`, `egm-style`), Stage 8 (`egm-zoom-out`), Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`, `egm-style`)
* **Affected Scope:** `Lines 172, 188, 210-214, 228, 349, 412, 439-441, 477, 490` (`app/oauth.py`, `app/models.py`, `config.py`)
* **Discrepancy:** Line 213 asks `oauth_callback()` not to re-promote DB-demoted admins unless they are "locked bootstrap admins", while line 441 instructs decorators to check DB `is_admin` *"plus `Config.ADMIN_USERS`"* on every request—which makes env-listed admins impossible to revoke via `POST /admin/admins/revoke`. Additionally, `User` has only one `is_admin` boolean (no demoted/locked state), `bootstrap_admins` is undefined, and non-rostered Admins provisioned with `is_member=False` hit HTTP 403 on `@member_required` endpoints (`POST /project/translate`, `POST /<slug>/sync`, `/project/new`).
* **Actionable Remediation:** Treat `Config.ADMIN_USERS` (comma-separated `set[str]`) strictly as initial seed/bootstrap data (`migrate_v3.py`, `seed_test.py`, and new-user insert in `oauth_callback()`) and use database `User.is_admin` as the sole runtime authorization authority; grant `is_admin` pass-through inside `@member_required`; replace `"upsert missing"` with `"insert missing"`; and document the full existing and new RBAC matrix (`anonymous`, `non-member`, `member`, `organizer`, `admin`).

#### `B3` — Missing Incremental Phase Partitioning & Unchecked Phase-Boundary Coupling (`/healthz`)
* **Stages / Lenses:** Stage 5 (`egm-zoom-out`), Stage 8 (`egm-zoom-out`), Stage 9 (`egm-implementation-readiness`)
* **Affected Scope:** `Lines 237, 404-631` (especially Item 9 `line 490`, Item 24, `Verification Plan`)
* **Discrepancy:** Lines 404–616 group work into one mixed file list combining Phase 1, Phase 2, and Phase 3 changes inside shared files with only one end-of-plan verification section. Item 9 (`line 490`) also adds an unrequested `GET /healthz` endpoint checking `i18n/` JSON files in Phase 1 before `i18n/` exists in Phase 2.
* **Actionable Remediation:** Reorganize `Detailed Implementation Plan` into three explicit incremental sections (Phase 1, Phase 2, Phase 3), each listing only its phase-scoped file edits and concluding with a mandatory verification checkpoint (`pytest` command + schema/asset assertions), and drop `GET /healthz` in favor of startup/test validation.

#### `B4` — `MOCK_AUTH` Startup Guard Conflicts with `.env.example`, `config.py`, `run.py`, & Existing Tests
* **Stages / Lenses:** Stage 7 (`egm-design`), Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`)
* **Affected Scope:** `Lines 211, 373, 419, 439-441` (`config.py`, `run.py`, `.env.example`, `tests/test_routes.py`)
* **Discrepancy:** Line 419 raises `RuntimeError` if `MOCK_AUTH=True` when `FLASK_DEBUG` is false or `OAUTH_CLIENT_ID` is set (omitting `TESTING=True` in FeatureRange lines 211/373). In the repository, `config.py` has no `FLASK_DEBUG`/`DEBUG` attribute, `.env.example` sets `DEBUG=True` alongside `MOCK_AUTH=True` and placeholder `OAUTH_CLIENT_ID=your-meta-client-id-here`, and `run.py` calls `create_app()` before `app.run(debug=True)`. Moreover, removing cookie `session["is_member"]` trust breaks 7 existing `tests/test_routes.py` tests unless `User` rows are seeded and `TestConfig` sets `MOCK_AUTH = False`.
* **Actionable Remediation:** Read both `DEBUG` and `FLASK_DEBUG` in `config.py`, ignore placeholder `OAUTH_CLIENT_ID` strings (and update `.env.example`), consistently exempt `TESTING=True` across the spec, clarify `get_current_user()`/decorator behavior under `MOCK_AUTH=True`, set `MOCK_AUTH = False` in `TestConfig`, and list exact `tests/test_routes.py` fixture updates.

#### `B5` — Cookie-Authenticated API Mutations Left Under `csrf.exempt(api_bp)`
* **Stages / Lenses:** Stage 7 (`egm-design`)
* **Affected Scope:** `Lines 373, 420` (`app/__init__.py:47`, `app/routes/api.py:81-85, 280-283, 409-412`)
* **Discrepancy:** Preserving `csrf.exempt(api_bp)` leaves cookie-authenticated `POST /api/<slug>/projects` and `PUT /api/projects/<id>` (which now accept `wiki_link`, `campaign`, `tags`, `translations`, and Admin cross-project writes) unprotected against CSRF.
* **Actionable Remediation:** Remove `csrf.exempt(api_bp)` (or exempt only `GET` routes / enforce CSRF validation on session-authenticated `POST`/`PUT` API mutations with `X-CSRFToken` sent by client scripts).

#### `B6` — Broken Date-Overlap Formula & Underspecified `filter_projects()` Contract
* **Stages / Lenses:** Stage 6 (`egm-comprehension`), Stage 7 (`egm-design`, `egm-structural`, `egm-style`), Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`)
* **Affected Scope:** `Lines 248-255, 459-460, 497` (`app/query_utils.py`, `app/routes/api.py`, `tests/test_api.py`, `app/static/js/filters.js`)
* **Discrepancy:** The overlap formula `(start_date IS NULL OR start_date <= period_end) AND (end_date IS NULL OR end_date >= period_start)` drops `created_at` fallback when dates are `NULL`—causing `tests/test_api.py:259-261` (`year=1999`) to falsely return `self.p2` (`start_date=None, end_date=None`) and matching 2025 projects with `end_date=None` in 2026. Unifying `api.py` onto `filter_projects()` also omits existing `target_wiki` filtering (`tests/test_api.py:147-151`), `"Other"` custom-type filtering, `filter_projects_by_status()` inclusion flags, `month`-only column targeting, return tuple signature, `q` fields, `campaign` match mode, and `IN`/`AND` tag semantics.
* **Actionable Remediation:** Compute overlap via coalesced effective bounds (`effective_start = coalesce(start_date, date(created_at))`, `effective_end = coalesce(end_date, start_date, date(created_at))`), preserve `target_wiki`, `"Other"` type, and `filter_projects_by_status()` flags, and specify exact `month`-only expression, return type, `q` scope, `campaign` matching, and multi-tag (`AND` vs `OR`) operator.

#### `B7` — Phase 3 MinT API Protocol, Multi-Worker Rate Limiting & `Project.localized_field()` Contract Gaps
* **Stages / Lenses:** Stage 5 (`egm-zoom-out`), Stage 6 (`egm-comprehension`), Stage 7 (`egm-design`, `egm-structural`, `egm-style`), Stage 8 (`egm-zoom-out`), Stage 9 (`egm-implementation-readiness`, `egm-style`)
* **Affected Scope:** `Lines 64, 222-223, 280-287, 355-356, 379, 413, 432-433, 490, 549, 570, 593, 609` (`Procfile:1`, `app/routes/web.py:102-103, 242-254`)
* **Discrepancy:** Upstream MinT endpoint (`POST {MINT_API_URL}/translate/{src}/{tgt}`), HTML/plain-text handling, coalesced single-request schema on `POST /project/translate`, `<meta name="csrf-token">`, HTTP error codes, and `Project.localized_field()` / `Project.to_dict(lang=...)` return shapes (including `results_summary`/`results_notes` nested key mapping) are unspecified. In addition, a cookie-backed Flask `session` rate limit is bypassable by cookie replay across 4 Gunicorn workers, and `POST /add-community` / `POST /<slug>/sync` risk worker starvation via `daemon=True` threads and synchronous CentralAuth loops.
* **Actionable Remediation:** Lock exact MinT upstream and `POST /project/translate` coalesced JSON schemas, server-side per-user cooldown (lightweight DB timestamp/counter rather than Redis/cookies), HTTP `401`/`403`/`429`/`502`/`504` JSON responses, exact `localized_field()` string/metadata signatures, and `to_dict()` keys; for roster sync on add/edit, run only the single Meta-Wiki roster parse (`timeout=15`) and leave bulk CentralAuth stats to `jobs.yaml` cron (removing `force=True` on `manual_sync`).

#### `B8` — `determine_project_status()` Divergence Breaks `tests/test_routes.py` & Leaves `"Canceled"` Overwrite in `api.py`
* **Stages / Lenses:** Stage 8 (`egm-zoom-out`), Stage 9 (`egm-codebase-details`, `egm-implementation-readiness`)
* **Affected Scope:** `Lines 200, 449, 489, 499` (`app/wiki_utils.py`, `app/routes/web.py`, `app/routes/api.py`, `tests/test_routes.py`)
* **Discrepancy:** `web.py` recalculates non-`Canceled` statuses from dates (explicitly asserted in `tests/test_routes.py:220-237`), whereas `determine_project_status()` honors manual statuses and returns un-normalized strings, and `api.py:492-494` (`update_project`) still passes `"auto"` when dates change without `status`, overwriting `"Canceled"` projects.
* **Actionable Remediation:** Skip `"auto"` recalculation in `api.py:492-494` when `project.status in ("Canceled", "Cancelled")`, normalize `"Canceled"`/`"Cancelled"` in `determine_project_status()`, and preserve `web.py`'s date-derived calculation for non-`Canceled` submissions while unifying input parsing across `web.py` and `api.py`.

#### `B9` — Missing `Risks & Mitigations` Section & Unresolved Zero-Decision Choices
* **Stages / Lenses:** Stage 6 (`egm-comprehension`), Stage 7 (`egm-design`, `egm-structural`, `egm-style`), Stage 8 (`egm-zoom-out`), Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`, `egm-style`)
* **Affected Scope:** `Lines 47, 78, 193-194, 210, 232, 269, 368-400, 412-413, 447, 450, 476-477, 483, 490, 548, 628`
* **Discrepancy:** `FeatureRange` omits a mandatory `## Risks & Mitigations` section; `Config.DELETION_REQUEST_URL` default/empty UI behavior is unresolved; `wiki_link` validation contradicts between normalizing vs. rejecting `http://`, rejects empty root paths (`eventmetrics.wmcloud.org`), and omits `ValueError` vs. `None` error signaling; `sanitize_project_text_fields()` uses an ellipsis instead of `tags=[], attributes={}`; `POST /lang (or ?set_lang=)` is undecided and `"lang"` is missing from `RESERVED_SLUGS`; purge confirmation (`ID` vs. `title`) and audit log destination (`app.logger` schema) are undefined; and self-revocation / CentralAuth failure handling in `check_user()` are ambiguous.
* **Actionable Remediation:** Add a concise `## Risks & Mitigations` table in `FeatureRange`, and lock concrete defaults, rules, schemas, and field names for every undecided item above before implementation.

---

### 🟡 Majors (Design, Ergonomic & Maintainability Improvements)

#### `M1` — Dual SSR + CSR Activity Pipeline on `/activities` & Form/Modal Gaps
* **Stages / Lenses:** Stage 5 (`egm-zoom-out`), Stage 6 (`egm-comprehension`), Stage 7 (`egm-structural`), Stage 8 (`egm-zoom-out`), Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`)
* **Affected Scope:** `Lines 247-257, 283, 371, 487, 535-547, 584, 592` (`activities.html`, `filters.js`, `project_form.html`)
* **Discrepancy:** Maintaining both server-rendered cards (`activities.html`) and JS-rebuilt cards/modals (`filters.js`) causes drift, breaks SSR `GET` parity on `community_activities()`, fails on `community=None` (`activities.html:3,6`), lacks `name` attributes and working `#reset-filters` semantics, and creates a conflict between banning `.innerHTML` vs. rendering Bleach-sanitized HTML descriptions in `#modal-project-description`. Separately, `project_form.html` needs a `form_data` fallback for HTTP 400 retention, `type="text"` on `wiki_link` so schemeless inputs reach backend normalization, and defined async/sync submit behavior in `chip-input.js`.
* **Actionable Remediation:** Simplify `/activities` and `/<slug>/activities` to standard `GET` form submission onto server-rendered Jinja cards linking to `/project/<id>` (eliminating the redundant CSR card/modal builder in `filters.js`), or explicitly specify every SSR/CSR parity contract, `activities.html` guards/DOM IDs, and allowlist `DOMParser` modal rendering alongside `form_data` retention and `chip-input.js` submit semantics.

#### `M2` — Over-Engineered `banana-i18n` Domain Split, Plural Rules & `?lang=` Template Overrides
* **Stages / Lenses:** Stage 5 (`egm-zoom-out`), Stage 6 (`egm-comprehension`), Stage 7 (`egm-design`, `egm-structural`, `egm-style`), Stage 8 (`egm-zoom-out`), Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`)
* **Affected Scope:** `Lines 261-272, 413, 422, 432-433, 451, 462-468, 569-570, 584-586, 596-600`
* **Discrepancy:** Splitting ~60–100 static strings into `i18n/ui/*.json` and `i18n/reports/*.json` duplicates shared types/statuses/roles and conflicts with `_(key, *args)` vs. `get_message(domain, ...)`. `DEFAULT_LOCALE` is stated ambiguously at line 269, `qqq` exclusion is omitted from FeatureRange, report templates call parameterless `{{ p.status_ar }}` (ignoring `?lang=en`), and dynamic JS counts receive raw `{{PLURAL:$1|...}}` strings with no JS runtime specified.
* **Actionable Remediation:** Merge into one `i18n/{en,ar,qqq}.json` bundle per locale, lock `DEFAULT_LOCALE = "ar"`, exclude `qqq` from locales, invoke `i18n.py` directly with `report_lang` instead of 4-layer `*_ar` wrappers, support CLDR plural lookup for future locales, and specify a JS helper (`@wikimedia/banana-i18n` or `Intl.PluralRules`).

#### `M3` — Blueprint Ownership Split, ORM/RBAC Coupling & Missed Codebase Reuse
* **Stages / Lenses:** Stage 5 (`egm-zoom-out`), Stage 6 (`egm-comprehension`), Stage 7 (`egm-structural`, `egm-style`), Stage 8 (`egm-zoom-out`), Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`)
* **Affected Scope:** `Lines 116-166, 216-227, 256, 422, 432, 470, 484, 490, 498, 510-515, 521`
* **Discrepancy:** `POST /add-community` is placed in `admin_bp` (`line 222`) yet modified in `web.py` (`line 484`); `?paginated=1` on `/api/projects` has no UI caller; `Project.to_dict(current_user=..., lang=...)` couples `models.py` to RBAC/presentation; `@app.context_processor` for `current_user` is missing (`base.html` fails on `create_project`/`view_project`); `migrate_sqlite_to_mariadb.py` already handles dynamic tables via `db.metadata`; the Mermaid diagram mislabels `/report/*` and omits edges; and existing reuse opportunities (`latest_snapshots` subquery in `community_report`, shared `web.py`/`api.py` project payload validation, `is_allowed_wikimedia_host()`, `check_user` CentralAuth helper with `Config.USER_AGENT`, `normalize_meta_page_title()`) are missed.
* **Actionable Remediation:** Consolidate Admin routes in `admin_bp`, drop `?paginated=1`, remove `migrate_sqlite_to_mariadb.py` edits, register `@app.context_processor` for `current_user`, evaluate `can_edit` in `app/oauth.py` rather than `models.py`, extract/reuse the 5 existing helpers above, and update the Mermaid diagram.

#### `M4` — Unbounded Queries, Missing Eager Loading & Uncapped `Project.translations` Serialization
* **Stages / Lenses:** Stage 7 (`egm-design`), Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`)
* **Affected Scope:** `Lines 241-256, 280-281, 377-378, 430, 432, 458, 498-501`
* **Discrepancy:** List endpoints lack `selectinload(Project.tags_rel)` + `joinedload(Project.community)` + `defer(Project.translations)`, `export_view` scans `Project.query.all()` for years, `Project.translations` lacks per-field length caps (Phase 3), `sync_project_tags()` leaves `PUT` partial-update and `>20` tag handling undefined, `translations` mutations need `MutableDict`/copy assignment, and CSV `stream_with_context` generators must bind `?lang=` eagerly and localize raw `p.status`/`p.project_type`.
* **Actionable Remediation:** Mandate eager loading and `defer(Project.translations)` on list queries, cap per-field translation character lengths, replace `export_view` full scan with `SELECT DISTINCT`, define `sync_project_tags()` `PUT`/overflow semantics, use `MutableDict`/copies, and bind CSV `?lang=` before streaming.

#### `M5` — Non-Transactional MariaDB DDL, `migrate_v3.py` / `seed_test.py` Traps & Community Edit Validation
* **Stages / Lenses:** Stage 7 (`egm-design`, `egm-structural`), Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`)
* **Affected Scope:** `Lines 184-188, 222-223, 421, 475, 503-515` (`scripts/migrate_v2.py`, `seed_test.py`, `scripts/sync_data.py`)
* **Discrepancy:** MariaDB DDL commits implicitly (ignoring `engine.begin()` rollback); invoking `create_app()` in `migrate_v3.py` risks premature startup hook failures; raw SQL table/admin inserts risk `NoSuchTableError` on stale `inspector`, missing `InnoDB`/`utf8mb4` parity, missing `is_member=0`, or duplicate idempotency `actions`; `seed_test.py:11` bulk `Project.query.delete()` leaves orphan `project_tags`; `create_app()` must merge `json_serializer` into `SQLALCHEMY_ENGINE_OPTIONS`; `sync_active_project_statuses()`'s trigger inside `sync_data.py` is unstated; and community add/edit lacks `Community.name` uniqueness, `[a-z0-9-]` non-empty `slug`, and `meta_roster_page` URL validation.
* **Actionable Remediation:** Use pure-engine inspection (`ProjectTag.__table__.create(checkfirst=True)`), explicit `is_member=0` inserts, and silent no-op idempotency in `migrate_v3.py`; delete `ProjectTag` rows first in `seed_test.py`; merge `json_serializer` in `create_app()`; call `sync_active_project_statuses()` inside `sync_data.py:run_sync()`; and validate community `name`, `[a-z0-9-]` `slug`, and `meta_roster_page`.

#### `M6` — Phase 3 Inline Style / RTL / Chart.js Initial Theme & H2/H3 Hierarchy Violations
* **Stages / Lenses:** Stage 7 (`egm-structural`), Stage 9 (`egm-codebase-details`)
* **Affected Scope:** `Lines 385-400, 561-586` (`app/static/js/export.js:245-261`, `codex.style.css:1113`, `index.html:52`, `dashboard.html:61`)
* **Discrepancy:** `### Additional Resources` and `### Future Improvements` (`lines 387, 394`) are H3 headings nested under `## Non-Functional Requirements` instead of H2. Additionally, `export.js:245-261` embeds inline `#fafafa` / `text-align: right` styles, `codex.style.css:1113` uses asymmetric physical padding, `index.html:52` (`←`) and `dashboard.html:61` (`&larr;`) hardcode RTL arrows, and `charts.js` must read theme CSS variables on initial load (not only on `athar:themechange`).
* **Actionable Remediation:** Promote lines 387 and 394 to `##`, move `export.js` preview styling into CSS classes, convert line 1113 padding and template arrows to logical/direction-aware styling, and read theme tokens on `charts.js` initialization.

#### `M7` — Terminology Precision ("Stewards", "Tool Admin", "Commons-style") & Unexplained Legacy Symbols
* **Stages / Lenses:** Stage 6 (`egm-comprehension`), Stage 7 (`egm-style`)
* **Affected Scope:** `Lines 13, 15, 31, 39, 49, 55-57, 64, 72, 85, 106, 196, 205, 221-226, 284, 484, 499`
* **Discrepancy:** Uses `"stewards"` (`line 31`) instead of `"administrators"`, leaves `"Tool Admin"` and `"Commons-style"` undefined relative to Wikimedia Toolforge terminology, blurs browser print-to-PDF vs. server PDF, references `pending_community_*`, `create_projetct`, `target_wiki_url`, and `/api/check-user` without brief explanations, and uses open-ended scope phrasing (`"full community editing"`, `"load cleanly"`).
* **Actionable Remediation:** Define `"Tool Admin"` on first use, replace `"stewards"` and `"Commons-style"`, clarify browser `@media print` PDF workflow, add brief context for referenced legacy symbols, and specify exact moderation links and acceptance criteria.

#### `M8` — Unmeasurable Verification Claims (`100%` / `19+`) & Missing Verification Commands
* **Stages / Lenses:** Stage 7 (`egm-style`), Stage 9 (`egm-style`)
* **Affected Scope:** `Lines 355-356, 377, 417, 491, 505, 515, 524, 532, 555, 584, 622-631`
* **Discrepancy:** `Verification Plan` claims `"100% branch verification"` across `"19+ Project query touchpoints"` without listing touchpoints or coverage commands, omits `python3 -m compileall app scripts`, omits env vars for `create_app()` boot verification, skips `margin-left`/`padding-right`/`translateX(-4px)` in CSS checks and reverse-key/placeholder checks in `i18n` validation, lacks explicit E2E assertions across Phases 1–3, and uses subjective modifiers (`"cleanly"`, `"safely"`, `"tiny"`, `"sub-second"` without dataset scale).
* **Actionable Remediation:** Replace unmeasurable claims with concrete `pytest --cov` / enumerated checks, exact CLI verification commands, objective E2E assertions per phase, and precise engineering wording.

---

### 🟢 Nits (Polish & Minor Hygiene)

#### `N1` — Security & Schema Polish (`rel="noopener noreferrer"`, Composite Index, `"Cancelled"` Filter Normalization)
* **Stages / Lenses:** Stage 6 (`egm-comprehension`), Stage 7 (`egm-design`)
* **Affected Scope:** `Lines 200, 241, 254, 283`
* **Remediation:** Append `rel="noopener noreferrer"` on `<a>` tags in `bleach.clean` link callback, add `(is_deleted, status, start_date)` composite index in `migrate_v3.py`, and handle `"Canceled"`/`"Cancelled"` uniformly in `filter_projects()`.

#### `N2` — Missed Existing Reuse (`is_allowed_wikimedia_host()`, `dashboard.html` Chart.js, Already-Registered `SITEMAP.md`)
* **Stages / Lenses:** Stage 5 (`egm-zoom-out`), Stage 8 (`egm-zoom-out`), Stage 9 (`egm-codebase-details`)
* **Affected Scope:** `Lines 447, 522, 561, 615` (`dashboard.html:116`, `docs/designs/SITEMAP.md:6`)
* **Remediation:** Parameterize `is_allowed_wikimedia_host(hostname, allowed_domains=...)`; delete duplicate Chart.js only from `base.html:11` (already loaded in `dashboard.html:116`); note `SITEMAP.md` already includes this entry.

#### `N3` — Dead Duplicate Factory in `app/routes/__init__.py` & Target File Ordering
* **Stages / Lenses:** Stage 9 (`egm-codebase-details`, `egm-implementation-readiness`, `egm-style`)
* **Affected Scope:** `Lines 406, 470` (`app/routes/__init__.py:1-37`)
* **Remediation:** Decide explicitly whether to clean up or leave untouched the unused duplicate `create_app()` in `app/routes/__init__.py`, and fix the `"dependency order"` claim by grouping Target Files by Phase 1 -> Phase 2 -> Phase 3.

#### `N4` — Altitude Drops (Weeds), Cross-Section Repetition, & Markdown Formatting / Portable Links
* **Stages / Lenses:** Stage 5 (`egm-zoom-out`), Stage 7 (`egm-structural`), Stage 8 (`egm-zoom-out`)
* **Affected Scope:** `Lines 35, 44-65, 170-293, 370-392, 408-615`
* **Remediation:** Keep `Goals` and `NFRs` at contract altitude without repeating regexes/DDL strings; standardize `*   ` and 4-space list indentation across `lines 171-292`; convert `Additional Resources` links to relative repo paths; and fix `"four JavaScript files"` on line 35 (`three standalone JS files plus inline template scripts`).

#### `N5` — Open Questions vs. Plan Alignment & Minor UI/Test Edge Cases
* **Stages / Lenses:** Stage 6 (`egm-comprehension`), Stage 9 (`egm-implementation-readiness`, `egm-style`)
* **Affected Scope:** `Lines 78-79, 226, 396, 422, 524, 548-555, 569, 606-609`
* **Remediation:** Align Open Question #2 (`line 79`) with the chosen Phase 1 behavior (`no redirect + warning note`); add `localStorage` `try/catch` and `prefers-color-scheme` fallback notes (`line 524`), `#export-lang` DOM ID, `ar_type`/`ar_status` filter signatures (`line 422`), and explicit Phase 1/2/3 edge-case tests in Item 24.

#### `N6` — Plain-English Style & Minor Terminology Nits
* **Stages / Lenses:** Stage 7 (`egm-style`), Stage 9 (`egm-style`)
* **Affected Scope:** `Lines 27, 35, 40, 49, 53, 55, 61, 65, 91, 95, 101, 204, 244, 257, 335, 371`
* **Remediation:** Replace `"lego strings"`, `"SSR"`, `"CTA"`, `"FOUC"`, `"Patchwork"`, and `"Hygiene"` with direct technical terms, strip filler adverbs (`"strictly"`, `"cleanly"`, `"harmlessly"`), keep CUJs free of internal schema phrasing, and align `project_type` examples.

---

## Traceability Matrix

| Raw Finding ID | Stage & Reviewer | Consolidated Item |
| :--- | :--- | :--- |
| `S5-1` | Stage 5 `egm-zoom-out` #1 | `B1` |
| `S5-2` | Stage 5 `egm-zoom-out` #2 | `M1` |
| `S5-3` | Stage 5 `egm-zoom-out` #3 | `M2` |
| `S5-4` | Stage 5 `egm-zoom-out` #4 | `B2` |
| `S5-5` | Stage 5 `egm-zoom-out` #5 | `B3`, `M3` |
| `S5-6` | Stage 5 `egm-zoom-out` #6 | `B7`, `M3` |
| `S5-7` | Stage 5 `egm-zoom-out` #7 | `N2` |
| `S5-8` | Stage 5 `egm-zoom-out` #8 | `N4` |
| `S6-1` | Stage 6 `egm-comprehension` #1 | `B2` |
| `S6-2` | Stage 6 `egm-comprehension` #2 | `B2`, `B7` |
| `S6-3` | Stage 6 `egm-comprehension` #3 | `B9` |
| `S6-4` | Stage 6 `egm-comprehension` #4 | `B1`, `B7` |
| `S6-5` | Stage 6 `egm-comprehension` #5 | `B6`, `M1` |
| `S6-6` | Stage 6 `egm-comprehension` #6 | `M2` |
| `S6-7` | Stage 6 `egm-comprehension` #7 | `B9`, `M3`, `M7` |
| `S6-8` | Stage 6 `egm-comprehension` #8 | `B9`, `N1`, `N5` |
| `S7-1` | Stage 7 `critic` #1 (`egm-design`, `egm-structural`) | `B9` |
| `S7-2` | Stage 7 `critic` #2 (`egm-design`) | `B5` |
| `S7-3` | Stage 7 `critic` #3 (`egm-design`, `egm-structural`) | `B7` |
| `S7-4` | Stage 7 `critic` #4 (`egm-structural`) | `B1` |
| `S7-5` | Stage 7 `critic` #5 (`egm-design`, `egm-structural`, `egm-style`) | `B2`, `B4` |
| `S7-6` | Stage 7 `critic` #6 (`egm-structural`, `egm-style`) | `M3` |
| `S7-7` | Stage 7 `critic` #7 (`egm-design`) | `M4` |
| `S7-8` | Stage 7 `critic` #8 (`egm-design`, `egm-structural`, `egm-style`) | `B6`, `B9`, `M5` |
| `S7-9` | Stage 7 `critic` #9 (`egm-design`, `egm-structural`, `egm-style`) | `B7`, `M1`, `M2` |
| `S7-10` | Stage 7 `critic` #10 (`egm-design`, `egm-structural`) | `M5`, `M6` |
| `S7-11` | Stage 7 `critic` #11 (`egm-style`) | `B9`, `M7` |
| `S7-12` | Stage 7 `critic` #12 (`egm-design`, `egm-structural`, `egm-style`) | `M8`, `N1`, `N4`, `N6` |
| `S8-1` | Stage 8 `egm-zoom-out` #1 | `B2`, `B7`, `B9` |
| `S8-2` | Stage 8 `egm-zoom-out` #2 | `M1` |
| `S8-3` | Stage 8 `egm-zoom-out` #3 | `B1`, `M3` |
| `S8-4` | Stage 8 `egm-zoom-out` #4 | `M2` |
| `S8-5` | Stage 8 `egm-zoom-out` #5 | `B3`, `M3` |
| `S8-6` | Stage 8 `egm-zoom-out` #6 | `B8`, `M3`, `N2` |
| `S8-7` | Stage 8 `egm-zoom-out` #7 | `N4` |
| `S9-1` | Stage 9 `impl_readiness` #1 (`egm-implementation-readiness`) | `B3` |
| `S9-2` | Stage 9 `impl_readiness` #2 (`egm-implementation-readiness`, `egm-codebase-details`) | `B4` |
| `S9-3` | Stage 9 `impl_readiness` #3 (`egm-implementation-readiness`, `egm-codebase-details`, `egm-style`) | `B2` |
| `S9-4` | Stage 9 `impl_readiness` #4 (`egm-implementation-readiness`, `egm-codebase-details`) | `B1` |
| `S9-5` | Stage 9 `impl_readiness` #5 (`egm-implementation-readiness`, `egm-codebase-details`) | `B6` |
| `S9-6` | Stage 9 `impl_readiness` #6 (`egm-implementation-readiness`, `egm-style`) | `B7` |
| `S9-7` | Stage 9 `impl_readiness` #7 (`egm-codebase-details`, `egm-implementation-readiness`) | `B8` |
| `S9-8` | Stage 9 `impl_readiness` #8 (`egm-implementation-readiness`, `egm-codebase-details`, `egm-style`) | `B9` |
| `S9-9` | Stage 9 `impl_readiness` #9 (`egm-implementation-readiness`, `egm-codebase-details`) | `M1`, `M3` |
| `S9-10` | Stage 9 `impl_readiness` #10 (`egm-codebase-details`, `egm-implementation-readiness`) | `M5` |
| `S9-11` | Stage 9 `impl_readiness` #11 (`egm-codebase-details`, `egm-implementation-readiness`) | `M4` |
| `S9-12` | Stage 9 `impl_readiness` #12 (`egm-codebase-details`, `egm-implementation-readiness`) | `M2`, `M6` |
| `S9-13` | Stage 9 `impl_readiness` #13 (`egm-style`) | `M8` |
| `S9-14` | Stage 9 `impl_readiness` #14 (`egm-codebase-details`, `egm-implementation-readiness`, `egm-style`) | `N2`, `N3`, `N5`, `N6` |
