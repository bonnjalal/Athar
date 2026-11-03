import os
import sys
import unittest
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.migrate_v2 import run_migration


class TestMigrationV2(unittest.TestCase):
    def setUp(self):
        # Create an in-memory SQLite engine simulating v1 schema
        self.engine = create_engine("sqlite:///:memory:")
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE communities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(120) NOT NULL UNIQUE,
                    slug VARCHAR(64) NOT NULL UNIQUE,
                    meta_roster_page VARCHAR(255) NOT NULL,
                    contact_email VARCHAR(128),
                    created_at DATETIME NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(128) NOT NULL UNIQUE,
                    is_member BOOLEAN NOT NULL DEFAULT 1,
                    first_seen DATETIME,
                    last_synced DATETIME
                )
            """))
            conn.execute(text("""
                CREATE TABLE stat_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    total_edits INTEGER NOT NULL DEFAULT 0,
                    home_wiki VARCHAR(64) DEFAULT 'ar.wikipedia.org',
                    wiki_breakdown JSON,
                    recorded_at DATETIME
                )
            """))
            # Old v1 projects schema without participants and results, unindexed lead_organizer
            conn.execute(text("""
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    community_id INTEGER REFERENCES communities(id),
                    title VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL,
                    project_type VARCHAR(64) NOT NULL DEFAULT 'Workshop',
                    target_wiki VARCHAR(64) NOT NULL DEFAULT 'ar.wikipedia.org',
                    start_date DATE,
                    end_date DATE,
                    status VARCHAR(32) NOT NULL DEFAULT 'In Progress',
                    lead_organizer VARCHAR(128) NOT NULL,
                    co_organizers JSON,
                    is_contest BOOLEAN NOT NULL DEFAULT 0,
                    jury_members JSON,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
            # Insert sample legacy record
            conn.execute(text("""
                INSERT INTO projects (title, description, project_type, target_wiki, status, lead_organizer)
                VALUES ('Legacy Workshop', '<p>Test</p>', 'Workshop', 'ar.wikipedia.org', 'Completed', 'UserA')
            """))

    def test_migration_adds_columns_and_preserves_data(self):
        # 1. Verify legacy columns before migration
        insp_before = inspect(self.engine)
        cols_before = [c["name"] for c in insp_before.get_columns("projects")]
        self.assertNotIn("participants", cols_before)
        self.assertNotIn("results", cols_before)

        # 2. Run migration
        actions = run_migration(self.engine)
        self.assertIn("added column projects.participants", actions)
        self.assertIn("added column projects.results", actions)

        # 3. Verify columns exist after migration
        insp_after = inspect(self.engine)
        cols_after = [c["name"] for c in insp_after.get_columns("projects")]
        self.assertIn("participants", cols_after)
        self.assertIn("results", cols_after)

        # 4. Verify existing data preserved
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT id, title, lead_organizer, participants, results FROM projects WHERE id = 1")).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[1], "Legacy Workshop")
            self.assertEqual(row[2], "UserA")
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])

    def test_migration_is_idempotent(self):
        # Run first time
        actions1 = run_migration(self.engine)
        self.assertTrue(len(actions1) > 0)

        # Run second time on same engine
        actions2 = run_migration(self.engine)
        self.assertEqual(len(actions2), 0)

    def test_indexes_created(self):
        run_migration(self.engine)
        insp = inspect(self.engine)
        
        proj_idx_names = [idx["name"] for idx in insp.get_indexes("projects") if idx.get("name")]
        self.assertIn("ix_projects_lead_organizer", proj_idx_names)

        snap_idx_names = [idx["name"] for idx in insp.get_indexes("stat_snapshots") if idx.get("name")]
        self.assertIn("ix_stat_snapshots_user_recorded", snap_idx_names)


if __name__ == "__main__":
    unittest.main()

