# Consolidated Review Report: Athar Multi-Level Export & Contributor Intelligence

**Target Document:** `docs/designs/multi_level_export_and_user_intelligence.md`  
**Review Standard:** EGM Multi-Lens Goldfish Review Protocol (Uninterrupted Full Flow)  
**Evaluated Reviewers:** `egm-zoom-out`, `egm-comprehension`, `egm-design`, `egm-structural`, `egm-style`, `egm-implementation-readiness`, `egm-codebase-details`

---

## Executive Summary

The uninterrupted review swarm executed all five pipeline stages across high-level architecture, naive reader comprehension, antagonistic design critique, intermediate simplicity, and implementation readiness. The overall architecture (relying on local relational storage, browser `@media print` for PDF exports, and volunteer-friendly form inputs) is strongly validated. However, **4 Blockers, 7 Major issues, and 5 Nits** were identified that require remediation before the design is implementation-ready.

---

## Prioritized Action Items

### 🔴 Blockers

#### 1. Eliminate Synchronous External CentralAuth Lookup in User Profile
* **Originating Stages:** Initial Zoom Out (#1), Comprehension (#1), Critic Review (#2), Implementation Readiness (#2).
* **Actionable Task:** Remove the synchronous CentralAuth API fallback from `GET /user/<username>` (Lines 206–207). If a requested username does not exist in local storage (`User` or `Project`), return an immediate HTTP 404. This upholds the Zero-External-Network Invariant and prevents Toolforge Gunicorn worker starvation.

#### 2. Restructure Implementation Plan into 5 Phased Checkpoints
* **Originating Stages:** Implementation Readiness (#1), Codebase Details (#1).
* **Actionable Task:** Replace the flat 19-file enumeration in Lines 285–429 with 5 sequential phases, each with verifiable tests and exit criteria:
  * **Phase 1: Domain Entities & Migration Tooling** (`app/models.py`, `scripts/migrate_v2.py`, `tests/test_migration.py`)
  * **Phase 2: Core Utilities & Ingestion Optimization** (`app/wiki_utils.py`, `scripts/sync_data.py`)
  * **Phase 3: Presentation Routes & Form Handlers** (`app/routes/web.py`, form templates, reserved slug protection)
  * **Phase 4: CSV Export Endpoints & Security** (`app/routes/api.py`, `tests/test_exports_v2.py`)
  * **Phase 5: Print Architecture & Contributor Views** (Report templates, `user_profile.html`, `app/static/js/export.js`, `tests/test_user_profile.py`)

#### 3. Formalize Data Modeling Alternatives Evaluation
* **Originating Stages:** Critic Review (#1).
* **Actionable Task:** Under "Alternatives Considered", add an explicit evaluation comparing denormalized `db.JSON` storage vs. a normalized relational junction table (`ProjectParticipant`), documenting trade-offs in query performance, schema migrations, write contention, and cross-dialect portability.

#### 4. Define Explicit CSV Column Schemas for Level 1 and Level 3 Exports
* **Originating Stages:** Implementation Readiness (#2), Comprehension (#4).
* **Actionable Task:** Define the exact list of localized string headers:
  * Level 1 CSV: `["اسم المستخدم", "الدور في النشاط", "عنوان النشاط", "المشروع المستهدف", "تاريخ البدء", "تاريخ الانتهاء"]`.
  * Level 3 CSV: `["معرف النشاط", "عنوان النشاط", "المجتمع التابع له", "الدور", "الحالة", "المشروع المستهدف", "تاريخ البدء", "تاريخ الانتهاء"]`.

---

### 🟡 Major Issues

#### 5. Add Dedicated "Risks & Mitigations" Section
* **Originating Stages:** Critic Review (#3).
* **Actionable Task:** Insert a standard-compliant `## Risks & Mitigations` section detailing Wikimedia API rate limits (HTTP 429), MariaDB connection handling, memory limits, and volunteer data entry constraints.

#### 6. Ingestion Pipeline & Contributor Identity Disconnect
* **Originating Stages:** Critic Review (#4), Initial Zoom Out (#2).
* **Actionable Task:** Update `scripts/sync_data.py` to synchronize unique contributors found across both community rosters and project participation roles, while utilizing `User.last_synced` threshold (< 4 hours) inside `sync_community()` to eliminate redundant API calls.

#### 7. Define Cross-Dialect JSON Query Strategy Across SQLite & MariaDB
* **Originating Stages:** Implementation Readiness (#3), Comprehension (#4).
* **Actionable Task:** Specify in-memory Python filtering on candidate projects to prevent cross-database SQL crashes on SQLite during automated tests:
  ```python
  [p for p in candidate_projects if username == p.lead_organizer or username in (p.co_organizers or []) or username in (p.jury_members or []) or username in (p.participants or [])]
  ```

#### 8. Form Field Names & Deserialization Specification for `Project.results`
* **Originating Stages:** Implementation Readiness (#4).
* **Actionable Task:** Document exact HTML input `name` attributes (`results_summary`, `results_winners`, `results_articles_created`, `results_articles_improved`, `results_files_uploaded`, `results_notes`) and validation casting in `web.py`.

#### 9. Add `app/static/js/export.js` to File Modification Scope
* **Originating Stages:** Implementation Readiness (#5).
* **Actionable Task:** Include `app/static/js/export.js` in the target files list to bind active UI filter parameters (year, month, custom date) to the printable executive report URL (`/<slug>/report?...`).

#### 10. Standardize Route Naming & Clean Marketing Buzzwords
* **Originating Stages:** Critic Review (#5, #6).
* **Actionable Task:** Standardize API resource naming (`/api/users/...` and `/api/projects/...`) and replace inflated buzzwords with plain technical terms (3 export scopes × 2 formats).

#### 11. Document Template Context Variable Contracts
* **Originating Stages:** Implementation Readiness (#6).
* **Actionable Task:** Explicitly document the expected template context dictionaries for all 4 new presentation views.

---

### 🟢 Nits

#### 12. Complete CSV Formula Injection Sanitization
* **Originating Stages:** Critic Review (#7).
* **Actionable Task:** Strip leading whitespace with `.lstrip()` before checking trigger characters (`=`, `+`, `-`, `@`, `\t`, `\r`, `|`).

#### 13. Fix Print Stylesheet Table Page-Break Overflow
* **Originating Stages:** Critic Review (#8).
* **Actionable Task:** Remove `break-inside: avoid` from `.report-table`, retaining it strictly on `tr`, `.report-card`, and `.kpi-tile`.

#### 14. Display Factual Sync Timestamp Instead of Speculative Projections
* **Originating Stages:** Initial Zoom Out (#5).
* **Actionable Task:** Display factual relative time (e.g., "تم التحديث قبل ساعة واحدة") based on `last_synced`.

#### 15. Add XTools URL Helper to `app/wiki_utils.py`
* **Originating Stages:** Implementation Readiness (#7).
* **Actionable Task:** Add `build_xtools_user_url(wiki_code, username)` to `app/wiki_utils.py`.

#### 16. Remove Metaconversational Artifacts
* **Originating Stages:** Critic Review (#6), Comprehension (#7).
* **Actionable Task:** Strip references to "Goldfish brainstorm" and `*Drafted with EGM*`.

---

## Traceability Matrix

| Raw Finding | Stage / Reviewer Lens | Priority | Consolidated Action Item |
| :--- | :--- | :--- | :--- |
| Synchronous CentralAuth query during GET /user/<username> | Stage 5 (`egm-zoom-out`), Stage 6 (`egm-comprehension`), Stage 7 (`egm-design`) | 🔴 Blocker | Item 1 |
| Monolithic flat list of 19 files without phases/checkpoints | Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`) | 🔴 Blocker | Item 2 |
| Missing alternative evaluation for JSON vs relational participant model | Stage 7 (`egm-design`) | 🔴 Blocker | Item 3 |
| Missing CSV column headers for Level 1 and Level 3 | Stage 9 (`egm-implementation-readiness`, `egm-codebase-details`) | 🔴 Blocker | Item 4 |
| Missing dedicated Risks & Mitigations section | Stage 7 (`egm-design`, `egm-structural`) | 🟡 Major | Item 5 |
| Ghost contributor sync disconnect between rosters and project entries | Stage 7 (`egm-design`), Stage 5 (`egm-zoom-out`) | 🟡 Major | Item 6 |
| SQLite vs MariaDB JSON query dialect divergence | Stage 9 (`egm-implementation-readiness`), Stage 6 (`egm-comprehension`) | 🟡 Major | Item 7 |
| Undefined form field names for results sub-fields | Stage 9 (`egm-implementation-readiness`) | 🟡 Major | Item 8 |
| Omission of `export.js` from file modification scope | Stage 9 (`egm-codebase-details`) | 🟡 Major | Item 9 |
| Inconsistent tier terminology and marketing buzzwords | Stage 7 (`egm-style`, `egm-structural`) | 🟡 Major | Item 10 |
| Missing template context contracts for new views | Stage 9 (`egm-implementation-readiness`) | 🟡 Major | Item 11 |
| CSV formula injection leading whitespace bypass | Stage 7 (`egm-design`) | 🟢 Nit | Item 12 |
| Multi-page table print clipping caused by container break-inside | Stage 7 (`egm-design`) | 🟢 Nit | Item 13 |
| Speculative next-sync timestamp calculation | Stage 5 (`egm-zoom-out`) | 🟢 Nit | Item 14 |
| Missing XTools URL construction helper | Stage 9 (`egm-codebase-details`) | 🟢 Nit | Item 15 |
| Leaked framework acronyms and metaconversational provenance | Stage 7 (`egm-style`), Stage 6 (`egm-comprehension`) | 🟢 Nit | Item 16 |

