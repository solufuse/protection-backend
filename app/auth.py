
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, ProjectMember
import firebase_admin
from firebase_admin import auth, credentials

# Init Firebase
if not firebase_admin._apps:
    try:
        if os.path.exists("firebase_credentials.json"):
            cred = credentials.Certificate("firebase_credentials.json")
            firebase_admin.initialize_app(cred)
        else:
            print("[WARNING] No firebase_credentials.json found.")
    except Exception as e:
        print(f"[ERROR] Firebase Init: {e}")

# SECURITY SCHEME
# Cela permet à Swagger d'afficher le bon formulaire de login
security = HTTPBearer()

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    # HTTPBearer extrait automatiquement le token et vérifie le préfixe "Bearer"
    token = creds.credentials 
    
    try:
        # --- VERIFICATION TOKEN ---
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')

        # --- ADMIN UID CHECK ---
        env_admin_uid = os.getenv("ADMIN_UID")
        
        user = db.query(User).filter(User.firebase_uid == uid).first()
        
        # Super Admin Check
        if env_admin_uid and uid == env_admin_uid:
            if not user:
                user = User(firebase_uid=uid, email=email, global_role="super_admin")
                db.add(user)
                db.commit()
                db.refresh(user)
            elif user.global_role != "super_admin":
                user.global_role = "super_admin"
                db.commit()
                db.refresh(user)
            return user

        # Standard User Check
        if not user:
            user = User(firebase_uid=uid, email=email, global_role="user")
            db.add(user)
            db.commit()
            db.refresh(user)
            
        return user

    except Exception as e:
        print(f"Auth Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Credentials or Expired Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

# --- PERMISSIONS CHECKERS (Inchangé) ---
class ProjectAccessChecker:
    def __init__(self, required_role: str = "viewer"):
        self.levels = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}
        self.req_level = self.levels.get(required_role, 1)

    def __call__(self, project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        if not user: raise HTTPException(401)
        if user.global_role == "super_admin": return True
        
        if user.global_role == "moderator":
            if self.req_level == 1: return True
            
        member = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id
        ).first()

        if not member:
             if user.global_role == "moderator": raise HTTPException(403, "Read Only")
             raise HTTPException(403, "Access Denied")
        
        if self.levels.get(member.project_role, 0) < self.req_level:
            raise HTTPException(403, "Insufficient Permissions")
        
        return True
