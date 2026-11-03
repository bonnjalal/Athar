# Comprehension Test Report

**Target:** `docs/designs/multi_level_export_and_user_intelligence.md`  
**Reviewer:** `egm-comprehension`

## Document Proposal Paraphrase

The document proposes introducing an end-to-end contributor intelligence feature and a symmetrical, three-tier reporting architecture for Athar. It adds a global contributor profile (`/user/<username>`) that aggregates multi-affiliate group memberships, cached cross-wiki edit metrics, and a role-categorized history of project involvement. To support comprehensive project tracking, the `Project` model is extended with structured JSON fields for participant rosters and competition results via volunteer-friendly form inputs and an automated migration script (`scripts/migrate_v2.py`). Finally, it implements both streaming CSV data exports and print-optimized HTML templates (`@media print`) across single projects, affiliates, and individual contributors, enabling one-click browser PDF generation without requiring heavy, crash-prone server-side rendering engines on Toolforge.

## Existing System Paraphrase

Per the document, Athar is an open-source analytics dashboard that currently tracks affiliate community rosters and logs activities, but lacks contributor-centric analytics and detailed reporting. When users click contributor handles in member lists, they are redirected out of Athar directly to Meta-Wiki rather than seeing internal project histories or unified cross-wiki metrics. The existing `Project` entity only models organizers and jury members, omitting structured data for participant attendees and contest outcomes. Furthermore, data export is currently restricted to a single affiliate-wide project CSV, with no support for single-project dossiers, individual contributor portfolios, or server-safe PDF generation under Toolforge resource limits.

---

## Findings

### 1. Architectural Contradiction Between Zero-Network Invariant and Synchronous User Lookup Fallback
* **Severity:** 🔴 Blocker
* **Affected Scope:** Lines 206–207 vs. Lines 24, 32, 246, 274
* **Description:** Goal 2 and NFRs explicitly state that zero outbound HTTP requests are permitted during web requests. However, Section 6 specifies that if a user is missing locally, the controller queries CentralAuth synchronously via `check_user`.
* **Recommendation:** Eliminate the synchronous external network call. If a requested username is not found in the local database, return an immediate HTTP 404 without touching the network.

### 2. Undefined Internal Routines and Assumed Institutional Knowledge
* **Severity:** 🟡 Major
* **Affected Scope:** Lines 207, 221, 330, 385 (`check_user`, `fetch_global_stats`, `exp_community_projects`)
* **Description:** The document references `check_user`, `fetch_global_stats()`, and `exp_community_projects` without indicating their module locations, signatures, or error behaviors.
* **Recommendation:** Document module paths, signatures, and contracts for all referenced functions.

### 3. Unlinked and Undefined Wikimedia-Specific Systems
* **Severity:** 🟡 Major
* **Affected Scope:** Lines 13, 28, 46, 92–93, 131, 207, 246, 305, 357 (`CentralAuth`, `Translatewiki.net`, `XTools`, `ToolsDB`)
* **Description:** Specialized Wikimedia infrastructure tools are cited without definitions or documentation links.
* **Recommendation:** Provide brief contextual definitions and links (e.g. MediaWiki CentralAuth, XTools on Toolforge, ToolsDB MariaDB cluster).

### 4. Ambiguous Relational Model and Role Filtering Resolution
* **Severity:** 🟡 Major
* **Affected Scope:** Lines 81, 212–215, 292–296
* **Description:** The document omits the relationship connecting `User`, `Community`, and `CommunityMember`, and does not state how membership across JSON arrays is queried cross-database.
* **Recommendation:** Explicitly document the relationship and specify the query strategy (in-memory candidate filtering or dialect-safe query).

### 5. Undefined Date Filter Parameter Contract for Printable Reports
* **Severity:** 🟢 Nit
* **Affected Scope:** Lines 56, 169, 310, 319, 347
* **Description:** Query parameters accepted by report controllers (`?year=`, `?month=`, `?start_date=`, `?end_date=`) are not explicitly listed.
* **Recommendation:** Document the canonical list of query parameters accepted by report routes.

### 6. Typo in Implementation Plan Endpoint Function Identifier
* **Severity:** 🟢 Nit
* **Affected Scope:** Line 327
* **Description:** Refers to `create_projetct` (with an extra `t`).
* **Recommendation:** Note the existing codebase spelling while establishing clean routing aliases.

### 7. Leaked Meta-Prompting Acronym (`EGM`)
* **Severity:** 🟢 Nit
* **Affected Scope:** Lines 408, 428
* **Description:** Mentions internal framework acronym `EGM` which has no domain relevance for external contributors.
* **Recommendation:** Remove internal meta-prompting acronyms.

