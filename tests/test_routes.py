import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models import Project

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

if __name__ == "__main__":
    unittest.main()
