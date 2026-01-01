
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime

ValidRole = Literal["super_admin", "admin", "moderator", "nitro", "user", "guest"]

class ProjectSummary(BaseModel):
    id: str
    role: str
    class Config:
        orm_mode = True

class UserPublic(BaseModel):
    uid: str
    email_masked: Optional[str]
    global_role: str
    is_active: bool
    created_at: Optional[datetime]
    class Config:
        orm_mode = True

class UserProfile(UserPublic):
    email: Optional[str]
    projects: List[ProjectSummary] = []

class UserAdminView(UserPublic):
    email: Optional[str]
    ban_reason: Optional[str]
    admin_notes: Optional[str]

class BanRequest(BaseModel):
    user_id: str
    is_active: bool
    reason: Optional[str] = None
    notes: Optional[str] = None
