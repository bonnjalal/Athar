from datetime import date, datetime
from app import create_app, db
from app.models import Community, User, CommunityMember, StatSnapshot, Project

app = create_app()

with app.app_context():
    db.create_all()

    # مسح البيانات القديمة لتفادي التكرار عند كل تجربة
    Project.query.delete()
    StatSnapshot.query.delete()
    CommunityMember.query.delete()
    User.query.delete()
    Community.query.delete()
    db.session.commit()

    # 1. إضافة المجتمعات (Communities)
    wm_ma = Community(
        name="Wikimedia Morocco",
        slug="wm-ma",
        meta_roster_page="https://meta.wikimedia.org/wiki/Wikimedia_MA_User_Group/Members",
    )
    wm_tn = Community(
        name="Wikimedia Kuwait",
        slug="wm-tn",
        meta_roster_page="https://meta.wikimedia.org/wiki/Wikimedians_of_Kuwait_User_Group/Membership",
    )
    db.session.add_all([wm_ma, wm_tn])
    db.session.flush()

    # 2. إضافة الأعضاء وإحصائياتهم (Users & StatSnapshots)
    users_sample = [
        {
            "username": "MoroccoVolunteer",
            "community": wm_ma,
            "total_edits": 4850,
            "home_wiki": "ar.wikipedia",
            "wiki_breakdown": {"ar.wikipedia": 3100, "commons": 1200, "wikidata": 550},
        },
        {
            "username": "Bonnjalal00",
            "community": wm_ma,
            "total_edits": 15420,
            "home_wiki": "ar.wikipedia",
            "wiki_breakdown": {"ar.wikipedia": 8900, "commons": 3520, "wikidata": 3000},
        },
        {
            "username": "Mounir_Afifi",
            "community": wm_ma,
            "total_edits": 11200,
            "home_wiki": "commons",
            "wiki_breakdown": {"commons": 7200, "ar.wikipedia": 2800, "wikidata": 1200},
        },
        {
            "username": "Rotana_Wiki",
            "community": wm_ma,
            "total_edits": 6340,
            "home_wiki": "wikidata",
            "wiki_breakdown": {"wikidata": 4100, "ar.wikipedia": 1540, "commons": 700},
        },
        {
            "username": "KuwaitiEditor",
            "community": wm_tn,
            "total_edits": 9800,
            "home_wiki": "ar.wikipedia",
            "wiki_breakdown": {"ar.wikipedia": 6000, "commons": 2800, "wikidata": 1000},
        },
    ]

    for item in users_sample:
        u = User(
            username=item["username"],
            is_member=True,
            first_seen=datetime.utcnow(),
            last_synced=datetime.utcnow(),
        )
        db.session.add(u)
        db.session.flush()

        cm = CommunityMember(
            community_id=item["community"].id, user_id=u.id
        )
        snap = StatSnapshot(
            user_id=u.id,
            total_edits=item["total_edits"],
            home_wiki=item["home_wiki"],
            wiki_breakdown=item["wiki_breakdown"],
            recorded_at=datetime.utcnow(),
        )
        db.session.add_all([cm, snap])

    # 3. إضافة المشاريع التجريبية (Projects)
    projects_sample = [
        Project(
            community_id=wm_ma.id,
            title="Wiki Loves Monuments 2026 Morocco",
            description="Annual photography contest documenting historic Moroccan monuments on Wikimedia Commons.",
            project_type="Contest / Competition",
            target_wiki="commons",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 10, 31),
            status="In Progress",
            lead_organizer="MoroccoVolunteer",
            co_organizers=["Bonnjalal00", "Mounir_Afifi"],
            jury_members=["Rotana_Wiki"],
        ),
        Project(
            community_id=wm_ma.id,
            title="OpenRefine & Wikidata Workshop",
            description="Hands-on training session for university students on structured data.",
            project_type="Workshop",
            target_wiki="wikidata",
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 12),
            status="Completed",
            lead_organizer="Bonnjalal00",
            co_organizers=["MoroccoVolunteer"],
            jury_members=[],
        ),
        Project(
            community_id=wm_ma.id,
            title="Moroccan Cultural Heritage Edit-a-thon",
            description="Collaborative editing drive expanding Arabic Wikipedia articles.",
            project_type="Edit-a-thon",
            target_wiki="ar.wikipedia",
            start_date=date(2026, 10, 15),
            end_date=date(2026, 10, 25),
            status="In Progress",
            lead_organizer="Mounir_Afifi",
            co_organizers=["Rotana_Wiki"],
            jury_members=[],
        ),
        Project(
            community_id=wm_ma.id,
            title="Medina Architectural Photo Walk",
            description="Guided photography walk capturing high-resolution images of traditional gates.",
            project_type="Photo Walk",
            target_wiki="commons",
            start_date=date(2026, 11, 2),
            end_date=date(2026, 11, 2),
            status="Planned",
            lead_organizer="MoroccoVolunteer",
            co_organizers=[],
            jury_members=[],
        ),
        Project(
            community_id=wm_tn.id,
            title="Carthage Archaeological Sites Edit-a-thon",
            description="Documenting Kuwaiti historical landmarks across Arabic Wikipedia.",
            project_type="Edit-a-thon",
            target_wiki="ar.wikipedia",
            start_date=date(2026, 10, 5),
            end_date=date(2026, 10, 20),
            status="Completed",
            lead_organizer="KuwaitiEditor",
            co_organizers=[],
            jury_members=[],
        ),
    ]

    db.session.add_all(projects_sample)
    db.session.commit()
    print("✅ Done! Test data inserted successfully into dev.db.")
