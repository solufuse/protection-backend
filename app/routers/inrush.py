from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from app.schemas.inrush_schema import InrushRequest, GlobalInrushResponse
from app.calculations import inrush_calculator
from app.core.security import get_current_token
import json

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

@router.post("/calculate", response_model=GlobalInrushResponse)
async def calculate_inrush_json(
    request: InrushRequest, 
    token: str = Depends(get_current_token)
):
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Liste vide.")
        
    # Le calculator renvoie maintenant un dict avec "summary" et "details"
    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "count": len(data["details"]),
        "summary": data["summary"],
        "details": data["details"]
    }

@router.post("/calculate-file", response_model=GlobalInrushResponse)
async def calculate_inrush_file(
    file: UploadFile = File(...),
    token: str = Depends(get_current_token)
):
    try:
        content = await file.read()
        data_json = json.loads(content)
        request = InrushRequest(**data_json)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erreur : {e}")

    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "count": len(data["details"]),
        "summary": data["summary"],
        "details": data["details"]
    }
