
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, ProjectMember
from ..auth import get_current_user
from pydantic import BaseModel
from typing import List

router = APIRouter()

# Schema
class RoleUpdate(BaseModel):
    email: str
    role: str # "super_admin", "moderator", "user"

# Dependency: Only Super Admin can manage roles
def require_super_admin(user: User = Depends(get_current_user)):
    if not user or user.global_role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin privileges required")
    return user

@router.get("/users", dependencies=[Depends(require_super_admin)])
def list_all_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@router.put("/users/role", dependencies=[Depends(require_super_admin)])
def update_user_role(data: RoleUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update Role
    user.global_role = data.role
    db.commit()
    
    return {"status": "updated", "email": user.email, "new_role": user.global_role}

@router.get("/me")
def get_my_profile(user: User = Depends(get_current_user)):
    if not user:
        return {"role": "guest", "permissions": []}
    return {
        "uid": user.firebase_uid,
        "email": user.email,
        "global_role": user.global_role,
        "projects": [p.project_id for p in user.project_memberships]
    }
