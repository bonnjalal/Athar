# Implementation Readiness Review Report

**Target:** `docs/designs/multi_level_export_and_user_intelligence.md` (Lines 285–429)  
**Standard:** `resources/document_standards/implementation-readiness-standard.md`  
**Reviewers:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`

## Prioritized Findings

### 1. Total Omission of Phasing and Checkpoints
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Severity:** 🔴 Blocker
* **Affected Scope:** Lines 285–429
* **Description:** The plan presents an unphased flat list of 19 files without incremental sequence, dependency ordering, or intermediate buildable/testable checkpoints.
* **Recommendation:** Restructure the implementation plan into 5 sequential phases with explicit verification checkpoints:
  * **Phase 1: Domain Entities & Migration** (`app/models.py`, `scripts/migrate_v2.py`, `tests/test_migration.py`) -> Checkpoint: Run migration tests.
  * **Phase 2: Core Utilities & Ingestion Optimization** (`app/wiki_utils.py`, `scripts/sync_data.py`) -> Checkpoint: Run query normalization and sync tests.
  * **Phase 3: Presentation Routes & Form Handlers** (`app/routes/web.py`, form templates, reserved slug protection) -> Checkpoint: Run route and profile tests.
  * **Phase 4: CSV Export Endpoints & Security** (`app/routes/api.py`, `tests/test_exports_v2.py`) -> Checkpoint: Run CSV export and formula escaping tests.
  * **Phase 5: Print Architecture & Contributor Views** (Report templates, `user_profile.html`, `app/static/js/export.js`, `tests/test_user_profile.py`) -> Checkpoint: Run full regression suite and verify print layout.

### 2. Undefined CSV Column Schemas for Level 1 and Level 3
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Severity:** 🔴 Blocker
* **Affected Scope:** Lines 328–329
* **Description:** The plan specifies that `GET /api/projects/<int:project_id>/export?format=csv` streams a participant roster and `GET /api/user/<string:username>/export?format=csv` streams project history, but specifies zero column headers or row structures.
* **Recommendation:** Define the exact list of localized Arabic string headers:
  * Level 1 CSV: `["اسم المستخدم", "الدور في النشاط", "عنوان النشاط", "المشروع المستهدف", "تاريخ البدء", "تاريخ الانتهاء"]`.
  * Level 3 CSV: `["معرف النشاط", "عنوان النشاط", "المجتمع التابع له", "الدور", "الحالة", "المشروع المستهدف", "تاريخ البدء", "تاريخ الانتهاء"]`.

### 3. Missing Cross-Dialect JSON Query Strategy Across SQLite & MariaDB
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Severity:** 🟡 Major
* **Affected Scope:** Line 213, Line 317
* **Description:** Querying membership across `co_organizers`, `jury_members`, and `participants` in SQLite (in-memory pytest) vs MariaDB (ToolsDB) requires different SQL functions (`json_each` vs `JSON_CONTAINS`).
* **Recommendation:** Pre-determine the querying strategy: fetch candidate projects by community or year, then execute in-memory Python filtering:
  ```python
  [p for p in candidate_projects if username == p.lead_organizer or username in (p.co_organizers or []) or username in (p.jury_members or []) or username in (p.participants or [])]
  ```

### 4. Missing Form Input Names and Deserialization Spec for `Project.results`
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Severity:** 🟡 Major
* **Affected Scope:** Lines 321, 373–374
* **Description:** The plan does not specify the exact HTML form input `name` attributes for the structured results sub-fields, nor template fallback handling when `project.results` is `None`.
* **Recommendation:** Document exact input names: `results_summary`, `results_winners`, `results_articles_created`, `results_articles_improved`, `results_files_uploaded`, `results_notes`. In `web.py`, parse and cast integer metrics safely with zero defaults and Bleach sanitization.

### 5. Omission of `app/static/js/export.js` from File Scope
* **Reviewer Lens:** `egm-codebase-details`
* **Severity:** 🟡 Major
* **Affected Scope:** Lines 376–380
* **Description:** Filter state and export triggers are driven by `app/static/js/export.js`. Without updating `export.js` to serialize active filters into the printable report URL (`/<slug>/report?...`), dynamic UI selections cannot be reflected.
* **Recommendation:** Add `app/static/js/export.js` to the target files list to bind active filters to the report button.

### 6. Template Context Contracts Omitted
* **Reviewer Lens:** `egm-implementation-readiness`
* **Severity:** 🟡 Major
* **Affected Scope:** Lines 317–320, 332–358
* **Description:** The exact context variable dictionaries passed via `render_template` across the 4 new presentation views are unstated.
* **Recommendation:** Explicitly document the expected template context variables for each view (e.g. `community`, `projects`, `user`, `snapshot`, `top_wikis`, `projects_by_role`).

### 7. Missing XTools URL Helper in `app/wiki_utils.py`
* **Reviewer Lens:** `egm-codebase-details`
* **Severity:** 🟢 Nit
* **Affected Scope:** Line 357
* **Description:** CentralAuth returns database names (e.g. `arwiki`, `commonswiki`), but `wiki_utils.py` lacks a helper to construct canonical XTools URLs.
* **Recommendation:** Add `build_xtools_user_url(wiki_code, username)` to `app/wiki_utils.py`.

