
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, ProjectMember
import firebase_admin
from firebase_admin import auth, credentials

if not firebase_admin._apps:
    try:
        if os.path.exists("firebase_credentials.json"):
            cred = credentials.Certificate("firebase_credentials.json")
            firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"[ERROR] Firebase Init: {e}")

security = HTTPBearer()

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = creds.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        
        env_admin_uid = os.getenv("ADMIN_UID")
        user = db.query(User).filter(User.firebase_uid == uid).first()
        
        # Super Admin Auto-Promote
        if env_admin_uid and uid == env_admin_uid:
            if not user:
                user = User(firebase_uid=uid, email=email, global_role="super_admin")
                db.add(user)
                db.commit()
            elif user.global_role != "super_admin":
                user.global_role = "super_admin"
                db.commit()
            return user

        if not user:
            user = User(firebase_uid=uid, email=email, global_role="user")
            db.add(user)
            db.commit()
            
        return user
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid Authentication")

class ProjectAccessChecker:
    def __init__(self, required_role: str = "viewer"):
        self.levels = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}
        self.req_level = self.levels.get(required_role, 1)

    def __call__(self, project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        if not user: raise HTTPException(401)
        if user.global_role == "super_admin": return True
        
        member = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
        if not member: raise HTTPException(403, "Access Denied")
        
        if self.levels.get(member.project_role, 0) < self.req_level:
            raise HTTPException(403, "Insufficient Permissions")
        return True
