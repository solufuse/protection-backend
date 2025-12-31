
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, ProjectMember
from firebase_admin import auth as firebase_auth
import os

# [+] [INFO] Hiérarchie numérique pour comparer les droits facilement
# owner(5) > admin(4) > moderator(3) > editor(2) > viewer(1)
ROLE_LEVELS = {
    "owner": 5,
    "admin": 4,
    "moderator": 3,
    "editor": 2,
    "viewer": 1
}

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Récupère l'utilisateur via le token (Header ou Query Param).
    Vérifie l'existence dans la base de données SQL.
    """
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    else:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="No token provided")

    try:
        decoded_token = firebase_auth.verify_id_token(token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        # Création automatique de l'utilisateur s'il n'existe pas encore en SQL
        user = User(firebase_uid=uid, email=email, global_role="user")
        db.add(user)
        db.commit()
        db.refresh(user)

    return user

class ProjectAccessChecker:
    """
    Le 'Vigile' du projet. 
    Vérifie si l'utilisateur a un rôle suffisant dans le projet spécifié.
    """
    def __init__(self, required_role: str = "viewer"):
        self.required_role = required_role

    def __call__(self, project_id: str, user: User, db: Session):
        # [!] [CRITICAL] Le Super Admin passe toujours
        if user.global_role == "super_admin":
            return True

        # [+] [INFO] Recherche du membre dans le projet
        membership = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id
        ).first()

        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this project"
            )

        # [?] [THOUGHT] Comparaison des niveaux de privilèges
        user_level = ROLE_LEVELS.get(membership.project_role, 0)
        required_level = ROLE_LEVELS.get(self.required_role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required role: {self.required_role}"
            )

        return True
