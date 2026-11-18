# Goldfish Review Report — Stage 7: Critic Review (Feature Spec)

**Target:** `docs/designs/platform_redesign_i18n_and_admin_governance.md` (`1-401`)
**Standard:** `/home/bonnjalal/.gemini/config/plugins/egm/resources/document_standards/feature-spec-standard.md`

## Reviewer Status

| Reviewer | Status |
| :--- | :--- |
| `egm-design` | completed |
| `egm-structural` | completed |
| `egm-style` | completed |

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. Missing Mandatory `Risks & Mitigations` Section & Quantified Limits - Severity: Blocker
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Affected Scope:** `Lines 368-400` (`## Non-Functional Requirements`)
* **Discrepancy Description:** `feature-spec-standard.md` mandates explicit coverage of architectural risks, failure modes, scalability ceilings, and mitigations (`## Risks & Mitigations`). `FeatureRange` (`lines 1-401`) omits this section entirely. Critical operational risks remain absent or unconsolidated: Toolforge 4-worker concurrency ceilings, MinT upstream unavailability and stale-translation drift / HTML distortion, daemon thread termination on Gunicorn worker recycle (`_async_sync_community`), `Community.projects` `cascade="all, delete-orphan"` hard-delete exposure, and client JS lacking automated test coverage.
* **Rationale & Recommendation:** Add a dedicated `## Risks & Mitigations` table (`Risk | Impact | Mitigation Strategy`) after `## Non-Functional Requirements` detailing failure modes, quantitative limits, and explicit mitigations across all three phases.

### 2. Cookie-Authenticated Mutations Left Under `csrf.exempt(api_bp)` - Severity: Blocker
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** `Line 373` (and `app/__init__.py:47`, `app/routes/api.py:81-85, 280-283, 409-412`)
* **Discrepancy Description:** The specification preserves `csrf.exempt(api_bp)` while expanding `POST /api/<slug>/projects` and `PUT /api/projects/<id>` to accept `wiki_link`, `campaign`, `tags`, and Phase 3 `translations` (HTML), and granting Tool Admins cross-project write permissions via `@project_editor_required`. Because `api_bp` authenticates solely via Flask session cookies (`get_request_data()` also accepts form submissions), leaving mutations exempt from CSRF tokens exposes Admin and project writes to cross-site request forgery.
* **Rationale & Recommendation:** Remove `csrf.exempt(api_bp)` (or require explicit CSRF token validation on all session-authenticated mutating `POST`/`PUT` endpoints on `api_bp` and pass `X-CSRFToken` from client scripts).

### 3. Multi-Worker MinT Rate Limiting & Sync-Worker Starvation Risk - Severity: Blocker
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Affected Scope:** `Lines 284-286`, `Line 379`, `Lines 222-223`, `Procfile:1`, `app/routes/web.py:102-103, 242-254`
* **Discrepancy Description:** Lines 286 and 379 specify a `"session rate limit"` and 6-hour in-memory language cache, yet `Procfile` runs `gunicorn -w 4` synchronous workers without shared Redis/Memcached. Cookie-backed Flask `session` counters can be bypassed by replaying pre-request cookies, while in-worker memory grants 4x burst capacity and resets on recycle. Additionally, lines 284–286 omit numeric rate limits, time windows, and single-request batching across the 4 translatable fields (`title`, `description`, `results_summary`, `results_notes`), meaning concurrent translations (`timeout=10`, up to 40s per click) or synchronous `POST /<slug>/sync` / `daemon=True` roster threads can exhaust all 4 Gunicorn workers and trigger Toolforge 504 timeouts.
* **Rationale & Recommendation:** Define a database-persisted or shared rate-limit counter with explicit numeric quotas/windows, mandate coalesced single-request multi-field translation for MinT, and move blocking/daemon roster syncs off Gunicorn request workers.

### 4. Ambiguous Soft-Delete Query Boundary (`active_projects_query()` vs. Optional `do_orm_execute`) - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** `Line 231` (`Global Active-Project Query Boundary`), `Line 214`
* **Discrepancy Description:** Line 231 makes registering a global SQLAlchemy `do_orm_execute` filter optional while relying on `execution_options(include_deleted=True)` in `/admin`. If `do_orm_execute` is omitted, legacy `Project.query.get_or_404()`, `db.session.get(Project, ...)`, `db.session.query(func.count(Project.id))` (`slug_Stat`), and `community.projects` relationship loads leak soft-deleted projects unless replaced everywhere. Conversely, if `do_orm_execute` is used, SQLAlchemy 2.0 `select()` statements are needed in `/admin` and `Community.projects` (`cascade="all, delete-orphan"`) still requires protection against cascading hard deletes.
* **Rationale & Recommendation:** Commit to one non-optional soft-delete query mechanism, mandate a shared active-lookup helper across `@project_editor_required` and every route/API/sync site, and remove/guard hard cascade deletion on `Community.projects`.

### 5. RBAC Contradictions (`ADMIN_USERS` vs. DB Revocation), Non-Member Admin Lockout, and `MOCK_AUTH` Guard Exceptions - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`, `egm-style`
* **Affected Scope:** `Lines 172, 188, 210-214, 228, 373`
* **Discrepancy Description:**
  * **Split-brain admin precedence:** Line 213 instructs `oauth_callback()` not to re-promote admins demoted in the DB *"unless configured as locked bootstrap admins (`Bonnjalal00`)"*, yet `User` has only one boolean `is_admin` column (`line 172`), no locked-admin config key exists, and no flag distinguishes a demoted admin from an unpromoted one.
  * **Non-member Admin lockout:** Non-rostered Admins are provisioned with `is_member=False` (`lines 188, 213`), and line 214 updates `@project_editor_required` to allow `is_admin`, yet `POST /project/translate` (`line 286`), `POST /<slug>/sync` (`line 214`), and project creation routes require `@member_required` without allowing `is_admin` pass-through.
  * **`MOCK_AUTH` test exception & username collation:** Lines 211 and 373 forbid `MOCK_AUTH=True` when `FLASK_DEBUG` is false or `OAUTH_CLIENT_ID` is set without mentioning the `TESTING=True` exemption (breaking tests that inherit `.env`). SQLite case-sensitive `UNIQUE` vs. MariaDB `utf8mb4` case-insensitive collation also needs normalization cleanup in `migrate_v3.py`.
* **Rationale & Recommendation:** Use `Config.ADMIN_USERS` strictly as an initial seed/bootstrap (or explicitly add a separate immutable `LOCKED_ADMINS` list), grant `is_admin` pass-through on `@member_required`, document the `TESTING=True` exception on `MOCK_AUTH` consistently, and normalize legacy `users.username` values during migration.

### 6. Blueprint Coupling, Layering Leaks (`Project.to_dict`), & Architecture Diagram Mismatches - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** `Lines 116-166`, `Lines 216-227`, `Line 256`, `Line 286`
* **Discrepancy Description:**
  * `line 216` leaves blueprint placement indecisive (`app/routes/admin.py or admin_bp`) and places `POST /add-community` in `admin_bp` (`line 222`), while `app/routes/web.py` (`web_bp`) still absorbs global `/activities`, `/healthz`, locale switching, and Phase 3 `POST /project/translate` alongside its existing 871 lines. CentralAuth user lookup (`/api/check-user helper`, `line 227`) also sits inline inside an `api_bp` route handler.
  * Placing `can_edit` inside `Project.to_dict()` (`line 256`) couples ORM models to request authorization, and serializing `community_name`/`community_slug`/`tags` triggers `2N+1` lazy queries without mandatory eager loading.
  * The Mermaid diagram (`lines 116-166`) collapses `web_bp + admin_bp`, mislabels report paths as `/report/*`, omits `ApiBP --> WikiSvc`, leaves `MinTProxy` disconnected from `WebBP`/`WikiSvc`, and omits `scripts/sync_data.py`.
* **Rationale & Recommendation:** Extract Wikimedia HTTP clients (MinT, CentralAuth) into dedicated service helpers, clarify `POST /add-community` blueprint ownership, move `can_edit` evaluation into a shared auth helper, and align the Mermaid diagram with actual module paths and edges.

### 7. Unbounded Queries, N+1 Loops, & Uncapped `translations` Bloat - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** `Lines 241-256`, `Lines 280-281`, `Lines 377-378`
* **Discrepancy Description:** Global `GET /activities`, `/<slug>/activities`, and default `GET /api/projects` lack pagination; `GET /` (`line 241`) omits `selectinload(Project.tags_rel)` while displaying tags (`line 244`); existing `StatSnapshot` N+1 loops in `dashboard`/`/<slug>/stats` and full-table `Project.query.all()` scans in `user_profile`/`user_report`/`export_view` remain unaddressed; and `Project.translations` (up to 20 languages of rich HTML) has no total serialized byte cap or column `defer()` on summary list queries.
* **Rationale & Recommendation:** Mandate pagination on `/activities`, mandate `joinedload(Project.community)` + `selectinload(Project.tags_rel)` + `defer(Project.translations)` on summary/list queries, cap total `translations` payload size (e.g., `<= 64 KB`), and eliminate `StatSnapshot` N+1 loops and `export_view` full-table scans.

### 8. Contradictory `wiki_link` / `meta_roster_page` Validation & Faulty Date-Overlap Logic - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`, `egm-style`
* **Affected Scope:** `Lines 47, 193-194, 222-223, 248-255, 372`
* **Discrepancy Description:**
  * `wiki_link` rules contradict across the spec: `L193` normalizes `http://` to `https://`, while `L372` hedges (`rejects http:// (upgrading or rejecting cleanly)`) and `L194` rejects `"missing path"` (breaking valid root URLs like `https://eventmetrics.wmcloud.org`). Backslash smuggling (`\`) and `meta_roster_page` URL validation (`community_nav.html:8`) are also omitted.
  * Date-overlap SQL `(start_date IS NULL OR start_date <= period_end) AND (end_date IS NULL OR end_date >= period_start)` (`line 255`) returns `TRUE` for any year when `end_date` is `NULL` or when both dates are `NULL` (breaking `created_at` fallback), `extract('month', ...)` column target is unspecified, `target_wiki` filtering is missing from `filter_projects()`, `"campaign"` match mode (exact vs. substring) and `"IN/AND"` tag semantics are undecided, and `q` description matching (`"where needed"`) is ambiguous.
* **Rationale & Recommendation:** Lock one deterministic `wiki_link` `http://` rule and allow empty root paths; validate `meta_roster_page`; use coalesced effective dates (`COALESCE(end_date, start_date, date(created_at))`) for overlap filtering; preserve `target_wiki` filtering; and specify exact `campaign`, `q`, and multi-tag (`AND` vs `OR`) behavior.

### 9. Phase 2 & 3 Underspecified Contracts: `i18n` Switching, JS Pluralization, MinT HTML Mode, & `filters.js` Rendering - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`, `egm-style`
* **Affected Scope:** `Lines 64, 237, 265-271, 280-287, 371, 379`
* **Discrepancy Description:**
  * `line 269` leaves `DEFAULT_LOCALE` ambiguous (`"ar" initially or "en" per config`), `/lang` is missing from `RESERVED_SLUGS` (`line 237`), `Project.project_type_ar` and `Project.status_ar` model properties (`app/models.py:130-138`) are unaddressed for `?lang=` report overrides, and client JS plural evaluation (`{{PLURAL:$1|...}}`) and non-`ar`/`en` CLDR plural extensibility are omitted.
  * `POST /project/translate` does not specify HTML vs. plain-text handling for `description` or numeric MinT rate-limit thresholds (`lines 64, 286, 379`); `api.py` lacks `Project.results` schema/sanitization parity; and `filters.js` bans `.innerHTML` (`line 371`) without specifying how whitelisted HTML descriptions render safely inside `#project-details-modal`.
* **Rationale & Recommendation:** Fix `DEFAULT_LOCALE = "ar"` (with `"en"` key fallback), unify `Project.*_ar` properties with `app/i18n.py`, specify client JS plural formatting, specify MinT HTML mode and exact rate-limit quotas, validate `results` in `api.py`, and specify safe allowlist DOM rendering in `filters.js`.

### 10. Non-Transactional MariaDB DDL, `Community.slug` Edit Edge Cases, & H2/H3 Hierarchy Violation - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Affected Scope:** `Lines 184-188, 223, 385-400`
* **Discrepancy Description:**
  * `with engine.begin()` (`line 184`) cannot roll back MariaDB DDL statements (`ALTER TABLE`, `CREATE TABLE`), which implicitly commit; safety depends on per-statement inspection and verification.
  * `Community.slug` editing (`line 223`) relies on `slugify()` (`web.py:33-38`), which allows Arabic `\w` characters and returns `""` on punctuation-only inputs; empty-slug rejection, column max lengths (`slug <= 64`, `name <= 120`, `meta_roster_page <= 255`), and cross-user stale `session['community_slug']` handling are unspecified.
  * `### Additional Resources` (`line 387`) and `### Future Improvements` (`line 394`) appear after a section divider `---` (`line 385`) as H3 headings instead of H2, nesting them improperly inside `## Non-Functional Requirements`.
* **Rationale & Recommendation:** Document MariaDB implicit-commit migration handling, enforce `[a-z0-9-]` and max-length checks on `Community.slug` edits, and promote `Additional Resources` and `Future Improvements` to `##` (H2) headings.

### 11. Terminology Misuse ("Stewards", "Tool Admin", "Commons-style") & Vague Scope Phrasing - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** `Lines 13, 15, 31, 55-57, 64, 85, 106, 221-226, 284`
* **Discrepancy Description:**
  * Uses Wikimedia `"stewards"` (`line 31`) instead of `"administrators"`, introduces `"Tool Admins"` without distinguishing in-app database roles from Toolforge shell maintainers, and uses `"Commons-style"` without describing the UI component.
  * Uses open-ended scope phrasing (`"full community editing"`, `"bounded preview"` without repeating the 6-item cap, `"active project quick-moderation links"`, `"logs structured audit line"` without specifying `app.logger` vs. DB, `"matching project ID/title"` ambiguity, and `"load cleanly"`).
* **Rationale & Recommendation:** Replace misleading Wikimedia terms, define `"Tool Admin"` on first use, and replace subjective phrases with exact field lists, numeric caps, log targets, and verifiable acceptance criteria.

### 12. Security Hygiene, Formatting Symmetry, Portable Links, & Style Nits - Severity: Nit
* **Reviewer Lens:** `egm-design`, `egm-structural`, `egm-style`
* **Affected Scope:** `Lines 27, 35, 39, 49, 72, 78, 91, 95, 101, 171-292, 335, 355-356, 371-396`
* **Discrepancy Description:**
  * `bleach.clean` on `description` omits adding `rel="noopener noreferrer"` on external `<a>` links; `projects` lacks composite index `(is_deleted, status, start_date)` for `GET /`; `DELETION_REQUEST_URL` needs explicit hide/fallback behavior when unset; and `export.js` (`getFilterDescriptionText()`) + RTL arrows (`index.html:52`, `dashboard.html:61`) should be explicitly covered in Phase 2.
  * `lines 171-292` use 1-space list markers and 2-space indents vs. 3-space markers and 4-space indents elsewhere; `lines 389-392` use machine-local `file://` links instead of relative repo paths; `line 35` counts `"four JavaScript files"` instead of three standalone JS files plus inline template scripts; and repeated filler adverbs (`"strictly"`, `"cleanly"`, `"lightweight"`), marketing/SPA jargon (`"CTA"`, `"SSR"`, `"lego strings"`, `"FOUC"`), and unqualified latency claims (`"sub-second"` vs. `"<500ms"` without dataset scale) weaken technical precision.
* **Rationale & Recommendation:** Add `rel="noopener noreferrer"` link callback and `(is_deleted, status, start_date)` index, standardize list indentation and relative links, and strip filler modifiers and jargon in favor of measurable plain-English criteria.
