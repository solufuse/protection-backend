
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..auth import get_current_user
from pydantic import BaseModel
from typing import List

router = APIRouter()

class RoleUpdate(BaseModel):
    email: str
    role: str # "super_admin", "moderator", "user"

def require_super_admin(user: User = Depends(get_current_user)):
    if not user or user.global_role != "super_admin":
        raise HTTPException(status_code=403, detail="Droits Super Admin requis")
    return user

@router.get("/users", dependencies=[Depends(require_super_admin)])
def list_all_users(db: Session = Depends(get_db)):
    """Liste tous les utilisateurs inscrits dans le système."""
    return db.query(User).all()

@router.put("/users/role", dependencies=[Depends(require_super_admin)])
def update_user_role(data: RoleUpdate, db: Session = Depends(get_db)):
    """Change le rôle global d'un utilisateur (ex: promouvoir en modérateur)."""
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    user.global_role = data.role
    db.commit()
    return {"status": "updated", "email": user.email, "new_role": user.global_role}
