from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from app.schemas.inrush_schema import InrushRequest, GlobalInrushResponse
from app.calculations import inrush_calculator
from app.core.security import get_current_token
from app.services import session_manager
import json

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

# --- HELPER ---
def get_config_from_session(token: str) -> InrushRequest:
    files = session_manager.get_files(token)
    if not files:
        raise HTTPException(status_code=400, detail="Aucun fichier en session.")
    
    # On cherche un fichier qui s'appelle "config.json"
    # Ou n'importe quel .json si config.json n'existe pas
    target_content = None
    
    if "config.json" in files:
        target_content = files["config.json"]
    else:
        # Fallback : on prend le premier .json trouvé
        for name, content in files.items():
            if name.lower().endswith(".json"):
                target_content = content
                break
    
    if target_content is None:
        raise HTTPException(status_code=404, detail="Aucun 'config.json' trouvé en session RAM.")

    try:
        data = json.loads(target_content)
        return InrushRequest(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Le JSON en session est invalide pour l'Inrush : {e}")

# --- ROUTES ---

@router.post("/calculate-json", response_model=GlobalInrushResponse)
async def calculate_inrush_manual(
    request: InrushRequest, 
    token: str = Depends(get_current_token)
):
    """
    (Anciennement /calculate)
    Calcul en envoyant le JSON directement dans le Body.
    """
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Liste vide.")
        
    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "count": len(data["details"]),
        "summary": data["summary"],
        "details": data["details"]
    }

@router.post("/calculate", response_model=GlobalInrushResponse)
async def calculate_inrush_auto(token: str = Depends(get_current_token)):
    """
    (NOUVEAU)
    Calcul automatique en utilisant le 'config.json' déjà présent en session.
    Plus besoin d'envoyer de données ici.
    """
    # 1. On va chercher le config.json en RAM
    request = get_config_from_session(token)
    
    # 2. On lance le calcul
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Liste vide dans le config.json.")

    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "source": "session_memory",
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
