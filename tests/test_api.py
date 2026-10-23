import sys
import os
import unittest
from datetime import datetime, date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models import Community, User, CommunityMember, StatSnapshot, Project

from config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    MOCK_AUTH = True

class TestApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            # Seed test community
            self.community = Community(
                name="Wikimedia Morocco",
                slug="wm-ma",
                meta_roster_page="Wikimedia_MA/Members",
                default_wiki="ar.wikipedia.org",
                contact_email="contact@wikimedia.ma"
            )
            db.session.add(self.community)

            # Seed test user & member
            self.user = User(username="MoroccoVolunteer", is_member=True)
            db.session.add(self.user)
            db.session.flush()

            self.member = CommunityMember(
                community_id=self.community.id,
                user_id=self.user.id,
                role="coordinator",
                verified=True
            )
            self.snapshot = StatSnapshot(
                user_id=self.user.id,
                total_edits=450,
                home_wiki="ar.wikipedia.org"
            )
            db.session.add_all([self.member, self.snapshot])

            # Seed projects
            self.p1 = Project(
                community_id=self.community.id,
                title="Wikipedia Workshop",
                description="<p>Hands-on session</p>",
                project_type="Workshop",
                target_wiki="ar.wikipedia.org",
                status="Completed",
                start_date=date(2026, 1, 10),
                end_date=date(2026, 1, 12),
                lead_organizer="MoroccoVolunteer",
                co_organizers=["UserB"],
                is_contest=False
            )
            self.p2 = Project(
                community_id=self.community.id,
                title="Photo Contest",
                description="<p>Heritage photo drive</p>",
                project_type="Contest",
                target_wiki="commons.wikimedia.org",
                status="In Progress",
                lead_organizer="MoroccoVolunteer",
                co_organizers=[],
                is_contest=True,
                jury_members=["JuryA"]
            )
            db.session.add_all([self.p1, self.p2])
            db.session.commit()
            self.p1_id = self.p1.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_get_communities(self):
        res = self.client.get("/api/communities")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["slug"], "wm-ma")

    def test_global_stats(self):
        res = self.client.get("/api/stats")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["total_members"], 1)
        self.assertEqual(data["total_projects"], 2)
        self.assertEqual(data["total_edits"], 450)

    def test_community_stats(self):
        res = self.client.get("/api/wm-ma/stats")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["total_members"], 1)
        self.assertEqual(data["total_projects"], 2)
        self.assertEqual(data["total_edits"], 450)

        # 404 for unknown community
        res_404 = self.client.get("/api/unknown-slug/stats")
        self.assertEqual(res_404.status_code, 404)

    def test_community_members(self):
        res = self.client.get("/api/wm-ma/members")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["username"], "MoroccoVolunteer")
        self.assertEqual(data[0]["role"], "coordinator")
        self.assertEqual(data[0]["total_edits"], 450)

    def test_scoped_projects_and_filtering(self):
        # All projects
        res = self.client.get("/api/wm-ma/projects")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data), 2)

        # Filter by status
        res_completed = self.client.get("/api/wm-ma/projects?status=Completed")
        self.assertEqual(res_completed.status_code, 200)
        data_completed = res_completed.get_json()
        self.assertEqual(len(data_completed), 1)
        self.assertEqual(data_completed[0]["title"], "Wikipedia Workshop")

        # Filter by type
        res_contest = self.client.get("/api/wm-ma/projects?type=Contest")
        self.assertEqual(res_contest.status_code, 200)
        data_contest = res_contest.get_json()
        self.assertEqual(len(data_contest), 1)
        self.assertEqual(data_contest[0]["title"], "Photo Contest")

        # Filter by target wiki
        res_commons = self.client.get("/api/wm-ma/projects?target_wiki=commons.wikimedia.org")
        self.assertEqual(res_commons.status_code, 200)
        data_commons = res_commons.get_json()
        self.assertEqual(len(data_commons), 1)
        self.assertEqual(data_commons[0]["title"], "Photo Contest")

    def test_create_project_and_xss_sanitization(self):
        payload = {
            "title": "Edit-a-thon",
            "description": "Safe text <script>alert('xss')</script> <b>Bold text</b>",
            "project_type": "Edit-a-thon",
            "target_wiki": "ar.wikipedia.org",
            "status": "Planned",
            "co_organizers": ["UserX", "UserY"],
            "is_contest": True,
            "jury_members": ["Jury1"]
        }
        res = self.client.post("/api/wm-ma/projects", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertIn("project", data)
        p = data["project"]
        self.assertEqual(p["title"], "Edit-a-thon")
        # Ensure bleach sanitized the script tag
        self.assertNotIn("<script>", p["description"])
        self.assertIn("<b>Bold text</b>", p["description"])

    def test_create_project_validation(self):
        # Empty title should fail
        res = self.client.post("/api/wm-ma/projects", json={"title": "   "})
        self.assertEqual(res.status_code, 400)

    def test_update_project(self):
        pid = self.p1_id

        update_payload = {
            "title": "Updated Workshop Title",
            "description": "Updated <a href='https://example.org'>link</a>",
            "status": "In Progress"
        }
        res = self.client.put(f"/api/wm-ma/projects/{pid}", json=update_payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["project"]["title"], "Updated Workshop Title")
        self.assertEqual(data["project"]["status"], "In Progress")

    def test_export_csv(self):
        res = self.client.get("/api/wm-ma/export?format=csv")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers.get("Content-Type", ""))
        self.assertIn("athar_wm-ma_projects.csv", res.headers.get("Content-Disposition", ""))
        self.assertIn(b"Wikipedia Workshop", res.data)

        # Invalid format
        res_bad = self.client.get("/api/wm-ma/export?format=json")
        self.assertEqual(res_bad.status_code, 400)

if __name__ == "__main__":
    unittest.main()
