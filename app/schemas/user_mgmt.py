
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime

# Shared Types
ValidRole = Literal["super_admin", "admin", "moderator", "nitro", "user", "guest"]

# --- PROJECT SCHEMAS ---
class ProjectSummary(BaseModel):
    id: str
    role: str
    class Config:
        orm_mode = True

# --- USER SCHEMAS ---

# 1. Public View (Base)
class UserPublic(BaseModel):
    uid: str
    email_masked: Optional[str]
    global_role: str
    is_active: bool
    created_at: Optional[datetime]
    class Config:
        orm_mode = True

# 2. Me View (Profile)
class UserProfile(UserPublic):
    email: Optional[str]
    projects: List[ProjectSummary] = []

# 3. Admin View (Full Details)
class UserAdminView(UserPublic):
    email: Optional[str]
    ban_reason: Optional[str]
    admin_notes: Optional[str]

# --- ACTION SCHEMAS ---
class BanRequest(BaseModel):
    user_id: str
    is_active: bool
    reason: Optional[str] = None
    notes: Optional[str] = None


class RoleUpdate(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None
    role: ValidRole
