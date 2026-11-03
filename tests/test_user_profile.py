import os
import sys
import unittest
from datetime import datetime, date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models import Community, Project, User, StatSnapshot, CommunityMember
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class TestUserProfileAndReports(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

            # Community
            self.comm = Community(
                name="Wikimedia Morocco",
                slug="wm-ma",
                meta_roster_page="Wikimedia_MA_User_Group/Members"
            )
            db.session.add(self.comm)
            db.session.commit()

            # Registered member user with StatSnapshot
            self.member = User(
                username="Anass Sedrati",
                is_member=True,
                first_seen=datetime(2023, 1, 1),
                last_synced=datetime(2025, 1, 1, 12, 0)
            )
            db.session.add(self.member)
            db.session.flush()

            cm = CommunityMember(
                community_id=self.comm.id,
                user_id=self.member.id,
                role="Board Member"
            )
            snap = StatSnapshot(
                user_id=self.member.id,
                total_edits=45000,
                home_wiki="ar.wikipedia.org",
                wiki_breakdown={"ar.wikipedia.org": 40000, "commons.wikimedia.org": 5000},
                recorded_at=datetime(2025, 1, 1, 12, 0)
            )
            db.session.add_all([cm, snap])

            # Projects where Anass has different roles
            self.p1 = Project(
                community_id=self.comm.id,
                title="Workshop Rabat",
                description="<p>Rabat training workshop</p>",
                lead_organizer="Anass Sedrati",
                project_type="Workshop",
                target_wiki="arwiki",
                start_date=date(2025, 2, 1),
                status="Completed",
                participants=["ParticipantUser", "VolunteerMorocco"]
            )
            self.p2 = Project(
                community_id=self.comm.id,
                title="Contest Wiki Loves Africa",
                description="<p>Photo contest</p>",
                lead_organizer="OtherLead",
                co_organizers=["Anass Sedrati"],
                is_contest=True,
                jury_members=["JuryPerson"],
                project_type="Contest",
                start_date=date(2025, 3, 1),
                status="Completed",
                participants=["ParticipantUser"],
                results={
                    "summary": "Successful contest",
                    "winners": ["Winner1", "Winner2"],
                    "metrics": {"articles_created": 50, "articles_improved": 120, "files_uploaded": 300},
                    "notes": "Excellent participation"
                }
            )
            self.p3 = Project(
                community_id=self.comm.id,
                title="Jury Event",
                description="<p>Jury judging event</p>",
                lead_organizer="OtherLead",
                is_contest=True,
                jury_members=["Anass Sedrati"],
                project_type="Contest",
                start_date=date(2025, 4, 1),
                status="In Progress"
            )
            self.p4 = Project(
                community_id=self.comm.id,
                title="Edit-a-thon Casablanca",
                description="<p>Casablanca editing session</p>",
                lead_organizer="OtherLead",
                project_type="Edit-a-thon",
                participants=["Anass Sedrati", "ParticipantUser"],
                start_date=date(2025, 5, 1),
                status="Completed"
            )
            db.session.add_all([self.p1, self.p2, self.p3, self.p4])
            db.session.commit()
            self.p1_id = self.p1.id
            self.p2_id = self.p2.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_user_profile_rendering(self):
        res = self.client.get("/user/Anass Sedrati")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")

        self.assertIn("Anass Sedrati", content)
        self.assertIn("45,000", content)
        self.assertIn("Wikimedia Morocco", content)
        self.assertIn("Workshop Rabat", content)
        self.assertIn("Contest Wiki Loves Africa", content)
        self.assertIn("Jury Event", content)
        self.assertIn("Edit-a-thon Casablanca", content)

        # Horizontal line charts for Top Wikis
        self.assertIn("wiki-charts-list", content)
        self.assertIn("wiki-bar-fill", content)
        self.assertIn("ar.wikipedia.org", content)
        self.assertIn("40,000", content)
        self.assertIn("commons.wikimedia.org", content)
        self.assertIn("5,000", content)
        self.assertIn("عرض في XTools", content)

    def test_user_profile_normalization(self):
        # Test underscore replacing and URL decoding
        res1 = self.client.get("/user/Anass_Sedrati")
        self.assertEqual(res1.status_code, 200)

        res2 = self.client.get("/user/Anass%20Sedrati")
        self.assertEqual(res2.status_code, 200)

    def test_user_profile_unknown_user_returns_404(self):
        # User not present in User table AND not present in any project
        res = self.client.get("/user/UnknownGhostUser999")
        self.assertEqual(res.status_code, 404)

    def test_user_profile_unassociated_participant(self):
        # ParticipantUser has no User row in database, but exists in projects
        res = self.client.get("/user/ParticipantUser")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")
        self.assertIn("ParticipantUser", content)
        self.assertIn("Workshop Rabat", content)

    def test_single_project_report(self):
        res = self.client.get(f"/project/{self.p2_id}/report")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")

        self.assertIn("Contest Wiki Loves Africa", content)
        self.assertIn("المنظمون:", content)
        self.assertIn("OtherLead", content)
        self.assertIn("Anass Sedrati", content)
        self.assertIn("Winner1", content)
        self.assertIn("50", content)
        self.assertIn("120", content)
        self.assertIn("300", content)
        self.assertIn("window.print()", content)

    def test_community_report(self):
        res = self.client.get("/wm-ma/report")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")

        self.assertIn("Wikimedia Morocco", content)
        self.assertIn("Workshop Rabat", content)
        self.assertIn("تقرير الأداء التنفيذي للمجتمع", content)
        self.assertIn("المنظمون", content)

    def test_community_report_detailed(self):
        res = self.client.get("/wm-ma/report?detailed=1")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")

        self.assertIn("التقرير المفصل لأنشطة ومشاريع المجتمع", content)
        self.assertIn("ملفات وتفاصيل الأنشطة الكاملة", content)
        self.assertIn("Rabat training workshop", content)
        self.assertIn("Successful contest", content)
        self.assertIn("Winner1", content)

    def test_user_report(self):
        res = self.client.get("/user/Anass Sedrati/report")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")

        self.assertIn("ملف إنجاز المساهم", content)
        self.assertIn("Anass Sedrati", content)
        self.assertIn("Workshop Rabat", content)
        self.assertIn("45,000", content)

    def test_user_report_detailed(self):
        res = self.client.get("/user/Anass Sedrati/report?detailed=1")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")

        self.assertIn("التقرير المفصل لأنشطة ومساهمات المساهم", content)
        self.assertIn("تفاصيل الأنشطة والمشاريع المشارك بها", content)
        self.assertIn("Photo contest", content)
        self.assertIn("Winner1", content)

    def test_reserved_slug_protection(self):
        # Reserved slugs must return 404 on community routes
        res_user = self.client.get("/user/")
        self.assertEqual(res_user.status_code, 404)

        res_project = self.client.get("/project/")
        self.assertEqual(res_project.status_code, 404)

        res_api = self.client.get("/api/")
        self.assertEqual(res_api.status_code, 404)

        res_export = self.client.get("/export/")
        self.assertEqual(res_export.status_code, 404)


if __name__ == "__main__":
    unittest.main()

