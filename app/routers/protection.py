from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, Depends
from typing import List, Optional
import json
from app.managers import session_manager
# from app.services import engine # Sera activé quand l'engine utilisera la nouvelle structure

router = APIRouter(prefix="/protection", tags=["Protection"])

# Simulation de dépendance Token
async def get_token_header(x_token: str = Header(default="demo-token")):
    return x_token

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...), 
    config: str = Form(...),
    token: str = Depends(get_token_header)
):
    # 1. Lecture fichiers en RAM
    files_data = {}
    for f in files:
        files_data[f.filename] = await f.read()
    
    user_config = json.loads(config)
    
    # 2. Sauvegarde Session Isolée
    session_manager.save_session(token, files_data, user_config)
    
    return {"status": "saved", "token": token, "file_count": len(files_data)}

@router.post("/run")
async def run_calculation(token: str = Depends(get_token_header), mode: str = "light"):
    # 3. Récupération Session
    session = session_manager.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session expirée ou inexistante. Veuillez réuploader.")
    
    # Ici on appellera l'Engine (à mettre à jour pour lire depuis la session)
    # result = engine.compute(session['files'], session['config'], mode)
    
    return {"status": "success", "mode": mode, "msg": "Calcul simulé sur architecture V2.1"}

@router.post("/clear")
async def clear_session(token: str = Depends(get_token_header)):
    session_manager.clear_session(token)
    return {"status": "cleared"}
