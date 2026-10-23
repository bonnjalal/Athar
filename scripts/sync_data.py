#!/usr/bin/env python3
"""
Scheduled Background Worker for Toolforge
Runs every 4 hours to synchronize member rosters across all registered communities
and query Wikimedia CentralAuth global stats.
"""
import sys
import os
from datetime import datetime
import requests

# Ensure app package is importable when script is executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config
from app import create_app, db
from app.models import Community, User, CommunityMember, StatSnapshot
from scripts.parse_members import fetch_members_from_meta

DEFAULT_USER_AGENT = "Athar/1.0 (https://athar.toolforge.org; bonnjalal@gmail.com)"

def fetch_global_stats(username, user_agent=None):
    """
    Query MediaWiki CentralAuth API for global edit counts and wiki breakdown.
    Returns a dictionary of stats, or None if the request fails.
    """
    url = "https://meta.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "meta": "globaluserinfo",
        "guiuser": username,
        "guiprop": "editcount|merged",
        "format": "json"
    }
    ua = user_agent or getattr(Config, "USER_AGENT", DEFAULT_USER_AGENT)
    headers = {"User-Agent": ua}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"[Warning] HTTP {resp.status_code} for CentralAuth query '{username}'")
            return None

        data = resp.json()
        gui = data.get("query", {}).get("globaluserinfo", {})
        if not gui or "missing" in gui:
            return {
                "total_edits": 0,
                "home_wiki": "ar.wikipedia.org",
                "wiki_breakdown": {}
            }

        breakdown = {}
        for item in gui.get("merged", []):
            count = item.get("editcount", 0)
            if count > 0:
                breakdown[item.get("wiki")] = count

        return {
            "total_edits": gui.get("editcount", 0),
            "home_wiki": gui.get("home", "ar.wikipedia.org"),
            "wiki_breakdown": breakdown
        }
    except requests.RequestException as e:
        print(f"[Warning] CentralAuth network timeout/error for {username}: {e}")
        return None
    except Exception as e:
        print(f"[Warning] Unexpected error parsing CentralAuth stats for {username}: {e}")
        return None

def sync_community(community):
    """
    Synchronize roster and CentralAuth statistics for a single community.
    Errors are isolated to this community so other communities are not aborted.
    """
    page_title = community.meta_roster_page
    if not page_title:
        print(f"[Skip] Community '{community.name}' has no meta_roster_page defined.")
        return 0

    print(f"[Sync] Processing '{community.name}' from Meta page: '{page_title}'...")
    usernames = fetch_members_from_meta(page_title)

    if not usernames:
        print(f"[Warning] No members retrieved for '{community.name}'. Retaining existing database records.")
        return 0

    synced_count = 0
    now = datetime.utcnow()

    for username in usernames:
        try:
            # 1. User resolution
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(
                    username=username,
                    is_member=True,
                    first_seen=now,
                    last_synced=now
                )
                db.session.add(user)
                db.session.flush()
            else:
                user.is_member = True
                user.last_synced = now

            # 2. Community membership resolution
            membership = CommunityMember.query.filter_by(
                community_id=community.id,
                user_id=user.id
            ).first()

            if not membership:
                membership = CommunityMember(
                    community_id=community.id,
                    user_id=user.id,
                    role="member",
                    verified=True,
                    added_at=now
                )
                db.session.add(membership)
            else:
                membership.verified = True

            # 3. Fetch global stats from CentralAuth
            stats = fetch_global_stats(username)
            if stats:
                snapshot = StatSnapshot(
                    user_id=user.id,
                    total_edits=stats["total_edits"],
                    home_wiki=stats["home_wiki"],
                    wiki_breakdown=stats["wiki_breakdown"],
                    recorded_at=now
                )
                db.session.add(snapshot)

            synced_count += 1
        except Exception as member_err:
            print(f"[Warning] Error syncing member '{username}' for '{community.name}': {member_err}")
            continue

    db.session.commit()
    print(f"[Sync] Successfully synchronized {synced_count}/{len(usernames)} members for '{community.name}'.")
    return synced_count

def run_sync():
    """
    Multi-community sync loop:
    Iterates over all registered communities in the database with strict error isolation.
    """
    app = create_app()
    with app.app_context():
        communities = Community.query.all()
        if not communities:
            print("[Sync] No communities found in database. Initializing default Wikimedia Morocco community...")
            default_comm = Community(
                name="Wikimedia Morocco",
                slug="wm-ma",
                meta_roster_page="Wikimedia_MA_User_Group/Members",
                default_wiki="ar.wikipedia.org",
                contact_email="bonnjalal@gmail.com"
            )
            db.session.add(default_comm)
            db.session.commit()
            communities = [default_comm]

        total_communities = len(communities)
        print(f"[Sync] Starting ingestion for {total_communities} registered community/communities...")

        for index, community in enumerate(communities, start=1):
            try:
                print(f"\n--- [{index}/{total_communities}] {community.name} (slug: {community.slug}) ---")
                sync_community(community)
            except Exception as comm_err:
                db.session.rollback()
                print(f"[Error] Failed to process community '{community.name}': {comm_err}")
                print("[Error] Isolated failure: continuing to next community.")

        print("\n[Sync] Multi-community synchronization cycle complete.")

if __name__ == "__main__":
    run_sync()
