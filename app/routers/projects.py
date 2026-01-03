
# [structure:root]
# PROJECTS ROUTER - Handles Project CRUD & Membership
# Features: Forum Logic (PUBLIC_), Namespacing (UID_), and Quota enforcement.

import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from ..database import get_db
from ..models import User, Project, ProjectMember
from ..auth import get_current_user, ProjectAccessChecker, GLOBAL_LEVELS, PROJECT_LEVELS, QUOTAS
from pydantic import BaseModel, Field
from typing import List, Optional

router = APIRouter()

# --- SCHEMAS ---
class ProjectCreate(BaseModel):
    # [decision:logic] Limit ID to 20 chars and restrict special chars to avoid URL issues
    id: str = Field(..., min_length=3, max_length=20, pattern="^[a-zA-Z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=20)

class MemberInvite(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None
    role: str = "viewer"

# --- ROUTES ---

@router.get("/")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [decision:logic] Hybrid Visibility Logic:
    1. Staff (>=60) sees EVERYTHING.
    2. Users see:
       - Projects they joined (Private).
       - AND Projects starting with 'PUBLIC_' (Open Forums).
    """
    if not user: return []
    results = {} # Use dict to avoid duplicates
    
    # 1. Global Staff Logic
    if GLOBAL_LEVELS.get(user.global_role, 0) >= 60:
        all_projs = db.query(Project).all()
        for p in all_projs:
            mem = db.query(ProjectMember).filter(ProjectMember.project_id == p.id, ProjectMember.user_id == user.id).first()
            role = mem.project_role if mem else "admin"
            results[p.id] = {"id": p.id, "name": p.name, "role": role}
            
    # 2. Standard User Logic
    else:
        # A. Private Memberships
        for m in user.project_memberships:
            results[m.project.id] = {"id": m.project.id, "name": m.project.name, "role": m.project_role}
        
        # B. Public Projects (Forum)
        public_projects = db.query(Project).filter(Project.id.like("PUBLIC_%")).all()
        for p in public_projects:
            if p.id not in results:
                # Default role for non-members in public channels is viewer
                results[p.id] = {"id": p.id, "name": p.name, "role": "viewer"}
            
    return list(results.values())

@router.post("/create")
def create_project(project: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [+] [INFO] Create project with Namespace Protection.
    [decision:logic] 
    - PUBLIC_: Reserved for Admins. No Prefix.
    - Private: Prefixed with UID_ to prevent ID collisions between users.
    """
    if not user: raise HTTPException(401)
    
    final_project_id = project.id.strip()
    
    # [!] [CRITICAL] PUBLIC RESERVATION
    if final_project_id.upper().startswith("PUBLIC_"):
        # Security Check
        if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
            raise HTTPException(403, "Only Admins can create PUBLIC_ channels.")
        # Logic: Keep ID clean (e.g. "PUBLIC_NEWS")
        pass 
    else:
        # [decision:logic] PRIVATE NAMESPACING
        # "my-app" becomes "firebaseuid_my-app"
        final_project_id = f"{user.firebase_uid}_{final_project_id}"

    # Quota Check
    user_quota = QUOTAS.get(user.global_role, QUOTAS["guest"])
    max_projects = user_quota["max_projects"]
    
    if max_projects != -1:
        owned_count = sum(1 for m in user.project_memberships if m.project_role == "owner")
        if owned_count >= max_projects:
            if user.global_role == "guest": raise HTTPException(403, "Guests cannot create projects.")
            elif user.global_role == "user": raise HTTPException(403, "Free plan limit reached (1 Project). Upgrade to Nitro.")
            else: raise HTTPException(403, f"Project limit reached ({max_projects}).")

    # Collision Check
    if db.query(Project).filter(Project.id == final_project_id).first():
        raise HTTPException(400, "You already have a project with this name (or ID collision)")
    
    # Storage Creation
    storage_path = f"/app/storage/{final_project_id}"
    if not os.path.exists(storage_path): 
        os.makedirs(storage_path, exist_ok=True)
    
    owner_uid = str(user.firebase_uid)

    new_proj = Project(
        id=final_project_id, 
        name=project.name, 
        storage_path=storage_path,
        owner_id=owner_uid
    )
    db.add(new_proj); db.commit()
    
    mem = ProjectMember(project_id=new_proj.id, user_id=user.id, project_role="owner")
    db.add(mem); db.commit()
    
    # [!] [INFO] Return actual ID so frontend knows the real path
    return {"status": "created", "id": final_project_id, "role": "owner"}

@router.delete("/{project_id}")
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """ [!] [CRITICAL] Deletes DB entry AND Storage folder. """
    is_staff = user.global_role in ["super_admin", "admin"]
    member = db.query(ProjectMember).filter(ProjectMember.project_id==project_id, ProjectMember.user_id==user.id).first()
    is_owner = member and member.project_role == "owner"
    
    if not (is_staff or is_owner): 
        raise HTTPException(403, "Insufficient permissions to delete this project")
        
    proj = db.query(Project).filter(Project.id == project_id).first()
    if proj:
        # Clean Disk
        folder_path = f"/app/storage/{project_id}"
        if os.path.exists(folder_path):
            try: shutil.rmtree(folder_path)
            except: pass
        # Clean DB
        db.delete(proj); db.commit()
        return {"status": "deleted", "id": project_id}
    raise HTTPException(404, "Project not found")

@router.post("/{project_id}/members")
def invite_or_update_member(project_id: str, invite: MemberInvite, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 1. Determine Inviter Level
    inviter_level = 0
    is_global_staff = GLOBAL_LEVELS.get(user.global_role, 0) >= 60
    
    if is_global_staff:
        inviter_level = 100 
    else:
        current_mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
        if not current_mem:
            # [decision:logic] Allow self-join to PUBLIC_ as viewer
            if project_id.startswith("PUBLIC_") and invite.role == "viewer" and (invite.user_id == user.firebase_uid or not invite.user_id):
                 inviter_level = 10 
            else:
                 raise HTTPException(403, "You are not a member of this project")
        else:
            if PROJECT_LEVELS.get(current_mem.project_role, 0) < PROJECT_LEVELS.get("moderator"):
                 raise HTTPException(403, "Moderator rights required")
            inviter_level = PROJECT_LEVELS.get(current_mem.project_role, 0)

    # 2. Determine Target Role Level
    target_role_level = PROJECT_LEVELS.get(invite.role, 0)
    
    if target_role_level >= inviter_level and not is_global_staff:
        raise HTTPException(403, f"Cannot assign role '{invite.role}' equal/higher than yours")

    # 3. Find Target
    target_user = None
    if invite.user_id: target_user = db.query(User).filter(User.firebase_uid == invite.user_id).first()
    elif invite.email: target_user = db.query(User).filter(User.email == invite.email).first()
    if not target_user: raise HTTPException(404, "User not found")

    # 4. Update/Create
    existing = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target_user.id).first()
    if existing:
        existing_level = PROJECT_LEVELS.get(existing.project_role, 0)
        if existing_level >= inviter_level and not is_global_staff:
            raise HTTPException(403, "Cannot modify a member with equal/higher rank")
        existing.project_role = invite.role
        db.commit()
        return {"status": "updated", "uid": target_user.firebase_uid, "role": invite.role}

    new_member = ProjectMember(project_id=project_id, user_id=target_user.id, project_role=invite.role)
    db.add(new_member); db.commit()
    return {"status": "added", "uid": target_user.firebase_uid, "role": invite.role}

@router.get("/{project_id}/members")
def list_project_members(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Public projects are readable, so we skip strict check
    if not project_id.startswith("PUBLIC_"):
        if GLOBAL_LEVELS.get(user.global_role, 0) < 60:
            checker = ProjectAccessChecker(required_role="viewer")
            checker(project_id, user, db)
        
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    
    # [+] [INFO] Return enriched member list (with Username)
    return [{
        "uid": m.user.firebase_uid, 
        "email": m.user.email, 
        "username": m.user.username,
        "role": m.project_role,
        "global_role": m.user.global_role 
    } for m in members]

@router.delete("/{project_id}/members/{target_uid}")
def kick_member(project_id: str, target_uid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inviter_level = 0
    is_global_staff = GLOBAL_LEVELS.get(user.global_role, 0) >= 60
    
    if is_global_staff:
        inviter_level = 100
    else:
        current_mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
        if not current_mem: raise HTTPException(403, "Access denied")
        inviter_level = PROJECT_LEVELS.get(current_mem.project_role, 0)
        if inviter_level < PROJECT_LEVELS.get("moderator"):
             raise HTTPException(403, "Rights required")

    target_user = db.query(User).filter(User.firebase_uid == target_uid).first()
    if not target_user: raise HTTPException(404, "User not found")

    membership = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target_user.id).first()
    if not membership: raise HTTPException(404, "Member not found")
    
    target_level = PROJECT_LEVELS.get(membership.project_role, 0)
    if target_level >= inviter_level:
        raise HTTPException(403, "Cannot kick this member")
    
    if target_user.global_role == "super_admin" and user.global_role != "super_admin":
        raise HTTPException(403, "Cannot kick a Super Admin")

    db.delete(membership); db.commit()
    return {"status": "kicked", "uid": target_uid}
