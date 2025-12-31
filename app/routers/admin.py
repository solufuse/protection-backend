
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..auth import get_current_user, GLOBAL_LEVELS
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime, timedelta

router = APIRouter()

ValidRole = Literal["super_admin", "admin", "moderator", "nitro", "user", "guest"]

class RoleUpdate(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None
    role: ValidRole

class BanRequest(BaseModel):
    user_id: str
    is_active: bool  # False = Banni, True = Actif
    reason: Optional[str] = "Violation des conditions d'utilisation"

@router.get("/me", summary="Mon Profil")
def get_my_profile(user: User = Depends(get_current_user)):
    return {
        "uid": user.firebase_uid,
        "email": user.email,
        "global_role": user.global_role,
        "is_active": user.is_active,
        "projects_count": len(user.project_memberships)
    }

@router.get("/users", summary="Lister les utilisateurs (Paginé)")
def list_all_users(
    # [?] [THOUGHT] Pagination pour éviter de charger 10 000 users d'un coup
    skip: int = 0,
    limit: int = 50,
    role: Optional[ValidRole] = Query(None),
    email_search: Optional[str] = Query(None),
    only_guests: bool = Query(False),
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Liste paginée des utilisateurs.
    Utilisez 'skip' (décalage) et 'limit' (nombre max) pour naviguer.
    """
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
        raise HTTPException(status_code=403, detail="Accès Admin requis")
    
    query = db.query(User)
    
    if only_guests:
        query = query.filter(User.email == None)
    if role:
        query = query.filter(User.global_role == role)
    if email_search:
        query = query.filter(User.email.ilike(f"%{email_search}%"))
        
    # [+] [INFO] Application de la pagination
    total_count = query.count()
    users = query.offset(skip).limit(limit).all()
    
    return {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "data": users
    }

@router.put("/users/role", summary="Changer le rôle")
def update_user_role(data: RoleUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    
    if current_level < 60:
        raise HTTPException(status_code=403, detail="Accès Modérateur requis")
        
    target_user = None
    if data.user_id:
        target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    elif data.email:
        target_user = db.query(User).filter(User.email == data.email).first()
        
    if not target_user: raise HTTPException(404, "Utilisateur introuvable")

    # Protection hiérarchique
    target_role_level = GLOBAL_LEVELS.get(data.role, 0)
    if current_level < 100 and target_role_level >= current_level:
         raise HTTPException(status_code=403, detail="Promotion interdite à ce niveau")

    target_user.global_role = data.role
    db.commit()
    return {"status": "updated", "user": target_user.email, "role": target_user.global_role}

# --- NOUVELLES FONCTIONNALITÉS ---

@router.put("/users/ban", summary="Bannir/Débannir un utilisateur")
def ban_user(data: BanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [!] [CRITICAL] Active ou Désactive l'accès d'un utilisateur au site.
    Ne supprime pas les données, empêche juste la connexion.
    """
    # Seul Admin (80) et plus peut bannir
    if GLOBAL_LEVELS.get(user.global_role, 0) < 80:
        raise HTTPException(status_code=403, detail="Droit de bannissement requis (Admin)")

    target_user = db.query(User).filter(User.firebase_uid == data.user_id).first()
    if not target_user:
        raise HTTPException(404, "Utilisateur introuvable")
        
    # Protection: On ne peut pas bannir un supérieur
    target_level = GLOBAL_LEVELS.get(target_user.global_role, 0)
    current_level = GLOBAL_LEVELS.get(user.global_role, 0)
    if target_level >= current_level and user.global_role != "super_admin":
        raise HTTPException(403, "Impossible de bannir un supérieur hiérarchique")

    target_user.is_active = data.is_active
    db.commit()
    
    status_msg = "Activé" if data.is_active else "Banni"
    return {"status": "success", "user_uid": target_user.firebase_uid, "account_state": status_msg}

@router.delete("/guests/cleanup", summary="Nettoyage automatique des Guests")
def cleanup_guests(
    hours_old: int = 24, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [decision:logic] Supprime définitivement les utilisateurs sans email (Guests)
    créés il y a plus de X heures. Permet de garder la DB propre.
    """
    if user.global_role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin requis pour le nettoyage")

    cutoff_time = datetime.utcnow() - timedelta(hours=hours_old)
    
    # Recherche des guests expirés
    expired_guests = db.query(User).filter(
        User.email == None,
        User.created_at < cutoff_time
    ).all()
    
    count = len(expired_guests)
    
    # Suppression
    for guest in expired_guests:
        db.delete(guest)
    
    db.commit()
    
    return {
        "status": "cleaned", 
        "deleted_count": count, 
        "criteria": f"Guests older than {hours_old} hours"
    }
