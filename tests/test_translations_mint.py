import json
import os
import re
import sys
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models import Community, CommunityMember, Project, User
from app.routes import web as web_module
from config import Config


class StrictMintConfig(Config):
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


class TestPhase3MultilingualMinTAndSanitization(unittest.TestCase):
    def setUp(self):
        web_module._MINT_LANGUAGES_CACHE.clear()
        self.app = create_app(StrictMintConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            self.comm = Community(
                name="Wikimedia Morocco",
                slug="wm-ma",
                meta_roster_page="Wikimedia_MA_User_Group/Members",
            )
            self.member = User(username="MemberAuthor", is_member=True, is_admin=False)
            self.outsider = User(username="NonMemberUser", is_member=False, is_admin=False)
            self.admin = User(username="ToolAdmin", is_member=False, is_admin=True)
            db.session.add_all([self.comm, self.member, self.outsider, self.admin])
            db.session.flush()
            db.session.add(CommunityMember(community_id=self.comm.id, user_id=self.member.id, role="member"))
            db.session.commit()
            self.comm_id = self.comm.id
            self.member_id = self.member.id

    def _login_as(self, username: str):
        with self.client.session_transaction() as sess:
            sess.pop("logged_out", None)
            sess["username"] = username
            sess["user"] = username

    def _get_csrf(self) -> str:
        res = self.client.get("/")
        return _extract_csrf_token(res.data)

    def test_translate_requires_csrf_and_member_rbac(self):
        # Missing CSRF -> 400
        self._login_as("MemberAuthor")
        r_no_csrf = self.client.post(
            "/project/translate",
            json={"source_lang": "ar", "target_lang": "en", "fields": {"title": "مرحبا"}},
        )
        self.assertEqual(r_no_csrf.status_code, 400)

        # Anonymous with CSRF -> 401 JSON
        self.client.get("/logout")
        csrf = self._get_csrf()
        r_anon = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "ar", "target_lang": "en", "fields": {"title": "مرحبا"}},
        )
        self.assertEqual(r_anon.status_code, 401)

        # Authenticated non-member with CSRF -> 403 JSON
        self._login_as("NonMemberUser")
        csrf = self._get_csrf()
        r_outsider = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "ar", "target_lang": "en", "fields": {"title": "مرحبا"}},
        )
        self.assertEqual(r_outsider.status_code, 403)

    @patch("app.routes.web.requests.post")
    @patch("app.routes.web.requests.get")
    def test_translate_payload_size_cap_and_language_validation(self, mock_get, mock_post):
        self._login_as("MemberAuthor")
        csrf = self._get_csrf()

        # > 12 KB UTF-8 body cap rejected with 400 before touching upstream
        oversized_desc = "أ" * 5000  # 10000+ bytes UTF-8
        r_big = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "ar", "target_lang": "en", "fields": {"title": "test", "description": oversized_desc}},
        )
        self.assertEqual(r_big.status_code, 400)
        mock_get.assert_not_called()
        mock_post.assert_not_called()

        # Bad language code & identical languages rejected
        r_bad_lang = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "../en", "target_lang": "fr", "fields": {"title": "test"}},
        )
        self.assertEqual(r_bad_lang.status_code, 400)

        r_same = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "ar", "target_lang": "ar", "fields": {"title": "test"}},
        )
        self.assertEqual(r_same.status_code, 400)

    @patch("app.routes.web.requests.post")
    @patch("app.routes.web.requests.get")
    def test_mint_cache_xss_sanitization_and_db_rate_limit(self, mock_get, mock_post):
        self._login_as("MemberAuthor")
        csrf = self._get_csrf()

        lang_resp = MagicMock(status_code=200)
        lang_resp.json.return_value = {"ar": ["en", "fr"], "en": ["ar", "fr"]}
        mock_get.return_value = lang_resp

        def fake_post(url, json=None, headers=None, timeout=None):
            self.assertTrue(url.endswith("/translate"), f"Expected /translate endpoint, got {url}")
            body_sent = json or {}
            self.assertEqual(body_sent.get("source_language"), "ar")
            self.assertEqual(body_sent.get("target_language"), "en")
            res = MagicMock(status_code=200)
            fmt = body_sent.get("format")
            if fmt == "html":
                res.json.return_value = {
                    "translation": '<p>Clean output</p><script>alert(1)</script><a href="https://meta.wikimedia.org" onclick="hack()">Meta</a>'
                }
            else:
                res.json.return_value = {"translation": '<b>Clean Title</b><script>bad()</script>'}
            return res

        mock_post.side_effect = fake_post

        # Call 1 succeeds, caches /languages, sanitizes XSS in returned JSON
        r1 = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={
                "source_lang": "ar",
                "target_lang": "en",
                "fields": {"title": "ورشة", "description": "<p>تفاصيل</p>"},
            },
        )
        self.assertEqual(r1.status_code, 200)
        body1 = r1.get_json()
        self.assertEqual(body1["target_lang"], "en")
        self.assertNotIn("<script>", body1["fields"]["title"])
        self.assertNotIn("<b>", body1["fields"]["title"])
        self.assertIn("Clean Title", body1["fields"]["title"])
        self.assertIn("<p>Clean output</p>", body1["fields"]["description"])
        self.assertNotIn("<script>", body1["fields"]["description"])
        self.assertNotIn("onclick=", body1["fields"]["description"])
        self.assertIn('rel="noopener noreferrer"', body1["fields"]["description"])

        # Calls 2..10 reuse cached /languages (requests.get still called only once!)
        for _ in range(9):
            rn = self.client.post(
                "/project/translate",
                headers={"X-CSRFToken": csrf},
                json={"source_lang": "ar", "target_lang": "en", "fields": {"title": "ورشة"}},
            )
            self.assertEqual(rn.status_code, 200)
        self.assertEqual(mock_get.call_count, 1)

        # Call 11 inside 60s window hits DB cooldown -> HTTP 429
        call_count_before_429 = mock_post.call_count
        r11 = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "ar", "target_lang": "en", "fields": {"title": "ورشة"}},
        )
        self.assertEqual(r11.status_code, 429)
        self.assertEqual(mock_post.call_count, call_count_before_429)

        # After sliding window expires (> 60s), limit resets cleanly
        with self.app.app_context():
            u = db.session.get(User, self.member_id)
            u.mint_window_start = datetime.utcnow() - timedelta(seconds=65)
            db.session.commit()

        r12 = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "ar", "target_lang": "en", "fields": {"title": "ورشة"}},
        )
        self.assertEqual(r12.status_code, 200)

    @patch("app.routes.web.requests.post")
    @patch("app.routes.web.requests.get")
    def test_mint_unsupported_pair_timeout_and_upstream_errors(self, mock_get, mock_post):
        self._login_as("ToolAdmin")
        csrf = self._get_csrf()

        # Unsupported pair from cached /languages returns 400 manual_only=True
        lang_resp = MagicMock(status_code=200)
        lang_resp.json.return_value = {"ar": ["en", "fr"]}
        mock_get.return_value = lang_resp

        r_unsupp = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "ar", "target_lang": "ary", "fields": {"title": "ورشة"}},
        )
        self.assertEqual(r_unsupp.status_code, 400)
        self.assertTrue(r_unsupp.get_json().get("manual_only"))
        mock_post.assert_not_called()

        # Timeout -> 504
        mock_post.side_effect = requests.Timeout("timed out")
        r_timeout = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "ar", "target_lang": "en", "fields": {"title": "ورشة"}},
        )
        self.assertEqual(r_timeout.status_code, 504)

        # Upstream 502 / connection error -> 502
        mock_post.side_effect = requests.ConnectionError("down")
        r_down = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "ar", "target_lang": "en", "fields": {"title": "ورشة"}},
        )
        self.assertEqual(r_down.status_code, 502)

        bad_http = MagicMock(status_code=503)
        mock_post.side_effect = None
        mock_post.return_value = bad_http
        r_503 = self.client.post(
            "/project/translate",
            headers={"X-CSRFToken": csrf},
            json={"source_lang": "ar", "target_lang": "en", "fields": {"title": "ورشة"}},
        )
        self.assertEqual(r_503.status_code, 502)

    @patch("app.routes.web.requests.post")
    @patch("app.routes.web.requests.get")
    def test_project_translations_persistence_xss_cleanup_and_localized_fallback(self, mock_get, mock_post):
        self._login_as("MemberAuthor")
        csrf = self._get_csrf()

        translations_payload = {
            "ar": {"title": "Duplicate Primary Copy Should Be Stripped"},
            "en": {
                "title": 'English <img src=x onerror="evil()">Title',
                "description": '<p>English safe body</p><img src=x onerror="evil()"><script>alert(2)</script>',
                "results_summary": "Summary <b>plain</b>",
                "results_notes": "Notes <b>text</b>",
            },
            "fr": {
                "title": "Titre en français",
                # description omitted on purpose to test field-level primary fallback
            },
        }

        res = self.client.post(
            "/project/new",
            data={
                "csrf_token": csrf,
                "community_id": str(self.comm_id),
                "title": "العنوان الأساسي بالعربية",
                "project_type": "Workshop",
                "target_wiki": "arwiki",
                "start_date": "2026-04-01",
                "end_date": "2026-04-05",
                "description": "<p>الوصف العربي الأساسي</p>",
                "primary_lang": "ar",
                "translations_json": json.dumps(translations_payload),
            },
            follow_redirects=False,
        )
        self.assertEqual(res.status_code, 302)

        with self.app.app_context():
            proj = Project.query.filter_by(title="العنوان الأساسي بالعربية").first()
            self.assertIsNotNone(proj)
            proj_id = proj.id
            self.assertEqual(proj.primary_lang, "ar")
            # Primary language shadow copy is stripped cleanly
            self.assertNotIn("ar", proj.translations)
            # XSS neutralized in en entry
            en_entry = proj.translations["en"]
            self.assertEqual(en_entry["title"], "English Title")
            self.assertIn("<p>English safe body</p>", en_entry["description"])
            self.assertNotIn("<script>", en_entry["description"])
            self.assertNotIn("onerror=", en_entry["description"])
            self.assertEqual(en_entry["results_summary"], "Summary plain")
            self.assertEqual(en_entry["results_notes"], "Notes text")

        # UI detail rendering under English uses translations['en'] wrapped in <bdi dir="auto">
        self.client.post("/lang", data={"csrf_token": csrf, "lang": "en", "next": f"/project/{proj_id}"})
        detail_en = self.client.get(f"/project/{proj_id}")
        self.assertEqual(detail_en.status_code, 200)
        detail_html = detail_en.data.decode("utf-8")
        self.assertIn('<bdi lang="en" dir="auto">English Title</bdi>', detail_html)
        self.assertIn("English safe body", detail_html)

        # Printable report & CSV exports use Project.translations with primary fallback and ZERO network calls
        rep_en = self.client.get(f"/project/{proj_id}/report?lang=en")
        self.assertEqual(rep_en.status_code, 200)
        self.assertIn("English Title", rep_en.data.decode("utf-8"))

        comm_csv = self.client.get("/api/wm-ma/export?lang=en&include_in_progress=1&include_planned=1")
        self.assertEqual(comm_csv.status_code, 200)
        self.assertIn("English Title", comm_csv.data.decode("utf-8-sig"))

        mock_get.assert_not_called()
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
