
import os
from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth

router = APIRouter()
security = HTTPBearer()

@router.get("/whoami")
def debug_who_am_i(creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = creds.credentials
        decoded = auth.verify_id_token(token)
        uid = decoded['uid']
        
        env_admin_uid = os.getenv("ADMIN_UID")
        
        return {
            "your_uid_from_token": uid,
            "server_admin_uid_env": env_admin_uid,
            "match": uid == env_admin_uid,
            "is_super_admin_logic": (uid == env_admin_uid) if env_admin_uid else False
        }
    except Exception as e:
        return {"error": f"Token invalid: {str(e)}"}
