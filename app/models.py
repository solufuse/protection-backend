
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    # Core IDs
    id = Column(Integer, primary_key=True, index=True)
    firebase_uid = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    global_role = Column(String, default="user")
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Profile Fields
    username = Column(String, unique=True, index=True, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)
    bio = Column(String, nullable=True)

    # Admin / Ban System
    ban_reason = Column(String, nullable=True)
    admin_notes = Column(Text, nullable=True)

    project_memberships = relationship("ProjectMember", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="author", cascade="all, delete-orphan") # [+] Link to messages

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    storage_path = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    owner_id = Column(String, nullable=True)

    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="project", cascade="all, delete-orphan") # [+] Link to messages

class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    project_role = Column(String, default="viewer")

    user = relationship("User", back_populates="project_memberships")
    project = relationship("Project", back_populates="members")

# [+] [NEW] MESSAGE TABLE FOR FORUM/CHAT
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False) # Le corps du message
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True) # Pour savoir si édité

    # Relationships
    user_id = Column(Integer, ForeignKey("users.id")) # Qui ?
    project_id = Column(String, ForeignKey("projects.id")) # Où ?

    author = relationship("User", back_populates="messages")
    project = relationship("Project", back_populates="messages")
