
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from ..models import User
from ..schemas import UserPublic, UserProfile, ProjectSummary
from ..auth import get_current_user

router = APIRouter()

@router.get("/me", response_model=UserProfile)
def get_my_profile(user: User = Depends(get_current_user)):
    projects_list = []
    # Logic to map SQL relationships to Pydantic
    for membership in user.project_memberships:
        projects_list.append(ProjectSummary(id=membership.project_id, role=membership.project_role))
    
    return UserProfile(
        uid=user.firebase_uid,
        email=user.email,
        email_masked=user.email,
        global_role=user.global_role,
        is_active=user.is_active,
        created_at=user.created_at,
        projects=projects_list
    )

@router.get("/", response_model=List[UserPublic])
def list_public_users(
    skip: int = 0, limit: int = 50, role: Optional[str] = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    query = db.query(User).filter(User.is_active == True)
    if role: query = query.filter(User.global_role == role)
    users = query.offset(skip).limit(limit).all()
    
    results = []
    for u in users:
        masked = None
        if u.email:
            parts = u.email.split("@")
            if len(parts) == 2: masked = f"{parts[0][:2]}***@{parts[1]}"
        results.append(UserPublic(
            uid=u.firebase_uid, email_masked=masked, global_role=u.global_role,
            is_active=u.is_active, created_at=u.created_at
        ))
    return results
