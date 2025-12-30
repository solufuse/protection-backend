
import os
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, ProjectMember
import firebase_admin
from firebase_admin import auth, credentials

# Initialize Firebase
if not firebase_admin._apps:
    try:
        # In Production, ensure this file is injected via secrets/volumes
        if os.path.exists("firebase_credentials.json"):
            cred = credentials.Certificate("firebase_credentials.json")
            firebase_admin.initialize_app(cred)
        else:
            print("[CRITICAL WARNING] No firebase_credentials.json found. Auth checks will likely fail.")
    except Exception as e:
        print(f"[ERROR] Firebase Init: {e}")

def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)):
    if not authorization:
        # Anonymous/Guest access is not allowed on protected routes
        return None
        
    try:
        token = authorization.replace("Bearer ", "")
        
        # [SECURITY] STRICT VERIFICATION
        # Verify ID token using Firebase. Will throw error if invalid/expired.
        decoded_token = auth.verify_id_token(token)
        
        uid = decoded_token['uid']
        email = decoded_token.get('email')

        # --- ADMIN UID CHECK (Environment Variable) ---
        env_admin_uid = os.getenv("ADMIN_UID")
        
        user = db.query(User).filter(User.firebase_uid == uid).first()
        
        # Case: Super Admin Login
        if env_admin_uid and uid == env_admin_uid:
            if not user:
                user = User(firebase_uid=uid, email=email, global_role="super_admin")
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"[AUTH] Super Admin created via ENV: {email}")
            elif user.global_role != "super_admin":
                user.global_role = "super_admin"
                db.commit()
                db.refresh(user)
                print(f"[AUTH] User promoted to Super Admin via ENV: {email}")
            return user

        # Case: Standard User Login
        if not user:
            # Auto-register new users as standard 'user'
            user = User(firebase_uid=uid, email=email, global_role="user")
            db.add(user)
            db.commit()
            db.refresh(user)
            
        return user

    except Exception as e:
        # [SECURITY] Log error but strictly return 401 to client
        print(f"Auth Verification Failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# --- PERMISSIONS CHECKERS ---

class ProjectAccessChecker:
    def __init__(self, required_role: str = "viewer"):
        self.levels = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}
        self.req_level = self.levels.get(required_role, 1)

    def __call__(self, project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        if not user: 
            raise HTTPException(status_code=401, detail="Not authenticated")

        # 1. SUPER ADMIN BYPASS
        if user.global_role == "super_admin": 
            return True
        
        # 2. MODERATOR (Read-Only Global)
        if user.global_role == "moderator":
            if self.req_level == 1: return True # Read allowed
            # Write forbidden unless explicitly member (logic handled below)

        # 3. MEMBERSHIP CHECK
        member = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id
        ).first()

        if not member:
             if user.global_role == "moderator": 
                 raise HTTPException(403, "Moderator: Read-Only Access (Write Forbidden)") 
             raise HTTPException(403, "Access Denied to this Project")
        
        if self.levels.get(member.project_role, 0) < self.req_level:
            raise HTTPException(403, "Insufficient Project Permissions")
        
        return True
