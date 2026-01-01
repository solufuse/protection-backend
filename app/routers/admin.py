
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from firebase_admin import auth 
from typing import List, Optional
from datetime import datetime, timedelta

from ..database import get_db
from ..models import User
# [!] [CRITICAL] Import via the package (thanks to __init__.py fix)
from ..schemas import UserAdminView, BanRequest, ValidRole, RoleUpdate
from ..auth import get_current_user, GLOBAL_LEVELS

router = APIRouter()
STORAGE_ROOT = "/app/storage"

# --- PERMISSIONS ---
def require_admin(user: User = Depends(get_current_user)):
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
        raise HTTPException(403, "Admin access required")
    return user

def require_super_admin(user: User = Depends(get_current_user)):
    if user.global_role != "super_admin":
        raise HTTPException(403, "Super Admin access required")
    return user

# --- 1. LIST USERS (Admin View) ---
@router.get("/users", response_model=List[UserAdminView], summary="List Users (Full Details)")
def list_admin_users(
    skip: int = 0, 
    limit: int = 50, 
    email_search: Optional[str] = None, 
    role: Optional[str] = None,
    user: User = Depends(require_admin), 
    db: Session = Depends(get_db)
):
    query = db.query(User)
    
    if email_search:
        query = query.filter(User.email.ilike(f"%{email_search}%"))
    if role:
        query = query.filter(User.global_role == role)
        
    users = query.offset(skip).limit(limit).all()
    
    # Mapping logic is handled by Pydantic 'orm_mode = True' in schemas
    # But we explicitly build the list to ensure all fields are passed
    results = []
    for u in users:
        results.append(UserAdminView(
            uid=u.firebase_uid,
            email=u.email,
            email_masked=u.email, # Admin sees full email
            global_role=u.global_role,
            is_active=u.is_active,
            created_at=u.created_at,
            ban_reason=u.ban_reason,
            admin_notes=u.admin_notes
        ))
    return results

# --- 2. UPDATE ROLE (The Missing Function) ---
@router.put("/users/role", summary="Promote/Demote User")
def update_user_role(
    data: RoleUpdate, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    # Hierarchy Check
    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    target_role_level = GLOBAL_LEVELS.get(data.role, 0)

    if current_level < 60: # Moderator Min
        raise HTTPException(403, "Moderator access required")
    
    # Cannot promote someone above yourself
    if current_level < 100 and target_role_level >= current_level:
        raise HTTPException(403, "Cannot assign a rank equal or higher than your own")

    # Find Target
    target_user = None
    if data.user_id:
        target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    elif data.email:
        target_user = db.query(User).filter(User.email == data.email).first()
    
    if not target_user:
        raise HTTPException(404, "User not found")

    # Cannot modify a superior
    target_current_level = GLOBAL_LEVELS.get(target_user.global_role, 0)
    if current_level < 100 and target_current_level >= current_level:
         raise HTTPException(403, "Cannot modify a superior")

    target_user.global_role = data.role
    db.commit()
    
    return {"status": "success", "new_role": target_user.global_role, "user": target_user.email}

# --- 3. BAN SYSTEM ---
@router.put("/users/ban", summary="Ban/Unban User")
def ban_user(data: BanRequest, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    if not target_user: 
        raise HTTPException(404, "User not found")
    
    if GLOBAL_LEVELS.get(target_user.global_role, 0) >= GLOBAL_LEVELS.get(user.global_role, 0) and user.global_role != "super_admin":
        raise HTTPException(403, "Cannot ban a superior")

    target_user.is_active = data.is_active
    
    if not data.is_active:
        target_user.ban_reason = data.reason
        if data.notes: 
            target_user.admin_notes = data.notes
    else:
        target_user.ban_reason = None
        
    db.commit()
    return {"status": "success", "is_active": target_user.is_active}

# --- 4. CLEANUP (Firebase + Disk + DB) ---
@router.delete("/guests/cleanup", summary="Total Guest Purge")
def cleanup_guests(
    hours_old: int = 24, 
    user: User = Depends(require_super_admin), 
    db: Session = Depends(get_db)
):
    cutoff = datetime.utcnow() - timedelta(hours=hours_old)
    expired = db.query(User).filter(User.email == None, User.created_at < cutoff).all()
    report = {"found": len(expired), "errors": []}
    
    for guest in expired:
        uid = guest.firebase_uid
        # 1. Firebase
        try: auth.delete_user(uid)
        except Exception as e: report["errors"].append(f"Auth {uid}: {e}")
        
        # 2. Storage
        try:
            if os.path.exists(STORAGE_ROOT):
                for f in os.listdir(STORAGE_ROOT):
                    # Matches folder starting with UID (e.g. UID_ProjectID)
                    if f.startswith(uid): 
                        shutil.rmtree(os.path.join(STORAGE_ROOT, f))
        except Exception as e: report["errors"].append(f"Storage {uid}: {e}")
        
        # 3. DB
        try: db.delete(guest)
        except Exception as e: report["errors"].append(f"DB {uid}: {e}")
        
    db.commit()
    return report
