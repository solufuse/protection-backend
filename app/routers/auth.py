import os
from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login")
def login():
    """
    ROUTE DE DÉPANNAGE (DEV ONLY).
    Affiche le Master Token configuré dans l'environnement.
    """
    token = os.getenv("MASTER_TOKEN", "❌ Aucun MASTER_TOKEN configuré dans l'environnement (.env)")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "message": "Copiez ce token pour tester l'API."
    }
