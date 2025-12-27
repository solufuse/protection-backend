from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login")
def login():
    """
    Endpoint sécurisé.
    Ne renvoie PLUS le token maître.
    """
    return {
        "message": "Authentification serveur active.",
        "instruction": "Pour obtenir un token, connectez-vous via le Frontend (Google Auth) ou utilisez votre MASTER_TOKEN connu (via .env) pour les tests API."
    }
