#!/usr/bin/env python3
"""
scripts/migrate_sqlite_to_mariadb.py

One-time data migration helper to copy all Athar tables from SQLite
(instance/dev.db) into Toolforge ToolsDB (MariaDB) while preserving IDs,
JSON payloads, Arabic UTF-8 text, and foreign-key relationships.
"""
import argparse
import os
import sys

# Ensure project root is importable when executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.engine import make_url

from config import resolve_database_uri
from app.models import db


DEFAULT_SQLITE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "instance", "dev.db")
)


def _normalize_source_uri(source):
    """Accept either a filesystem path to dev.db or a SQLAlchemy database URI."""
    if "://" in source:
        return source
    return f"sqlite:///{os.path.abspath(source)}"


def _table_row_count(conn, table):
    return conn.execute(select(func.count()).select_from(table)).scalar_one()


def migrate_database(source_uri, target_uri, dry_run=False, batch_size=500):
    """
    Copy all rows from source_uri into target_uri in foreign-key dependency order.
    Returns a dict mapping table name -> {"source": int, "copied": int}.
    """
    if source_uri == target_uri:
        raise ValueError("Source and target database URIs must be different.")

    src_url = make_url(source_uri)
    if src_url.get_backend_name() == "sqlite" and src_url.database and src_url.database != ":memory:":
        if not os.path.exists(src_url.database):
            raise FileNotFoundError(f"Source SQLite database not found: {src_url.database}")

    src_engine = create_engine(source_uri)
    target_engine_kwargs = (
        {"pool_pre_ping": True, "pool_recycle": 280}
        if target_uri.startswith("mysql")
        else {}
    )
    dst_engine = create_engine(target_uri, **target_engine_kwargs)

    tables = list(db.metadata.sorted_tables)
    summary = {}

    try:
        if not dry_run:
            db.metadata.create_all(dst_engine)

        dst_inspector = inspect(dst_engine)
        existing_dst_tables = set(dst_inspector.get_table_names())

        with src_engine.connect() as src_conn:
            for table in tables:
                src_count = _table_row_count(src_conn, table)
                if table.name in existing_dst_tables:
                    with dst_engine.connect() as dst_check_conn:
                        dst_count = _table_row_count(dst_check_conn, table)
                    if dst_count > 0:
                        raise RuntimeError(
                            f"Target table '{table.name}' already contains {dst_count} row(s). "
                            "Aborting to prevent duplicate keys or overwriting existing data."
                        )
                summary[table.name] = {"source": src_count, "copied": 0}

            if dry_run:
                return summary

            with dst_engine.begin() as dst_conn:
                for table in tables:
                    result = src_conn.execute(select(table))
                    while True:
                        mappings = result.mappings().fetchmany(batch_size)
                        if not mappings:
                            break
                        rows = [dict(row) for row in mappings]
                        dst_conn.execute(table.insert(), rows)
                        summary[table.name]["copied"] += len(rows)

        with dst_engine.connect() as dst_verify_conn:
            for table in tables:
                dst_count = _table_row_count(dst_verify_conn, table)
                src_count = summary[table.name]["source"]
                if dst_count != src_count:
                    raise RuntimeError(
                        f"Row count mismatch for '{table.name}': "
                        f"expected {src_count}, found {dst_count} in target."
                    )

        return summary
    finally:
        src_engine.dispose()
        dst_engine.dispose()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Athar data from SQLite instance/dev.db to ToolsDB MariaDB."
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SQLITE_PATH,
        help=f"Source SQLite file path or URI (default: {DEFAULT_SQLITE_PATH})",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Target SQLAlchemy URI (defaults to resolved Config URI / ToolsDB envvars).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate source and check that target tables are empty without writing.",
    )
    args = parser.parse_args()

    source_uri = _normalize_source_uri(args.source)
    target_uri = args.target or resolve_database_uri()

    if target_uri.startswith("sqlite") and not args.target and not args.dry_run:
        raise SystemExit(
            "Error: Target resolved to local SQLite instead of MariaDB. "
            "Run inside Toolforge envvars (TOOL_TOOLSDB_USER / TOOL_TOOLSDB_PASSWORD), "
            "set DATABASE_URL, or pass --target explicitly."
        )

    redacted_target = make_url(target_uri).render_as_string(hide_password=True)
    print(f"[Migrate] Source: {source_uri}")
    print(f"[Migrate] Target: {redacted_target}")
    if args.dry_run:
        print("[Migrate] Mode: DRY RUN (no data will be written)")

    summary = migrate_database(source_uri, target_uri, dry_run=args.dry_run)
    for table_name, counts in summary.items():
        print(f"  - {table_name}: source={counts['source']}, copied={counts['copied']}")

    print("[Migrate] Done.")


if __name__ == "__main__":
    main()

