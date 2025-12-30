
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, ProjectMember
import firebase_admin
from firebase_admin import auth, credentials

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("firebase_credentials.json")
        firebase_admin.initialize_app(cred)
    except:
        pass # Dev mode without creds

def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)):
    if not authorization:
        return None
    try:
        token = authorization.replace("Bearer ", "")
        # Simulation en dev si pas de firebase:
        # return db.query(User).first()
        
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']
        
        user = db.query(User).filter(User.firebase_uid == uid).first()
        if not user:
            # Auto-create as standard USER
            user = User(firebase_uid=uid, email=decoded_token.get('email'), global_role="user")
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    except Exception as e:
        print(f"Auth Error: {e}")
        raise HTTPException(status_code=401, detail="Invalid Credentials")

# --- CHECKER 1: ACCÈS PROJET (Hierarchique) ---
class ProjectAccessChecker:
    def __init__(self, required_role: str = "viewer"):
        # Hierarchy: owner > admin > editor > viewer
        self.levels = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}
        self.req_level = self.levels.get(required_role, 1)

    def __call__(self, project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        if not user: raise HTTPException(401)

        # 1. GLOBAL OVERRIDE (Staff Solufuse)
        if user.global_role == "super_admin": return True
        if user.global_role == "moderator": 
            # Moderator can READ everything (level 1), but cannot WRITE (level > 1) unless specified
            if self.req_level == 1: return True 
            # If moderator tries to edit/delete/add_member, we check if he is ALSO a member of the project
            # Otherwise, forbid.

        # 2. PROJECT MEMBERSHIP CHECK
        member = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id
        ).first()

        if not member: 
            # If mod tries to write but isn't member -> Forbidden
            if user.global_role == "moderator": raise HTTPException(403, "Moderators strictly have Read-Only access.")
            raise HTTPException(403, "Access Denied")
        
        if self.levels.get(member.project_role, 0) < self.req_level:
            raise HTTPException(403, "Insufficient Project Privileges")
        
        return True
