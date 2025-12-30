
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
from app.calculations.ansi_code import AVAILABLE_ANSI_MODULES
import json, pandas as pd

from app.routers import ansi_51 as ansi_51_router
from app.routers import common as common_router

router = APIRouter(prefix="/protection", tags=["Protection Coordination (PC)"])
router.include_router(ansi_51_router.router)
router.include_router(common_router.router)

def get_merged_data(target_id, is_proj):
    files = session_manager.get_files(target_id, is_proj)
    if not files: return {}
    merged = {}
    for name, content in files.items():
        if name.lower().endswith(('.si2s', '.mdb')):
            dfs = db_converter.extract_data_from_db(content)
            if dfs:
                for t, df in dfs.items():
                    if t not in merged: merged[t] = []
                    df['SourceFilename'] = name 
                    merged[t].append(df)
    final = {}
    for k, v in merged.items():
        try: final[k] = pd.concat(v, ignore_index=True)
        except: final[k] = v[0]
    return final

def get_config(target_id, is_proj) -> ProjectConfig:
    files = session_manager.get_files(target_id, is_proj)
    if not files: raise HTTPException(400, "Empty")
    tgt = files.get("config.json")
    if not tgt:
        for n, c in files.items():
            if n.lower().endswith(".json"): tgt = c; break
    if not tgt: raise HTTPException(404, "No config")
    try: return ProjectConfig(**json.loads(tgt))
    except Exception as e: raise HTTPException(422, str(e))

@router.post("/run")
async def run_global(token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target, is_proj = (project_id, True) if project_id else (token, False)
    if is_proj and not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied")

    config = get_config(target, is_proj)
    dfs = get_merged_data(target, is_proj)
    config_updated = topology_manager.resolve_all(config, dfs)
    
    results = []
    for plan in config_updated.plans:
        res = {"plan_id": plan.id, "ansi_results": {}}
        for func in plan.active_functions:
            if func in AVAILABLE_ANSI_MODULES:
                try: res["ansi_results"][func] = AVAILABLE_ANSI_MODULES[func].calculate(plan, config.settings, dfs)
                except Exception as e: res["ansi_results"][func] = {"error": str(e)}
        results.append(res)
    return {"status": "success", "results": results}

@router.get("/data-explorer")
def explore(table: str = None, filename: str = None, token: str = Depends(get_current_token), project_id: str = Query(None)):
    target, is_proj = (project_id, True) if project_id else (token, False)
    if is_proj and not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied")
    
    files = session_manager.get_files(target, is_proj)
    results = {}
    for fname, content in files.items():
        if filename and filename.lower() not in fname.lower(): continue
        if not fname.lower().endswith(('.si2s','.mdb')): continue
        dfs = db_converter.extract_data_from_db(content)
        if dfs:
            fres = {}
            for t, df in dfs.items():
                if table and table.upper() not in t.upper(): continue
                fres[t] = {"rows": len(df), "columns": list(df.columns)}
            if fres: results[fname] = fres
    return {"data": results}
