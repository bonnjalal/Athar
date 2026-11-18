from datetime import date, datetime
import os
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models import Community, CommunityMember, Project, ProjectTag, User
from app.wiki_utils import validate_activity_wiki_url
from config import Config
from scripts.migrate_v3 import run_migration as run_migration_v3
from scripts.sync_data import sync_active_project_statuses, sync_project_contributors


class StrictGovernanceConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = True
    MOCK_AUTH = False


def _extract_csrf_token(html_bytes: bytes) -> str:
    html = html_bytes.decode("utf-8", errors="ignore")
    m = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
    if m:
        return m.group(1)
    m2 = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return m2.group(1) if m2 else ""


class TestPhase1GovernanceAndDiscovery(unittest.TestCase):
    def setUp(self):
        self.app = create_app(StrictGovernanceConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            self.comm_ma = Community(
                name="Wikimedia Morocco",
                slug="wm-ma",
                meta_roster_page="Wikimedia_MA_User_Group/Members",
            )
            self.comm_tn = Community(
                name="Wikimedia Tunisia",
                slug="wm-tn",
                meta_roster_page="Wikimedia_Tunisie/Membres",
            )
            self.admin_user = User(username="Bonnjalal00", is_member=False, is_admin=True)
            self.backup_admin = User(username="SecondAdmin", is_member=True, is_admin=True)
            self.member_user = User(username="ActiveMember", is_member=True, is_admin=False)
            self.non_member = User(username="OutsiderUser", is_member=False, is_admin=False)
            db.session.add_all(
                [self.comm_ma, self.comm_tn, self.admin_user, self.backup_admin, self.member_user, self.non_member]
            )
            db.session.flush()

            db.session.add(
                CommunityMember(community_id=self.comm_ma.id, user_id=self.member_user.id, role="member")
            )
            db.session.commit()
            self.comm_ma_id = self.comm_ma.id
            self.comm_tn_id = self.comm_tn.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _login(self, username):
        with self.app.app_context():
            u = User.query.filter_by(username=username).first()
            is_member = bool(u.is_member) if u else False
            is_admin = bool(u.is_admin) if u else False
        with self.client.session_transaction() as sess:
            sess.clear()
            sess["username"] = username
            sess["is_member"] = is_member
            sess["is_admin"] = is_admin

    def _get_csrf(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        return _extract_csrf_token(res.data)

    def test_mock_auth_startup_guard(self):
        class BadProdConfig(Config):
            TESTING = False
            DEBUG = False
            MOCK_AUTH = True
            OAUTH_CLIENT_ID = ""
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

        with self.assertRaises(RuntimeError):
            create_app(BadProdConfig)

        class BadMixedOAuthConfig(Config):
            TESTING = False
            DEBUG = True
            MOCK_AUTH = True
            OAUTH_CLIENT_ID = "real-oauth-client-id"
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

        with self.assertRaises(RuntimeError):
            create_app(BadMixedOAuthConfig)

        class ValidPlaceholderDebugConfig(Config):
            TESTING = False
            DEBUG = True
            MOCK_AUTH = True
            OAUTH_CLIENT_ID = "your-meta-client-id-here"
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

        ok_app = create_app(ValidPlaceholderDebugConfig)
        self.assertIsNotNone(ok_app)

    def test_oauth_callback_provisioning_and_no_repromotion(self):
        # Revoke Bonnjalal00 while SecondAdmin remains active
        with self.app.app_context():
            bonn = User.query.filter_by(username="Bonnjalal00").first()
            bonn.is_admin = False
            db.session.commit()

        from app.oauth import oauth

        with patch.object(oauth.wikimedia, "authorize_access_token", return_value={"access_token": "tok"}):
            # 1. Brand new un-rostered user gets is_member=False, is_admin=False
            with patch.object(
                oauth.wikimedia,
                "get",
                return_value=MagicMock(json=lambda: {"username": "Brand_New_Wiki_User"}),
            ):
                res = self.client.get("/oauth/callback")
                self.assertEqual(res.status_code, 302)

            with self.app.app_context():
                new_u = User.query.filter_by(username="Brand New Wiki User").first()
                self.assertIsNotNone(new_u)
                self.assertFalse(new_u.is_member)
                self.assertFalse(new_u.is_admin)

            # 2. Previously revoked seeded admin stays non-admin on re-login
            with patch.object(
                oauth.wikimedia,
                "get",
                return_value=MagicMock(json=lambda: {"username": "Bonnjalal00"}),
            ):
                res = self.client.get("/oauth/callback")
                self.assertEqual(res.status_code, 302)

            with self.app.app_context():
                bonn = User.query.filter_by(username="Bonnjalal00").first()
                self.assertFalse(bonn.is_admin)

    def test_validate_activity_wiki_url_cases(self):
        self.assertIsNone(validate_activity_wiki_url(""))
        self.assertIsNone(validate_activity_wiki_url("   "))
        self.assertIsNone(validate_activity_wiki_url(None))

        self.assertEqual(
            validate_activity_wiki_url("http://eventmetrics.wmcloud.org"),
            "https://eventmetrics.wmcloud.org",
        )
        self.assertEqual(
            validate_activity_wiki_url("outreachdashboard.wmflabs.org/courses/MA/Workshop"),
            "https://outreachdashboard.wmflabs.org/courses/MA/Workshop",
        )
        self.assertEqual(
            validate_activity_wiki_url("https://athar.toolforge.org/wm-ma/"),
            "https://athar.toolforge.org/wm-ma/",
        )
        self.assertEqual(
            validate_activity_wiki_url("https://ar.wikipedia.org/wiki/ويكيبيديا:مشروع"),
            "https://ar.wikipedia.org/wiki/ويكيبيديا:مشروع",
        )

        invalid_urls = [
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "ftp://ar.wikipedia.org/file",
            "https://evil.com@ar.wikipedia.org/wiki/Main_Page",
            "https://ar.wikipedia.org:8443/wiki/Main_Page",
            "https://ar.wikipedia.org:badport/wiki/Main_Page",
            "https://ar.wikipedia.org\\wiki\\Test",
            "https://ar.wikipedia.org/wiki/Has Space",
            "https://evil.example.org/phishing",
            "https://ar.wikipedia.org/wiki/" + ("a" * 1020),
        ]
        for bad in invalid_urls:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_activity_wiki_url(bad)

    def test_rbac_matrix_and_csrf_protection(self):
        with self.app.app_context():
            p = Project(
                community_id=self.comm_ma_id,
                title="Member Activity",
                description="<p>Desc</p>",
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 2),
                status="In Progress",
                lead_organizer="ActiveMember",
            )
            db.session.add(p)
            db.session.commit()
            pid = p.id

        # 1. Anonymous user
        anon_csrf = self._get_csrf()
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.assertEqual(self.client.post("/wm-ma/sync").status_code, 400)
        self.assertEqual(self.client.post("/wm-ma/sync", data={"csrf_token": anon_csrf}).status_code, 302)

        # 2. Outsider (is_member=False, is_admin=False)
        self._login("OutsiderUser")
        token = self._get_csrf()
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.assertEqual(self.client.get("/project/new").status_code, 403)
        self.assertEqual(self.client.post("/wm-ma/sync", data={"csrf_token": token}).status_code, 403)
        self.assertEqual(self.client.get(f"/project/{pid}/edit").status_code, 403)

        # 3. ActiveMember (is_member=True, is_admin=False)
        self._login("ActiveMember")
        token = self._get_csrf()
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.assertEqual(self.client.post("/add-community", data={"csrf_token": token}).status_code, 403)
        self.assertEqual(self.client.get(f"/project/{pid}/edit").status_code, 200)

        # Missing CSRF token on mutating API routes MUST be rejected with 400
        res_no_csrf = self.client.post("/api/wm-ma/projects", json={"title": "No CSRF"})
        self.assertEqual(res_no_csrf.status_code, 400)
        res_put_no_csrf = self.client.put(f"/api/projects/{pid}", json={"title": "No CSRF Put"})
        self.assertEqual(res_put_no_csrf.status_code, 400)

        # Valid CSRF header succeeds
        res_with_csrf = self.client.post(
            "/api/wm-ma/projects",
            json={"title": "API With CSRF", "campaign": "1Lib1Ref", "tags": ["glam", "#Library"]},
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(res_with_csrf.status_code, 201)
        self.assertEqual(res_with_csrf.get_json()["project"]["tags"], ["glam", "library"])

        # 4. Tool Admin with is_member=False passes @member_required and can edit any project
        self._login("Bonnjalal00")
        token = self._get_csrf()
        self.assertEqual(self.client.get("/admin").status_code, 200)
        self.assertEqual(self.client.get("/project/new").status_code, 200)
        self.assertEqual(self.client.get(f"/project/{pid}/edit").status_code, 200)

    def test_admin_community_slug_edit_and_admin_grant_revoke(self):
        self._login("Bonnjalal00")
        token = self._get_csrf()

        # Reserved slug rejected with 400
        res_res = self.client.post(
            f"/admin/community/{self.comm_ma_id}/edit",
            data={
                "csrf_token": token,
                "name": "Wikimedia Morocco",
                "slug": "activities",
                "meta_roster_page": "Wikimedia_MA_User_Group/Members",
            },
        )
        self.assertEqual(res_res.status_code, 400)

        # Non-ASCII slug rejected with 400
        res_bad_slug = self.client.post(
            f"/admin/community/{self.comm_ma_id}/edit",
            data={
                "csrf_token": token,
                "name": "Wikimedia Morocco",
                "slug": "المغرب_1",
                "meta_roster_page": "Wikimedia_MA_User_Group/Members",
            },
        )
        self.assertEqual(res_bad_slug.status_code, 400)

        # Valid slug edit updates route and preserves relationships
        with self.client.session_transaction() as sess:
            sess["community_slug"] = "wm-ma"
        res_ok = self.client.post(
            f"/admin/community/{self.comm_ma_id}/edit",
            data={
                "csrf_token": token,
                "name": "Wikimedia Morocco Renamed",
                "slug": "morocco-ug",
                "meta_roster_page": "Wikimedia_MA_User_Group/Members",
            },
            follow_redirects=False,
        )
        self.assertEqual(res_ok.status_code, 302)
        self.assertEqual(self.client.get("/morocco-ug/").status_code, 200)

        # Grant admin to non-existent local Wikimedia user via CentralAuth mock
        with patch("app.routes.admin.verify_wikimedia_username", return_value={"exists": True, "username": "NewToolAdmin"}):
            res_grant = self.client.post(
                "/admin/admins/grant",
                data={"csrf_token": token, "username": "NewToolAdmin"},
            )
            self.assertEqual(res_grant.status_code, 302)

        with self.app.app_context():
            u = User.query.filter_by(username="NewToolAdmin").first()
            self.assertIsNotNone(u)
            self.assertTrue(u.is_admin)
            self.assertFalse(u.is_member)
            new_admin_id = u.id
            bonn_id = User.query.filter_by(username="Bonnjalal00").first().id

        # Self-revocation blocked (400)
        res_self = self.client.post(
            "/admin/admins/revoke",
            data={"csrf_token": token, "user_id": str(bonn_id)},
        )
        self.assertEqual(res_self.status_code, 400)

        # Revoke works while >1 admins remain
        res_rev = self.client.post(
            "/admin/admins/revoke",
            data={"csrf_token": token, "user_id": str(new_admin_id)},
        )
        self.assertEqual(res_rev.status_code, 302)

        # Revoking SecondAdmin leaves Bonnjalal00 as the sole admin
        with self.app.app_context():
            second_id = User.query.filter_by(username="SecondAdmin").first().id
        self.client.post("/admin/admins/revoke", data={"csrf_token": token, "user_id": str(second_id)})

        # Verify DB still has 1 admin
        with self.app.app_context():
            self.assertEqual(User.query.filter(User.is_admin.is_(True)).count(), 1)

    def test_soft_delete_restore_purge_and_full_exclusion(self):
        with self.app.app_context():
            p_del = Project(
                community_id=self.comm_ma_id,
                title="Secret Deleted Event",
                description="<p>Hidden</p>",
                project_type="Workshop",
                target_wiki="arwiki",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 5),
                status="In Progress",
                lead_organizer="ActiveMember",
                participants=["UniqueGhostParticipant"],
            )
            p_keep = Project(
                community_id=self.comm_ma_id,
                title="Visible Active Event",
                description="<p>Public</p>",
                project_type="Workshop",
                target_wiki="arwiki",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 5),
                status="In Progress",
                lead_organizer="ActiveMember",
            )
            db.session.add_all([p_del, p_keep])
            db.session.commit()
            del_id = p_del.id

        self._login("Bonnjalal00")
        token = self._get_csrf()

        # Purge before soft-delete is rejected
        self.assertEqual(
            self.client.post(
                f"/admin/project/{del_id}/purge",
                data={"csrf_token": token, "confirm_project_id": str(del_id)},
            ).status_code,
            400,
        )

        # Soft-delete succeeds (follow_redirects consumes flash message)
        res_sd = self.client.post(
            f"/admin/project/{del_id}/soft-delete",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        self.assertEqual(res_sd.status_code, 200)

        # Verify soft-deleted project is excluded from all public/API/report/export endpoints
        self.assertNotIn(b"Secret Deleted Event", self.client.get("/").data)
        self.assertNotIn(b"Secret Deleted Event", self.client.get("/activities").data)
        self.assertNotIn(b"Secret Deleted Event", self.client.get("/wm-ma/").data)
        self.assertNotIn(b"Secret Deleted Event", self.client.get("/wm-ma/activities").data)
        self.assertEqual(self.client.get(f"/project/{del_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/project/{del_id}/edit").status_code, 404)
        self.assertEqual(self.client.get(f"/project/{del_id}/report").status_code, 404)
        self.assertEqual(self.client.get("/user/UniqueGhostParticipant").status_code, 404)
        self.assertEqual(self.client.get("/user/UniqueGhostParticipant/report").status_code, 404)
        self.assertNotIn(b"Secret Deleted Event", self.client.get("/user/ActiveMember").data)
        self.assertNotIn(b"Secret Deleted Event", self.client.get("/wm-ma/report").data)
        self.assertNotIn(b"Secret Deleted Event", self.client.get("/user/ActiveMember/report").data)

        self.assertEqual(self.client.get("/api/stats").get_json()["total_projects"], 1)
        self.assertEqual(self.client.get("/api/wm-ma/stats").get_json()["total_projects"], 1)
        self.assertEqual(len(self.client.get("/api/projects").get_json()), 1)
        self.assertEqual(len(self.client.get("/api/wm-ma/projects").get_json()), 1)
        self.assertEqual(self.client.get(f"/api/projects/{del_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/projects/{del_id}/export?format=csv").status_code, 404)
        self.assertNotIn(b"Secret Deleted Event", self.client.get("/api/wm-ma/export?format=csv").data)
        self.assertNotIn(b"Secret Deleted Event", self.client.get("/api/users/ActiveMember/export?format=csv").data)

        # sync_project_contributors ignores soft-deleted projects
        with self.app.app_context():
            with patch("scripts.sync_data.fetch_global_stats", return_value=None):
                sync_project_contributors()
                self.assertIsNone(User.query.filter_by(username="UniqueGhostParticipant").first())

        # Restore works
        self.client.post(f"/admin/project/{del_id}/restore", data={"csrf_token": token})
        self.assertEqual(self.client.get(f"/project/{del_id}").status_code, 200)

        # Soft-delete again, wrong confirm ID -> 400, exact confirm ID -> permanently removed
        self.client.post(f"/admin/project/{del_id}/soft-delete", data={"csrf_token": token})
        self.assertEqual(
            self.client.post(
                f"/admin/project/{del_id}/purge",
                data={"csrf_token": token, "confirm_project_id": "999999"},
            ).status_code,
            400,
        )
        res_purge = self.client.post(
            f"/admin/project/{del_id}/purge",
            data={"csrf_token": token, "confirm_project_id": str(del_id)},
        )
        self.assertEqual(res_purge.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Project, del_id))

    def test_landing_global_activities_tags_and_form_ux(self):
        with self.app.app_context():
            # Seed 7 In Progress projects across two communities -> landing caps at 6
            for i in range(7):
                p = Project(
                    community_id=self.comm_ma_id if i % 2 == 0 else self.comm_tn_id,
                    title=f"Running Event {i}",
                    description="<p>Details</p>",
                    project_type="Workshop",
                    target_wiki="arwiki",
                    campaign="Wiki Loves Ramadan" if i == 0 else "Wiki Loves Africa",
                    start_date=date(2026, 2, 10 + i),
                    end_date=date(2026, 4, 10 + i),
                    status="In Progress",
                    lead_organizer="ActiveMember",
                )
                db.session.add(p)
                db.session.flush()
                if i == 0:
                    db.session.add(ProjectTag(project_id=p.id, tag="ramadan"))
                    db.session.add(ProjectTag(project_id=p.id, tag="heritage"))
            p_cancel = Project(
                community_id=self.comm_ma_id,
                title="Canceled Summit",
                description="<p>Canceled</p>",
                project_type="Conference / Meetup",
                target_wiki="metawiki",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 2),
                status="Canceled",
                lead_organizer="ActiveMember",
            )
            db.session.add(p_cancel)
            db.session.commit()

        # Anonymous user sees header links on /, no Add Community form, and 6 running cards max
        res_home = self.client.get("/")
        self.assertEqual(res_home.status_code, 200)
        html_home = res_home.data.decode("utf-8")
        self.assertIn('href="/activities"', html_home)
        self.assertNotIn('action="/add-community"', html_home)
        self.assertEqual(html_home.count("Running Event"), 6)

        # Global /activities filter tests
        self.assertEqual(len(self.client.get("/api/projects?tag=ramadan,heritage").get_json()), 1)
        self.assertEqual(len(self.client.get("/api/projects?tag=ramadan,nonexistent").get_json()), 0)
        self.assertEqual(len(self.client.get("/api/projects?campaign=Ramadan").get_json()), 1)
        self.assertEqual(len(self.client.get("/api/projects?month=3").get_json()), 7)
        self.assertEqual(len(self.client.get("/api/projects?year=1999").get_json()), 0)
        self.assertEqual(len(self.client.get("/api/projects?status=Canceled").get_json()), 1)
        self.assertEqual(len(self.client.get("/api/projects?community=unknown-slug").get_json()), 0)

        # Single date/status IDs in project_form.html & HTTP 400 retains input
        self._login("ActiveMember")
        form_html = self.client.get("/project/new").data.decode("utf-8")
        self.assertEqual(form_html.count('id="start_date"'), 1)
        self.assertEqual(form_html.count('id="end_date"'), 1)
        self.assertEqual(form_html.count('id="status"'), 1)

        token = _extract_csrf_token(form_html.encode("utf-8"))
        res_bad = self.client.post(
            "/project/new",
            data={
                "csrf_token": token,
                "title": "Preserved Title Value",
                "description": "<p>Test</p>",
                "wiki_link": "https://evil.com/bad",
                "campaign": "WikiGap",
                "tags": "women, gaps",
                "start_date": "2026-06-01",
                "end_date": "2026-06-02",
            },
        )
        self.assertEqual(res_bad.status_code, 400)
        self.assertIn(b"Preserved Title Value", res_bad.data)
        self.assertIn(b"https://evil.com/bad", res_bad.data)
        self.assertIn(b"WikiGap", res_bad.data)

        # Check tag > 20 rejection
        too_many_tags = ",".join(f"tag{i}" for i in range(21))
        res_too_many = self.client.post(
            "/api/wm-ma/projects",
            json={"title": "Too Many Tags", "tags": too_many_tags.split(",")},
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(res_too_many.status_code, 400)

        # GET dashboard and scheduled sync preserve Canceled
        self.client.get("/wm-ma/")
        with self.app.app_context():
            sync_active_project_statuses()
            c_proj = Project.query.filter_by(title="Canceled Summit").first()
            self.assertEqual(c_proj.status, "Canceled")

    def test_migrate_v3_idempotent_from_v2_schema(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
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
                    participants JSON,
                    results JSON,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
            conn.execute(text("""
                INSERT INTO projects (title, description, project_type, target_wiki, status, lead_organizer)
                VALUES ('Legacy V2 Event', '<p>Keep me</p>', 'Workshop', 'arwiki', 'Completed', 'UserA')
            """))

        actions1 = run_migration_v3(engine)
        self.assertTrue(len(actions1) > 0)
        actions2 = run_migration_v3(engine)
        self.assertEqual(actions2, [])

        insp = inspect(engine)
        self.assertIn("project_tags", insp.get_table_names())
        proj_cols = {c["name"] for c in insp.get_columns("projects")}
        self.assertTrue({"wiki_link", "campaign", "primary_lang", "translations", "is_deleted"}.issubset(proj_cols))

        with engine.connect() as conn:
            bonn = conn.execute(text("SELECT is_member, is_admin FROM users WHERE username='Bonnjalal00'")).fetchone()
            self.assertIsNotNone(bonn)
            self.assertEqual(bonn[0], 0)
            self.assertEqual(bonn[1], 1)
            legacy = conn.execute(text("SELECT title, is_deleted FROM projects WHERE id=1")).fetchone()
            self.assertEqual(legacy[0], "Legacy V2 Event")
            self.assertEqual(legacy[1], 0)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
