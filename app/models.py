
from sqlalchemy import Column, Integer, String, ForeignKey, Enum, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    firebase_uid = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    global_role = Column(String, default="user")
    
    # [+] [INFO] Nouveaux champs pour la gestion avancée
    is_active = Column(Boolean, default=True)  # True = Autorisé, False = Banni
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project_memberships = relationship("ProjectMember", back_populates="user")

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    storage_path = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")

class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    project_role = Column(String, default="viewer")

    user = relationship("User", back_populates="project_memberships")
    project = relationship("Project", back_populates="members")
