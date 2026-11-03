# Critic Review Report (Feature Specification)

**Target:** `docs/designs/multi_level_export_and_user_intelligence.md` (Lines 1–284)  
**Standard:** `resources/document_standards/feature-spec-standard.md`  
**Reviewers:** `egm-design`, `egm-structural`, `egm-style`

## Prioritized Findings

### 1. Violation of the Alternatives Rule for Data Modeling
* **Reviewer Lens:** `egm-design`
* **Severity:** 🔴 Blocker
* **Affected Scope:** Lines 114–121, 142–163, 226–264
* **Description:** The specification proposes storing project participants (`participants = db.Column(db.JSON, nullable=True)`) as denormalized JSON string arrays without evaluating alternative data models (such as a normalized relational junction table `project_participants`).
* **Recommendation:** Add a formal evaluation in Alternatives Considered comparing denormalized `db.JSON` storage against a normalized relational junction table, detailing trade-offs in query performance, schema migrations, write contention, and cross-dialect portability.

### 2. Architectural Contradiction & DoS Vulnerability on User Lookup
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Severity:** 🔴 Blocker
* **Affected Scope:** Lines 24, 32, 206–207, 274
* **Description:** Lines 206–207 instruct calling MediaWiki CentralAuth synchronously via `check_user` if a user is not found locally. This directly violates the Zero-External-Network Invariant and exposes Toolforge workers to thread exhaustion and HTTP 504 timeouts.
* **Recommendation:** Strictly eliminate synchronous external network calls in web controllers. If a user is missing from local storage, return an immediate HTTP 404.

### 3. Missing Dedicated "Risks & Mitigations" Section
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Severity:** 🟡 Major
* **Affected Scope:** Lines 266–284
* **Description:** The Feature Specification Standard explicitly mandates a dedicated `## Risks & Mitigations` section analyzing potential failure modes, scalability boundaries, and security implications.
* **Recommendation:** Add a dedicated `## Risks & Mitigations` section mapping out CentralAuth API throttling, MariaDB connection handling, memory limits, and volunteer data entry constraints.

### 4. Ghost Contributor Failure Mode in Ingestion Pipeline
* **Reviewer Lens:** `egm-design`
* **Severity:** 🟡 Major
* **Affected Scope:** Lines 206–214, 221
* **Description:** Event participants entered into `Project.participants` may not be official affiliate members on Meta-Wiki rosters. Because `sync_data.py` only extracts usernames from community rosters, participants will never be enqueued for background CentralAuth synchronization.
* **Recommendation:** Ensure `sync_data.py` synchronizes unique contributors found across both community rosters and project participation fields.

### 5. Pluralization Asymmetry in Route Matrix
* **Reviewer Lens:** `egm-structural`
* **Severity:** 🟡 Major
* **Affected Scope:** Lines 166–170
* **Description:** Mixing plural resource roots (`/api/projects/...`) with singular roots (`/api/user/...`) violates structural symmetry in the API namespace.
* **Recommendation:** Standardize resource naming across all levels (e.g., `/api/projects/...` and `/api/users/...`).

### 6. Inconsistent Tier Nomenclature & Marketing Buzzwords
* **Reviewer Lens:** `egm-style`
* **Severity:** 🟡 Major
* **Affected Scope:** Lines 1, 11, 13, 27, 56, 164, 172
* **Description:** Uses conflicting terms ("three-tiered" vs "dual-tier"), conflates browser script rendering with i18n, and employs enterprise buzzwords ("contributor intelligence", "executive report", "ergonomics").
* **Recommendation:** Standardize on "3 export scopes × 2 formats", clarify browser typography vs Translatewiki.net localization, and use plain engineering language ("contributor profiles", "annual activity report", "input parsing").

### 7. Incomplete CSV Formula Injection Sanitization
* **Reviewer Lens:** `egm-design`
* **Severity:** 🟢 Nit
* **Affected Scope:** Lines 219, 269
* **Description:** Formula sanitization checking `startswith(...)` can be bypassed by leading whitespace or the pipe (`|`) operator.
* **Recommendation:** Strip leading whitespace with `.lstrip()` and include pipe `|` in the formula trigger character set.

### 8. Print Stylesheet Break-Inside Container Overflow
* **Reviewer Lens:** `egm-design`
* **Severity:** 🟢 Nit
* **Affected Scope:** Line 191
* **Description:** Applying `break-inside: avoid !important` to parent `.report-table` causes multi-page tables to clip in print preview.
* **Recommendation:** Remove `break-inside: avoid` from `.report-table`, retaining it strictly on `tr`, `.report-card`, and `.kpi-tile`.

