from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from app.schemas.inrush_schema import InrushRequest, GlobalInrushResponse
from app.calculations import inrush_calculator
from app.core.security import get_current_token
from app.services import session_manager
import json

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

# --- HELPER (Avec Logique Robust V2) ---
def get_config_from_session(token: str) -> InrushRequest:
    files = session_manager.get_files(token)
    if not files:
        raise HTTPException(status_code=400, detail="Session vide. Veuillez uploader un config.json.")
    
    target_content = None
    if "config.json" in files:
        target_content = files["config.json"]
    else:
        for name, content in files.items():
            if name.lower().endswith(".json"):
                target_content = content
                break
    
    if target_content is None:
        raise HTTPException(status_code=404, detail="Aucun 'config.json' trouvé en session.")

    try:
        # Décodage Bytes -> String
        if isinstance(target_content, bytes):
            text_content = target_content.decode('utf-8')
        else:
            text_content = target_content
        
        # Pydantic V2 s'occupe du reste grâce au schéma permissif qu'on a mis avant
        data = json.loads(text_content)
        return InrushRequest(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"JSON Session invalide : {e}")

# --- 1. VIA SESSION DATA ---
@router.post("/calculate", response_model=GlobalInrushResponse)
async def calculate_via_session(token: str = Depends(get_current_token)):
    """
    Calcul en utilisant le 'config.json' stocké en Session RAM.
    """
    request = get_config_from_session(token)
    
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Liste vide dans le config.json.")

    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "source": "session_data",
        "count": len(data["details"]), # <--- C'ÉTAIT L'OUBLI !
        "summary": data["summary"],
        "details": data["details"]
    }

# --- 2. VIA JSON BODY ---
@router.post("/calculate-json", response_model=GlobalInrushResponse)
async def calculate_via_json(
    request: InrushRequest, 
    token: str = Depends(get_current_token)
):
    """
    Calcul en envoyant la configuration dans le corps (Body) de la requête.
    """
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Liste vide.")
        
    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "source": "json_body",
        "count": len(data["details"]), # <--- AJOUTÉ ICI AUSSI
        "summary": data["summary"],
        "details": data["details"]
    }

# --- 3. VIA FILE UPLOAD (Config Download) ---
@router.post("/calculate-config", response_model=GlobalInrushResponse)
async def calculate_via_file_upload(
    file: UploadFile = File(...),
    token: str = Depends(get_current_token)
):
    """
    Calcul en uploadant un fichier 'config.json' spécifique pour ce calcul.
    """
    try:
        content = await file.read()
        text_content = content.decode('utf-8')
        data_json = json.loads(text_content)
        request = InrushRequest(**data_json)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Fichier invalide : {e}")

    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "source": "file_upload",
        "count": len(data["details"]), # <--- AJOUTÉ ICI AUSSI
        "summary": data["summary"],
        "details": data["details"]
    }
