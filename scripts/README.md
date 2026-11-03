# Data Synchronization & Parsing Scripts (`scripts`)

## Overview
Standalone CLI utilities and ingestion jobs for Athar. Parses Meta-Wiki wikitext member rosters and aggregates cross-wiki CentralAuth user statistics into the local application database.

## Interface
- `[migrate_v2.py:run_migration]` Standalone idempotent database migration script adding v2 columns and indexes
- `[parse_members.py:DEFAULT_USER_AGENT]` Default User-Agent header string for requests to Meta-Wiki API
- `[parse_members.py:USER_TEMPLATE_NAMES]` Set of recognized MediaWiki wikitext member templates (`user`, `user2`, `user3`, `u`, `userlink`, `user-link`, `مستخدم`)
- `[parse_members.py:USER_PREFIXES]` Tuple of MediaWiki user namespace prefixes (`user:`, `user_talk:`, `مستخدم:`, `نقاش_المستخدم:`)
- `[parse_members.py:normalize_meta_page_title]` Converts full Meta-Wiki URLs or raw titles into canonical MediaWiki page titles
- `[parse_members.py:extract_members_from_wikitext]` Parses wikitext AST using `mwparserfromhell` to extract and deduplicate usernames
- `[parse_members.py:fetch_members_from_meta]` Queries Meta-Wiki API to retrieve page wikitext and extract member list
- `[sync_data.py:DEFAULT_USER_AGENT]` Default User-Agent header string for Wikimedia CentralAuth API queries
- `[sync_data.py:fetch_global_stats]` Queries Wikimedia CentralAuth API for global edit counts and per-wiki breakdown
- `[sync_data.py:sync_community]` Synchronizes roster and CentralAuth statistics for a single `Community` model instance
- `[sync_data.py:sync_project_contributors]` Discovers unique contributors across all project roles and synchronizes CentralAuth metrics
- `[sync_data.py:run_sync]` Orchestrates the ingestion loop across all registered communities and project contributors

## Invariants
- `[migrate_v2.py:run_migration]` Idempotently adds `participants` (JSON) and `results` (JSON) columns to `projects` table and creates indexes on `projects.lead_organizer` and `stat_snapshots` across SQLite and MariaDB without raising exceptions on repeated executions.
- `[parse_members.py:normalize_meta_page_title]` Returns empty string `""` if input `page_or_url` is empty or falsy.
- `[parse_members.py:extract_members_from_wikitext]` Returns empty list `[]` if input `raw_wikitext` is empty or falsy.
- `[parse_members.py:extract_members_from_wikitext]` Deduplicates extracted usernames case-insensitively while preserving insertion order.
- `[parse_members.py:extract_members_from_wikitext]` Strips namespace prefixes in `USER_PREFIXES`, removes subpage suffixes (`/`), and replaces underscores with spaces.
- `[parse_members.py:fetch_members_from_meta]` Returns empty list `[]` on non-200 HTTP response, `requests.RequestException`, or parse failure without raising unhandled exceptions.
- `[parse_members.py:fetch_members_from_meta]` Falls back to `Config.META_ROSTER_PAGE` (`Wikimedia_MA_User_Group/Members`) if `page_title` is omitted, and `Config.USER_AGENT` if `user_agent` is omitted.
- `[sync_data.py:fetch_global_stats]` Returns None on non-200 HTTP status, `requests.RequestException`, or unexpected response payload.
- `[sync_data.py:fetch_global_stats]` Returns `{'total_edits': 0, 'home_wiki': 'ar.wikipedia.org', 'wiki_breakdown': {}}` if `globaluserinfo` is absent or flagged `missing`.
- `[sync_data.py:fetch_global_stats]` Excludes wikis with 0 editcount from `wiki_breakdown`.
- `[sync_data.py:sync_community]` Returns 0 without syncing if `community.meta_roster_page` is empty or undefined.
- `[sync_data.py:sync_community]` Returns 0 and preserves existing database records without modifying membership if `fetch_members_from_meta` yields an empty roster.
- `[sync_data.py:sync_community]` Skips querying CentralAuth API if `user.last_synced` is within the last 4 hours.
- `[sync_data.py:sync_project_contributors]` Creates non-member `User` records (`is_member=False`) for newly discovered organizers, jury, and participants; skips CentralAuth calls if synced within the last 4 hours.
- `[sync_data.py:run_sync]` Automatically creates and commits default 'Wikimedia Morocco' community if no communities are found in database.
- `[sync_data.py:run_sync]` Executes `db.session.rollback()` on single-community sync failure to isolate errors and continue processing subsequent communities.

## Side Effects
- `[parse_members.py:sys.path]`, `[sync_data.py:sys.path]` Prepends repository root directory to `sys.path`.
- `[parse_members.py:fetch_members_from_meta]` Sends outbound HTTP GET requests to `https://meta.wikimedia.org/w/api.php` via `requests.get`.
- `[parse_members.py:fetch_members_from_meta]` Writes warning and error logs to stdout on HTTP failure or parsing exceptions.
- `[parse_members.py:__main__]` Prints extracted member counts and preview to stdout when executed as script.
- `[sync_data.py:fetch_global_stats]` Sends outbound HTTP GET requests to Wikimedia CentralAuth API (`https://meta.wikimedia.org/w/api.php`) via `requests.get`.
- `[sync_data.py:sync_community]` Inserts and updates `User`, `CommunityMember`, and `StatSnapshot` records in database via `db.session.add`, `flush`, and `commit`.
- `[sync_data.py:sync_community]` Writes progress logs and skip warnings to stdout.
- `[sync_data.py:run_sync]` Initializes Flask application context via `create_app()` and queries `Community` table; inserts default record if empty; rolls back on failure; prints progress messages.

## Verification
- Run: `pytest`

