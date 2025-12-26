from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.security import get_current_token
from app.calculations import text_parser

router = APIRouter(prefix="/extraction", tags=["AI Extraction"])

class TextRequest(BaseModel):
    text: str

@router.post("/parse")
async def parse_text(req: TextRequest, token: str = Depends(get_current_token)):
    """
    Parses raw text to extract electrical data (Sn, Un, In).
    Example: "Transfo 63MVA 225kV" -> {power_kva: 63000, voltage_kv: 225}
    """
    result = text_parser.parse_technical_text(req.text)
    return {
        "status": "success",
        "data": result
    }
