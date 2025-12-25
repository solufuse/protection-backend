from fastapi import APIRouter, Depends
from app.core.security import get_current_token

router = APIRouter(prefix="/extraction", tags=["AI Extraction"])

@router.post("/parse")
async def parse_text(text: str, token: str = Depends(get_current_token)):
    return {"status": "success", "message": "Extraction module ready", "received": text}
