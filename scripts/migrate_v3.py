#!/usr/bin/env python3
"""
scripts/migrate_v3.py

Standalone, idempotent database schema migration script for Athar v3
(Admin Governance, Taxonomy, Localization & MinT Translation Support).

Adds:
- users: is_admin, mint_window_start, mint_window_count
- projects: wiki_link, campaign, primary_lang, translations,
            is_deleted, deleted_at, deleted_by
- project_tags table (normalized many-to-one tags join table)
- Indexes: ix_projects_campaign, ix_projects_is_deleted,
           ix_projects_active_status_start, ix_project_tags_tag
- Seeds initial Tool Admins (Bonnjalal00 + Config.ADMIN_USERS) with is_member=0
  for newly inserted rows.

Notes on MariaDB DDL safety:
- On Toolforge ToolsDB (MariaDB), DDL statements (ALTER TABLE, CREATE TABLE,
  CREATE INDEX) trigger implicit commits per statement. Safety and recoverability
  relies on per-item existence inspection before each statement rather than
  multi-DDL transaction rollback, so re-running migrate_v3.py resumes cleanly.
- Connects directly via config.resolve_database_uri() without calling create_app().
"""

from datetime import datetime
import os
import re
import sys
from urllib.parse import unquote

from sqlalchemy import create_engine, inspect, text

# Add project root to sys.path
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

from config import Config, resolve_database_uri
from app.models import ProjectTag


def _resolve_standalone_uri(uri: str) -> str:
    """Match Flask-SQLAlchemy instance/ resolution for relative SQLite URIs like sqlite:///dev.db."""
    if uri.startswith("sqlite:///") and not uri.startswith("sqlite:////") and uri != "sqlite:///:memory:":
        rel_path = uri[len("sqlite:///"):]
        if rel_path and not os.path.isabs(rel_path) and not rel_path.startswith("instance/"):
            instance_dir = os.path.join(_REPO_ROOT, "instance")
            instance_candidate = os.path.join(instance_dir, rel_path)
            root_candidate = os.path.join(_REPO_ROOT, rel_path)
            if os.path.exists(instance_candidate) or (
                os.path.isdir(instance_dir)
                and (not os.path.exists(root_candidate) or os.path.getsize(root_candidate) == 0)
            ):
                return f"sqlite:///{instance_candidate}"
    return uri


def _normalize_username_key(username: str) -> str:
    if not username:
        return ""
    return unquote(str(username)).replace("_", " ").strip()


def run_migration(engine=None, admin_users=None):
    """
    Executes idempotent v3 migration against the provided SQLAlchemy engine
    or resolves the database URI directly via config.resolve_database_uri().
    Returns a list of applied action descriptions (empty [] when already up-to-date).
    """
    owns_engine = False
    if engine is None:
        uri = _resolve_standalone_uri(resolve_database_uri())
        connect_args = {}
        engine_kwargs = {"pool_pre_ping": True} if uri.startswith("mysql") else {}
        engine = create_engine(uri, **engine_kwargs)
        owns_engine = True

    try:
        return _execute_migration(engine, admin_users=admin_users)
    finally:
        if owns_engine:
            engine.dispose()


def _ensure_columns(conn, inspector, table_name, column_specs, actions):
    existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
    for col_name, ddl in column_specs:
        if col_name not in existing_cols:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {ddl}"))
            actions.append(f"added column {table_name}.{col_name}")
            print(f"  [+] Added column '{col_name}' to '{table_name}'")
        else:
            print(f"  [-] Column '{col_name}' already exists in '{table_name}'")


def _ensure_index(conn, existing_indexes, table_name, index_name, cols_sql, actions):
    if index_name not in existing_indexes:
        conn.execute(text(f"CREATE INDEX {index_name} ON {table_name} ({cols_sql})"))
        actions.append(f"created index {index_name}")
        print(f"  [+] Created index '{index_name}' on '{table_name} ({cols_sql})'")
    else:
        print(f"  [-] Index '{index_name}' already exists on '{table_name}'")


def _audit_username_collisions(conn):
    """Warn on case/underscore-folded duplicate usernames without mutating rows."""
    rows = conn.execute(text("SELECT id, username FROM users")).fetchall()
    seen = {}
    for uid, uname in rows:
        key = _normalize_username_key(uname).lower()
        if not key:
            continue
        if key in seen:
            print(
                f"  [!] Warning: username normalization collision in users: "
                f"id={seen[key][0]} ({seen[key][1]!r}) vs id={uid} ({uname!r})"
            )
        else:
            seen[key] = (uid, uname)


def _seed_admins(conn, admin_users, actions):
    """Idempotently seed Bonnjalal00 + Config.ADMIN_USERS as Tool Admins (is_member=0 on new insert)."""
    configured = set(getattr(Config, "ADMIN_USERS", {"Bonnjalal00"}))
    if admin_users is not None:
        configured = set(admin_users)
    configured.add("Bonnjalal00")

    now = datetime.utcnow()
    for raw_name in sorted(configured):
        canonical = _normalize_username_key(raw_name)
        if not canonical:
            continue
        existing = conn.execute(
            text("SELECT id, is_admin FROM users WHERE LOWER(username) = :lower_u"),
            {"lower_u": canonical.lower()},
        ).fetchone()

        if existing is None:
            conn.execute(
                text(
                    "INSERT INTO users (username, is_member, is_admin, mint_window_count, first_seen, last_synced) "
                    "VALUES (:username, 0, 1, 0, :now, :now)"
                ),
                {"username": canonical, "now": now},
            )
            actions.append(f"seeded admin user.{canonical}")
            print(f"  [+] Seeded admin user '{canonical}' (is_member=0, is_admin=1)")
        elif not bool(existing[1]):
            conn.execute(
                text("UPDATE users SET is_admin = 1 WHERE id = :uid"),
                {"uid": existing[0]},
            )
            actions.append(f"granted admin users.{canonical}")
            print(f"  [+] Granted admin role to existing user '{canonical}'")
        else:
            print(f"  [-] Admin user '{canonical}' already has is_admin=1")


def _execute_migration(engine, admin_users=None):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    actions = []

    with engine.begin() as conn:
        # 1. Users table extensions
        if "users" in tables:
            _ensure_columns(
                conn,
                inspector,
                "users",
                [
                    ("is_admin", "BOOLEAN NOT NULL DEFAULT 0"),
                    ("mint_window_start", "DATETIME NULL"),
                    ("mint_window_count", "INTEGER NOT NULL DEFAULT 0"),
                ],
                actions,
            )

        # 2. Projects table extensions
        if "projects" in tables:
            _ensure_columns(
                conn,
                inspector,
                "projects",
                [
                    ("wiki_link", "VARCHAR(1024) NULL"),
                    ("campaign", "VARCHAR(128) NULL"),
                    ("primary_lang", "VARCHAR(16) NOT NULL DEFAULT 'ar'"),
                    ("translations", "JSON NULL"),
                    ("is_deleted", "BOOLEAN NOT NULL DEFAULT 0"),
                    ("deleted_at", "DATETIME NULL"),
                    ("deleted_by", "VARCHAR(128) NULL"),
                ],
                actions,
            )

        # 3. Create project_tags join table if missing
        if "projects" in tables and "project_tags" not in tables:
            ProjectTag.__table__.create(bind=conn, checkfirst=True)
            actions.append("created table project_tags")
            print("  [+] Created table 'project_tags'")
        elif "project_tags" in tables:
            print("  [-] Table 'project_tags' already exists")

    # 4. Refresh inspector after DDL changes before verifying/creating indexes
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        if "projects" in tables:
            existing_proj_idx = {
                idx["name"] for idx in inspector.get_indexes("projects") if idx.get("name")
            }
            _ensure_index(conn, existing_proj_idx, "projects", "ix_projects_campaign", "campaign", actions)
            _ensure_index(conn, existing_proj_idx, "projects", "ix_projects_is_deleted", "is_deleted", actions)
            _ensure_index(
                conn,
                existing_proj_idx,
                "projects",
                "ix_projects_active_status_start",
                "is_deleted, status, start_date",
                actions,
            )

        if "project_tags" in tables:
            existing_tag_idx = {
                idx["name"] for idx in inspector.get_indexes("project_tags") if idx.get("name")
            }
            _ensure_index(conn, existing_tag_idx, "project_tags", "ix_project_tags_tag", "tag", actions)

        # 5. Audit username collisions, seed Tool Admins, and normalize non-ASCII legacy slugs
        if "users" in tables:
            _audit_username_collisions(conn)
            _seed_admins(conn, admin_users, actions)

        if "communities" in tables:
            _normalize_legacy_community_slugs(conn, actions)

    return actions


_ASCII_SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _normalize_legacy_community_slugs(conn, actions):
    rows = conn.execute(text("SELECT id, name, slug, meta_roster_page FROM communities ORDER BY id ASC")).fetchall()
    used_slugs = {r[2] for r in rows if r[2] and _ASCII_SLUG_REGEX.match(str(r[2]))}

    for cid, name, slug, roster in rows:
        if slug and _ASCII_SLUG_REGEX.match(str(slug)):
            continue
        raw_combo = f"{name or ''} {roster or ''} {slug or ''}"
        if "المغرب" in raw_combo or "morocco" in raw_combo.lower() or "ma_user_group" in raw_combo.lower():
            base = "wm-ma"
        else:
            ascii_name = re.sub(r"[^a-z0-9\s-]", "", (name or "").lower()).strip()
            base = re.sub(r"[\s-]+", "-", ascii_name).strip("-")[:64] or f"community-{cid}"

        candidate = base
        counter = 1
        while candidate in used_slugs:
            candidate = f"{base[:58]}-{counter}"
            counter += 1

        used_slugs.add(candidate)
        conn.execute(text("UPDATE communities SET slug = :slug WHERE id = :cid"), {"slug": candidate, "cid": cid})
        actions.append(f"normalized community slug id={cid} -> {candidate}")
        print(f"  [+] Normalized non-ASCII community slug '{slug}' -> '{candidate}'")


if __name__ == "__main__":
    print("Running Athar v3 database schema migration...")
    executed_actions = run_migration()
    print(f"Migration completed successfully. {len(executed_actions)} action(s) applied.")

