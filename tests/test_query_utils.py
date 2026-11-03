import os
import sys
import unittest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models import Project
from app.query_utils import filter_projects_by_date, sanitize_csv_cell, normalize_username
from app.wiki_utils import build_xtools_user_url
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class TestQueryUtils(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_sanitize_csv_cell(self):
        # Normal strings
        self.assertEqual(sanitize_csv_cell("Regular Text"), "Regular Text")
        self.assertEqual(sanitize_csv_cell("12345"), "12345")
        self.assertEqual(sanitize_csv_cell(""), "")
        self.assertIsNone(sanitize_csv_cell(None))
        self.assertEqual(sanitize_csv_cell(42), 42)

        # Formula injection triggers
        self.assertEqual(sanitize_csv_cell("=1+1"), "'=1+1")
        self.assertEqual(sanitize_csv_cell("+cmd|' /C calc'!A0"), "'+cmd|' /C calc'!A0")
        self.assertEqual(sanitize_csv_cell("-10"), "'-10")
        self.assertEqual(sanitize_csv_cell("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(sanitize_csv_cell("|cmd|' /C calc'!A0"), "'|cmd|' /C calc'!A0")
        self.assertEqual(sanitize_csv_cell("\t=SUM"), "'\t=SUM")
        self.assertEqual(sanitize_csv_cell("\r=SUM"), "'\r=SUM")

        # Whitespace evasion tests (starts with whitespace then trigger)
        self.assertEqual(sanitize_csv_cell("   =cmd"), "'   =cmd")
        self.assertEqual(sanitize_csv_cell(" \t +malicious"), "' \t +malicious")

    def test_normalize_username(self):
        self.assertEqual(normalize_username("Bonnjalal_00"), "Bonnjalal 00")
        self.assertEqual(normalize_username("User%20Name_Test"), "User Name Test")
        self.assertEqual(normalize_username("  Spaced_User  "), "Spaced User")
        self.assertEqual(normalize_username(""), "")
        self.assertEqual(normalize_username(None), "")

    def test_build_xtools_user_url(self):
        url1 = build_xtools_user_url("arwiki", "Bonnjalal00")
        self.assertEqual(url1, "https://xtools.wmcloud.org/ec/arwiki/Bonnjalal00")

        url2 = build_xtools_user_url("ar.wikipedia.org", "User Name")
        self.assertEqual(url2, "https://xtools.wmcloud.org/ec/arwiki/User_Name")

        url3 = build_xtools_user_url("commonswiki", "Reda benkhadra")
        self.assertEqual(url3, "https://xtools.wmcloud.org/ec/commonswiki/Reda_benkhadra")

    def test_filter_projects_by_date(self):
        with self.app.app_context():
            p1 = Project(
                title="P 2024",
                description="desc",
                lead_organizer="Admin",
                start_date=date(2024, 5, 10),
                end_date=date(2024, 5, 12)
            )
            p2 = Project(
                title="P 2025 Jan",
                description="desc",
                lead_organizer="Admin",
                start_date=date(2025, 1, 15),
                end_date=date(2025, 1, 16)
            )
            p3 = Project(
                title="P 2025 Feb",
                description="desc",
                lead_organizer="Admin",
                start_date=date(2025, 2, 20),
                end_date=date(2025, 2, 22)
            )
            db.session.add_all([p1, p2, p3])
            db.session.commit()

            base_q = Project.query

            # Year filter
            q_year, s, e = filter_projects_by_date(base_q, {"year": "2025"})
            self.assertEqual(q_year.count(), 2)

            # Month filter
            q_month, s, e = filter_projects_by_date(base_q, {"year": "2025", "month": "2"})
            self.assertEqual(q_month.count(), 1)
            self.assertEqual(q_month.first().title, "P 2025 Feb")

            # Custom range filter
            q_custom, s, e = filter_projects_by_date(base_q, {"start_date": "2024-01-01", "end_date": "2024-12-31"})
            self.assertEqual(q_custom.count(), 1)
            self.assertEqual(q_custom.first().title, "P 2024")


if __name__ == "__main__":
    unittest.main()

