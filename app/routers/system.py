from fastapi import APIRouter
import firebase_admin
import os

router = APIRouter(tags=["System"])

@router.get("/")
def read_root(): 
    return {"status": "Solufuse API v2 Ready", "repo": "protection-backend"}

@router.get("/health")
def health(): 
    return {"status": "ok"}

@router.get("/firebase-health")
def firebase_check():
    """
    Vérifie si la connexion Firebase Admin est active.
    Permet de savoir si la variable FIREBASE_CREDENTIALS_JSON a bien été chargée.
    """
    try:
        # On essaie de récupérer l'application par défaut
        app = firebase_admin.get_app()
        return {
            "status": "connected", 
            "message": "Firebase Admin est actif ✅",
            "app_name": app.name,
            # On vérifie si on est en mode Service Account (JSON) ou Auto (Google Cloud)
            "credential_type": "Service Account JSON" if os.getenv("FIREBASE_CREDENTIALS_JSON") else "Automatic/None"
        }
    except ValueError:
        return {
            "status": "disconnected", 
            "message": "⚠️ Firebase n'est pas initialisé. Vérifiez vos variables d'environnement."
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}
