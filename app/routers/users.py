
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from ..models import User
# [!] [INFO] Import new schemas including UserUpdate
from ..schemas import UserPublic, UserProfile, ProjectSummary, UserUpdate
from ..auth import get_current_user

router = APIRouter()

@router.get("/me", response_model=UserProfile, summary="Get My Profile")
def get_my_profile(user: User = Depends(get_current_user)):
    projects_list = []
    for membership in user.project_memberships:
        projects_list.append(ProjectSummary(id=membership.project_id, role=membership.project_role))
    
    # [?] [THOUGHT] Logic for email masking is handled in frontend or public view, 
    # but here we return full data because it's ME.
    return UserProfile(
        uid=user.firebase_uid,
        email=user.email,
        email_masked=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        birth_date=user.birth_date,
        bio=user.bio,
        global_role=user.global_role,
        is_active=user.is_active,
        created_at=user.created_at,
        projects=projects_list
    )

@router.put("/me", response_model=UserProfile, summary="Update My Profile")
def update_my_profile(
    data: UserUpdate, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Allows user to set nickname, bio, etc.
    [!] [CRITICAL] Checks uniqueness of username if changed.
    """
    if data.username and data.username != user.username:
        # Check if taken
        existing = db.query(User).filter(User.username == data.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        user.username = data.username

    if data.first_name is not None: user.first_name = data.first_name
    if data.last_name is not None: user.last_name = data.last_name
    if data.bio is not None: user.bio = data.bio
    if data.birth_date is not None: user.birth_date = data.birth_date

    db.commit()
    db.refresh(user)
    
    # Re-use the GET logic (copy-paste for simplicity in response)
    projects_list = [ProjectSummary(id=m.project_id, role=m.project_role) for m in user.project_memberships]
    
    return UserProfile(
        uid=user.firebase_uid,
        email=user.email,
        email_masked=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        birth_date=user.birth_date,
        bio=user.bio,
        global_role=user.global_role,
        is_active=user.is_active,
        created_at=user.created_at,
        projects=projects_list
    )

@router.get("/", response_model=List[UserPublic], summary="List Public Users")
def list_public_users(
    skip: int = 0, limit: int = 50, role: Optional[str] = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    query = db.query(User).filter(User.is_active == True)
    if role: query = query.filter(User.global_role == role)
    users = query.offset(skip).limit(limit).all()
    
    results = []
    for u in users:
        # [decision:logic] If username exists, use it. Else mask email.
        masked = None
        if u.email:
            parts = u.email.split("@")
            if len(parts) == 2: masked = f"{parts[0][:2]}***@{parts[1]}"
            
        results.append(UserPublic(
            uid=u.firebase_uid, 
            username=u.username,
            email_masked=masked, 
            bio=u.bio,
            global_role=u.global_role,
            is_active=u.is_active, 
            created_at=u.created_at
        ))
    return results
