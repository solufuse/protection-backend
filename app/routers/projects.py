
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Project, ProjectMember
from ..auth import get_current_user, ProjectAccessChecker, GLOBAL_LEVELS, PROJECT_LEVELS
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

# --- CORE ROUTES ---

@router.get("/")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    #
    if not user: return []
    if user.global_role == "super_admin": 
        return db.query(Project).all()
    return [m.project for m in user.project_memberships]

@router.post("/create")
def create_project(project: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    #
    if not user: raise HTTPException(401)
    if db.query(Project).filter(Project.id == project.id).first():
        raise HTTPException(400, "Project ID exists")
    
    storage_path = f"/app/storage/{project.id}"
    if not os.path.exists(storage_path):
        os.makedirs(storage_path, exist_ok=True)
    
    new_proj = Project(id=project.id, name=project.name, storage_path=storage_path)
    db.add(new_proj)
    db.commit()
    
    # Créateur = Owner
    mem = ProjectMember(project_id=new_proj.id, user_id=user.id, project_role="owner")
    db.add(mem)
    db.commit()
    return {"status": "created", "id": new_proj.id}

@router.delete("/{project_id}")
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    #
    is_admin = user.global_role == "super_admin"
    member = db.query(ProjectMember).filter(ProjectMember.project_id==project_id, ProjectMember.user_id==user.id).first()
    is_owner = member and member.project_role == "owner"
    
    if not (is_admin or is_owner): 
        raise HTTPException(403, "Seul le propriétaire peut supprimer le projet")
        
    proj = db.query(Project).filter(Project.id == project_id).first()
    if proj:
        folder_path = f"/app/storage/{project_id}"
        if os.path.exists(folder_path):
            try: shutil.rmtree(folder_path)
            except: pass
        db.delete(proj)
        db.commit()
        return {"status": "deleted", "id": project_id}
    raise HTTPException(404, "Projet non trouvé")

# --- MEMBERSHIP (DISCORD STYLE) ---

@router.post("/{project_id}/members")
def invite_or_update_member(project_id: str, invite: MemberInvite, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # [+] [INFO] Le Moderator peut inviter, mais seul l'Admin peut promouvoir
    checker = ProjectAccessChecker(required_role="moderator")
    checker(project_id, user, db)

    # Vérification du grade de celui qui fait la requête
    current_mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
    is_super_admin = user.global_role == "super_admin"
    
    # [decision:logic] Un Moderator ne peut inviter que des viewers ou editors
    if not is_super_admin and current_mem.project_role == "moderator" and invite.role not in ["viewer", "editor"]:
        raise HTTPException(403, "Un modérateur ne peut pas nommer de nouveaux Admins")

    # Recherche cible
    target_user = None
    if invite.user_id:
        target_user = db.query(User).filter(User.firebase_uid == invite.user_id).first()
    elif invite.email:
        target_user = db.query(User).filter(User.email == invite.email).first()
    
    if not target_user:
        raise HTTPException(404, "Utilisateur introuvable")

    existing = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target_user.id).first()
    
    if existing:
        # [!] [CRITICAL] Seul l'Admin ou Owner peut changer un rôle existant
        if not is_super_admin and PROJECT_LEVELS.get(current_mem.project_role, 0) < PROJECT_LEVELS.get("admin"):
            raise HTTPException(403, "Seul un Admin peut modifier les rôles existants")
        
        existing.project_role = invite.role
        db.commit()
        return {"status": "updated", "uid": target_user.firebase_uid, "role": invite.role}

    new_member = ProjectMember(project_id=project_id, user_id=target_user.id, project_role=invite.role)
    db.add(new_member); db.commit()
    return {"status": "added", "uid": target_user.firebase_uid, "role": invite.role}

@router.get("/{project_id}/members")
def list_project_members(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    #
    checker = ProjectAccessChecker(required_role="viewer")
    checker(project_id, user, db)
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    return [{"uid": m.user.firebase_uid, "email": m.user.email, "role": m.project_role} for m in members]

@router.delete("/{project_id}/members/{target_uid}")
def kick_member(project_id: str, target_uid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Le Moderator peut kick
    checker = ProjectAccessChecker(required_role="moderator")
    checker(project_id, user, db)

    target_user = db.query(User).filter(User.firebase_uid == target_uid).first()
    if not target_user: raise HTTPException(404, "User not found")

    membership = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target_user.id).first()
    if not membership: raise HTTPException(404, "Membre non trouvé")
    
    # [!] [CRITICAL] Protection de l'Owner et hiérarchie du Kick
    if membership.project_role == "owner": raise HTTPException(403, "Impossible d'expulser le propriétaire")
    
    current_mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
    if user.global_role != "super_admin":
        if PROJECT_LEVELS.get(current_mem.project_role) <= PROJECT_LEVELS.get(membership.project_role):
            raise HTTPException(403, "Vous ne pouvez expulser que des membres de rang inférieur")

    db.delete(membership); db.commit()
    return {"status": "kicked", "uid": target_uid}
