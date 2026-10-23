import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models import Community, User, CommunityMember, StatSnapshot
from scripts.sync_data import fetch_global_stats, sync_community, run_sync

from config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False

class TestSyncData(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            self.c1 = Community(
                name="Wikimedia Morocco",
                slug="wm-ma",
                meta_roster_page="Wikimedia_MA_User_Group/Members",
                default_wiki="ar.wikipedia.org"
            )
            self.c2 = Community(
                name="Wikimedia Tunisia",
                slug="wm-tn",
                meta_roster_page="Wikimedia_Tunisie/Membres",
                default_wiki="ar.wikipedia.org"
            )
            db.session.add_all([self.c1, self.c2])
            db.session.commit()
            self.c1_id = self.c1.id
            self.c2_id = self.c2.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    @patch("requests.get")
    def test_fetch_global_stats_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "query": {
                "globaluserinfo": {
                    "id": 1234,
                    "name": "Bonnjalal00",
                    "editcount": 56000,
                    "home": "arwiki",
                    "merged": [
                        {"wiki": "arwiki", "editcount": 50000},
                        {"wiki": "commonswiki", "editcount": 6000},
                        {"wiki": "enwiki", "editcount": 0}
                    ]
                }
            }
        }
        mock_get.return_value = mock_resp

        stats = fetch_global_stats("Bonnjalal00")
        self.assertIsNotNone(stats)
        self.assertEqual(stats["total_edits"], 56000)
        self.assertEqual(stats["home_wiki"], "arwiki")
        self.assertEqual(stats["wiki_breakdown"], {"arwiki": 50000, "commonswiki": 6000})

    @patch("requests.get")
    def test_fetch_global_stats_missing_user(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "query": {
                "globaluserinfo": {
                    "missing": ""
                }
            }
        }
        mock_get.return_value = mock_resp

        stats = fetch_global_stats("NonExistentUser1234567")
        self.assertEqual(stats["total_edits"], 0)
        self.assertEqual(stats["wiki_breakdown"], {})

    @patch("scripts.sync_data.fetch_members_from_meta")
    @patch("scripts.sync_data.fetch_global_stats")
    def test_sync_community_success(self, mock_stats, mock_members):
        mock_members.return_value = ["Reda benkhadra", "Anass Sedrati"]
        mock_stats.return_value = {
            "total_edits": 1200,
            "home_wiki": "ar.wikipedia.org",
            "wiki_breakdown": {"ar.wikipedia.org": 1200}
        }

        with self.app.app_context():
            comm = Community.query.get(self.c1_id)
            synced = sync_community(comm)
            self.assertEqual(synced, 2)

            users = User.query.all()
            self.assertEqual(len(users), 2)
            self.assertTrue(all(u.is_member for u in users))

            memberships = CommunityMember.query.filter_by(community_id=self.c1_id).all()
            self.assertEqual(len(memberships), 2)

            snapshots = StatSnapshot.query.all()
            self.assertEqual(len(snapshots), 2)

    @patch("scripts.sync_data.fetch_members_from_meta")
    def test_sync_community_retains_records_on_failure(self, mock_members):
        with self.app.app_context():
            # Seed an existing user and member
            existing_user = User(username="ExistingUser", is_member=True)
            db.session.add(existing_user)
            db.session.flush()

            cm = CommunityMember(
                community_id=self.c1_id,
                user_id=existing_user.id,
                role="member",
                verified=True
            )
            db.session.add(cm)
            db.session.commit()

            # Simulate network failure returning []
            mock_members.return_value = []

            comm = Community.query.get(self.c1_id)
            synced = sync_community(comm)
            self.assertEqual(synced, 0)

            # Records MUST NOT be wiped
            retained_users = User.query.all()
            self.assertEqual(len(retained_users), 1)
            retained_memberships = CommunityMember.query.filter_by(community_id=self.c1_id).all()
            self.assertEqual(len(retained_memberships), 1)

    @patch("scripts.sync_data.fetch_members_from_meta")
    @patch("scripts.sync_data.fetch_global_stats")
    def test_multi_community_sync_isolation(self, mock_stats, mock_members):
        # Community 1 succeeds, Community 2 fails with exception
        def side_effect(page_title):
            if "MA" in page_title:
                return ["UserMorocco"]
            raise RuntimeError("Tunisia parsing error")

        mock_members.side_effect = side_effect
        mock_stats.return_value = {
            "total_edits": 500,
            "home_wiki": "ar.wikipedia.org",
            "wiki_breakdown": {"ar.wikipedia.org": 500}
        }

        with self.app.app_context():
            # Community 1
            comm1 = Community.query.get(self.c1_id)
            c1_synced = sync_community(comm1)
            self.assertEqual(c1_synced, 1)

            # Community 2 should be isolated and caught
            comm2 = Community.query.get(self.c2_id)
            with self.assertRaises(RuntimeError):
                sync_community(comm2)

            # Ensure comm1 records were saved
            u1 = User.query.filter_by(username="UserMorocco").first()
            self.assertIsNotNone(u1)

if __name__ == "__main__":
    unittest.main()
