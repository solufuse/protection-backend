
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..auth import get_current_user, GLOBAL_LEVELS
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

# [?] [THOUGHT] Liste immuable des rôles autorisés pour éviter les injections/erreurs
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
    role: Optional[str] = Query(None, description="Filtrer par rôle (ex: nitro)"),
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Liste et recherche filtrée des utilisateurs.
    [decision:logic] Réservé aux rangs Admin (80) et plus.
    """
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    query = db.query(User)
    
    # [+] [INFO] Application du filtre de recherche par rôle
    if role:
        if role not in VALID_GLOBAL_ROLES:
            raise HTTPException(status_code=400, detail=f"Rôle '{role}' invalide. Utilisez: {VALID_GLOBAL_ROLES}")
        query = query.filter(User.global_role == role)
        
    return query.all()

@router.put("/users/role")
def update_user_role(data: RoleUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [!] [CRITICAL] Mise à jour STRICTE des rôles.
    """
    # 1. Validation du rôle cible
    if data.role not in VALID_GLOBAL_ROLES:
        raise HTTPException(status_code=400, detail="Nom de rôle inconnu")

    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    target_role_level = GLOBAL_LEVELS.get(data.role, 0)

    # 2. Sécurité hiérarchique (Moderator mini)
    if current_level < 60:
        raise HTTPException(status_code=403, detail="Droit de modération requis")
    
    # 3. Interdiction de promouvoir au dessus de soi
    if current_level < 100 and target_role_level >= current_level:
        raise HTTPException(status_code=403, detail="Vous ne pouvez pas donner un rang égal ou supérieur au vôtre")

    # 4. Recherche de l'utilisateur
    target_user = None
    if data.user_id:
        target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    elif data.email:
        target_user = db.query(User).filter(User.email == data.email).first()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    # [+] [INFO] Application stricte
    target_user.global_role = data.role
    db.commit()
    
    return {"status": "success", "user": target_user.email, "new_role": target_user.global_role}
