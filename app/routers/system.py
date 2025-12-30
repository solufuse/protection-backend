
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
import firebase_admin
import os
import subprocess

router = APIRouter(tags=["System"])

# Modèle pour la requête
class AdminRequest(BaseModel):
    uid: str

# [SECURITE] Fonction qui vérifie l'UID via la variable d'environnement
def is_admin_authorized(uid: str) -> bool:
    # On récupère la variable définie dans Dokploy
    admin_uid = os.getenv("ADMIN_UID")
    
    # Si pas de variable définie, sécurité maximale : personne ne passe
    if not admin_uid:
        return False
        
    # On compare (strip retire les espaces éventuels)
    return uid.strip() == admin_uid.strip()

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

@router.post("/system/unlock-storage")
def unlock_storage_permissions(payload: AdminRequest):
    """
    Force les permissions 777 sur /app/storage.
    Requiert que l'UID envoyé corresponde à la variable d'environnement ADMIN_UID.
    """
    
    # 1. Vérification de sécurité
    if not is_admin_authorized(payload.uid):
        # On ne dit pas pourquoi pour ne pas aider les pirates (juste "Forbidden")
        raise HTTPException(status_code=403, detail="⛔ Access Denied.")

    # 2. Exécution
    target_dir = "/app/storage"
    if not os.path.exists(target_dir):
        raise HTTPException(404, "Storage directory not found")

    try:
        result = subprocess.run(["chmod", "-R", "777", target_dir], capture_output=True, text=True)
        
        if result.returncode == 0:
            return {
                "status": "success", 
                "message": "Storage unlocked successfully.", 
                "executed_by": "Authorized Admin"
            }
        else:
            raise Exception(result.stderr)
            
    except Exception as e:
        raise HTTPException(500, f"Failed to unlock storage: {str(e)}")
