# أثر (Athar) — Wikimedia Community Dashboard

An open-source analytics & activity dashboard for Wikimedia affiliates.
Aggregates cross-wiki CentralAuth metrics, tracks Meta-Wiki community rosters,
and logs events. Built with Flask, ToolsDB, and Wikimedia Codex on Toolforge.

---

## Quickstart for Students (Day 1)

### 1. Clone your Fork

```bash
git clone https://github.com/bonnjalal/Athar.git
cd Athar
git remote add upstream https://github.com/bonnjalal/Athar.git
git fetch upstream
```

### 2. Set Up Virtual Environment & Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Local Environment

```bash
cp .env.example .env
```

_(Set `MOCK_AUTH=True` with `DEBUG=True` for local development only; non-debug startup rejects `MOCK_AUTH=True`.)_

### 4. Run the Application

```bash
python3 run.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## Contribution Workflow

Always create feature branches off `dev`:

```bash
git checkout dev
git pull upstream dev
git checkout -b task-<number>-<short-description>
```

Submit your Pull Request targeting `base: dev`.

---

# Athar Repository Blueprint

## System Overview
Athar is an affiliate intelligence and reporting platform for Wikimedia communities. The system maintains affiliate rosters by parsing Meta-Wiki user group pages, tracks cross-wiki metrics (edit counts, home wikis, multi-project breakdowns) via the Wikimedia CentralAuth API, logs multilingual community activities with taxonomy campaigns and topic tags, governs communities and moderation via the Tool Admin console (`/admin`), supports bilingual Translatewiki-compatible localization (`ar`/`en`) with RTL/LTR CSS logical properties and dynamic dark/light theming, optionally pre-translates activity fields via Wikimedia MinT, provides dedicated contributor profiles (`/user/<username>`), and delivers multi-level reports (Single Project, Affiliate Group, Contributor Profile) via streaming CSV and light-mode print-optimized HTML reports.

## Local Interface & Invariants
- `[config.py:Config]` Base configuration class loading environment settings with secure defaults
- `[config.py:Config.DEBUG]` Explicit Flask debug toggle (`False` by default)
- `[config.py:Config.SECRET_KEY]` Application secret key (defaults to `'dev-secret-key'`)
- `[config.py:Config.SESSION_COOKIE_HTTPONLY]` Cookie security flag set strictly to True
- `[config.py:Config.SESSION_COOKIE_SAMESITE]` SameSite cookie policy set strictly to `'Lax'`
- `[config.py:Config.SESSION_COOKIE_SECURE]` Secure cookie flag active unless `FLASK_DEBUG` is explicitly `'true'`
- `[config.py:Config.SQLALCHEMY_DATABASE_URI]` Database URI resolved from `DATABASE_URL` or local SQLite `'sqlite:///dev.db'`
- `[config.py:Config.SQLALCHEMY_TRACK_MODIFICATIONS]` Disabled modification tracking (strictly False)
- `[config.py:Config.USER_AGENT]` User-Agent header for Wikimedia and MinT API requests
- `[config.py:Config.MOCK_AUTH]`, `[config.py:Config.MOCK_USERNAME]`, `[config.py:Config.MOCK_IS_ADMIN]` Development-only mock volunteer authentication flags
- `[config.py:Config.ADMIN_USERS]` Bootstrap Tool Admin username seed set (includes `'Bonnjalal00'`)
- `[config.py:Config.DELETION_REQUEST_URL]` External Meta-Wiki deletion request URL (hidden when empty)
- `[config.py:Config.DEFAULT_LOCALE]` Default UI locale (`'ar'`)
- `[config.py:Config.MINT_API_URL]`, `[config.py:Config.MINT_TIMEOUT_SECONDS]` Wikimedia MinT endpoint base URL and HTTP timeout (`10s`)
- `[config.py:Config.OAUTH_CLIENT_ID]`, `[config.py:Config.OAUTH_CLIENT_SECRET]` Wikimedia OAuth 2.0 credentials
- `[run.py:app]` Flask application instance created via `create_app()`
- `[seed_test.py]` Database initialization and sample seed fixture with Tool Admin, campaign, tags, and multilingual activity examples
- `[setup_repo.py:build_repository]` Idempotent repository scaffolding script

## Subdirectories & System Boundaries
- [app](./app/README.md): Core application package including the application factory (`create_app`), database models (`Community`, `User`, `Project`, `ProjectTag`, `StatSnapshot`), OAuth and DB-backed RBAC handlers, Translatewiki-compatible i18n engine (`i18n.py`), query utilities, and wiki/sanitization utilities.
- [scripts](./scripts/README.md): Standalone CLI utilities and background ingestion jobs parsing Meta-Wiki rosters (`parse_members.py`), syncing cross-wiki CentralAuth metrics (`sync_data.py`), and running idempotent schema migrations (`migrate_v2.py`, `migrate_v3.py`).
- `i18n/ui/`, `i18n/reports/`: Externalized `banana-i18n` JSON localization catalogs (`en.json`, `ar.json`, `qqq.json`) for UI strings and reports/CSV exports.

## Global Invariants
- CentralAuth statistics synchronization runs in background/CLI jobs (`scripts/sync_data.py`), and public profile/report/CSV endpoints adhere strictly to the Zero-External-Network Invariant (reading local DB snapshots only).
- `create_app()` raises `RuntimeError` if `MOCK_AUTH=True` outside debug or testing mode, or if placeholder OAuth credentials are configured without `MOCK_AUTH`/`TESTING`.
- All web routes, `/admin`, `POST /lang`, `POST /project/translate`, and mutating `POST`/`PUT` API routes enforce Flask-WTF CSRF validation when `WTF_CSRF_ENABLED` is True; all authorization checks query live DB `User.is_admin`/`User.is_member` state.
- Soft-deleted activities (`Project.is_deleted == True`) are excluded from all public views, queries, KPIs, user profiles, reports, and CSV exports (`active_projects_query()`).
- Target wiki identifiers must resolve within `ALLOWED_WIKIMEDIA_DOMAINS`, and optional external activity URLs (`wiki_link`) must use `https://` on `ALLOWED_ACTIVITY_LINK_DOMAINS` (Wikimedia projects + `wmcloud.org`, `wmflabs.org`, `toolforge.org`).
- Outbound Wikimedia MinT translation calls (`POST /project/translate`) enforce a 12 KB payload limit, DB-backed per-user 10 req/min rate limit, 6-hour cached `/languages` support checks, and `bleach.clean` HTML/text sanitization.

## Global Side Effects
- Local SQLite database persistence at `instance/dev.db` (or ToolsDB MySQL/MariaDB in Wikimedia Toolforge production).
- Outbound HTTP requests to Wikimedia Meta-Wiki API (`https://meta.wikimedia.org/w/api.php`), Wikimedia OAuth 2.0 endpoints, and Wikimedia MinT API (`https://translate.wmcloud.org/api`).

## System Verification
- Run: `./venv/bin/pytest -v`
