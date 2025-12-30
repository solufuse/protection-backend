
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    firebase_uid = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    
    # ROLE GLOBAL (Staff Solufuse)
    # Values: "super_admin", "moderator", "user"
    global_role = Column(String, default="user") 
    
    project_memberships = relationship("ProjectMember", back_populates="user")

class Project(Base):
    __tablename__ = "projects"
    id = Column(String, primary_key=True, index=True) 
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    storage_path = Column(String)
    
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")

class ProjectMember(Base):
    __tablename__ = "project_members"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # ROLE PROJET (Interne au client)
    # Values: "owner" (Delete), "admin" (Add Member), "editor" (Write), "viewer" (Read)
    project_role = Column(String, default="viewer")
    
    user = relationship("User", back_populates="project_memberships")
    project = relationship("Project", back_populates="members")
