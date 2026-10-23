import sys
import os
import unittest
from unittest.mock import patch
import requests

# Ensure project root is in sys.path when running script directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.parse_members import (
    extract_members_from_wikitext,
    fetch_members_from_meta,
    normalize_meta_page_title
)

class TestWikitextParser(unittest.TestCase):
    def test_normalize_meta_page_url(self):
        cases = {
            "https://meta.wikimedia.org/wiki/Wikimedia_MA_User_Group/Members": "Wikimedia_MA_User_Group/Members",
            "https://meta.wikimedia.org/wiki/Wikimedia_MA_User_Group/Members#List": "Wikimedia_MA_User_Group/Members",
            "https://meta.wikimedia.org/w/index.php?title=Wikimedia_MA_User_Group/Members": "Wikimedia_MA_User_Group/Members",
            "Wikimedia_MA_User_Group/Members": "Wikimedia_MA_User_Group/Members",
            "https://meta.wikimedia.org/wiki/Wikimedia_Tunisie/Membres": "Wikimedia_Tunisie/Membres"
        }
        for url, expected in cases.items():
            self.assertEqual(normalize_meta_page_title(url), expected)

    def test_morocco_roster_extraction(self):
        sample = """
        {{:Wikimedia MA User Group/tabs}}
        {{Wikimedia Morocco}}

        == List of current members ==
        #{{user|Reda benkhadra}}
        #{{user|Anass Sedrati}}
        #{{user|Rachidourkia}}
        #{{user|رشيدة رقي}}
        #{{user|Lhoussine_AIT_TAYFST}}
        #{{user|Bonnjalal00}}
        """
        members = extract_members_from_wikitext(sample)
        self.assertIn("Reda benkhadra", members)
        self.assertIn("Anass Sedrati", members)
        self.assertIn("Rachidourkia", members)
        self.assertIn("رشيدة رقي", members)
        self.assertIn("Lhoussine AIT TAYFST", members)
        self.assertIn("Bonnjalal00", members)
        self.assertEqual(len(members), 6)

    def test_template_variants(self):
        sample = """
        * {{user|UserOne}}
        * {{User|UserTwo}}
        * {{u|UserThree}}
        * {{user2|UserFour}}
        * {{مستخدم|مستخدم_تجريبي}}
        """
        members = extract_members_from_wikitext(sample)
        self.assertEqual(members, ["UserOne", "UserTwo", "UserThree", "UserFour", "مستخدم تجريبي"])

    def test_wikilinks_and_subpages(self):
        sample = """
        * [[User:RedaMorocco|رضا]]
        * [[User:FatimaWiki|فاطمة]]
        * [[User:TestUser/Sandbox|مسودة]]
        * [[مستخدم:عمر_الناقد]]
        """
        members = extract_members_from_wikitext(sample)
        self.assertIn("RedaMorocco", members)
        self.assertIn("FatimaWiki", members)
        self.assertIn("TestUser", members)
        self.assertIn("عمر الناقد", members)

    def test_deduplication_and_order(self):
        sample = """
        # {{user|Bonnjalal00}}
        # [[User:bonnjalal00]]
        # {{user|Bonnjalal00}}
        # {{user|AnotherUser}}
        """
        members = extract_members_from_wikitext(sample)
        self.assertEqual(members, ["Bonnjalal00", "AnotherUser"])

    @patch("builtins.print")
    @patch("requests.get")
    def test_fetch_error_isolation(self, mock_get, mock_print):
        # Network failure returns empty list rather than throwing
        mock_get.side_effect = requests.RequestException("Connection timeout")
        result = fetch_members_from_meta("https://meta.wikimedia.org/wiki/Faulty_Page_Title")
        self.assertEqual(result, [])

if __name__ == "__main__":
    unittest.main()
