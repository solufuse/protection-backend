from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.core.security import get_current_token
from app.services import session_manager
from app.calculations import loadflow_calculator
from app.schemas.loadflow_schema import LoadflowSettings, LoadflowResponse
import json

router = APIRouter(prefix="/loadflow", tags=["Loadflow Analysis"])

def get_lf_config_from_session(token: str) -> LoadflowSettings:
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="Session vide.")
    
    target_content = None
    if "config.json" in files: target_content = files["config.json"]
    else:
        for name, content in files.items():
            if name.lower().endswith(".json"):
                target_content = content
                break
    
    if target_content is None: raise HTTPException(status_code=404, detail="Aucun config.json trouvé.")

    try:
        if isinstance(target_content, bytes): text_content = target_content.decode('utf-8')
        else: text_content = target_content
        data = json.loads(text_content)
        if "loadflow_settings" not in data:
            raise HTTPException(status_code=400, detail="La section 'loadflow_settings' est manquante")
        return LoadflowSettings(**data["loadflow_settings"])
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Config Loadflow invalide : {e}")

# --- ROUTES ---

@router.post("/run", response_model=LoadflowResponse)
async def run_loadflow_session(token: str = Depends(get_current_token)):
    """
    Lance l'analyse et retourne TOUS les résultats.
    """
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    return loadflow_calculator.analyze_loadflow(files, config, only_winners=False)

@router.post("/run-win", response_model=LoadflowResponse)
async def run_loadflow_winners_only(token: str = Depends(get_current_token)):
    """
    Lance l'analyse et retourne UNIQUEMENT le(s) meilleur(s) résultat(s).
    """
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    # On active le mode only_winners=True
    return loadflow_calculator.analyze_loadflow(files, config, only_winners=True)

@router.post("/run-json", response_model=LoadflowResponse)
async def run_loadflow_json(config: LoadflowSettings, token: str = Depends(get_current_token)):
    files = session_manager.get_files(token)
    return loadflow_calculator.analyze_loadflow(files, config, only_winners=False)
