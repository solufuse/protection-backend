
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Project, ProjectMember
from ..auth import get_current_user, ProjectAccessChecker
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

# --- SCHEMAS ---
class ProjectCreate(BaseModel):
    id: str
    name: str

class MemberInvite(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None # Support direct Firebase UID
    role: str = "viewer"

# --- CORE ROUTES ---

@router.get("/")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return []
    # [+] [INFO] Super Admin voit tout, l'user normal voit ses memberships
    if user.global_role == "super_admin": 
        return db.query(Project).all()
    return [m.project for m in user.project_memberships]

@router.post("/create")
def create_project(project: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: raise HTTPException(401)
    
    if db.query(Project).filter(Project.id == project.id).first():
        raise HTTPException(400, "Project ID exists")
    
    storage_path = f"/app/storage/{project.id}"
    if not os.path.exists(storage_path):
        os.makedirs(storage_path, exist_ok=True)
    
    new_proj = Project(id=project.id, name=project.name, storage_path=storage_path)
    db.add(new_proj)
    db.commit()
    
    # [!] [CRITICAL] Le créateur devient 'owner' (Droit de suppression)
    mem = ProjectMember(project_id=new_proj.id, user_id=user.id, project_role="owner")
    db.add(mem)
    db.commit()
    
    return {"status": "created", "id": new_proj.id, "path": storage_path}

@router.delete("/{project_id}")
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    is_admin = user.global_role == "super_admin"
    member = db.query(ProjectMember).filter(ProjectMember.project_id==project_id, ProjectMember.user_id==user.id).first()
    is_owner = member and member.project_role == "owner"
    
    if not (is_admin or is_owner): 
        raise HTTPException(403, "Permission Denied: Only Owners or Super Admins can delete.")
        
    proj = db.query(Project).filter(Project.id == project_id).first()
    if proj:
        # [+] [INFO] Nettoyage physique du dossier sur le disque
        folder_path = f"/app/storage/{project_id}"
        if os.path.exists(folder_path):
            try: shutil.rmtree(folder_path)
            except Exception as e: print(f"Error deleting folder: {e}")

        db.delete(proj)
        db.commit()
        return {"status": "deleted", "id": project_id}
    raise HTTPException(404, "Project not found")

# --- DISCORD-LIKE MEMBERS MANAGEMENT ---

@router.post("/{project_id}/members")
def invite_member(project_id: str, invite: MemberInvite, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Invite un utilisateur via Email ou Firebase UID."""
    # [?] [THOUGHT] On exige d'être Admin du projet pour inviter
    checker = ProjectAccessChecker(required_role="admin")
    checker(project_id, user, db)

    target_user = None
    if invite.user_id:
        target_user = db.query(User).filter(User.firebase_uid == invite.user_id).first()
    elif invite.email:
        target_user = db.query(User).filter(User.email == invite.email).first()
    
    if not target_user:
        raise HTTPException(404, "User not found in database. They must log in once first.")

    existing = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target_user.id).first()
    if existing:
        existing.project_role = invite.role
        db.commit()
        return {"status": "updated", "uid": target_user.firebase_uid, "role": invite.role}

    new_member = ProjectMember(project_id=project_id, user_id=target_user.id, project_role=invite.role)
    db.add(new_member)
    db.commit()
    return {"status": "added", "uid": target_user.firebase_uid, "email": target_user.email, "role": invite.role}

@router.get("/{project_id}/members")
def list_project_members(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Liste les membres en renvoyant le Firebase UID."""
    checker = ProjectAccessChecker(required_role="viewer")
    checker(project_id, user, db)

    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    # [FIX] On renvoie explicitement le firebase_uid
    return [
        {
            "uid": m.user.firebase_uid,
            "email": m.user.email,
            "role": m.project_role
        } for m in members
    ]

@router.delete("/{project_id}/members/{target_uid}")
def kick_member(project_id: str, target_uid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Expulse un membre via son Firebase UID."""
    checker = ProjectAccessChecker(required_role="admin")
    checker(project_id, user, db)

    # Recherche de l'utilisateur par son Firebase UID
    target_user = db.query(User).filter(User.firebase_uid == target_uid).first()
    if not target_user: raise HTTPException(404, "User not found")

    membership = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target_user.id).first()
    if not membership: raise HTTPException(404, "Member not found in project")
    if membership.project_role == "owner": raise HTTPException(403, "Cannot kick the project owner")

    db.delete(membership)
    db.commit()
    return {"status": "kicked", "uid": target_uid}
