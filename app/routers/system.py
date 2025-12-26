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
    Checks if Firebase Admin connection is active.
    Indicates if FIREBASE_CREDENTIALS_JSON variable was loaded.
    """
    try:
        # Attempt to retrieve default app
        app = firebase_admin.get_app()
        return {
            "status": "connected", 
            "message": "Firebase Admin is active ✅",
            "app_name": app.name,
            # Check if in Service Account (JSON) or Auto (Google Cloud) mode
            "credential_type": "Service Account JSON" if os.getenv("FIREBASE_CREDENTIALS_JSON") else "Automatic/None"
        }
    except ValueError:
        return {
            "status": "disconnected", 
            "message": "⚠️ Firebase is not initialized. Check your environment variables."
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}
