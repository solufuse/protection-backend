
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    # [!] [CRITICAL] We keep Integer ID as Primary Key to match existing ProjectMember FK
    id = Column(Integer, primary_key=True, index=True)
    firebase_uid = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    global_role = Column(String, default="user")
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # [+] [INFO] New Ban Fields
    ban_reason = Column(String, nullable=True)
    admin_notes = Column(Text, nullable=True)

    project_memberships = relationship("ProjectMember", back_populates="user", cascade="all, delete-orphan")

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    storage_path = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # owner_id implies a relationship, we assume it exists or is handled by logic. 
    # Keeping structure generic based on your upload.
    owner_id = Column(String, nullable=True) 

    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")

class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id"))
    user_id = Column(Integer, ForeignKey("users.id")) # Points to Integer ID
    project_role = Column(String, default="viewer")

    user = relationship("User", back_populates="project_memberships")
    project = relationship("Project", back_populates="members")
