
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import auth
import os
import subprocess

router = APIRouter(tags=["System"])

# Sécurité : Schéma Bearer Token pour Swagger/API
security = HTTPBearer()

# --- DEPENDENCIES ---

def get_current_user_uid(creds: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Vérifie le token JWT Firebase et retourne l'UID de l'utilisateur.
    Si le token est invalide, renvoie une erreur 401.
    """
    token = creds.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

def require_admin_access(uid: str = Depends(get_current_user_uid)):
    """
    Dépendance qui vérifie si l'UID extrait du token correspond à l'ADMIN_UID du serveur.
    """
    admin_uid = os.getenv("ADMIN_UID")
    
    if not admin_uid:
        # Sécurité par défaut : Si pas de variable configurée, personne ne passe.
        raise HTTPException(status_code=403, detail="Server configuration error: ADMIN_UID missing.")
        
    if uid != admin_uid:
        raise HTTPException(status_code=403, detail="⛔ Access Denied: You are not the administrator.")
        
    return uid

# --- ROUTES ---

@router.get("/")
def read_root(): 
    return {"status": "Solufuse API v2 Ready", "repo": "protection-backend"}

@router.get("/health")
def health(): 
    return {"status": "ok"}

@router.get("/firebase-health")
def firebase_check():
    try:
        app = firebase_admin.get_app()
        return {
            "status": "connected", 
            "message": "Firebase Admin est actif ✅",
            "app_name": app.name
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# [!] SECURED ROUTE (JWT)
@router.post("/system/unlock-storage")
def unlock_storage_permissions(uid: str = Depends(require_admin_access)):
    """
    Force les permissions 777 sur /app/storage.
    Sécurité : Le token JWT dans le Header doit appartenir à l'ADMIN_UID.
    """
    
    target_dir = "/app/storage"
    if not os.path.exists(target_dir):
        raise HTTPException(404, "Storage directory not found")

    try:
        # Execution de la commande
        result = subprocess.run(["chmod", "-R", "777", target_dir], capture_output=True, text=True)
        
        if result.returncode == 0:
            return {
                "status": "success", 
                "message": "Storage unlocked successfully. FileBrowser has full access.", 
                "admin": uid
            }
        else:
            raise Exception(result.stderr)
            
    except Exception as e:
        raise HTTPException(500, f"Failed to unlock storage: {str(e)}")
