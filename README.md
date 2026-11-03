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

_(Notice that `MOCK_AUTH=True` is enabled by default so you can test project
creation immediately!)_

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
Athar is an affiliate intelligence and reporting platform for Wikimedia communities. The system maintains affiliate rosters by parsing Meta-Wiki user group pages, tracks cross-wiki metrics (edit counts, home wikis, multi-project breakdowns) via the Wikimedia CentralAuth API, logs community projects and contests, provides dedicated contributor profiles (`/user/<username>`), and delivers multi-level reports (Single Project, Affiliate Group, Contributor Profile) via streaming CSV and print-optimized HTML reports.

## Local Interface & Invariants
- `[config.py:Config]` Base configuration class loading environment settings with secure defaults
- `[config.py:Config.SECRET_KEY]` Application secret key (defaults to `'dev-secret-key'`)
- `[config.py:Config.SESSION_COOKIE_HTTPONLY]` Cookie security flag set strictly to True
- `[config.py:Config.SESSION_COOKIE_SAMESITE]` SameSite cookie policy set strictly to `'Lax'`
- `[config.py:Config.SESSION_COOKIE_SECURE]` Secure cookie flag active unless `FLASK_DEBUG` is explicitly `'true'`
- `[config.py:Config.SQLALCHEMY_DATABASE_URI]` Database URI (defaults to `'sqlite:///dev.db'`)
- `[config.py:Config.SQLALCHEMY_TRACK_MODIFICATIONS]` Disabled modification tracking (strictly False)
- `[config.py:Config.USER_AGENT]` User-Agent header for Wikimedia API requests
- `[config.py:Config.MOCK_AUTH]` Boolean enabling mock volunteer authentication
- `[config.py:Config.OAUTH_CLIENT_ID]`, `[config.py:Config.OAUTH_CLIENT_SECRET]` Wikimedia OAuth 2.0 credentials
- `[run.py:app]` Flask application instance created via `create_app()`
- `[seed_test.py:app]`, `[seed_test.py:wm_ma]`, `[seed_test.py:wm_tn]` Database initialization and sample seed fixture
- `[setup_repo.py:build_repository]` Idempotent repository scaffolding script

## Subdirectories & System Boundaries
- [app](./app/README.md): Core application package including the application factory (`create_app`), database models (`Community`, `User`, `Project`, `StatSnapshot`), OAuth authentication handlers, query utilities, and wiki utilities.
- [scripts](./scripts/README.md): Standalone CLI utilities and background ingestion jobs parsing Meta-Wiki rosters (`parse_members.py`), syncing cross-wiki CentralAuth metrics (`sync_data.py`), and running database schema migrations (`migrate_v2.py`).

## Global Invariants
- CentralAuth statistics synchronization runs asynchronously in background threads or standalone CLI jobs to prevent blocking web request threads.
- Profile and report web views adhere strictly to the Zero-External-Network Invariant, reading exclusively from local database snapshots without synchronous external API calls.
- All community and user entities maintain referential integrity with cascade deletion (`cascade='all, delete-orphan'`) on dependent membership, statistics snapshots, and project records.
- CSRF protection is strictly enforced across all session-authenticated web views, while REST API endpoints under `/api` are explicitly exempt.
- Target wiki URLs and domain inputs must strictly match or end with authorized Wikimedia domains defined in `ALLOWED_WIKIMEDIA_DOMAINS`.
- In non-debug deployments, session cookies enforce `HttpOnly`, `SameSite=Lax`, and `Secure` attributes.

## Global Side Effects
- Local SQLite database persistence at `instance/dev.db` (or ToolsDB MySQL in Wikimedia Toolforge production).
- External HTTP GET requests to Wikimedia Meta-Wiki API (`https://meta.wikimedia.org/w/api.php`) for wikitext parsing and CentralAuth data aggregation.
- Outbound OAuth 2.0 network handshakes to Wikimedia authentication servers for user authorization and profile fetching.

## System Verification
- Run: `pytest`
