
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..auth import get_current_user, GLOBAL_LEVELS
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

# AI-REMARK: SCHEMAS
class RoleUpdate(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None  # Support for Firebase UID
    role: str # super_admin, admin, moderator, nitro, user

@router.get("/me")
def get_my_profile(user: User = Depends(get_current_user)):
    """ [+] [INFO] Returns current logged user profile & global rank. """
    return {
        "uid": user.firebase_uid,
        "email": user.email,
        "global_role": user.global_role,
        "projects": [p.project_id for p in user.project_memberships]
    }

@router.get("/users")
def list_all_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """ [+] [INFO] Only Super Admin or Admin can see the full user list. """
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80: # Min Admin (80)
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return db.query(User).all()

@router.put("/users/role")
def update_user_role(data: RoleUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [+] [INFO] Promotes/Demotes a user via Email OR Firebase UID.
    [decision:logic] Hierarchy check: Cannot promote someone to a rank higher than yours.
    """
    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    
    # 1. Security: Need at least Moderator (60)
    if current_level < 60:
        raise HTTPException(status_code=403, detail="Droit de modération requis")
    
    # 2. Prevent promoting to a role higher than self
    target_role_level = GLOBAL_LEVELS.get(data.role, 0)
    if current_level < 100 and target_role_level >= current_level:
        raise HTTPException(status_code=403, detail="Interdit de promouvoir à un rang supérieur ou égal au vôtre")

    # 3. Find target user (UID priority, then Email)
    target_user = None
    if data.user_id:
        target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    elif data.email:
        target_user = db.query(User).filter(User.email == data.email).first()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    # [+] [INFO] Applying the new global role
    target_user.global_role = data.role
    db.commit()
    
    return {
        "status": "success", 
        "target_email": target_user.email, 
        "new_global_role": target_user.global_role
    }
