from fastapi import APIRouter, HTTPException
from app.schemas.inrush_schema import InrushRequest
from app.calculations import inrush_calculator

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

@router.post("/calculate")
async def calculate_inrush(request: InrushRequest):
    """
    Calcule les courants d'enclenchement (Inrush).
    Retourne la courbe de décroissance (10ms -> 1000ms).
    """
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Liste vide.")
        
    results = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "count": len(results),
        "results": results
    }
