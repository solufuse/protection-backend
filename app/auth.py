
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, ProjectMember
from firebase_admin import auth as firebase_auth

security = HTTPBearer(auto_error=False)

GLOBAL_LEVELS = {
    "super_admin": 100,
    "admin": 80,
    "moderator": 60,
    "nitro": 40,
    "user": 20,
    "guest": 0
}

PROJECT_LEVELS = {
    "owner": 50,
    "admin": 40,
    "moderator": 30,
    "editor": 20,
    "viewer": 10
}

async def get_current_user(request: Request, creds: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = creds.credentials if creds else request.query_params.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentification requise")

    try:
        decoded = firebase_auth.verify_id_token(token)
        uid, email = decoded['uid'], decoded.get('email')
    except:
        raise HTTPException(status_code=401, detail="Session expirée ou invalide")

    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        user = User(firebase_uid=uid, email=email, global_role="user")
        db.add(user); db.commit(); db.refresh(user)

    # [!] [CRITICAL] Vérification du bannissement
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Votre compte a été suspendu. Contactez le support.")

    return user

class ProjectAccessChecker:
    def __init__(self, required_role: str = "viewer"):
        self.required_role = required_role

    def __call__(self, project_id: str, user: User, db: Session):
        if user.global_role == "super_admin": return True

        membership = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        ).first()

        if not membership:
            raise HTTPException(status_code=403, detail="Accès au projet refusé")

        if PROJECT_LEVELS.get(membership.project_role, 0) < PROJECT_LEVELS.get(self.required_role, 0):
            raise HTTPException(status_code=403, detail=f"Action requérant le rang {self.required_role}")
        return True
