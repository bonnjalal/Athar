import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models import Project, Community

from config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False

class TestRoutesAndSecurity(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_dashboard_accessible(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Athar", response.data)

    def test_mock_auth_login(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "TestVolunteer"
            sess["is_member"] = True

        response = self.client.get("/project/new")
        self.assertEqual(response.status_code, 200)

    def test_create_project_web(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "TestVolunteer"
            sess["is_member"] = True

        response = self.client.post("/project/new", data={
            "title": "Web Test Project",
            "description": "Created from web interface",
            "project_type": "Workshop",
            "target_wiki": "ar.wikipedia.org",
            "status": "In Progress"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            p = Project.query.filter_by(title="Web Test Project").first()
            self.assertIsNotNone(p)
            self.assertEqual(p.lead_organizer, "TestVolunteer")

    def test_create_contest_with_chips_web(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "MoroccoLead"
            sess["is_member"] = True

        response = self.client.post("/project/new", data={
            "title": "Wiki Loves Monuments Contest",
            "description": "Annual photo competition with jury",
            "project_type": "Contest",
            "target_wiki": "commons",
            "status": "In Progress",
            "co_organizers": "Houssain tork,Taloubant",
            "is_contest": "1",
            "jury_members": "RACHID BAYA,DERDAKI ILIAS"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            p = Project.query.filter_by(title="Wiki Loves Monuments Contest").first()
            self.assertIsNotNone(p)
            self.assertTrue(p.is_contest)
            self.assertEqual(p.co_organizers, ["Houssain tork", "Taloubant"])
            self.assertEqual(p.jury_members, ["RACHID BAYA", "DERDAKI ILIAS"])
            self.assertEqual(p.target_wiki, "commonswiki")
            self.assertEqual(p.target_wiki_url, "https://commons.wikimedia.org")

    def test_login_mock_auth_redirects_cleanly(self):
        # Without prior community
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/")

        # With prior community slug in session
        with self.client.session_transaction() as sess:
            sess["community_slug"] = "wm-ma"
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/wm-ma/")

    def test_logout_redirects_cleanly(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "TestVolunteer"
            sess["is_member"] = True
        res = self.client.get("/logout")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/")

    def test_add_community_requires_auth(self):
        res = self.client.post("/add-community", data={
            "community_name": "Wikimedia Test Community",
            "community_link": "https://meta.wikimedia.org/wiki/Test_Group/Members"
        })
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location"))

    def test_add_community_persists_to_db(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "MoroccoVolunteer"

        res = self.client.post("/add-community", data={
            "community_name": "Wikimedia Algeria",
            "community_link": "https://meta.wikimedia.org/wiki/Wikimedia_DZ/Members",
            "contact_email": "contact@dz.wikimedia.org"
        }, follow_redirects=False)

        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/wikimedia-algeria/")

        with self.app.app_context():
            comm = Community.query.filter_by(slug="wikimedia-algeria").first()
            self.assertIsNotNone(comm)
            self.assertEqual(comm.name, "Wikimedia Algeria")
            self.assertEqual(comm.meta_roster_page, "https://meta.wikimedia.org/wiki/Wikimedia_DZ/Members")

    def test_index_displays_db_communities(self):
        with self.app.app_context():
            comm = Community(
                name="Wikimedia Libya",
                slug="wm-ly",
                meta_roster_page="https://meta.wikimedia.org/wiki/Wikimedia_Libya/Members"
            )
            db.session.add(comm)
            db.session.commit()

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Wikimedia Libya", res.data)
        self.assertIn(b"wm-ly", res.data)

    def test_create_project_web_custom_type(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "TestVolunteer"
            sess["is_member"] = True

        response = self.client.post("/project/new", data={
            "title": "Custom Activity Project",
            "description": "Activity with a custom specified type",
            "project_type": "Other",
            "custom_project_type": "ندوة فكرية وثقافية",
            "target_wiki": "ar.wikipedia.org",
            "status": "In Progress"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            p = Project.query.filter_by(title="Custom Activity Project").first()
            self.assertIsNotNone(p)
            self.assertEqual(p.project_type, "ندوة فكرية وثقافية")

    def test_edit_project_web_custom_type(self):
        with self.app.app_context():
            p = Project(
                title="Existing Workshop",
                description="Testing edit",
                project_type="Workshop",
                target_wiki="ar.wikipedia.org",
                status="In Progress",
                lead_organizer="MoroccoVolunteer"
            )
            db.session.add(p)
            db.session.commit()
            p_id = p.id

        with self.client.session_transaction() as sess:
            sess["username"] = "MoroccoVolunteer"
            sess["is_member"] = True

        response = self.client.post(f"/project/{p_id}/edit", data={
            "title": "Existing Workshop",
            "description": "Testing edit updated",
            "project_type": "Other",
            "custom_project_type": "بودكاست مجتمعي",
            "target_wiki": "ar.wikipedia.org",
            "status": "In Progress"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            updated = db.session.get(Project, p_id)
            self.assertEqual(updated.project_type, "بودكاست مجتمعي")

    def test_view_project_web(self):
        with self.app.app_context():
            p = Project(
                title="Public Workshop",
                description="Testing public view",
                project_type="Workshop",
                target_wiki="ar.wikipedia.org",
                status="In Progress",
                lead_organizer="MoroccoVolunteer"
            )
            db.session.add(p)
            db.session.commit()
            p_id = p.id

        response = self.client.get(f"/project/{p_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Public Workshop", response.data)
        self.assertIn(b"Testing public view", response.data)

    def test_create_project_wiki_normalization_and_security(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "TestVolunteer"
            sess["is_member"] = True

        # Valid project code 'commons'
        res_ok = self.client.post("/project/new", data={
            "title": "Photo Contest",
            "description": "Photo contest on commons",
            "project_type": "Contest",
            "target_wiki": "commons",
            "status": "In Progress"
        }, follow_redirects=True)
        self.assertEqual(res_ok.status_code, 200)

        with self.app.app_context():
            p = Project.query.filter_by(title="Photo Contest").first()
            self.assertIsNotNone(p)
            self.assertEqual(p.target_wiki, "commonswiki")
            self.assertEqual(p.target_wiki_url, "https://commons.wikimedia.org")

        # Malicious / invalid target wiki must be rejected
        res_bad = self.client.post("/project/new", data={
            "title": "Malicious Project",
            "description": "SSRF / Open Redirect attempt",
            "project_type": "Workshop",
            "target_wiki": "evil.com",
            "status": "In Progress"
        }, follow_redirects=True)
        self.assertEqual(res_bad.status_code, 400)
        self.assertIn(b"Invalid Wikimedia project identifier", res_bad.data)

    def test_community_tabs_and_activities_page(self):
        with self.app.app_context():
            comm = Community(name="Wikimedia Morocco", slug="wm-ma", meta_roster_page="WM_MA/Members")
            db.session.add(comm)
            db.session.commit()

            p1 = Project(
                community_id=comm.id,
                title="Active Workshop",
                description="Running now",
                project_type="Workshop",
                target_wiki="arwiki",
                status="In Progress",
                lead_organizer="MoroccoVolunteer"
            )
            p2 = Project(
                community_id=comm.id,
                title="Finished Editathon",
                description="Completed past event",
                project_type="Edit-a-thon",
                target_wiki="arwiki",
                status="Completed",
                lead_organizer="MoroccoVolunteer"
            )
            db.session.add_all([p1, p2])
            db.session.commit()

        # Test Activities page
        res = self.client.get("/wm-ma/activities")
        self.assertEqual(res.status_code, 200)
        self.assertIn("الأنشطة".encode("utf-8"), res.data)
        self.assertIn("Active Workshop".encode("utf-8"), res.data)
        self.assertIn("dashboard-filters".encode("utf-8"), res.data)

    def test_community_users_page(self):
        with self.app.app_context():
            from app.models import User, CommunityMember, StatSnapshot
            comm = Community(name="Wikimedia Tunisia", slug="wm-tn", meta_roster_page="WM_TN/Members")
            db.session.add(comm)
            db.session.commit()

            u = User(username="TunisiaUser", is_member=True)
            db.session.add(u)
            db.session.commit()

            cm = CommunityMember(community_id=comm.id, user_id=u.id, role="Organizer")
            snap = StatSnapshot(user_id=u.id, total_edits=4500, home_wiki="ar.wikipedia.org")
            db.session.add_all([cm, snap])
            db.session.commit()

        # Test Users page
        res = self.client.get("/wm-tn/users")
        self.assertEqual(res.status_code, 200)
        self.assertIn("الأعضاء".encode("utf-8"), res.data)
        self.assertIn("TunisiaUser".encode("utf-8"), res.data)
        self.assertIn("user-search-input".encode("utf-8"), res.data)
        self.assertIn("4,500".encode("utf-8"), res.data)

    def test_community_dashboard_in_progress_only(self):
        with self.app.app_context():
            comm = Community(name="Wikimedia Egypt", slug="wm-eg", meta_roster_page="WM_EG/Members")
            db.session.add(comm)
            db.session.commit()

            p_in_prog = Project(
                community_id=comm.id,
                title="In Progress Sprint",
                description="Currently happening",
                project_type="Hackathon",
                target_wiki="arwiki",
                status="In Progress",
                lead_organizer="EgyptLead"
            )
            p_done = Project(
                community_id=comm.id,
                title="Old Finished Contest",
                description="Should not appear on overview",
                project_type="Contest",
                target_wiki="arwiki",
                status="Completed",
                lead_organizer="EgyptLead"
            )
            db.session.add_all([p_in_prog, p_done])
            db.session.commit()

        res = self.client.get("/wm-eg/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("In Progress Sprint".encode("utf-8"), res.data)
        self.assertNotIn("Old Finished Contest".encode("utf-8"), res.data)

    def test_check_user_api(self):
        # Missing username
        res = self.client.get("/api/check-user")
        self.assertEqual(res.status_code, 400)

        # Existing local user
        with self.app.app_context():
            from app.models import User
            u = User(username="ExistingLocalMember", is_member=True)
            db.session.add(u)
            db.session.commit()

        res = self.client.get("/api/check-user?username=existinglocalmember")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("exists"))
        self.assertEqual(data.get("username"), "ExistingLocalMember")
    def test_export_web_view(self):
        with self.app.app_context():
            comm = Community(name="Morocco Community", slug="wm-ma", meta_roster_page="Wikimedia_MA/Members")
            db.session.add(comm)
            db.session.commit()

        res = self.client.get("/export?community=wm-ma")
        self.assertEqual(res.status_code, 200)
        self.assertIn("تصدير تقارير الأنشطة المجتمعية".encode("utf-8"), res.data)
        self.assertIn("Morocco Community".encode("utf-8"), res.data)
        self.assertIn("حسب السنة".encode("utf-8"), res.data)
        self.assertIn("حسب الشهر".encode("utf-8"), res.data)
        self.assertIn("فترة مخصصة".encode("utf-8"), res.data)

    def test_create_project_with_dates_and_status_auto(self):
        with self.client.session_transaction() as sess:
            sess["username"] = "MoroccoVolunteer"
            sess["is_member"] = True

        # Past activity -> Should be automatically Completed
        res_past = self.client.post("/project/new", data={
            "title": "Old Finished Conference",
            "description": "Conference held in 2021",
            "project_type": "Workshop",
            "target_wiki": "arwiki",
            "start_date": "2021-05-01",
            "end_date": "2021-05-05",
            "status": "auto"
        }, follow_redirects=True)
        self.assertEqual(res_past.status_code, 200)

        with self.app.app_context():
            p_past = Project.query.filter_by(title="Old Finished Conference").first()
            self.assertIsNotNone(p_past)
            self.assertEqual(str(p_past.start_date), "2021-05-01")
            self.assertEqual(str(p_past.end_date), "2021-05-05")
            self.assertEqual(p_past.status, "Completed")
            self.assertEqual(p_past.status_ar, "مكتملة")

        # Future activity -> Should be automatically Planned
        res_future = self.client.post("/project/new", data={
            "title": "Future Summit 2030",
            "description": "Upcoming Summit",
            "project_type": "Workshop",
            "target_wiki": "arwiki",
            "start_date": "2030-08-10",
            "end_date": "2030-08-15",
            "status": "auto"
        }, follow_redirects=True)
        self.assertEqual(res_future.status_code, 200)

        with self.app.app_context():
            p_future = Project.query.filter_by(title="Future Summit 2030").first()
            self.assertIsNotNone(p_future)
            self.assertEqual(p_future.status, "Planned")
            self.assertEqual(p_future.status_ar, "مخططة")

        # Ongoing activity (start_date in past, end_date in future) -> In Progress
        res_running = self.client.post("/project/new", data={
            "title": "Ongoing Long Sprint",
            "description": "Continuous sprint",
            "project_type": "Workshop",
            "target_wiki": "arwiki",
            "start_date": "2026-01-01",
            "end_date": "2030-01-01",
            "status": "auto"
        }, follow_redirects=True)
        self.assertEqual(res_running.status_code, 200)

        with self.app.app_context():
            p_running = Project.query.filter_by(title="Ongoing Long Sprint").first()
            self.assertIsNotNone(p_running)
            self.assertEqual(p_running.status, "In Progress")
            self.assertEqual(p_running.status_ar, "جارية")

    def test_project_detail_view_shows_dates(self):
        with self.app.app_context():
            comm = Community(name="Community MA", slug="wm-ma", meta_roster_page="Wikimedia_MA/Members")
            db.session.add(comm)
            db.session.flush()
            from datetime import date
            p = Project(
                community_id=comm.id,
                title="Dated Activity Test",
                description="Testing date rendering",
                project_type="Workshop",
                target_wiki="arwiki",
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 5),
                status="Completed",
                lead_organizer="MoroccoVolunteer"
            )
            db.session.add(p)
            db.session.commit()
            pid = p.id

        res = self.client.get(f"/project/{pid}")
        self.assertEqual(res.status_code, 200)
        self.assertIn("2026-03-01".encode("utf-8"), res.data)
        self.assertIn("2026-03-05".encode("utf-8"), res.data)
        self.assertIn("تاريخ البدء".encode("utf-8"), res.data)
        self.assertIn("تاريخ الانتهاء".encode("utf-8"), res.data)
        self.assertIn("مكتملة".encode("utf-8"), res.data)

if __name__ == "__main__":
    unittest.main()



