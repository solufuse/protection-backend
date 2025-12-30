
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Project, ProjectMember
from ..auth import get_current_user, ProjectAccessChecker
from pydantic import BaseModel
from typing import List

router = APIRouter()

class ProjectCreate(BaseModel):
    id: str
    name: str

class MemberAdd(BaseModel):
    email: str
    role: str # owner, admin, editor, viewer

# 1. LIST PROJECTS (Logic: Admin/Mod sees ALL, User sees HIS)
@router.get("/")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return []
    
    # GLOBAL STAFF
    if user.global_role in ["super_admin", "moderator"]:
        return db.query(Project).all()
        
    # STANDARD USER
    return [m.project for m in user.project_memberships]

# 2. CREATE (User becomes OWNER)
@router.post("/create")
def create_project(project: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: raise HTTPException(401)
    
    if db.query(Project).filter(Project.id == project.id).first():
        raise HTTPException(400, "Project ID exists")
    
    new_proj = Project(id=project.id, name=project.name, storage_path=f"/data/{project.id}")
    db.add(new_proj)
    db.commit()
    
    # Creator = OWNER
    mem = ProjectMember(project_id=new_proj.id, user_id=user.id, project_role="owner")
    db.add(mem)
    db.commit()
    return {"status": "created", "id": new_proj.id}

# 3. DELETE (Only Super Admin OR Project Owner)
@router.delete("/{project_id}")
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Check permissions manually for finer control
    is_global_admin = user.global_role == "super_admin"
    
    member = db.query(ProjectMember).filter(ProjectMember.project_id==project_id, ProjectMember.user_id==user.id).first()
    is_owner = member and member.project_role == "owner"
    
    if not (is_global_admin or is_owner):
        raise HTTPException(403, "Only Super Admin or Project Owner can delete.")
        
    proj = db.query(Project).filter(Project.id == project_id).first()
    if proj:
        db.delete(proj)
        db.commit()
    return {"status": "deleted"}

# 4. ADD TEAM MEMBER (Requires Project Admin or Owner)
@router.post("/{project_id}/members")
def add_member(
    project_id: str, 
    member: MemberAdd, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db),
    _ = Depends(ProjectAccessChecker("admin")) # 'admin' level or 'owner' required
):
    target = db.query(User).filter(User.email == member.email).first()
    if not target: raise HTTPException(404, "User not found")
    
    existing = db.query(ProjectMember).filter(ProjectMember.project_id==project_id, ProjectMember.user_id==target.id).first()
    if existing:
        existing.project_role = member.role
    else:
        new_mem = ProjectMember(project_id=project_id, user_id=target.id, project_role=member.role)
        db.add(new_mem)
    
    db.commit()
    return {"status": "added", "role": member.role}
