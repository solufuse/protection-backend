
# [structure:root]
# ADMIN ROUTER - User Management & System Cleanup
# Handles Roles, Bans, and the critical Guest Cleanup Logic.

import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from firebase_admin import auth 
from typing import List, Optional, Literal
from pydantic import BaseModel
from datetime import datetime, timedelta

from ..database import get_db
from ..models import User
from ..auth import get_current_user, GLOBAL_LEVELS

router = APIRouter()

# [decision:logic] Centralized Storage Root definition
STORAGE_ROOT = "/app/storage"

# [?] [THOUGHT] Rigid typing for Swagger UI Dropdowns
ValidRole = Literal["super_admin", "admin", "moderator", "nitro", "user", "guest"]

# --- SCHEMAS ---
class RoleUpdate(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None
    role: ValidRole

class BanRequest(BaseModel):
    user_id: str
    is_active: bool  # False = Banned
    reason: Optional[str] = "Terms of Service Violation"

# --- ROUTES ---

@router.get("/me", summary="Get My Profile")
def get_my_profile(user: User = Depends(get_current_user)):
    # [+] [INFO] Essential for Frontend Auth State
    return {
        "uid": user.firebase_uid,
        "email": user.email,
        "global_role": user.global_role,
        "is_active": user.is_active,
        "projects_count": len(user.project_memberships)
    }

@router.get("/users", summary="List Users (Admin Filter)")
def list_all_users(
    skip: int = 0,
    limit: int = 50,
    role: Optional[ValidRole] = Query(None),
    email_search: Optional[str] = Query(None),
    only_guests: bool = Query(False),
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    # [!] [CRITICAL] Minimum Admin Level Required (80)
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
        raise HTTPException(403, "Admin access required")
    
    query = db.query(User)
    
    if only_guests:
        query = query.filter(User.email == None)
    if role:
        query = query.filter(User.global_role == role)
    if email_search:
        query = query.filter(User.email.ilike(f"%{email_search}%"))
        
    total_count = query.count()
    users = query.offset(skip).limit(limit).all()
    
    return {"total": total_count, "data": users}

@router.put("/users/role", summary="Update User Role")
def update_user_role(
    data: RoleUpdate, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    # [decision:logic] Hierarchical Protection
    # A moderator cannot promote someone to admin (above themselves).
    
    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    target_role_level = GLOBAL_LEVELS.get(data.role, 0)

    if current_level < 60: # Moderator Min
        raise HTTPException(403, "Moderator access required")
    
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

    # Protection: Do not touch superiors
    target_current_level = GLOBAL_LEVELS.get(target_user.global_role, 0)
    if current_level < 100 and target_current_level >= current_level:
         raise HTTPException(403, "Cannot modify a superior")

    target_user.global_role = data.role
    db.commit()
    
    return {"status": "success", "new_role": target_user.global_role}

@router.put("/users/ban", summary="Ban/Unban User")
def ban_user(data: BanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
        raise HTTPException(403, "Admin access required")

    target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    if not target_user:
        raise HTTPException(404, "User not found")
        
    target_level = GLOBAL_LEVELS.get(target_user.global_role, 0)
    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    
    if target_level >= current_level and user.global_role != "super_admin":
        raise HTTPException(403, "Cannot ban a superior")

    target_user.is_active = data.is_active
    db.commit()
    return {"status": "success", "is_active": target_user.is_active}

# --- CLEANUP LOGIC ---

@router.delete("/guests/cleanup", summary="Total Guest Purge (Firebase+Disk+DB)")
def cleanup_guests(
    hours_old: int = 24, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [!] [CRITICAL] SYSTEM MAINTENANCE
    1. Identifies Guests (no email) older than X hours.
    2. Deletes them from Firebase Auth (prevents ghost accounts).
    3. Wipes their data from /app/storage (frees up disk space).
    4. Removes them from SQL Database.
    """
    if user.global_role != "super_admin":
        raise HTTPException(403, "Super Admin required")

    cutoff_time = datetime.utcnow() - timedelta(hours=hours_old)
    
    expired_guests = db.query(User).filter(
        User.email == None,
        User.created_at < cutoff_time
    ).all()
    
    report = {
        "found": len(expired_guests),
        "firebase_deleted": 0,
        "storage_cleaned": 0,
        "db_deleted": 0,
        "errors": []
    }
    
    # [?] [THOUGHT] Pre-fetch directory listing to avoid repeated OS calls
    try:
        if os.path.exists(STORAGE_ROOT):
            all_folders = os.listdir(STORAGE_ROOT)
        else:
            all_folders = []
    except:
        all_folders = []

    for guest in expired_guests:
        uid = guest.firebase_uid
        
        # 1. Firebase Delete
        try:
            auth.delete_user(uid)
            report["firebase_deleted"] += 1
        except Exception as e:
            # AI-REMARK: User might already be deleted in Firebase, log but continue.
            report["errors"].append(f"Firebase {uid}: {str(e)}")

        # 2. Storage Delete
        # We look for any folder starting with the UID (e.g., UID_ProjectID)
        cleaned_folders = 0
        for folder_name in all_folders:
            if folder_name.startswith(uid):
                full_path = os.path.join(STORAGE_ROOT, folder_name)
                try:
                    if os.path.exists(full_path):
                        shutil.rmtree(full_path)
                        cleaned_folders += 1
                except Exception as e:
                    report["errors"].append(f"Storage {folder_name}: {str(e)}")
        
        if cleaned_folders > 0:
            report["storage_cleaned"] += 1

        # 3. DB Delete
        try:
            db.delete(guest)
            report["db_deleted"] += 1
        except Exception as e:
            report["errors"].append(f"DB {uid}: {str(e)}")

    db.commit()
    return report
