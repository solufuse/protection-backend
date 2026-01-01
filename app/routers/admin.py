
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from firebase_admin import auth 
from typing import List, Optional
from datetime import datetime, timedelta
from ..database import get_db
from ..models import User
from ..schemas import UserAdminView, BanRequest
from ..auth import get_current_user, GLOBAL_LEVELS

router = APIRouter()
STORAGE_ROOT = "/app/storage"

def require_admin(user: User = Depends(get_current_user)):
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
        raise HTTPException(403, "Admin access required")
    return user

@router.get("/users", response_model=List[UserAdminView])
def list_admin_users(skip: int = 0, limit: int = 50, email_search: Optional[str] = None, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(User)
    if email_search: query = query.filter(User.email.ilike(f"%{email_search}%"))
    users = query.offset(skip).limit(limit).all()
    results = []
    for u in users:
        results.append(UserAdminView(
            uid=u.firebase_uid, email=u.email, email_masked=u.email,
            global_role=u.global_role, is_active=u.is_active, created_at=u.created_at,
            ban_reason=u.ban_reason, admin_notes=u.admin_notes
        ))
    return results

@router.put("/users/ban")
def ban_user(data: BanRequest, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    if not target_user: raise HTTPException(404, "User not found")
    
    if GLOBAL_LEVELS.get(target_user.global_role, 0) >= GLOBAL_LEVELS.get(user.global_role, 0) and user.global_role != "super_admin":
        raise HTTPException(403, "Cannot ban a superior")

    target_user.is_active = data.is_active
    if not data.is_active:
        target_user.ban_reason = data.reason
        if data.notes: target_user.admin_notes = data.notes
    else:
        target_user.ban_reason = None
    db.commit()
    return {"status": "success", "is_active": target_user.is_active}

@router.delete("/guests/cleanup")
def cleanup_guests(hours_old: int = 24, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.global_role != "super_admin": raise HTTPException(403, "Super Admin only")
    
    cutoff = datetime.utcnow() - timedelta(hours=hours_old)
    expired = db.query(User).filter(User.email == None, User.created_at < cutoff).all()
    report = {"found": len(expired), "errors": []}
    
    for guest in expired:
        # 1. Firebase
        try: auth.delete_user(guest.firebase_uid)
        except: pass
        
        # 2. Storage
        try:
            if os.path.exists(STORAGE_ROOT):
                for f in os.listdir(STORAGE_ROOT):
                    if f.startswith(guest.firebase_uid): 
                        shutil.rmtree(os.path.join(STORAGE_ROOT, f))
        except: pass
        
        # 3. DB
        try: db.delete(guest)
        except: pass
        
    db.commit()
    return report
