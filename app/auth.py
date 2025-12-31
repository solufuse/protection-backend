
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, ProjectMember
from firebase_admin import auth as firebase_auth
from datetime import datetime

security = HTTPBearer(auto_error=False)

# AI-REMARK: GLOBAL ROLES (Backend Level)
GLOBAL_LEVELS = {
    "super_admin": 100,
    "admin": 80,
    "moderator": 60,
    "nitro": 40,
    "user": 20,
    "guest": 0
}

# AI-REMARK: PROJECT ROLES (Local Level)
PROJECT_LEVELS = {
    "owner": 50,
    "admin": 40,
    "moderator": 30,
    "editor": 20,
    "viewer": 10
}

async def get_current_user(request: Request, creds: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    # [+] [INFO] Hybrid Authentication (Header Bearer or ?token=)
    token = creds.credentials if creds else request.query_params.get("token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        decoded = firebase_auth.verify_id_token(token)
        uid, email = decoded['uid'], decoded.get('email')
    except:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        # [?] [THOUGHT] Force creation time in Python to avoid DB Null issues
        user = User(
            firebase_uid=uid, 
            email=email, 
            global_role="user",
            created_at=datetime.utcnow(), # Explicit timestamp
            is_active=True
        )
        db.add(user); db.commit(); db.refresh(user)

    # [!] [CRITICAL] Ban Check
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account suspended. Contact support.")

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
            raise HTTPException(status_code=403, detail="Access denied to this project")

        if PROJECT_LEVELS.get(membership.project_role, 0) < PROJECT_LEVELS.get(self.required_role, 0):
            raise HTTPException(status_code=403, detail=f"Action requires role {self.required_role}")
        return True
