from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Community(db.Model):
  __tablename__ = "communities"
  
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(120), unique=True, nullable=False)
  slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
  meta_roster_page = db.Column(db.String(255), nullable=False)
  default_wiki = db.Column(db.String(64), default="ar.wikipedia.org")
  contact_email = db.Column(db.String(128), nullable=True)
  created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


#Relationships
  members = db.relationship("CommunityMember", back_populates="community", lazy=True, cascade="all, delete-orphan")
  projects = db.relationship("Project", back_populates="community", lazy=True, cascade="all, delete-orphan")

  
  def to_dict(self):
    return {
      "id": self.id,
      "name": self.name,
      "slug": self.slug,
      "meta_roster_page": self.meta_roster_page,
      "default_wiki": self.default_wiki,
      "contact_email": self.contact_email,
      "created_at": self.created_at.isoformat() if self.created_at else None
    }

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(128), unique=True, nullable=False, index=True)
    is_member = db.Column(db.Boolean, default=True, nullable=False)
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_synced = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    memberships = db.relationship("CommunityMember", back_populates="user", lazy=True, cascade="all, delete-orphan")
    snapshots = db.relationship("StatSnapshot", back_populates="user", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username} member={self.is_member}>"
    
    def to_dict(self):
        return {
        "id": self.id,
        "username": self.username,
        "is_member": self.is_member,
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


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)  # Bleach sanitized HTML
    project_type = db.Column(db.String(64), default="Workshop", nullable=False)
    target_wiki = db.Column(db.String(64), default="ar.wikipedia.org", nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(32), default="In Progress", nullable=False)  # Planned, In Progress, Completed

    # Ownership & Roles
    lead_organizer = db.Column(db.String(128), nullable=False)
    co_organizers = db.Column(db.JSON, nullable=True)  # ["UserA", "UserB"]
    is_contest = db.Column(db.Boolean, default=False, nullable=False)
    jury_members = db.Column(db.JSON, nullable=True)   # ["Jury1", "Jury2"]

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    community = db.relationship("Community",back_populates="projects")

    def to_dict(self):
        return {
            "id": self.id,
            "community_id": self.community_id,
            "title": self.title,
            "description": self.description,
            "project_type": self.project_type,
            "target_wiki": self.target_wiki,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status,
            "lead_organizer": self.lead_organizer,
            "co_organizers": self.co_organizers or [],
            "is_contest": self.is_contest,
            "jury_members": self.jury_members or [],
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
