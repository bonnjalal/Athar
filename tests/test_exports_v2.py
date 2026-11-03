import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models import Community, Project, User
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class TestExportsV2(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            self.comm = Community(
                name="Wikimedia Morocco",
                slug="wm-ma",
                meta_roster_page="Wikimedia_MA_User_Group/Members"
            )
            db.session.add(self.comm)
            db.session.commit()

            # Create sample projects including a formula injection test project
            self.p1 = Project(
                community_id=self.comm.id,
                title="Workshop 1",
                description="desc",
                lead_organizer="LeadOrganizer",
                co_organizers=["CoOrg1"],
                is_contest=True,
                jury_members=["Jury1"],
                participants=["Participant1", "Participant2"],
                start_date=date(2025, 3, 1),
                end_date=date(2025, 3, 5),
                status="Completed"
            )
            # Malicious payload project to test formula escaping
            self.p_malicious = Project(
                community_id=self.comm.id,
                title="=cmd|' /C calc'!A0",
                description="desc",
                lead_organizer="+MaliciousLead",
                co_organizers=["-MaliciousCo"],
                is_contest=True,
                jury_members=["@MaliciousJury"],
                participants=["|MaliciousParticipant", "  =SpaceInjection"],
                start_date=date(2025, 4, 1),
                status="Completed"
            )
            db.session.add_all([self.p1, self.p_malicious])
            db.session.commit()
            self.p1_id = self.p1.id
            self.p_malicious_id = self.p_malicious.id
            self.comm_id = self.comm.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_level1_project_roster_export(self):
        res = self.client.get(f"/api/projects/{self.p1_id}/export?format=csv")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "text/csv")
        data = res.data.decode("utf-8")

        # Must start with UTF-8 BOM
        self.assertTrue(data.startswith("\ufeff"))

        # Verify headers
        self.assertIn("اسم المستخدم,الدور في النشاط,عنوان النشاط,المشروع المستهدف,تاريخ البدء,تاريخ الانتهاء", data)

        # Verify participants and roles present
        self.assertIn("LeadOrganizer,منظم رئيسي", data)
        self.assertIn("CoOrg1,منظم مشارك", data)
        self.assertIn("Jury1,لجنة تحكيم", data)
        self.assertIn("Participant1,مشارك", data)
        self.assertIn("Participant2,مشارك", data)

    def test_level1_project_formula_escaping(self):
        res = self.client.get(f"/api/projects/{self.p_malicious_id}/export?format=csv")
        self.assertEqual(res.status_code, 200)
        data = res.data.decode("utf-8")

        # Dangerous characters should be prepended with single quote
        self.assertIn("'+MaliciousLead", data)
        self.assertIn("'-MaliciousCo", data)
        self.assertIn("'@MaliciousJury", data)
        self.assertIn("'|MaliciousParticipant", data)
        self.assertIn("'  =SpaceInjection", data)

    def test_level2_community_projects_export(self):
        res = self.client.get("/api/wm-ma/export?format=csv")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "text/csv")
        data = res.data.decode("utf-8")

        self.assertTrue(data.startswith("\ufeff"))
        self.assertIn("Workshop 1", data)
        # Malicious project title should be escaped
        self.assertIn("'=cmd|' /C calc'!A0", data)

    def test_level3_user_projects_export(self):
        # Test Participant1
        res = self.client.get("/api/users/Participant1/export?format=csv")
        self.assertEqual(res.status_code, 200)
        data = res.data.decode("utf-8")

        self.assertTrue(data.startswith("\ufeff"))
        self.assertIn("معرف النشاط,عنوان النشاط,المجتمع التابع له,الدور,الحالة,المشروع المستهدف,تاريخ البدء,تاريخ الانتهاء", data)
        self.assertIn("Workshop 1", data)
        self.assertIn("مشارك", data)

        # Test alias route /api/user/<username>/export
        res_alias = self.client.get("/api/user/Participant1/export?format=csv")
        self.assertEqual(res_alias.status_code, 200)

    def test_level3_user_formula_escaping(self):
        res = self.client.get("/api/users/+MaliciousLead/export?format=csv")
        self.assertEqual(res.status_code, 200)
        data = res.data.decode("utf-8")

        self.assertIn("منظم", data)
        # Title of project with formula injection should be escaped
        self.assertIn("'=cmd|' /C calc'!A0", data)

    def test_export_invalid_format(self):
        res1 = self.client.get(f"/api/projects/{self.p1_id}/export?format=xml")
        self.assertEqual(res1.status_code, 400)

        res2 = self.client.get("/api/users/Participant1/export?format=json")
        self.assertEqual(res2.status_code, 400)

        res3 = self.client.get("/api/wm-ma/export?format=pdf")
        self.assertEqual(res3.status_code, 400)

    def test_status_inclusion_export(self):
        with self.app.app_context():
            p_planned = Project(
                community_id=self.comm_id,
                title="Planned Activity",
                description="desc",
                lead_organizer="LeadOrganizer",
                start_date=date(2027, 1, 1),
                end_date=date(2027, 1, 10),
                status="Planned"
            )
            p_in_prog = Project(
                community_id=self.comm_id,
                title="Ongoing Activity",
                description="desc",
                lead_organizer="LeadOrganizer",
                start_date=date(2026, 11, 1),
                end_date=date(2026, 11, 10),
                status="In Progress"
            )
            p_canceled = Project(
                community_id=self.comm_id,
                title="Canceled Activity",
                description="desc",
                lead_organizer="LeadOrganizer",
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 10),
                status="Canceled"
            )
            db.session.add_all([p_planned, p_in_prog, p_canceled])
            db.session.commit()

        # 1. When all inclusion flags are 0: only Completed ones are returned
        res_completed_only = self.client.get("/api/wm-ma/export?format=csv&include_planned=0&include_in_progress=0&include_canceled=0")
        self.assertEqual(res_completed_only.status_code, 200)
        data = res_completed_only.data.decode("utf-8")
        self.assertIn("Workshop 1", data)
        self.assertNotIn("Planned Activity", data)
        self.assertNotIn("Ongoing Activity", data)
        self.assertNotIn("Canceled Activity", data)

        # 2. Include planned: Completed + Planned returned
        res_planned = self.client.get("/api/wm-ma/export?format=csv&include_planned=1&include_in_progress=0&include_canceled=0")
        data_planned = res_planned.data.decode("utf-8")
        self.assertIn("Workshop 1", data_planned)
        self.assertIn("Planned Activity", data_planned)
        self.assertNotIn("Ongoing Activity", data_planned)
        self.assertNotIn("Canceled Activity", data_planned)

        # 3. Include in progress: Completed + In Progress returned
        res_prog = self.client.get("/api/wm-ma/export?format=csv&include_planned=0&include_in_progress=1&include_canceled=0")
        data_prog = res_prog.data.decode("utf-8")
        self.assertIn("Workshop 1", data_prog)
        self.assertNotIn("Planned Activity", data_prog)
        self.assertIn("Ongoing Activity", data_prog)
        self.assertNotIn("Canceled Activity", data_prog)

        # 4. Include canceled: Completed + Canceled returned
        res_canc = self.client.get("/api/wm-ma/export?format=csv&include_planned=0&include_in_progress=0&include_canceled=1")
        data_canc = res_canc.data.decode("utf-8")
        self.assertIn("Workshop 1", data_canc)
        self.assertNotIn("Planned Activity", data_canc)
        self.assertNotIn("Ongoing Activity", data_canc)
        self.assertIn("Canceled Activity", data_canc)


if __name__ == "__main__":
    unittest.main()

