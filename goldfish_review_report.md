# Goldfish Annotated Review Report

**Status:** resolved  
**Target:** `docs/designs/multi_level_export_and_user_intelligence.md` (`full file`)

## Prioritized Findings & AI Suggestions

### Issue 1: Synchronous External CentralAuth Lookup in User Profile [`egm-design`] - Severity: High
*   **Affected Scope:** [Lines 206-207](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L206-L207) (`### 6. Contributor Profile Controller Logic`)
*   **Discrepancy Description:** The design specifies that if a requested username is not found in local storage, `GET /user/<username>` calls MediaWiki CentralAuth synchronously via `check_user` to validate whether the account exists on-wiki.
*   **Rationale:** Violates the Zero-External-Network Invariant, Goal 2, and Non-Goal 1. A synchronous outbound HTTP request during web request handling introduces high latency, risks Toolforge HTTP 504 reverse-proxy timeouts, and exhausts Gunicorn worker threads.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Athar is an internal tracking tool for regional affiliates. If a contributor is neither registered in local `User` rosters nor referenced in any `Project` roles, they have no Athar footprint; returning HTTP 404 immediately preserves sub-second performance and eliminates worker thread exhaustion.
*   ***Proposed Edit:***
    *   Location: `### 6. Contributor Profile Controller Logic` (Lines 206–207)
    *   Change: Replace synchronous CentralAuth validation with immediate HTTP 404:
        ```markdown
        2. **User Lookup:** Queries local `User.query.filter(func.lower(User.username) == username.lower()).first()`.
           * *If missing in User table:* Check if username appears in any `Project` role (`lead_organizer`, `co_organizers`, `jury_members`, or `participants`). If present in projects, render profile in unassociated affiliate state with project history. If completely absent from all local tables, immediately return HTTP 404 without external network queries.
        ```

### Issue 2: Monolithic Flat List of 19 Files Lacks Phased Checkpoints [`egm-implementation-readiness`] - Severity: High
*   **Affected Scope:** [Lines 285-429](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L285-L429) (`## Detailed Implementation Plan`)
*   **Discrepancy Description:** Lines 285–429 enumerate 19 target files in a single flat list without execution order, dependencies, intermediate testing milestones, or rollout phases.
*   **Rationale:** Violates the Implementation Readiness Standard. An unphased 19-file batch increases integration risk and makes rollback and incremental automated testing impossible.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Grouping implementation into 5 sequential phases with automated testing gates guarantees isolated verification of database models, ingestion jobs, controllers, CSV streaming, and print views.
*   ***Proposed Edit:***
    *   Location: `## Detailed Implementation Plan` (Lines 285–429)
    *   Change: Restructure the 19 files into 5 sequential phases with explicit automated testing checkpoints:
        *   **Phase 1: Domain Entities & Migration Tooling** (`app/models.py`, `scripts/migrate_v2.py`, `tests/test_migration.py`) — *Checkpoint: `./venv/bin/pytest tests/test_migration.py`*
        *   **Phase 2: Core Utilities & Ingestion Optimization** (`app/wiki_utils.py`, `app/query_utils.py`, `scripts/sync_data.py`) — *Checkpoint: `./venv/bin/pytest tests/test_sync.py`*
        *   **Phase 3: Presentation Routes & Form Handlers** (`app/routes/web.py`, `app/templates/project_form.html`, `app/templates/project_detail.html`, `app/templates/users.html`, reserved slug check) — *Checkpoint: `./venv/bin/pytest tests/test_routes.py`*
        *   **Phase 4: CSV Export Endpoints & Security** (`app/routes/api.py`, `tests/test_exports_v2.py`) — *Checkpoint: `./venv/bin/pytest tests/test_exports_v2.py`*
        *   **Phase 5: Print Architecture & Contributor Views** (`app/templates/reports/base_report.html`, `project_report.html`, `community_report.html`, `user_report.html`, `user_profile.html`, `export.html`, `app/static/js/export.js`, `tests/test_user_profile.py`) — *Checkpoint: `./venv/bin/pytest` (all suites pass)*

### Issue 3: Missing Evaluation of Denormalized JSON vs. Relational Junction Table [`egm-design`] - Severity: High
*   **Affected Scope:** [Lines 226-264](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L226-L264) (`## Alternatives Considered`)
*   **Discrepancy Description:** The design adopts `Project.participants` (`db.JSON`) and `Project.results` (`db.JSON`) without evaluating a normalized relational approach (e.g., a `project_participants` junction table).
*   **Rationale:** Data modeling choices have direct consequences on query indexing, write contention, referential integrity, and migration complexity across SQLite and MariaDB.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Documenting the trade-offs of denormalized `db.JSON` vs. normalized relational tables establishes clear architectural rationale based on Athar's low-concurrency write patterns and schema migration simplicity on Wikimedia ToolsDB.
*   ***Proposed Edit:***
    *   Location: `## Alternatives Considered` (insert after Line 263)
    *   Change: Add `### Alternative E: Normalized Relational Junction Table (ProjectParticipant)`:
        ```markdown
        ### Alternative E: Normalized Relational Junction Table (ProjectParticipant)
        * **Pros**:
          * Allows native SQL `JOIN` operations and standard database foreign key constraints.
          * Direct indexing on individual participant usernames in relational storage.
        * **Cons**:
          * Requires complex relational migrations and cascading deletion handling across existing SQLite and Toolforge MariaDB databases.
          * Increases write complexity and transaction overhead for simple volunteer edit forms.
          * Over-engineers a dataset where typical project participant rosters range between 5 and 50 usernames.
        * **Reason for Rejection**: Storing participant lists and competition podium summaries as lightweight denormalized JSON columns (`Project.participants` and `Project.results`) matches Athar's existing schema patterns (such as `StatSnapshot.wiki_breakdown`), provides maximum schema flexibility, and enables safe idempotent DDL migrations on Toolforge without multi-table relational lock contention.
        ```

### Issue 4: Undefined CSV Column Schemas for Level 1 and Level 3 Exports [`egm-implementation-readiness`] - Severity: High
*   **Affected Scope:** [Lines 164-171](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L164-L171) (`### 4. Symmetrical Dual-Tier Routing Matrix`) and [Lines 324-331](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L324-L331) (`#### 5. app/routes/api.py`)
*   **Discrepancy Description:** The design outlines the routing matrix for Level 1 and Level 3 CSV exports but fails to document the exact localized header strings and column mappings.
*   **Rationale:** Developers cannot implement or test CSV streaming generators without deterministic column specifications.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Explicit column schemas ensure consistent, localized CSV output compatible with spreadsheet applications across all user locales.
*   ***Proposed Edit:***
    *   Location: `### 4. Symmetrical Dual-Tier Routing Matrix`
    *   Change: Add exact localized column definitions:
        *   **Level 1 (Single Project Participant Roster CSV):**
            `["اسم المستخدم", "الدور في النشاط", "عنوان النشاط", "المشروع المستهدف", "تاريخ البدء", "تاريخ الانتهاء"]`
        *   **Level 3 (Contributor History CSV):**
            `["معرف النشاط", "عنوان النشاط", "المجتمع التابع له", "الدور", "الحالة", "المشروع المستهدف", "تاريخ البدء", "تاريخ الانتهاء"]`

### Issue 5: Missing Dedicated "Risks & Mitigations" Section [`egm-design`] - Severity: Medium
*   **Affected Scope:** [Line 283](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L283) (between `## Non-Functional Requirements` and `## Detailed Implementation Plan`)
*   **Discrepancy Description:** The design document lacks a dedicated `## Risks & Mitigations` section analyzing operational hazards on Toolforge.
*   **Rationale:** Required by EGM design standards to account for operational edge cases (API rate limits, memory spikes, database connection drops, volunteer data entry anomalies).
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Documenting concrete mitigation strategies prevents production outages on Toolforge.
*   ***Proposed Edit:***
    *   Location: Insert before `## Detailed Implementation Plan`
    *   Change: Add section:
        ```markdown
        ## Risks & Mitigations

        | Risk | Impact | Mitigation Strategy |
        | :--- | :--- | :--- |
        | **Wikimedia CentralAuth API Rate-Limiting (HTTP 429)** | Ingestion job stalls or fails during background updates. | Deduplicate all usernames into a single global set across affiliates before polling; enforce a minimum 4-hour `last_synced` freshness threshold. |
        | **Toolforge MariaDB Connection Drops** | HTTP 500 errors during long-running streaming or cron runs. | Enable SQLAlchemy pool recycling (`pool_recycle=280`, `pool_pre_ping=True`) in database configuration. |
        | **Worker Memory Spikes during Large CSV Exports** | Toolforge Linux OOM kills Gunicorn worker processes. | Use Flask `stream_with_context` with generator yield chunks instead of loading entire datasets into `io.StringIO` buffers. |
        | **Malformed Volunteer Inputs in Results/Participants** | Application crashes or corrupted JSON during rendering. | Strip surrounding whitespace, normalize MediaWiki underscores, enforce structured HTML sub-inputs, and sanitize text with `bleach.clean()`. |
        ```

### Issue 6: Ingestion Pipeline & Contributor Identity Disconnect [`egm-critic`] - Severity: Medium
*   **Affected Scope:** [Line 221](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L221) (`### 7. Security & Ingestion Hardening`) and [Lines 381-386](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L381-L386) (`#### 15. scripts/sync_data.py`)
*   **Discrepancy Description:** `scripts/sync_data.py` only queues usernames from affiliate community member rosters (`CommunityMember`), omitting contributors who participate in affiliate projects but are not on formal affiliate rosters.
*   **Rationale:** Project participants without formal roster membership would never have CentralAuth statistics fetched, leaving their profiles devoid of edit counts.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Expanding username discovery in `scripts/sync_data.py` to union community rosters with project organizers and participants ensures complete data coverage without redundant API requests.
*   ***Proposed Edit:***
    *   Location: `### 7. Security & Ingestion Hardening` and `#### 15. scripts/sync_data.py`
    *   Change: Specify that `scripts/sync_data.py` discovers unique usernames by combining `User` roster records with all distinct usernames in `Project.lead_organizer`, `Project.co_organizers`, `Project.jury_members`, and `Project.participants`. In `sync_community()`, skip querying CentralAuth if `user.last_synced` is within the last 4 hours.

### Issue 7: Cross-Dialect JSON Query Divergence Across SQLite & MariaDB [`egm-implementation-readiness`] - Severity: Medium
*   **Affected Scope:** [Lines 212-215](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L212-L215) (`### 6. Contributor Profile Controller Logic`)
*   **Discrepancy Description:** Querying JSON list membership (`participants`, `co_organizers`, `jury_members`) via native SQL JSON functions differs between MariaDB (`JSON_CONTAINS`) and SQLite (`json_each`), risking test suite crashes.
*   **Rationale:** Athar uses SQLite for local development/automated unit tests and MariaDB 10.x for Toolforge production. Raw SQL JSON queries will break SQLite test runs.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Because regional affiliate project counts are modest (<10,000 records), filtering candidate projects in Python memory is fast (<5ms), perfectly portable across SQL dialects, and 100% test-compatible.
*   ***Proposed Edit:***
    *   Location: `### 6. Contributor Profile Controller Logic` (Line 213)
    *   Change: Specify in-memory Python filtering on candidate projects:
        ```python
        # Fetch candidate projects (optionally pre-filtered by date or affiliate)
        candidate_projects = Project.query.order_by(Project.start_date.desc()).all()
        # In-memory cross-dialect Python role resolution:
        user_projects = [
            p for p in candidate_projects
            if username == p.lead_organizer
            or (p.co_organizers and username in p.co_organizers)
            or (p.jury_members and username in p.jury_members)
            or (p.participants and username in p.participants)
        ]
        ```

### Issue 8: Undefined Form Field Names & Deserialization for `Project.results` [`egm-implementation-readiness`] - Severity: Medium
*   **Affected Scope:** [Lines 147-163](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L147-L163) (`#### Project.results Data Contract`) and [Line 321](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L321) (`#### 4. app/routes/web.py`)
*   **Discrepancy Description:** The design describes `Project.results` conceptually but omits the exact HTML `name` attributes and request parsing rules.
*   **Rationale:** Ambiguous form field names lead to template/controller naming mismatches during implementation.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Explicit input naming guarantees seamless integration between Jinja2 form templates and Flask request handlers.
*   ***Proposed Edit:***
    *   Location: `#### Project.results Data Contract` (Lines 161–163)
    *   Change: Document exact HTML input names:
        *   `results_summary`: Textarea for executive summary (`bleach.clean(request.form.get('results_summary', ''))`).
        *   `results_winners`: Textarea for winning usernames, parsed line-by-line / comma-separated into `List[str]`.
        *   `results_articles_created`: Integer input (`int(request.form.get('results_articles_created') or 0)`).
        *   `results_articles_improved`: Integer input (`int(request.form.get('results_articles_improved') or 0)`).
        *   `results_files_uploaded`: Integer input (`int(request.form.get('results_files_uploaded') or 0)`).
        *   `results_notes`: Textarea for jury comments and observations (`bleach.clean(...)`).

### Issue 9: Omission of `app/static/js/export.js` from File Scope [`egm-codebase-details`] - Severity: Medium
*   **Affected Scope:** [Lines 287-411](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L287-L411) (`## Detailed Implementation Plan`)
*   **Discrepancy Description:** The design modifies `app/templates/export.html` to add printable executive reports, but omits `app/static/js/export.js`, which manages the interactive date filter controls and dynamic export URL generation.
*   **Rationale:** The report button on the export page must dynamically pass active date filters (`year`, `month`, `custom`) to the report route (`/<slug>/report?year=...`).
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Adding `app/static/js/export.js` to the target file list ensures the print report button stays synchronized with the active date filter dropdowns.
*   ***Proposed Edit:</a>
    *   Location: Add to `## Detailed Implementation Plan` under Phase 5
    *   Change: Add `app/static/js/export.js` (Modify): Update JavaScript event listeners on filter dropdowns to dynamically update both the CSV download href and the Printable Executive Report href with matching query parameters.

### Issue 10: Standardize API Route Naming & Clean Marketing Buzzwords [`egm-style`] - Severity: Medium
*   **Affected Scope:** [Lines 164-171](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L164-L171) (`### 4. Symmetrical Dual-Tier Routing Matrix`) and [Lines 13, 27](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L13)
*   **Discrepancy Description:** Route naming contains inconsistent pluralization (`/api/projects/...` vs `/api/user/...`), and the text uses inflated promotional language ("contributor intelligence", "dual-tier reporting architecture").
*   **Rationale:** REST APIs should follow consistent plural resource conventions (`/api/users/<username>/export`), and technical designs should use objective engineering terminology.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Aligning routes to `/api/users/<username>/export` improves API consistency, and plain technical framing improves clarity.
*   ***Proposed Edit:***
    *   Location: Table in `### 4. Symmetrical Dual-Tier Routing Matrix` and `#### 5. app/routes/api.py`
    *   Change: Standardize API endpoint to `GET /api/users/<string:username>/export?format=csv` (with redirect/alias from `/api/user/...` for compatibility). Replace marketing buzzwords with direct descriptions (e.g., "3 export scopes across 2 formats: tabular CSV and printable HTML").

### Issue 11: Document Template Context Variable Contracts [`egm-implementation-readiness`] - Severity: Medium
*   **Affected Scope:** [Lines 339-358](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L339-L358) (`#### 7`, `#### 8`, `#### 9`, `#### 10` in `Detailed Implementation Plan`)
*   **Discrepancy Description:** The design enumerates new Jinja2 templates without documenting the expected context variables passed by Flask controllers.
*   **Rationale:** Template authors and route implementers need an agreed data interface to prevent missing variable errors during rendering.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Documenting context contracts clarifies the interface between `web.py` and Jinja2 templates.
*   ***Proposed Edit:***
    *   Location: `#### 7` through `#### 10` in `Detailed Implementation Plan`
    *   Change: Explicitly list context variables:
        *   `project_report.html`: `{"project": Project, "community": Community, "auto_print": bool}`
        *   `community_report.html`: `{"community": Community, "projects": List[Project], "stats": Dict, "filter_label": str, "auto_print": bool}`
        *   `user_report.html`: `{"user": User, "snapshot": StatSnapshot, "top_wikis": List[Tuple[str, int]], "projects_by_role": Dict[str, List[Project]], "auto_print": bool}`
        *   `user_profile.html`: `{"user": User, "snapshot": StatSnapshot, "top_wikis": List[Tuple[str, int]], "projects_by_role": Dict[str, List[Project]], "communities": List[Community], "last_synced_relative": str}`

### Issue 12: Complete CSV Formula Injection Sanitization [`egm-design`] - Severity: Low
*   **Affected Scope:** [Lines 219, 269, 311](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L219)
*   **Discrepancy Description:** CSV formula escaping checks if string begins with `=`, `+`, `-`, `@`, `\t`, `\r`, but does not strip leading whitespace first, and omits the pipe operator (`|`).
*   **Rationale:** Attackers can bypass naive startswith checks by prepending spaces (e.g., `"   =cmd|..."`) or using pipe commands in specific spreadsheet versions.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Calling `.lstrip()` before checking trigger characters (`=`, `+`, `-`, `@`, `|`, `\t`, `\r`) closes injection vectors.
*   ***Proposed Edit:***
    *   Location: `### 7. Security & Ingestion Hardening` and `#### 3. app/query_utils.py`
    *   Change: Update sanitization logic:
        ```python
        def sanitize_csv_cell(value: Any) -> Any:
            if not isinstance(value, str):
                return value
            stripped = value.lstrip()
            if stripped and stripped[0] in ("=", "+", "-", "@", "|", "\t", "\r"):
                return "'" + value
            return value
        ```

### Issue 13: Multi-Page Table Print Overflow Caused by Container `break-inside` [`egm-design`] - Severity: Low
*   **Affected Scope:** [Line 191](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L191) (`### 5. Universal HTML Print Architecture`)
*   **Discrepancy Description:** `break-inside: avoid !important;` is applied to `.report-table`. If a project or member table spans more than one A4 page, browsers will push the entire table to a new page or clip rows exceeding page height.
*   **Rationale:** Container elements spanning multiple pages must allow page breaks between child rows, while individual rows (`tr`) should avoid breaks.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Removing `break-inside: avoid` from `.report-table` allows smooth multi-page table pagination while keeping individual rows intact.
*   ***Proposed Edit:***
    *   Location: `### 5. Universal HTML Print Architecture` (Line 191)
    *   Change: In print CSS, replace `.report-card, .report-table, tr, .kpi-tile` with:
        ```css
        .report-card, tr, .kpi-tile {
            break-inside: avoid !important;
            page-break-inside: avoid !important;
        }
        ```

### Issue 14: Display Factual Sync Timestamp Instead of Speculative Projections [`egm-zoom-out`] - Severity: Low
*   **Affected Scope:** [Lines 25, 211, 357](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L25)
*   **Discrepancy Description:** The design specifies displaying a projected "next sync time (`last_synced + 4 hours`)", which is speculative if cron runs are delayed or queued.
*   **Rationale:** Displaying estimated future sync times risks confusing users if crons do not execute at that exact minute. Factual elapsed time is honest and sufficient.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Showing factual elapsed time ("تم التحديث قبل ساعة واحدة") based directly on `StatSnapshot.recorded_at` provides clarity without false precision.
*   ***Proposed Edit:***
    *   Location: `## Goals`, `### 6. Contributor Profile Controller Logic`, and `#### 10. app/templates/user_profile.html`
    *   Change: Simplify badge to show factual elapsed time: "آخر تحديث: قبل X ساعات/دقائق" (computed from `StatSnapshot.recorded_at` or `User.last_synced`).

### Issue 15: Missing XTools User URL Helper in `app/wiki_utils.py` [`egm-codebase-details`] - Severity: Low
*   **Affected Scope:** [Lines 307-313](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L307-L313)
*   **Discrepancy Description:** The design relies on outbound links to XTools on the user profile, but does not specify a reusable helper to construct these links.
*   **Rationale:** External URLs should be constructed centrally to avoid template string concatenation bugs.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Adding `build_xtools_user_url(wiki_domain, username)` to `app/wiki_utils.py` centralizes URL encoding and formatting.
*   ***Proposed Edit:</a>
    *   Location: Add `app/wiki_utils.py` (Modify) in Phase 2
    *   Change: Implement helper `build_xtools_user_url(wiki_code: str, username: str) -> str` returning `f"https://xtools.wmcloud.org/ec/{wiki_code}/{quote(username)}"`.

### Issue 16: Remove Metaconversational Artifacts and Acronyms [`egm-style`] - Severity: Low
*   **Affected Scope:** [Line 39](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L39) (`## Open Questions`) and [Lines 426-428](file:///home/bonnjalal/Documents/Athar/docs/designs/multi_level_export_and_user_intelligence.md#L426-L428) (document footer)
*   **Discrepancy Description:** The document includes conversational meta-notes ("Goldfish brainstorm", "*Drafted with EGM*").
*   **Rationale:** Production engineering design documents should remain clean, professional, and free of conversational agent artifacts.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:** Stripping meta-comments maintains document cleanliness and professional quality.
*   ***Proposed Edit:***
    *   Location: `## Open Questions` and document footer
    *   Change: Set `## Open Questions` to "None." and remove lines 426–428 entirely.

