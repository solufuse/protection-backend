
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
from app.calculations.ansi_code import common as common_lib
import json, copy
from typing import Optional

router = APIRouter(prefix="/common", tags=["Common Analysis"])

def get_config(target, is_proj) -> ProjectConfig:
    files = session_manager.get_files(target, is_proj)
    if not files: raise HTTPException(400, "Empty")
    tgt = files.get("config.json")
    if not tgt:
        for n, c in files.items():
            if n.lower().endswith(".json"): tgt = c; break
    if not tgt: raise HTTPException(404, "No config")
    try: return ProjectConfig(**json.loads(tgt))
    except: raise HTTPException(422, "Invalid Config")

@router.post("/run")
async def run(include_data: bool = False, token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target, is_proj = (project_id, True) if project_id else (token, False)
    if is_proj and not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied")

    config = get_config(target, is_proj)
    files = session_manager.get_files(target, is_proj)
    global_tx = common_lib.build_global_transformer_map(files)
    results = []
    
    for fname, content in files.items():
        if not common_lib.is_supported_protection(fname): continue
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        fconfig = copy.deepcopy(config)
        topology_manager.resolve_all(fconfig, dfs)
        
        for plan in fconfig.plans:
            try:
                data = common_lib.get_electrical_parameters(plan, fconfig, dfs, global_tx)
                if not include_data:
                    data.pop("raw_data_from", None)
                    data.pop("raw_data_to", None)
                results.append({"plan_id": plan.id, "file": fname, "common_data": data})
            except Exception as e:
                results.append({"plan_id": plan.id, "file": fname, "error": str(e)})
    return {"status": "success", "results": results}
