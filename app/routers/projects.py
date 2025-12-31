
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

# --- SCHEMAS ---
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
    [decision:logic] Returns projects enriched with the user's role (owner vs member).
    UI uses this to display the Crown icon 👑 for owners.
    """
    if not user: return []
    results = []
    
    # 1. Global Staff (Super Admin / Admin / Mod) sees ALL projects
    if GLOBAL_LEVELS.get(user.global_role, 0) >= 60:
        all_projs = db.query(Project).all()
        for p in all_projs:
            # Check if staff is explicitly a member, otherwise assign 'staff_override'
            mem = db.query(ProjectMember).filter(ProjectMember.project_id == p.id, ProjectMember.user_id == user.id).first()
            role = mem.project_role if mem else "admin"
            results.append({"id": p.id, "name": p.name, "role": role})
            
    # 2. Standard Users (Nitro / User) see only their memberships
    else:
        for m in user.project_memberships:
            results.append({"id": m.project.id, "name": m.project.name, "role": m.project_role})
            
    return results

@router.post("/create")
def create_project(project: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [+] [INFO] Create project with Quota checks.
    """
    if not user: raise HTTPException(401)
    
    # Check Quotas
    user_quota = QUOTAS.get(user.global_role, QUOTAS["guest"])
    max_projects = user_quota["max_projects"]
    
    if max_projects != -1:
        owned_count = 0
        for m in user.project_memberships:
            if m.project_role == "owner": owned_count += 1
        
        if owned_count >= max_projects:
            if user.global_role == "guest": raise HTTPException(403, "Guests cannot create projects.")
            elif user.global_role == "user": raise HTTPException(403, "Free plan limit reached (1 Project). Upgrade to Nitro.")
            else: raise HTTPException(403, f"Project limit reached ({max_projects}).")

    if db.query(Project).filter(Project.id == project.id).first():
        raise HTTPException(400, "Project ID already exists")
    
    storage_path = f"/app/storage/{project.id}"
    if not os.path.exists(storage_path): os.makedirs(storage_path, exist_ok=True)
    
    new_proj = Project(id=project.id, name=project.name, storage_path=storage_path)
    db.add(new_proj); db.commit()
    
    mem = ProjectMember(project_id=new_proj.id, user_id=user.id, project_role="owner")
    db.add(mem); db.commit()
    
    return {"status": "created", "id": new_proj.id, "role": "owner"}

@router.delete("/{project_id}")
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [decision:logic] Deletion Rules:
    - Super Admin / Admin: YES
    - Owner: YES
    - Moderator: NO (Read-only on structure)
    """
    is_staff = user.global_role in ["super_admin", "admin"]
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
    [+] [INFO] Add or Update project member with STRICT Hierarchy checks.
    [decision:logic] A user cannot assign a role higher or equal to their own.
    """
    
    # 1. Determine Inviter Level
    # Global Staff (>= 60) are implicitly above Project Owner (50), so they bypass strict checks.
    inviter_level = 0
    is_global_staff = GLOBAL_LEVELS.get(user.global_role, 0) >= 60
    
    if is_global_staff:
        inviter_level = 100 # God mode relative to project
    else:
        # Standard User: Must be a member of the project
        current_mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
        if not current_mem:
            raise HTTPException(403, "You are not a member of this project")
        
        # Check Entry Barrier (Must be at least Moderator to invite)
        if PROJECT_LEVELS.get(current_mem.project_role, 0) < PROJECT_LEVELS.get("moderator"):
             raise HTTPException(403, "Moderator rights required to invite")
             
        inviter_level = PROJECT_LEVELS.get(current_mem.project_role, 0)

    # 2. Determine Target Role Level
    target_role_level = PROJECT_LEVELS.get(invite.role, 0)
    
    # [!] [CRITICAL] Constraint 1: Cannot promote equal or higher
    if target_role_level >= inviter_level:
        raise HTTPException(403, f"Insufficient permissions: You (Lvl {inviter_level}) cannot assign role '{invite.role}' (Lvl {target_role_level})")

    # 3. Find Target User
    target_user = None
    if invite.user_id: target_user = db.query(User).filter(User.firebase_uid == invite.user_id).first()
    elif invite.email: target_user = db.query(User).filter(User.email == invite.email).first()
    
    if not target_user: raise HTTPException(404, "User not found")

    # 4. Handle Update or Create
    existing = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target_user.id).first()
    
    if existing:
        # [!] [CRITICAL] Constraint 2: Cannot modify someone equal or higher
        existing_level = PROJECT_LEVELS.get(existing.project_role, 0)
        if existing_level >= inviter_level:
            raise HTTPException(403, f"Insufficient permissions: You cannot modify a member with rank '{existing.project_role}'")
            
        existing.project_role = invite.role
        db.commit()
        return {"status": "updated", "uid": target_user.firebase_uid, "role": invite.role}

    new_member = ProjectMember(project_id=project_id, user_id=target_user.id, project_role=invite.role)
    db.add(new_member); db.commit()
    return {"status": "added", "uid": target_user.firebase_uid, "role": invite.role}

@router.get("/{project_id}/members")
def list_project_members(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [+] [INFO] Lists members. 
    [decision:logic] Includes 'global_role' so Frontend can display badges (Admin/Nitro).
    """
    if GLOBAL_LEVELS.get(user.global_role, 0) < 60:
        checker = ProjectAccessChecker(required_role="viewer")
        checker(project_id, user, db)
        
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    
    return [{
        "uid": m.user.firebase_uid, 
        "email": m.user.email, 
        "role": m.project_role,
        "global_role": m.user.global_role 
    } for m in members]

@router.delete("/{project_id}/members/{target_uid}")
def kick_member(project_id: str, target_uid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [+] [INFO] Kick a member from the project.
    """
    inviter_level = 0
    is_global_staff = GLOBAL_LEVELS.get(user.global_role, 0) >= 60
    
    if is_global_staff:
        inviter_level = 100
    else:
        current_mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
        if not current_mem: raise HTTPException(403, "Access denied")
        inviter_level = PROJECT_LEVELS.get(current_mem.project_role, 0)
        
        if inviter_level < PROJECT_LEVELS.get("moderator"):
            raise HTTPException(403, "Moderator rights required to kick")

    target_user = db.query(User).filter(User.firebase_uid == target_uid).first()
    if not target_user: raise HTTPException(404, "User not found")

    membership = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target_user.id).first()
    if not membership: raise HTTPException(404, "Member not found")
    
    # [!] [CRITICAL] Constraint: Cannot kick equal or higher
    target_level = PROJECT_LEVELS.get(membership.project_role, 0)
    if target_level >= inviter_level:
        raise HTTPException(403, "Insufficient permissions to kick this member")
    
    # Protection: Admin cannot kick Super Admin
    if target_user.global_role == "super_admin" and user.global_role != "super_admin":
        raise HTTPException(403, "Cannot kick a Super Admin")

    db.delete(membership); db.commit()
    return {"status": "kicked", "uid": target_uid}
