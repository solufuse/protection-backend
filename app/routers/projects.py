
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Project, ProjectMember
from ..auth import get_current_user, ProjectAccessChecker, GLOBAL_LEVELS, PROJECT_LEVELS, QUOTAS
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class ProjectCreate(BaseModel):
    id: str
    name: str

class MemberInvite(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None
    role: str = "viewer"

# --- ROUTES ---

@router.get("/")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [decision:logic] Visibility Rules:
    - Super Admin, Admin, Moderator: See ALL projects.
    - Nitro, User: See ONLY projects where they are members.
    """
    if not user: return []
    
    # Staff Global (Moderator+) sees everything
    if GLOBAL_LEVELS.get(user.global_role, 0) >= 60:
        return db.query(Project).all()
        
    # Standard Users see their memberships
    return [m.project for m in user.project_memberships]

@router.post("/create")
def create_project(project: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Guests cannot create. Check Quotas.
    if not user: raise HTTPException(401)
    
    user_quota = QUOTAS.get(user.global_role, QUOTAS["guest"])
    max_projects = user_quota["max_projects"]
    
    if max_projects != -1:
        owned_count = 0
        for m in user.project_memberships:
            if m.project_role == "owner": owned_count += 1
        
        if owned_count >= max_projects:
            if user.global_role == "guest": raise HTTPException(403, "Guests cannot create projects.")
            elif user.global_role == "user": raise HTTPException(403, "Limit reached (1 Project). Upgrade to Nitro.")
            else: raise HTTPException(403, f"Limit reached ({max_projects}).")

    if db.query(Project).filter(Project.id == project.id).first():
        raise HTTPException(400, "Project ID already exists")
    
    storage_path = f"/app/storage/{project.id}"
    if not os.path.exists(storage_path): os.makedirs(storage_path, exist_ok=True)
    
    new_proj = Project(id=project.id, name=project.name, storage_path=storage_path)
    db.add(new_proj); db.commit()
    
    mem = ProjectMember(project_id=new_proj.id, user_id=user.id, project_role="owner")
    db.add(mem); db.commit()
    return {"status": "created", "id": new_proj.id, "role": user.global_role}

@router.delete("/{project_id}")
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [decision:logic] Delete Rules:
    - Super Admin: YES
    - Admin: YES
    - Owner: YES
    - Moderator: NO (Can see but not delete)
    """
    is_staff = user.global_role in ["super_admin", "admin"] # Moderator excluded from delete
    
    member = db.query(ProjectMember).filter(ProjectMember.project_id==project_id, ProjectMember.user_id==user.id).first()
    is_owner = member and member.project_role == "owner"
    
    if not (is_staff or is_owner): 
        raise HTTPException(403, "Insufficient permissions to delete this project")
        
    proj = db.query(Project).filter(Project.id == project_id).first()
    if proj:
        folder_path = f"/app/storage/{project_id}"
        if os.path.exists(folder_path):
            try: shutil.rmtree(folder_path)
            except: pass
        db.delete(proj); db.commit()
        return {"status": "deleted", "id": project_id}
    raise HTTPException(404, "Project not found")

@router.post("/{project_id}/members")
def invite_or_update_member(project_id: str, invite: MemberInvite, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [decision:logic] Invite Rules:
    - Super Admin, Admin, Moderator: Can invite/update ANYONE in ANY project.
    - Project Owner/Admin: Can invite to their project.
    """
    
    # 1. Global Staff Bypass (Super Admin, Admin, Moderator)
    is_global_staff = GLOBAL_LEVELS.get(user.global_role, 0) >= 60
    
    if not is_global_staff:
        # Standard Check: Must be Project Moderator+
        checker = ProjectAccessChecker(required_role="moderator")
        checker(project_id, user, db)

    # 2. Logic to prevent Moderators from promoting to Admin if they are not Admin themselves
    # (Skipped for Global Staff who have power)
    
    target_user = None
    if invite.user_id: target_user = db.query(User).filter(User.firebase_uid == invite.user_id).first()
    elif invite.email: target_user = db.query(User).filter(User.email == invite.email).first()
    
    if not target_user: raise HTTPException(404, "User not found")

    existing = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target_user.id).first()
    
    if existing:
        existing.project_role = invite.role
        db.commit()
        return {"status": "updated", "uid": target_user.firebase_uid, "role": invite.role}

    new_member = ProjectMember(project_id=project_id, user_id=target_user.id, project_role=invite.role)
    db.add(new_member); db.commit()
    return {"status": "added", "uid": target_user.firebase_uid, "role": invite.role}

@router.get("/{project_id}/members")
def list_project_members(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Global Staff can always see members
    if GLOBAL_LEVELS.get(user.global_role, 0) < 60:
        checker = ProjectAccessChecker(required_role="viewer")
        checker(project_id, user, db)
        
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    return [{"uid": m.user.firebase_uid, "email": m.user.email, "role": m.project_role} for m in members]

@router.delete("/{project_id}/members/{target_uid}")
def kick_member(project_id: str, target_uid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Global Staff can kick anyone (except Super Admin owners)
    is_global_staff = GLOBAL_LEVELS.get(user.global_role, 0) >= 60
    
    if not is_global_staff:
        checker = ProjectAccessChecker(required_role="moderator")
        checker(project_id, user, db)

    target_user = db.query(User).filter(User.firebase_uid == target_uid).first()
    if not target_user: raise HTTPException(404, "User not found")

    membership = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target_user.id).first()
    if not membership: raise HTTPException(404, "Member not found")
    
    if membership.project_role == "owner": raise HTTPException(403, "Cannot kick the Owner")
    
    # Protection: Admin cannot kick Super Admin
    if target_user.global_role == "super_admin" and user.global_role != "super_admin":
        raise HTTPException(403, "Cannot kick a Super Admin")

    db.delete(membership); db.commit()
    return {"status": "kicked", "uid": target_uid}
