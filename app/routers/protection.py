
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
from app.calculations.ansi_code import AVAILABLE_ANSI_MODULES
import json
import pandas as pd

# IMPORT DU SOUS-ROUTEUR
from app.routers import ansi_51 as ansi_51_router

router = APIRouter(prefix="/protection", tags=["Protection Coordination (PC)"])

# --- INCLUSION DES SOUS-MODULES ---
# Cela génère automatiquement les routes :
# /protection/ansi_51/run
# /protection/ansi_51/export
router.include_router(ansi_51_router.router)

# --- HELPERS (Utilisés pour le RUN GLOBAL) ---

def is_supported_protection(fname: str) -> bool:
    e = fname.lower()
    return e.endswith('.si2s') or e.endswith('.mdb')

def get_merged_dataframes_for_calc(token: str):
    files = session_manager.get_files(token)
    if not files: return {}
    merged_dfs = {}
    for name, content in files.items():
        if is_supported_protection(name):
            dfs = db_converter.extract_data_from_db(content)
            if dfs:
                for t, df in dfs.items():
                    if t not in merged_dfs: merged_dfs[t] = []
                    df['SourceFilename'] = name 
                    merged_dfs[t].append(df)
    final = {}
    for k, v in merged_dfs.items():
        try: final[k] = pd.concat(v, ignore_index=True)
        except: final[k] = v[0]
    return final

def get_config_from_session(token: str) -> ProjectConfig:
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="Session is empty.")
    
    target_content = None
    if "config.json" in files:
        target_content = files["config.json"]
    else:
        for name, content in files.items():
            if name.lower().endswith(".json"):
                target_content = content
                break
    if target_content is None:
        raise HTTPException(status_code=404, detail="No 'config.json' found in session.")
    try:
        if isinstance(target_content, bytes): text_content = target_content.decode('utf-8')
        else: text_content = target_content  
        data = json.loads(text_content)
        return ProjectConfig(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid Config JSON: {e}")

# --- GLOBAL RUN (L'Orchestrateur) ---
# Cette route restera toujours là pour lancer TOUT d'un coup

@router.post("/run")
async def run_global_protection(token: str = Depends(get_current_token)):
    """
    L'Orchestrateur : Lance tous les modules (50, 51, 67, 87T...) en une seule fois.
    """
    config = get_config_from_session(token)
    dfs_dict = get_merged_dataframes_for_calc(token)
    config_updated = topology_manager.resolve_all(config, dfs_dict)
    
    global_results = []
    
    # Pour chaque équipement...
    for plan in config_updated.plans:
        plan_result = {"plan_id": plan.id, "ansi_results": {}}
        
        # Pour chaque fonction activée (50, 51, etc.)
        for func_code in plan.active_functions:
            if func_code in AVAILABLE_ANSI_MODULES:
                module = AVAILABLE_ANSI_MODULES[func_code]
                try:
                    # Chaque module se débrouille avec son calcul
                    res = module.calculate(plan, config.settings, dfs_dict)
                    plan_result["ansi_results"][func_code] = res
                except Exception as e:
                    plan_result["ansi_results"][func_code] = {"error": str(e)}
        global_results.append(plan_result)
        
    return {"status": "success", "results": global_results}

# --- DATA EXPLORER ---
@router.get("/data-explorer")
def explore_data(
    table_search: Optional[str] = Query(None),
    filename: Optional[str] = Query(None),
    token: str = Depends(get_current_token)
):
    files = session_manager.get_files(token)
    if not files: return {"data": {}}
    results = {}
    for fname, content in files.items():
        if filename and filename.lower() not in fname.lower(): continue
        if not is_supported_protection(fname): continue
        dfs = db_converter.extract_data_from_db(content)
        if dfs:
            file_results = {}
            for table_name, df in dfs.items():
                if table_search and table_search.upper() not in table_name.upper(): continue
                file_results[table_name] = {"rows": len(df), "columns": list(df.columns)}
            if file_results: results[fname] = file_results
    return {"data": results}
