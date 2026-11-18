from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.mutable import MutableDict

db = SQLAlchemy()

class Community(db.Model):
  __tablename__ = "communities"
  
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(120), unique=True, nullable=False)
  slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
  meta_roster_page = db.Column(db.String(255), nullable=False)
  contact_email = db.Column(db.String(128), nullable=True)
  created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


#Relationships
  members = db.relationship("CommunityMember", back_populates="community", lazy=True, cascade="all, delete-orphan")
  projects = db.relationship("Project", back_populates="community", lazy=True, cascade="save-update, merge")

  
  def to_dict(self):
    return {
      "id": self.id,
      "name": self.name,
      "slug": self.slug,
      "meta_roster_page": self.meta_roster_page,
      "contact_email": self.contact_email,
      "created_at": self.created_at.isoformat() if self.created_at else None
    }

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(128), unique=True, nullable=False, index=True)
    is_member = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    mint_window_start = db.Column(db.DateTime, nullable=True)
    mint_window_count = db.Column(db.Integer, default=0, nullable=False)
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_synced = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    memberships = db.relationship("CommunityMember", back_populates="user", lazy=True, cascade="all, delete-orphan")
    snapshots = db.relationship("StatSnapshot", back_populates="user", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username} member={self.is_member} admin={self.is_admin}>"
    
    def to_dict(self):
        return {
        "id": self.id,
        "username": self.username,
        "is_member": self.is_member,
        "is_admin": self.is_admin,
        "first_seen": self.first_seen.isoformat() if self.first_seen else None,
        "last_synced": self.last_synced.isoformat() if self.last_synced else None
        }

class CommunityMember(db.Model):
  __tablename__ = "community_members"
  community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), primary_key=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
  role = db.Column(db.String(32), default="member")
  verified = db.Column(db.Boolean, default=True)
  added_at = db.Column(db.DateTime, default=datetime.utcnow)

  #Relationships
  community = db.relationship("Community", back_populates="members")
  user = db.relationship("User", back_populates="memberships")

  def to_dict(self):
    return {
      "community_id": self.community_id,
      "user_id": self.user_id,
      "role": self.role,
      "verified": self.verified,
      "added_at": self.added_at.isoformat() if self.added_at else None
    }


class StatSnapshot(db.Model):
    __tablename__ = "stat_snapshots"
    __table_args__ = (
        db.Index("ix_stat_snapshots_user_recorded", "user_id", db.text("recorded_at DESC")),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    total_edits = db.Column(db.Integer, default=0, nullable=False)
    home_wiki = db.Column(db.String(64), default="ar.wikipedia.org")
    wiki_breakdown = db.Column(db.JSON, nullable=True)  # {"ar.wikipedia": 120, "commons": 45}
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    #relationship
    user = db.relationship("User",back_populates="snapshots")

    def __repr__(self):
        return f"<StatSnapshot user_id={self.user_id} edits={self.total_edits}>"


class ProjectTag(db.Model):
    __tablename__ = "project_tags"

    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag = db.Column(db.String(64), primary_key=True, index=True)

    project = db.relationship("Project", back_populates="tags_rel")

    def __repr__(self):
        return f"<ProjectTag project_id={self.project_id} tag={self.tag!r}>"


class Project(db.Model):
    __tablename__ = "projects"
    __table_args__ = (
        db.Index("ix_projects_active_status_start", "is_deleted", "status", "start_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)  # Bleach sanitized HTML
    project_type = db.Column(db.String(64), default="Workshop", nullable=False)
    target_wiki = db.Column(db.String(64), default="ar.wikipedia.org", nullable=False)
    wiki_link = db.Column(db.String(1024), nullable=True)
    campaign = db.Column(db.String(128), nullable=True, index=True)
    primary_lang = db.Column(db.String(16), default="ar", nullable=False)
    translations = db.Column(MutableDict.as_mutable(db.JSON), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(32), default="In Progress", nullable=False)  # Planned, In Progress, Completed, Canceled

    # Ownership & Roles
    lead_organizer = db.Column(db.String(128), nullable=False, index=True)
    co_organizers = db.Column(db.JSON, nullable=True)  # ["UserA", "UserB"]
    is_contest = db.Column(db.Boolean, default=False, nullable=False)
    jury_members = db.Column(db.JSON, nullable=True)   # ["Jury1", "Jury2"]
    participants = db.Column(db.JSON, nullable=True)   # ["User1", "User2"]
    results = db.Column(db.JSON, nullable=True)        # {"summary": str, "winners": List[str], "metrics": dict, "notes": str}

    # Soft-delete governance
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by = db.Column(db.String(128), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    community = db.relationship("Community", back_populates="projects")
    tags_rel = db.relationship("ProjectTag", back_populates="project", lazy=True, cascade="all, delete-orphan")

    @property
    def tags(self):
        return sorted(t.tag for t in (self.tags_rel or []))

    @property
    def target_wiki_url(self):
        from app.wiki_utils import resolve_wiki_url
        return resolve_wiki_url(self.target_wiki)

    @property
    def project_type_ar(self):
        from app.wiki_utils import translate_activity_type
        return translate_activity_type(self.project_type)

    @property
    def status_ar(self):
        from app.wiki_utils import translate_status
        return translate_status(self.status)

    def t_type(self, lang=None):
        from app.wiki_utils import translate_activity_type
        return translate_activity_type(self.project_type, lang=lang)

    def t_status(self, lang=None):
        from app.wiki_utils import translate_status
        return translate_status(self.status, lang=lang)

    def _primary_field_value(self, field_name):
        if field_name == "title":
            return self.title or ""
        if field_name == "description":
            return self.description or ""
        if field_name == "results_summary":
            return (self.results or {}).get("summary", "") or ""
        if field_name == "results_notes":
            return (self.results or {}).get("notes", "") or ""
        return ""

    def localized_text(self, field_name, target_lang=None):
        """Return localized text for target_lang, falling back to primary language value."""
        if target_lang is None:
            try:
                from flask import has_request_context
                if has_request_context():
                    from app.i18n import current_locale
                    target_lang = current_locale()
            except Exception:
                target_lang = "ar"
        primary = (self.primary_lang or "ar").strip().lower()
        tl = (target_lang or "").strip().lower()
        if tl and tl != primary and isinstance(self.translations, dict):
            entry = self.translations.get(tl) or self.translations.get(target_lang)
            if isinstance(entry, dict):
                val = entry.get(field_name)
                if isinstance(val, str) and val.strip():
                    return val
        return self._primary_field_value(field_name)

    def localized_source_lang(self, field_name, target_lang=None):
        """Return the language code actually backing localized_text(field_name, target_lang)."""
        if target_lang is None:
            try:
                from flask import has_request_context
                if has_request_context():
                    from app.i18n import current_locale
                    target_lang = current_locale()
            except Exception:
                target_lang = "ar"
        primary = (self.primary_lang or "ar").strip().lower()
        tl = (target_lang or "").strip().lower()
        if tl and tl != primary and isinstance(self.translations, dict):
            entry = self.translations.get(tl) or self.translations.get(target_lang)
            if isinstance(entry, dict):
                val = entry.get(field_name)
                if isinstance(val, str) and val.strip():
                    return tl
        return primary

    def sync_status_with_dates(self):
        """Update status if dates indicate a change based on calendar; preserve Canceled."""
        if self.status in ("Canceled", "Cancelled"):
            return self.status
        if not self.start_date and not self.end_date:
            return self.status
        from app.wiki_utils import determine_project_status
        new_status = determine_project_status(
            self.start_date, self.end_date, "auto", current_status=self.status
        )
        if new_status != self.status:
            self.status = new_status
        return self.status

    @property
    def all_organizers(self):
        orgs = []
        if self.lead_organizer and self.lead_organizer.strip():
            orgs.append(self.lead_organizer.strip())
        for co in (self.co_organizers or []):
            if co and isinstance(co, str) and co.strip() and co.strip() not in orgs:
                orgs.append(co.strip())
        return orgs

    def to_dict(self, lang=None):
        data = {
            "id": self.id,
            "community_id": self.community_id,
            "community_name": self.community.name if self.community else None,
            "community_slug": self.community.slug if self.community else None,
            "title": self.title,
            "description": self.description,
            "project_type": self.project_type,
            "target_wiki": self.target_wiki,
            "target_wiki_url": self.target_wiki_url,
            "wiki_link": self.wiki_link,
            "campaign": self.campaign,
            "tags": self.tags,
            "primary_lang": self.primary_lang or "ar",
            "translations": self.translations or {},
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status,
            "lead_organizer": self.lead_organizer,
            "co_organizers": self.co_organizers or [],
            "all_organizers": self.all_organizers,
            "is_contest": self.is_contest,
            "jury_members": self.jury_members or [],
            "participants": self.participants or [],
            "results": self.results or {},
            "is_deleted": bool(self.is_deleted),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
        if lang:
            data["localized_title"] = self.localized_text("title", lang)
            data["localized_description"] = self.localized_text("description", lang)
            data["localized_lang"] = self.localized_source_lang("title", lang)
        return data
