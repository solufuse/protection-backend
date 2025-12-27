from fastapi import APIRouter
try:
    from app.core.memory import SESSIONS
except ImportError:
    from core.memory import SESSIONS

router = APIRouter(prefix="/session", tags=["session"])

@router.get("/details")
async def get_session_ram(user_id: str):
    """
    DEV ENDPOINT: Reads directly from Server RAM.
    Bypasses Firestore completely.
    Resets on server restart.
    """
    user_files = SESSIONS.get(user_id, [])
    return {
        "user_id": user_id,
        "source": "RAM (Volatile)",
        "count": len(user_files),
        "files": user_files
    }
