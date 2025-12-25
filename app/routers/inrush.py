from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from app.schemas.inrush_schema import InrushRequest, GlobalInrushResponse
from app.calculations import inrush_calculator
from app.core.security import get_current_token
from app.services import session_manager
import json

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

# --- HELPER ROBUSTE ---
def get_config_from_session(token: str) -> InrushRequest:
    files = session_manager.get_files(token)
    if not files:
        raise HTTPException(status_code=400, detail="Session vide. Veuillez uploader un config.json via /session/upload.")
    
    target_content = None
    filename_found = ""
    
    # Priorité explicite à "config.json"
    if "config.json" in files:
        target_content = files["config.json"]
        filename_found = "config.json"
    else:
        # Sinon on cherche n'importe quel .json
        for name, content in files.items():
            if name.lower().endswith(".json"):
                target_content = content
                filename_found = name
                break
    
    if target_content is None:
        raise HTTPException(status_code=404, detail="Aucun fichier .json trouvé en session RAM.")

    try:
        # CORRECTION ICI : On décode les bytes en string avant de charger le JSON
        if isinstance(target_content, bytes):
            text_content = target_content.decode('utf-8')
        else:
            text_content = target_content

        data = json.loads(text_content)
        return InrushRequest(**data)
    except json.JSONDecodeError:
         raise HTTPException(status_code=422, detail=f"Le fichier {filename_found} n'est pas un JSON valide.")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erreur structure JSON ({filename_found}): {e}")

# --- ROUTES ---

@router.post("/calculate-json", response_model=GlobalInrushResponse)
async def calculate_inrush_manual(
    request: InrushRequest, 
    token: str = Depends(get_current_token)
):
    """
    ✅ MÉTHODE MANUELLE
    Copiez-collez votre JSON directement dans le "Request Body".
    """
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Liste vide.")
        
    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "source": "manual_json_body",
        "count": len(data["details"]),
        "summary": data["summary"],
        "details": data["details"]
    }

@router.post("/calculate", response_model=GlobalInrushResponse)
async def calculate_inrush_auto(token: str = Depends(get_current_token)):
    """
    ✅ MÉTHODE AUTO (SESSION)
    Utilise le fichier 'config.json' stocké en mémoire via /session/upload.
    Laissez le corps de la requête vide.
    """
    request = get_config_from_session(token)
    
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Liste vide dans le fichier config.json.")

    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "source": "session_memory",
        "count": len(data["details"]),
        "summary": data["summary"],
        "details": data["details"]
    }
