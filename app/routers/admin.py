
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..auth import get_current_user, GLOBAL_LEVELS
from pydantic import BaseModel

router = APIRouter()

class RoleUpdate(BaseModel):
    email: str
    role: str

@router.get("/me")
def get_my_profile(user: User = Depends(get_current_user)):
    return {
        "uid": user.firebase_uid,
        "email": user.email,
        "global_role": user.global_role,
        "projects": [p.project_id for p in user.project_memberships]
    }

@router.put("/users/role")
def update_user_role(data: RoleUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [+] [INFO] Gestion des rangs Nitro/User par les Modérateurs.
    [decision:logic] Un Moderator peut mettre Nitro, mais seul Super-Admin peut mettre Admin.
    """
    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    
    # 1. Sécurité : Il faut au moins être Moderator (60)
    if current_level < 60:
        raise HTTPException(status_code=403, detail="Droit de modération requis")
    
    # 2. Un Moderator ne peut pas créer de rôles > Moderator
    target_level = GLOBAL_LEVELS.get(data.role, 0)
    if current_level < 100 and target_level >= current_level:
        raise HTTPException(status_code=403, detail="Vous ne pouvez pas promouvoir à un rang supérieur au vôtre")

    target_user = db.query(User).filter(User.email == data.email).first()
    if not target_user: raise HTTPException(404, "Utilisateur non trouvé")
    
    target_user.global_role = data.role
    db.commit()
    return {"status": "success", "new_role": target_user.global_role}
