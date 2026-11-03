#!/usr/bin/env python3
"""
scripts/migrate_v2.py

Database migration script for Athar v2:
- Adds 'participants' (JSON) column to 'projects' table if missing.
- Adds 'results' (JSON) column to 'projects' table if missing.
- Creates index on 'projects.lead_organizer' if missing.
- Creates composite index on 'stat_snapshots (user_id, recorded_at DESC)' if missing.

Supports both SQLite and Toolforge ToolsDB MariaDB.
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import inspect, text


def run_migration(engine=None):
    """
    Executes idempotent migration against the provided engine or the default app database engine.
    Returns a list of actions executed.
    """
    if engine is None:
        from app import create_app, db
        app = create_app()
        with app.app_context():
            return _execute_migration(db.engine)
    else:
        return _execute_migration(engine)


def _execute_migration(engine):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    actions = []

    with engine.begin() as conn:
        # 1. Projects table alterations
        if "projects" in tables:
            columns = [col["name"] for col in inspector.get_columns("projects")]
            
            if "participants" not in columns:
                conn.execute(text("ALTER TABLE projects ADD COLUMN participants JSON NULL"))
                actions.append("added column projects.participants")
                print("  [+] Added column 'participants' to 'projects'")
            else:
                print("  [-] Column 'participants' already exists in 'projects'")

            if "results" not in columns:
                conn.execute(text("ALTER TABLE projects ADD COLUMN results JSON NULL"))
                actions.append("added column projects.results")
                print("  [+] Added column 'results' to 'projects'")
            else:
                print("  [-] Column 'results' already exists in 'projects'")

            # Check indexes on projects
            existing_project_indexes = [idx["name"] for idx in inspector.get_indexes("projects") if idx.get("name")]
            if "ix_projects_lead_organizer" not in existing_project_indexes:
                try:
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_projects_lead_organizer ON projects (lead_organizer)"))
                    actions.append("created index ix_projects_lead_organizer")
                    print("  [+] Created index 'ix_projects_lead_organizer' on 'projects (lead_organizer)'")
                except Exception as e:
                    print(f"  [!] Note on creating ix_projects_lead_organizer: {e}")

        # 2. Stat snapshots table indexes
        if "stat_snapshots" in tables:
            existing_snapshot_indexes = [idx["name"] for idx in inspector.get_indexes("stat_snapshots") if idx.get("name")]
            if "ix_stat_snapshots_user_recorded" not in existing_snapshot_indexes:
                try:
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_stat_snapshots_user_recorded ON stat_snapshots (user_id, recorded_at DESC)"))
                    actions.append("created index ix_stat_snapshots_user_recorded")
                    print("  [+] Created composite index 'ix_stat_snapshots_user_recorded' on 'stat_snapshots (user_id, recorded_at DESC)'")
                except Exception as e:
                    print(f"  [!] Note on creating ix_stat_snapshots_user_recorded: {e}")

    return actions


if __name__ == "__main__":
    print("Running Athar v2 database schema migration...")
    executed_actions = run_migration()
    print(f"Migration completed successfully. {len(executed_actions)} action(s) applied.")

