from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from app.schemas.inrush_schema import InrushRequest
from app.calculations import inrush_calculator
from app.core.security import get_current_token
import json

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

@router.post("/calculate")
async def calculate_inrush_json(
    request: InrushRequest, 
    token: str = Depends(get_current_token) # <--- LE VERROU EST ICI
):
    """
    Calcul via JSON brut. Nécessite un Token valide.
    """
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Liste vide.")
        
    results = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "mode": "json_body",
        "count": len(results),
        "results": results
    }

@router.post("/calculate-file")
async def calculate_inrush_file(
    file: UploadFile = File(...),
    token: str = Depends(get_current_token) # <--- ICI AUSSI
):
    """
    Calcul via UPLOAD. Nécessite un Token valide.
    """
    try:
        content = await file.read()
        data = json.loads(content)
        request = InrushRequest(**data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="JSON invalide.")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erreur : {e}")

    results = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "mode": "file_upload",
        "filename": file.filename,
        "count": len(results),
        "results": results
    }
