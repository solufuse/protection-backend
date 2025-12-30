
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from app.core.security import get_current_token
from app.services import session_manager
from app.calculations import loadflow_calculator
from app.schemas.loadflow_schema import LoadflowSettings
import json
from typing import Optional

router = APIRouter(prefix="/loadflow", tags=["Loadflow Analysis"])

def get_config(target, is_proj) -> LoadflowSettings:
    files = session_manager.get_files(target, is_proj)
    if not files: raise HTTPException(400, "Empty")
    tgt = files.get("config.json")
    if not tgt:
        for n, c in files.items():
            if n.lower().endswith(".json"): tgt = c; break
    if not tgt: raise HTTPException(404, "No config")
    try: return LoadflowSettings(**json.loads(tgt)["loadflow_settings"])
    except: raise HTTPException(422, "Invalid Config")

@router.post("/run")
async def run(format: str = "json", token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target, is_proj = (project_id, True) if project_id else (token, False)
    if is_proj and not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied")

    config = get_config(target, is_proj)
    files = session_manager.get_files(target, is_proj)
    data = loadflow_calculator.analyze_loadflow(files, config, False)
    return data

@router.post("/run-and-save")
async def run_save(basename: str = "lf_res", token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target, is_proj = (project_id, True) if project_id else (token, False)
    if is_proj and not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied")

    config = get_config(target, is_proj)
    files = session_manager.get_files(target, is_proj)
    data = loadflow_calculator.analyze_loadflow(files, config, False)
    
    jbytes = json.dumps(jsonable_encoder(data), indent=2, default=str).encode('utf-8')
    session_manager.add_file(target, f"{basename}.json", jbytes, is_proj)
    
    return {"status": "saved", "files": [f"{basename}.json"]}
