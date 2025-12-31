
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..auth import get_current_user
from pydantic import BaseModel
from typing import List

router = APIRouter()

# AI-REMARK: DEFINITION DES ROLES GLOBAUX (GLOBAL_ROLE)
# ------------------------------------------------------------------------------
# 1. super_admin : Accès total au backend, stockage, DB et gestion des users.
# 2. moderator   : Support technique. Peut auditer les projets mais pas supprimer.
# 3. nitro       : [FUTURE FEATURE] Utilisateur Premium avec quotas étendus.
# 4. user        : Utilisateur standard (limité à ses propres projets).
# ------------------------------------------------------------------------------

class RoleUpdate(BaseModel):
    email: str
    role: str # super_admin, moderator, nitro, user

def require_super_admin(user: User = Depends(get_current_user)):
    """ [!] [CRITICAL] Verrou de sécurité pour les fonctions critiques. """
    if not user or user.global_role != "super_admin":
        raise HTTPException(status_code=403, detail="Droits Super Admin requis")
    return user

@router.get("/me")
def get_my_profile(user: User = Depends(get_current_user)):
    """
    [+] [INFO] Retourne le profil et le rôle de l'utilisateur connecté.
    [?] [THOUGHT] Permet au Frontend d'adapter l'affichage (ex: bouton Admin).
    """
    return {
        "uid": user.firebase_uid,
        "email": user.email,
        "global_role": user.global_role, # super_admin, moderator, nitro, user
        "projects": [p.project_id for p in user.project_memberships]
    }

@router.get("/users", dependencies=[Depends(require_super_admin)])
def list_all_users(db: Session = Depends(get_db)):
    """ [+] [INFO] Liste exhaustive des utilisateurs pour l'administration. """
    return db.query(User).all()

@router.put("/users/role", dependencies=[Depends(require_super_admin)])
def update_user_role(data: RoleUpdate, db: Session = Depends(get_db)):
    """
    [+] [INFO] Promotion ou rétrogradation d'un utilisateur.
    [ decision:logic] Seul le Super Admin peut utiliser cette route.
    """
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    user.global_role = data.role
    db.commit()
    return {"status": "updated", "email": user.email, "new_role": user.global_role}
