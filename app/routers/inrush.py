from fastapi import APIRouter, HTTPException, UploadFile, File
from app.schemas.inrush_schema import InrushRequest
from app.calculations import inrush_calculator
import json

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

@router.post("/calculate")
async def calculate_inrush_json(request: InrushRequest):
    """
    Calcul via JSON brut (Copier-coller dans le Body).
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
async def calculate_inrush_file(file: UploadFile = File(...)):
    """
    Calcul via UPLOAD de fichier (.json).
    Déposez votre 'config.json' ici.
    """
    try:
        content = await file.read()
        data = json.loads(content)
        
        # Validation Pydantic automatique
        # Si le fichier ne correspond pas au format, ça lèvera une erreur
        request = InrushRequest(**data)
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Le fichier n'est pas un JSON valide.")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erreur de lecture ou de format : {e}")

    # Lancement du calcul
    results = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "mode": "file_upload",
        "filename": file.filename,
        "count": len(results),
        "results": results
    }
