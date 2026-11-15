import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config, resolve_database_uri
from app import create_app, db
from app.models import Community, CommunityMember, Project, StatSnapshot, User
from scripts.migrate_sqlite_to_mariadb import migrate_database
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


class TestToolsDbConfigAndTransfer(unittest.TestCase):
    def test_resolve_database_uri_precedence(self):
        self.assertEqual(
            resolve_database_uri({
                "DATABASE_URL": "mysql+pymysql://explicit:pw@host/db",
                "TOOL_TOOLSDB_USER": "s58235",
                "TOOL_TOOLSDB_PASSWORD": "ignored",
            }),
            "mysql+pymysql://explicit:pw@host/db",
        )
        self.assertEqual(
            resolve_database_uri({
                "TOOL_TOOLSDB_USER": "s58235",
                "TOOL_TOOLSDB_PASSWORD": "p@ss:w/ord%",
            }),
            "mysql+pymysql://s58235:p%40ss%3Aw%2Ford%25@tools.db.svc.wikimedia.cloud/s58235__athar?charset=utf8mb4",
        )
        self.assertEqual(resolve_database_uri({}), "sqlite:///dev.db")

    def test_migrate_database_preserves_ids_json_and_relations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = os.path.join(tmpdir, "src.db")
            dst_path = os.path.join(tmpdir, "dst.db")
            src_uri = f"sqlite:///{src_path}"
            dst_uri = f"sqlite:///{dst_path}"

            class SrcConfig(Config):
                TESTING = True
                SQLALCHEMY_DATABASE_URI = src_uri
                SQLALCHEMY_ENGINE_OPTIONS = {}

            app = create_app(SrcConfig)
            with app.app_context():
                comm = Community(
                    id=1,
                    name="ويكيميديا المغرب",
                    slug="ويكيميديا-المغرب",
                    meta_roster_page="Wikimedia MA User Group/Members",
                )
                user = User(id=7, username="DERDAKI ILIAS", is_member=True)
                db.session.add_all([comm, user])
                db.session.flush()

                db.session.add(CommunityMember(community_id=1, user_id=7, role="member"))
                db.session.add(
                    Project(
                        id=4,
                        community_id=1,
                        title="ويكي تهوى المعالم 2026 في المغرب",
                        description="<p>Contest</p>",
                        project_type="Contest",
                        target_wiki="commonswiki",
                        start_date=date(2026, 9, 1),
                        end_date=date(2026, 9, 30),
                        status="Completed",
                        lead_organizer="DERDAKI ILIAS",
                        co_organizers=["Essaidib2"],
                        is_contest=True,
                        jury_members=["Jury1"],
                        participants=["P1", "P2"],
                        results={"winners": ["P1"], "metrics": {"photos": 120}},
                        created_at=datetime(2026, 11, 5, 10, 0, 0),
                    )
                )
                db.session.add(
                    StatSnapshot(
                        id=99,
                        user_id=7,
                        total_edits=4321,
                        home_wiki="arwiki",
                        wiki_breakdown={"arwiki": 4000, "commonswiki": 321},
                        recorded_at=datetime(2026, 11, 14, 20, 0, 0),
                    )
                )
                db.session.commit()

            # Dry run checks source without creating target tables
            dry_summary = migrate_database(src_uri, dst_uri, dry_run=True)
            self.assertEqual(dry_summary["projects"]["source"], 1)
            self.assertEqual(dry_summary["projects"]["copied"], 0)
            dry_check_engine = create_engine(dst_uri)
            try:
                self.assertEqual(inspect(dry_check_engine).get_table_names(), [])
            finally:
                dry_check_engine.dispose()

            # Full migration
            summary = migrate_database(src_uri, dst_uri)
            self.assertEqual(summary["communities"], {"source": 1, "copied": 1})
            self.assertEqual(summary["users"], {"source": 1, "copied": 1})
            self.assertEqual(summary["community_members"], {"source": 1, "copied": 1})
            self.assertEqual(summary["projects"], {"source": 1, "copied": 1})
            self.assertEqual(summary["stat_snapshots"], {"source": 1, "copied": 1})

            # Verify transferred records via ORM against destination
            class DstConfig(Config):
                TESTING = True
                SQLALCHEMY_DATABASE_URI = dst_uri
                SQLALCHEMY_ENGINE_OPTIONS = {}

            dst_app = create_app(DstConfig)
            with dst_app.app_context():
                proj = db.session.get(Project, 4)
                self.assertIsNotNone(proj)
                self.assertEqual(proj.title, "ويكي تهوى المعالم 2026 في المغرب")
                self.assertEqual(proj.co_organizers, ["Essaidib2"])
                self.assertEqual(proj.results, {"winners": ["P1"], "metrics": {"photos": 120}})

                snap = db.session.get(StatSnapshot, 99)
                self.assertEqual(snap.total_edits, 4321)
                self.assertEqual(snap.wiki_breakdown, {"arwiki": 4000, "commonswiki": 321})

            # Re-running against non-empty target must abort safely
            with self.assertRaises(RuntimeError):
                migrate_database(src_uri, dst_uri)


if __name__ == "__main__":
    unittest.main()

