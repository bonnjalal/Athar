# Multi-Level Reporting & Contributor Intelligence Feature (`concepts_brief.md`)

* **Author:** Athar Engineering
* **Date:** 2026-11-03
* **Status:** Finalized Concept Brief (Goldfish Review Approved)

## Overview

This feature establishes an end-to-end contributor intelligence and multi-tiered reporting architecture for Athar, optimized for Wikimedia Toolforge hosting and universal internationalization (Translatewiki.net). It introduces a global Contributor Profile (`/user/<username>`) aggregating cross-wiki CentralAuth metrics and project involvement across multiple affiliate user groups. Additionally, it implements a symmetrical, three-tiered export system (Single Project, Affiliate Community, and Contributor Profile) delivered through structured CSV datasets and universal, print-optimized HTML reports designed for one-click browser PDF saving.

## Analysis & Architectural Decisions

### 1. Global Contributor Profile (`/user/<username>`)
* **Global Scope with Multi-Affiliate Aggregation:** Aggregates a contributor's activity across all registered affiliate user groups (`CommunityMember`).
* **Zero-External-Network Invariant:** The profile page reads strictly from the local database: cached `StatSnapshot.wiki_breakdown` (populated asynchronously by `scripts/sync_data.py` on a 4-hour schedule). No live outbound HTTP calls are made during web page loads, eliminating Toolforge HTTP 504 timeout risks.
* **Sync Transparency Badge:** Displays a prominent sync metadata badge showing:
  - Last synced timestamp and relative time (e.g., "تم التحديث قبل ساعة واحدة").
  - Next scheduled sync projection (based on the 4-hour cycle).
* **Wiki Breakdown Strategy:** The top 4–5 wikis are sorted locally in Python (`sorted(snapshot.wiki_breakdown.items(), key=lambda x: x[1], reverse=True)[:5]`). Outbound links point to `https://xtools.wmcloud.org/ec/{wiki}/{username}` for users seeking full revision history.
* **Interactive Filters:**
  - Affiliate Group filter: dropdown allowing viewing all groups or isolating a specific affiliate.
  - Role filter: filter by Lead Organizer, Co-organizer, Contest Jury, or Participant.
  - Date Range filter: filter project activities by year or custom date range.

### 2. Project Schema Evolution & Volunteer Form Ergonomics
* **Database Schema Extension:** Add two optional JSON fields to `Project`:
  - `participants: List[str]`: Homogeneous list of username strings, matching `co_organizers` and `jury_members`.
  - `results: Dict`: Standardized structured dictionary storing contest metrics, winners, Challenges and outcomes.
* **Volunteer Form Ergonomics (No Raw JSON):**
  - **Participants Input:** A user-friendly, multi-line textarea in `project_form.html` where volunteers paste usernames line-by-line or comma-separated. The backend trims whitespace, deduplicates entries, and stores clean strings.
  - **Results Input:** A guided form interface with dedicated, human-friendly input fields:
    - Executive Summary / Description (`summary: str`)
    - Contest Winners / Honorees (`winners: List[str]`, entered line-by-line)
    - Output Metrics (Articles Created, Articles Improved, Files Uploaded)
    - Additional Notes and challenes (`notes: str`)
  - The application automatically bundles these into the validated `results` JSON dictionary on submit, completely shielding volunteers from technical syntax.
* **Database Migration & Indexing:**
  - Provide an idempotent migration script (`scripts/migrate_v2.py`) executing:
    ```sql
    ALTER TABLE projects ADD COLUMN participants JSON NULL;
    ALTER TABLE projects ADD COLUMN results JSON NULL;
    ```
  - Add explicit indexing on `Project.lead_organizer` (`index=True`) and composite indexing on `StatSnapshot(user_id, recorded_at.desc())` to optimize lookups.

### 3. Symmetrical Multi-Level Routing & Dual-Tier Export Architecture
To support universal internationalization (Arabic RTL, Chinese, Hindi, etc.) without bundling language-specific TTF fonts or fragile C-libraries on Toolforge:
* **Tier 1: Presentation & Printable HTML Reports (`web_bp`)**:
  - Level 1 (Project Dossier): `GET /project/<int:project_id>/report`
  - Level 2 (Affiliate Executive Report): `GET /<slug>/report`
  - Level 3 (Contributor Dossier): `GET /user/<string:username>/report`
  - *Print Layout:* Dedicated `templates/reports/base_report.html` devoid of navbars, sidebars, and flash messages, enforcing `@page { size: A4; margin: 15mm; }`, `-webkit-print-color-adjust: exact;`, and `break-inside: avoid;` for clean, one-click PDF generation via the browser print dialog.
* **Tier 2: Structured Data Downloads (`api_bp`)**:
  - Level 1 (Participant Roster & Outcomes CSV): `GET /api/projects/<int:project_id>/export?format=csv`
  - Level 2 (Affiliate Activities CSV): `GET /api/<slug>/export?format=csv`
  - Level 3 (Contributor History & Metrics CSV): `GET /api/user/<string:username>/export?format=csv`
  - *CSV Security:* Prepend a single quote (`'`) to any exported CSV cell whose string value begins with `=`, `+`, `-`, `@`, `\t`, or `\r` to prevent spreadsheet formula injection.

### 4. Background Synchronization Hardening
* **Roster Deduplication:** In `scripts/sync_data.py`, aggregate and deduplicate usernames across all community Meta-Wiki rosters before dispatching CentralAuth queries, avoiding redundant requests for contributors who belong to multiple affiliate groups.
* **Namespace Isolation:** Enforce reserved word checks in `slugify()` to prevent communities from claiming `user`, `project`, `export`, or `api`.

## Goals vs. Non-Goals

* **In-Scope Goals:**
  - Build global `/user/<username>` profile view with multi-affiliate project aggregation, affiliate group filtering, sync transparency badge, and top-5 CentralAuth wiki breakdown.
  - Extend `Project` model with `participants: List[str]` and `results: Dict` JSON columns, accompanied by idempotent migration tooling and volunteer-friendly form controls.
  - Implement symmetrical dual-tier export routes across Level 1 (Single Project), Level 2 (Affiliate Group), and Level 3 (Contributor Profile).
  - Create dedicated, print-optimized HTML templates (`@media print`) enabling clean, universal browser PDF export without server font bundles.
  - Implement CSV formula injection escaping and background CentralAuth sync deduplication.

* **Out-of-Scope Non-Goals:**
  - Synchronous real-time external API crawling during web request lifecycles.
  - Server-side headless browser binary installation (Puppeteer, Playwright) or C-dependency PDF engines on Toolforge.
  - Automated wikitext web scraping of arbitrary on-wiki contest pages (replaced by structured form inputs).

## Alternatives Weighed

* **Synchronous Live XTools Queries vs. Local CentralAuth Snapshots:**
  - *Synchronous Live Queries:* Rejected due to high latency (5–25s) and fatal Toolforge HTTP 504 gateway timeout risks.
  - *Local Snapshot with Top-5 Python Sorting & Sync Badge:* Adopted for instant, sub-second page loads with zero external failure modes.
* **Monolithic Single-Project CSV vs. Participant Roster CSV + Printable Dossier:**
  - *Monolithic CSV:* Rejected because flattening 1-to-many hierarchical structures into a single spreadsheet row produces corrupt, unusable data.
  - *Targeted Roster CSV + Printable HTML Report:* Adopted as the optimal combination for spreadsheet analysis and grant reporting.
* **Server-Side PDF Engines vs. Universal `@media print` Reports:**
  - *Server-Side Engines (WeasyPrint / ReportLab):* Rejected due to font-bundling complexity for multi-language scripts (Arabic RTL, Chinese, Hindi) and memory overhead on Toolforge.
  - *Browser `@media print` Templates:* Selected for native typography, zero server memory consumption, and flawless multi-lingual rendering.

## Key Decisions & Staging for Next Steps

1. **Phase 1: Database Migration & Schema Extension**:
   - Create and run migration script for `Project.participants` and `Project.results`.
   - Add database indices on `Project.lead_organizer` and `StatSnapshot(user_id, recorded_at)`.
2. **Phase 2: Global Contributor Profile (`/user/<username>`)**:
   - Implement route, controller, and template displaying CentralAuth stats, sync badge, top-5 wikis, and multi-group project history.
3. **Phase 3: Form Updates for Participants & Results**:
   - Update `project_form.html`, `create_project`, and `edit_project` with non-technical text inputs, structured result fields, and Bleach sanitization.
4. **Phase 4: Symmetrical Dual-Tier Export Implementation**:
   - Create `base_report.html` and printable views for Level 1, 2, and 3.
   - Implement CSV endpoints with formula escaping and generator-based streaming.
