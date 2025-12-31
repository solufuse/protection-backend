
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Project, ProjectMember
from ..auth import get_current_user, ProjectAccessChecker
from pydantic import BaseModel
import os

router = APIRouter()

class ProjectCreate(BaseModel):
    id: str
    name: str

@router.get("/")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return []
    if user.global_role == "super_admin": return db.query(Project).all()
    return [m.project for m in user.project_memberships]

@router.post("/create")
def create_project(project: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: raise HTTPException(401)
    if db.query(Project).filter(Project.id == project.id).first():
        raise HTTPException(400, "Project ID exists")
    
    new_proj = Project(id=project.id, name=project.name, storage_path=f"/app/storage/{project.id}")
    db.add(new_proj)
    db.commit()
    
    mem = ProjectMember(project_id=new_proj.id, user_id=user.id, project_role="owner")
    db.add(mem)
    db.commit()
    return {"status": "created", "id": new_proj.id}

@router.delete("/{project_id}")
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Check permissions (Owner or Super Admin)
    is_admin = user.global_role == "super_admin"
    member = db.query(ProjectMember).filter(ProjectMember.project_id==project_id, ProjectMember.user_id==user.id).first()
    is_owner = member and member.project_role == "owner"
    
    if not (is_admin or is_owner): raise HTTPException(403, "Permission Denied")
        
    proj = db.query(Project).filter(Project.id == project_id).first()
    if proj:
        db.delete(proj)
        db.commit()
    return {"status": "deleted"}
