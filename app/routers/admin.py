
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..auth import get_current_user, GLOBAL_LEVELS
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

VALID_GLOBAL_ROLES = ["super_admin", "admin", "moderator", "nitro", "user", "guest"]

class RoleUpdate(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None
    role: str

@router.get("/me")
def get_my_profile(user: User = Depends(get_current_user)):
    return {
        "uid": user.firebase_uid,
        "email": user.email,
        "global_role": user.global_role,
        "projects": [p.project_id for p in user.project_memberships]
    }

@router.get("/users")
def list_all_users(
    role: Optional[str] = Query(None, description="Filtrer par rôle"),
    email_search: Optional[str] = Query(None, description="Recherche par email"),
    only_guests: bool = Query(False, description="Afficher uniquement les utilisateurs sans email"),
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Liste des utilisateurs avec filtres avancés.
    [?] [THOUGHT] only_guests=True permet d'isoler les comptes anonymes (email=null).
    """
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    query = db.query(User)
    
    # Filter 1: Rôle spécifique
    if role:
        query = query.filter(User.global_role == role)
    
    # Filter 2: Recherche par email (partielle)
    if email_search:
        query = query.filter(User.email.ilike(f"%{email_search}%"))
    
    # Filter 3: Détection stricte des Guests (Email is NULL)
    if only_guests:
        query = query.filter(User.email == None)
        
    return query.all()

@router.put("/users/role")
def update_user_role(data: RoleUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Validation stricte des rôles
    if data.role not in VALID_GLOBAL_ROLES:
        raise HTTPException(status_code=400, detail="Nom de rôle inconnu")

    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    target_role_level = GLOBAL_LEVELS.get(data.role, 0)

    if current_level < 60: # Minimum Moderator
        raise HTTPException(status_code=403, detail="Droit de modération requis")
    
    if current_level < 100 and target_role_level >= current_level:
        raise HTTPException(status_code=403, detail="Interdit de donner un rang égal ou supérieur au vôtre")

    target_user = None
    if data.user_id:
        target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    elif data.email:
        target_user = db.query(User).filter(User.email == data.email).first()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    target_user.global_role = data.role
    db.commit()
    
    return {"status": "success", "user": target_user.email or "Guest", "new_role": target_user.global_role}
