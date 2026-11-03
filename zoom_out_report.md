# Zoom Out Review Report

**Target:** `docs/designs/multi_level_export_and_user_intelligence.md` (Lines 1–429)  
**Standard:** `resources/document_standards/zoom-out-standard.md`  
**Reviewer:** `egm-zoom-out`

## Findings

### 1. Synchronous Meta-Wiki API Call in Web View Breaches Zero-External-Network Invariant
* **Severity:** 🔴 Blocker
* **Affected Scope:** Section 6, Step 2 (Lines 206–207); Section 16 (Line 392).
* **Rationale & Recommendation:**
  * Step 2 specifies that if a user is missing locally, the web controller queries MediaWiki CentralAuth synchronously via `check_user`.
  * This directly contradicts Goal 2 (Zero-External-Network Invariant), Non-Goal 1, and NFR Performance ("Zero outbound HTTP requests are permitted during web requests").
  * On Toolforge's constrained worker pools, slow external calls risk thread starvation and HTTP 504 Gateway Timeouts.
  * *Recommendation:* Athar tracks affiliate activity, not the global Wikimedia directory. If a user is not found in local storage (`users` or `projects`), return HTTP 404 immediately with zero network I/O.

### 2. Over-Engineering Cron Ingestion via Multi-Pass Deduplicated Roster Queue
* **Severity:** 🟡 Major
* **Affected Scope:** Section 1 (Lines 87–89); Section 7 (Line 221); Section 15 (Lines 381–386).
* **Rationale & Recommendation:**
  * The proposal creates a complex global multi-pass ingestion architecture that couples community syncs and complicates individual on-demand syncs (`web.py:manual_sync`).
  * *Recommendation:* In `scripts/sync_data.py:sync_community`, simply check if `user.last_synced` is within the last 4 hours (`now - user.last_synced < 14400s`) before calling `fetch_global_stats()`. This prevents redundant API requests while preserving per-community error isolation.

### 3. Premature Optimization with Chunked Generator Streaming for Small CSVs
* **Severity:** 🟡 Major
* **Affected Scope:** Section 7 (Line 220); Section "Performance & Latency" (Line 275); Section 5 (Line 330).
* **Rationale & Recommendation:**
  * Affiliate groups log 10 to 200 projects annually, producing CSV files between 5 KB and 100 KB.
  * Chunked generator streaming adds session lifecycle hazards and prevents returning clean HTTP error statuses once headers are sent.
  * *Recommendation:* Retain Athar's existing, reliable `io.StringIO` pattern with UTF-8 BOM encoding.

### 4. Unnecessary Grab-Bag Module `app/query_utils.py`
* **Severity:** 🟡 Major
* **Affected Scope:** Section 1 (Lines 77, 99–103); Section 3 (Lines 307–313).
* **Rationale & Recommendation:**
  * Creating `app/query_utils.py` bundles unrelated functions (query filtering, CSV escaping, and MediaWiki text normalization).
  * *Recommendation:* Place `normalize_username` in `app/wiki_utils.py` alongside other MediaWiki helpers; keep `_filter_projects_by_date` and CSV sanitization in route/export modules.

### 5. Speculative Next Scheduled Sync Calculation
* **Severity:** 🟢 Nit
* **Affected Scope:** Goals (Line 25); Section 6, Step 3 (Line 211); Section 10 (Line 357).
* **Rationale & Recommendation:**
  * Displaying a projected `last_synced + 4 hours` timestamp is misleading because Athar does not maintain an internal cron daemon.
  * *Recommendation:* Display the factual relative time (e.g., "تم التحديث قبل ساعة واحدة") based on `last_synced`.

### 6. Altitude Drop into CSS & Microcopy Weeds
* **Severity:** 🟢 Nit
* **Affected Scope:** Section 3 (Lines 142–163); Section 5 (Lines 177–201).
* **Rationale & Recommendation:**
  * Detailed CSS rules and exact Arabic placeholder strings belong in implementation files, not high-level architecture designs.

### 7. Overstated Indexing Rationale for Contributor Project Lookups
* **Severity:** 🟢 Nit
* **Affected Scope:** Section 2 (Lines 120, 126); Section "Performance & Latency" (Line 276).
* **Rationale & Recommendation:**
  * Adding an index to `Project.lead_organizer` accelerates organizer queries, but because `co_organizers`, `jury_members`, and `participants` are JSON arrays, full table scans are still needed across all 4 roles. State this realistically.

