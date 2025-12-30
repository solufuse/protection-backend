
from fastapi import APIRouter, HTTPException
import firebase_admin
import os
import subprocess

router = APIRouter(tags=["System"])

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
            "app_name": app.name,
            "credential_type": "Service Account JSON" if os.getenv("FIREBASE_CREDENTIALS_JSON") else "Automatic/None"
        }
    except ValueError:
        return {"status": "disconnected", "message": "⚠️ Firebase n'est pas initialisé."}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# [!] NEW: Route magique pour donner les droits à FileBrowser
@router.post("/system/unlock-storage")
def unlock_storage_permissions():
    """
    Force les permissions 777 sur tout le dossier /app/storage.
    Permet à FileBrowser de supprimer/modifier les fichiers créés par l'API.
    """
    target_dir = "/app/storage"
    
    if not os.path.exists(target_dir):
        raise HTTPException(404, "Storage directory not found")

    try:
        # Exécute la commande Linux 'chmod -R 777' en tant que root (car l'API est root)
        result = subprocess.run(["chmod", "-R", "777", target_dir], capture_output=True, text=True)
        
        if result.returncode == 0:
            return {"status": "success", "message": "Storage unlocked (chmod 777 applied recursively). FileBrowser has full access now."}
        else:
            raise Exception(result.stderr)
            
    except Exception as e:
        raise HTTPException(500, f"Failed to unlock storage: {str(e)}")
