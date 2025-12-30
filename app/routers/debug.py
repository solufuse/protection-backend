
import os
from fastapi import APIRouter, Header, Depends
from firebase_admin import auth

router = APIRouter()

@router.get("/whoami")
def debug_who_am_i(authorization: str = Header(None)):
    if not authorization:
        return {"error": "No Authorization header found"}
    
    try:
        token = authorization.replace("Bearer ", "")
        # On décode sans vérifier la signature pour le debug (si jamais les clés foirent)
        # Mais on utilise auth.verify_id_token en prod normalement
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
