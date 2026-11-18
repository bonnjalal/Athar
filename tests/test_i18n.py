import json
import os
import pathlib
import re
import sys
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.i18n import _, _cldr_plural_index, _r
from app.models import Community, Project, User
from config import Config


ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent


class StrictI18nConfig(Config):
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


class TestPhase2LocalizationAndLayout(unittest.TestCase):
    def setUp(self):
        self.app = create_app(StrictI18nConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            self.comm = Community(
                name="Wikimedia Morocco",
                slug="wm-ma",
                meta_roster_page="Wikimedia_MA_User_Group/Members",
            )
            self.user = User(username="I18nTester", is_member=True, is_admin=False)
            db.session.add_all([self.comm, self.user])
            db.session.flush()

            self.project = Project(
                community_id=self.comm.id,
                title="ورشة التحرير التعاوني",
                description="<p>وصف الورشة بالعربية</p>",
                project_type="Workshop",
                target_wiki="arwiki",
                primary_lang="ar",
                translations={
                    "en": {
                        "title": "Collaborative Editing Workshop",
                        "description": "<p>English workshop description</p>",
                        "results_summary": "20 articles improved",
                        "results_notes": "Completed on schedule",
                    }
                },
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 5),
                status="Completed",
                lead_organizer="I18nTester",
                participants=["I18nTester"],
                results={"summary": "تحسين 20 مقالة", "winners": [], "metrics": {"articles_created": 5}, "notes": "نجاح ممتاز"},
                created_at=datetime(2026, 3, 1, 10, 0, 0),
            )
            db.session.add(self.project)
            db.session.commit()
            self.project_id = self.project.id
            self.comm_slug = self.comm.slug

    def test_banana_i18n_arabic_6_form_and_english_2_form_plurals(self):
        # Verify CLDR plural indices directly
        self.assertEqual([_cldr_plural_index("ar", n) for n in (0, 1, 2, 5, 15, 100)], [0, 1, 2, 3, 4, 5])
        self.assertEqual([_cldr_plural_index("en", n) for n in (0, 1, 2, 11)], [1, 0, 1, 1])

        with self.app.app_context():
            ar_forms = [_("athar-export-preview-count", n, lang="ar") for n in (0, 1, 2, 5, 15, 100)]
            self.assertEqual(
                ar_forms,
                [
                    "لا توجد أنشطة مطابقة",
                    "نشاط واحد مطابق",
                    "نشاطان مطابقان",
                    "5 أنشطة مطابقة",
                    "15 نشاطاً مطابقاً",
                    "100 نشاط مطابق",
                ],
            )
            en_forms = [_("athar-export-preview-count", n, lang="en") for n in (0, 1, 2)]
            self.assertEqual(
                en_forms,
                [
                    "No matching activities",
                    "1 matching activity",
                    "2 matching activities",
                ],
            )

    def test_i18n_json_catalog_parity_and_placeholders(self):
        for namespace in ("ui", "reports"):
            base_dir = ROOT_DIR / "i18n" / namespace
            en_data = json.loads((base_dir / "en.json").read_text(encoding="utf-8"))
            ar_data = json.loads((base_dir / "ar.json").read_text(encoding="utf-8"))
            qqq_data = json.loads((base_dir / "qqq.json").read_text(encoding="utf-8"))

            en_keys = {k for k in en_data.keys() if not k.startswith("@")}
            ar_keys = {k for k in ar_data.keys() if not k.startswith("@")}
            qqq_keys = {k for k in qqq_data.keys() if not k.startswith("@")}

            self.assertEqual(en_keys, ar_keys, f"Key mismatch between en and ar in {namespace}")
            self.assertEqual(en_keys, qqq_keys, f"Key mismatch between en and qqq in {namespace}")

            for k in sorted(en_keys):
                self.assertTrue(str(en_data[k]).strip(), f"Empty en translation for {k}")
                self.assertTrue(str(ar_data[k]).strip(), f"Empty ar translation for {k}")
                self.assertTrue(str(qqq_data[k]).strip(), f"Empty qqq documentation for {k}")
                en_ph = set(re.findall(r"\$\d+", en_data[k]))
                ar_ph = set(re.findall(r"\$\d+", ar_data[k]))
                self.assertEqual(en_ph, ar_ph, f"Placeholder mismatch for {k}: {en_ph} != {ar_ph}")

    def test_post_lang_csrf_validation_and_open_redirect_guard(self):
        # Missing CSRF returns 400
        res_no_csrf = self.client.post("/lang", data={"lang": "en", "next": "/"})
        self.assertEqual(res_no_csrf.status_code, 400)

        home_res = self.client.get("/")
        csrf = _extract_csrf_token(home_res.data)
        self.assertTrue(csrf)

        # Invalid language returns 400
        res_bad_lang = self.client.post("/lang", data={"csrf_token": csrf, "lang": "de"})
        self.assertEqual(res_bad_lang.status_code, 400)

        # Open redirect attempts (//evil.com, https://evil.com) are neutralized to /
        for evil_next in ("//evil.com/phish", "https://evil.com/steal", "\\\\evil.com"):
            res = self.client.post(
                "/lang",
                data={"csrf_token": csrf, "lang": "en", "next": evil_next},
                follow_redirects=False,
            )
            self.assertEqual(res.status_code, 302)
            self.assertTrue(res.location.endswith("/"))
            self.assertNotIn("evil.com", res.location)

        # Safe relative path with query string is preserved and html dir becomes ltr
        res_ok = self.client.post(
            "/lang",
            data={"csrf_token": csrf, "lang": "en", "next": "/activities?status=Completed"},
            follow_redirects=True,
        )
        self.assertEqual(res_ok.status_code, 200)
        html_text = res_ok.data.decode("utf-8")
        self.assertIn('<html lang="en" dir="ltr">', html_text)
        self.assertIn("Collaborative Editing Workshop", html_text)

    def test_report_and_csv_lang_override_without_mutating_session_and_rejects_invalid_lang(self):
        # Set session locale to ar
        home = self.client.get("/")
        csrf = _extract_csrf_token(home.data)
        self.client.post("/lang", data={"csrf_token": csrf, "lang": "ar", "next": "/"})

        # Invalid ?lang= returns HTTP 400 on reports and CSVs
        for bad_url in (
            f"/project/{self.project_id}/report?lang=../etc/passwd",
            f"/{self.comm_slug}/report?lang=unknown",
            f"/user/I18nTester/report?lang=fr",
            f"/api/{self.comm_slug}/export?lang=../bad",
            f"/api/projects/{self.project_id}/export?lang=invalid",
        ):
            r = self.client.get(bad_url)
            self.assertEqual(r.status_code, 400, f"Expected 400 for {bad_url}, got {r.status_code}")

        # ?lang=en renders English report + CSV while keeping session['lang'] == 'ar'
        rep = self.client.get(f"/project/{self.project_id}/report?lang=en")
        self.assertEqual(rep.status_code, 200)
        rep_html = rep.data.decode("utf-8")
        self.assertIn('<html lang="en" dir="ltr" data-theme="light">', rep_html)
        self.assertIn("Collaborative Editing Workshop", rep_html)
        self.assertIn("Regional Wikimedia Affiliate Activity", rep_html)
        self.assertNotIn("css/main.css", rep_html)

        comm_csv = self.client.get(f"/api/{self.comm_slug}/export?lang=en&include_in_progress=1&include_planned=1")
        self.assertEqual(comm_csv.status_code, 200)
        csv_text = comm_csv.data.decode("utf-8-sig")
        self.assertIn("ID,Activity Title,Activity Type", csv_text)
        self.assertIn("Collaborative Editing Workshop", csv_text)

        proj_csv = self.client.get(f"/api/projects/{self.project_id}/export?lang=en")
        self.assertEqual(proj_csv.status_code, 200)
        self.assertIn("Organizer", proj_csv.data.decode("utf-8-sig"))

        # Confirm user session locale remained 'ar' (not mutated by ?lang=en)
        after_home = self.client.get("/").data.decode("utf-8")
        self.assertIn('<html lang="ar" dir="rtl">', after_home)

    def test_templates_and_css_structural_contracts(self):
        base_report_html = (ROOT_DIR / "app" / "templates" / "reports" / "base_report.html").read_text(encoding="utf-8")
        self.assertNotIn("css/main.css", base_report_html)
        self.assertIn('data-theme="light"', base_report_html)

        base_html = (ROOT_DIR / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("localStorage.getItem('athar-theme')", base_html)
        self.assertIn("theme-toggle-btn", base_html)
        self.assertIn("js/theme.js", base_html)

        css_text = (ROOT_DIR / "app" / "static" / "css" / "codex.style.css").read_text(encoding="utf-8")
        self.assertIn(':root[data-theme="light"]', css_text)
        self.assertIn(':root[data-theme="dark"]', css_text)
        self.assertNotRegex(css_text, r"prefers-color-scheme:\s*dark")
        self.assertIsNone(
            re.search(
                r"direction:\s*rtl|text-align:\s*(?:left|right)|margin-(?:left|right):|padding-(?:left|right):|(?:\s)(left|right):",
                css_text,
            )
        )


if __name__ == "__main__":
    unittest.main()
