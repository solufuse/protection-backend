
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime, date

# Shared Types
ValidRole = Literal["super_admin", "admin", "moderator", "nitro", "user", "guest"]

# --- PROJECT SCHEMAS ---
class ProjectSummary(BaseModel):
    id: str
    role: str
    class Config:
        orm_mode = True

# --- USER SCHEMAS ---

# 1. Update Request (What the user sends to change profile)
class UserUpdate(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[date] = None
    bio: Optional[str] = None

# 2. Public View (What others see in Forum/Directory)
class UserPublic(BaseModel):
    uid: str
    username: Optional[str]      # Show Pseudo if available
    email_masked: Optional[str]  # Fallback if no pseudo
    global_role: str
    bio: Optional[str]
    is_active: bool
    created_at: Optional[datetime]
    class Config:
        orm_mode = True

# 3. Me View (Private Profile)
class UserProfile(UserPublic):
    email: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    birth_date: Optional[date]
    projects: List[ProjectSummary] = []

# 4. Admin View (Full Details)
class UserAdminView(UserPublic):
    email: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
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
