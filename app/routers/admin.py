
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..auth import get_current_user, GLOBAL_LEVELS
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime, timedelta

router = APIRouter()

# [?] [THOUGHT] Use Literal to enforce dropdown menus in Swagger UI.
# This strictly limits the values that can be sent to the API.
ValidRole = Literal["super_admin", "admin", "moderator", "nitro", "user", "guest"]

# AI-REMARK: SCHEMAS
class RoleUpdate(BaseModel):
    # One of the two (email or user_id) must be provided.
    email: Optional[str] = None
    user_id: Optional[str] = None
    
    # [!] [CRITICAL] Strict Pydantic validation.
    # Swagger will display a Dropdown Menu instead of a text field.
    role: ValidRole

class BanRequest(BaseModel):
    user_id: str
    is_active: bool  # False = Banned, True = Active
    reason: Optional[str] = "Violation of Terms of Service"

@router.get("/me", summary="Get My Profile")
def get_my_profile(user: User = Depends(get_current_user)):
    """
    [+] [INFO] Frontend entry point.
    Returns vital info: UID, Email, Global Role, and Project List.
    """
    return {
        "uid": user.firebase_uid,
        "email": user.email,
        "global_role": user.global_role,
        "is_active": user.is_active,
        "projects_count": len(user.project_memberships)
    }

@router.get("/users", summary="List Users (Paginated & Filtered)")
def list_all_users(
    # [?] [THOUGHT] Pagination avoids crashing the browser with thousands of users.
    skip: int = 0,
    limit: int = 50,
    role: Optional[ValidRole] = Query(None, description="Filter by exact role (e.g., 'nitro')"),
    email_search: Optional[str] = Query(None, description="Partial email search (e.g., 'gmail')"),
    only_guests: bool = Query(False, description="If True, ignores other filters and shows only Guests (email=null)"),
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Administrator Search Engine.
    
    **Permissions:**
    - Requires at least **ADMIN (Level 80)**.
    
    **Filters:**
    1. **role**: Shows only users with this specific role.
    2. **email_search**: Checks if string is contained in email (case-insensitive).
    3. **only_guests**: Exclusive filter for anonymous users (no email).
    """
    
    # [!] [CRITICAL] Security Check (Min: Admin)
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
        raise HTTPException(status_code=403, detail="Access reserved for Administrators (Level 80+)")
    
    query = db.query(User)
    
    # [decision:logic] Priority to 'Guests' filter as it is exclusive
    if only_guests:
        query = query.filter(User.email == None)
    
    # Filter 1: Specific Role (Validated by Swagger)
    if role:
        query = query.filter(User.global_role == role)
    
    # Filter 2: Email Search (SQL LIKE)
    if email_search:
        query = query.filter(User.email.ilike(f"%{email_search}%"))
        
    # [+] [INFO] Applying Pagination
    total_count = query.count()
    users = query.offset(skip).limit(limit).all()
    
    return {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "data": users
    }

@router.put("/users/role", summary="Update User Role")
def update_user_role(
    data: RoleUpdate, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Secure Privilege Update.
    
    **Security Rules (Anti-Abuse):**
    1. You must be at least **Moderator**.
    2. You cannot promote someone to a rank **higher or equal** to yours.
    3. You cannot demote someone with a rank **higher or equal** to yours.
    """
    
    # 1. Retrieve Hierarchy Levels (Integer)
    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    target_role_level = GLOBAL_LEVELS.get(data.role, 0)

    # [!] [CRITICAL] Safeguard 1: Entry Level
    if current_level < 60: # Minimum Moderator
        raise HTTPException(status_code=403, detail="Moderation rights required (Level 60+)")
    
    # [!] [CRITICAL] Safeguard 2: Hierarchy Protection
    if current_level < 100 and target_role_level >= current_level:
        raise HTTPException(status_code=403, detail=f"Forbidden: You (Lvl {current_level}) cannot assign rank {data.role} (Lvl {target_role_level})")

    # 2. Find Target
    target_user = None
    if data.user_id:
        target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    elif data.email:
        target_user = db.query(User).filter(User.email == data.email).first()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    # [?] [THOUGHT] Optional Check: Do not touch superiors
    target_current_level = GLOBAL_LEVELS.get(target_user.global_role, 0)
    if current_level < 100 and target_current_level >= current_level:
         raise HTTPException(status_code=403, detail="Forbidden: You cannot modify a superior.")

    # 3. Apply Change
    previous_role = target_user.global_role
    target_user.global_role = data.role
    db.commit()
    
    return {
        "status": "success", 
        "user_email": target_user.email or "Guest (No Email)", 
        "user_uid": target_user.firebase_uid,
        "change": f"{previous_role} -> {target_user.global_role}"
    }

# --- NEW FEATURES ---

@router.put("/users/ban", summary="Ban/Unban User")
def ban_user(data: BanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [!] [CRITICAL] Activates or Deactivates user access.
    Does not delete data, only prevents login.
    """
    # Only Admin (80+) can ban
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
        raise HTTPException(status_code=403, detail="Ban rights required (Admin)")

    target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    if not target_user:
        raise HTTPException(404, "User not found")
        
    # Protection: Cannot ban a superior
    target_level = GLOBAL_LEVELS.get(target_user.global_role, 0)
    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    
    if target_level >= current_level and user.global_role != "super_admin":
        raise HTTPException(403, "Impossible to ban a hierarchical superior")

    target_user.is_active = data.is_active
    db.commit()
    
    status_msg = "Active" if data.is_active else "Banned"
    return {"status": "success", "user_uid": target_user.firebase_uid, "account_state": status_msg}

@router.delete("/guests/cleanup", summary="Cleanup Guests")
def cleanup_guests(
    hours_old: int = 24, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [decision:logic] Permanently deletes users without email (Guests)
    created more than X hours ago. Keeps the DB clean.
    """
    if user.global_role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin required for cleanup")

    cutoff_time = datetime.utcnow() - timedelta(hours=hours_old)
    
    # Find expired guests
    expired_guests = db.query(User).filter(
        User.email == None,
        User.created_at < cutoff_time
    ).all()
    
    count = len(expired_guests)
    
    # Delete
    for guest in expired_guests:
        db.delete(guest)
    
    db.commit()
    
    return {
        "status": "cleaned", 
        "deleted_count": count, 
        "criteria": f"Guests older than {hours_old} hours"
    }
