from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login")
def login():
    """
    Secure endpoint.
    NO LONGER returns the master token.
    """
    return {
        "message": "Server authentication active.",
        "instruction": "To get a token, login via Frontend (Google Auth) or use your known MASTER_TOKEN (via .env) for API tests."
    }
