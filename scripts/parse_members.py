#!/usr/bin/env python3
"""
Member List Parser for Meta-Wiki
Extracts usernames using mwparserfromhell AST instead of fragile regex.
Supports user templates ({{user|...}}, {{u|...}}, etc.) and User: wikilinks.
"""
import sys
import os
import requests
import mwparserfromhell

# Ensure app package is importable when script is executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from urllib.parse import urlparse, parse_qs, unquote
from config import Config

DEFAULT_USER_AGENT = "Athar/1.0 (https://athar.toolforge.org; bonnjalal@gmail.com)"

USER_TEMPLATE_NAMES = {
    "user", "user2", "user3", "u", "userlink", "user-link", "مستخدم"
}
USER_PREFIXES = ("user:", "user_talk:", "مستخدم:", "نقاش_المستخدم:")

def normalize_meta_page_title(page_or_url):
    """
    Extract the clean MediaWiki page title from a raw string or full URL.
    Examples:
      - 'https://meta.wikimedia.org/wiki/Wikimedia_MA_User_Group/Members' -> 'Wikimedia_MA_User_Group/Members'
      - 'https://meta.wikimedia.org/w/index.php?title=Wikimedia_MA_User_Group/Members' -> 'Wikimedia_MA_User_Group/Members'
      - 'Wikimedia_MA_User_Group/Members' -> 'Wikimedia_MA_User_Group/Members'
    """
    if not page_or_url:
        return ""

    raw = str(page_or_url).strip()

    if "://" in raw or raw.startswith("//") or raw.startswith("/wiki/"):
        parsed = urlparse(raw)
        qs = parse_qs(parsed.query)
        if "title" in qs and qs["title"]:
            title = qs["title"][0]
        elif "/wiki/" in parsed.path:
            title = parsed.path.split("/wiki/", 1)[1]
        else:
            title = parsed.path.lstrip("/")
    else:
        title = raw

    title = title.split("#")[0].strip()
    title = unquote(title).lstrip("/").strip()
    return title

def extract_members_from_wikitext(raw_wikitext):
    """
    Parse raw wikitext AST using mwparserfromhell to extract usernames.
    Extracts from templates ({{user|Username}}, etc.) and wikilinks ([[User:Username]]).
    """
    if not raw_wikitext:
        return []

    wikicode = mwparserfromhell.parse(raw_wikitext)
    members = []
    seen = set()

    def clean_and_add(raw_username):
        if not raw_username:
            return
        cleaned = str(raw_username).strip()
        # Strip namespace prefixes if present (e.g. User:Foo)
        for prefix in USER_PREFIXES:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        # Remove subpages (e.g. Foo/Sandbox -> Foo)
        cleaned = cleaned.split("/")[0].strip()
        # Canonicalize underscores to spaces per MediaWiki conventions
        cleaned = cleaned.replace("_", " ").strip()
        # Deduplicate case-insensitively while preserving order
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            members.append(cleaned)

    # 1. Extract from user templates
    for template in wikicode.filter_templates():
        tname = str(template.name).strip().lower()
        if tname in USER_TEMPLATE_NAMES:
            if template.has(1):
                clean_and_add(template.get(1).value)
            elif template.params:
                clean_and_add(template.params[0].value)

    # 2. Extract from direct wikilinks
    for link in wikicode.filter_wikilinks():
        target = str(link.title).strip()
        for prefix in USER_PREFIXES:
            if target.lower().startswith(prefix):
                clean_and_add(target)
                break

    return members

def fetch_members_from_meta(page_title=None, user_agent=None):
    """
    Fetch wikitext from Meta-Wiki API for a given page title or full URL and extract member usernames.
    Supports both raw page titles ('Wikimedia_MA_User_Group/Members') and full URLs
    ('https://meta.wikimedia.org/wiki/Wikimedia_MA_User_Group/Members').
    Guarantees that network errors, timeouts, or invalid pages return [] without crashing.
    """
    if not page_title:
        page_title = getattr(Config, "META_ROSTER_PAGE", "Wikimedia_MA_User_Group/Members")

    page_title = normalize_meta_page_title(page_title)
    if not page_title:
        return []

    ua = user_agent or getattr(Config, "USER_AGENT", DEFAULT_USER_AGENT)
    url = "https://meta.wikimedia.org/w/api.php"
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "wikitext",
        "format": "json"
    }
    headers = {"User-Agent": ua}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"[Warning] HTTP {resp.status_code} when fetching Meta page '{page_title}'")
            return []
        data = resp.json()
        raw_wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
    except requests.RequestException as e:
        print(f"[Error] Network error fetching Meta page '{page_title}': {e}")
        return []
    except Exception as e:
        print(f"[Error] Failed to parse response for Meta page '{page_title}': {e}")
        return []

    return extract_members_from_wikitext(raw_wikitext)

if __name__ == "__main__":
    page = sys.argv[1] if len(sys.argv) > 1 else None
    roster = fetch_members_from_meta(page)
    print(f"Extracted {len(roster)} members: {roster[:5]}...")
