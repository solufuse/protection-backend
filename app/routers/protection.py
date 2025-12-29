
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
# [+] [INFO] Import common specifically for the new endpoint
from app.calculations.ansi_code import AVAILABLE_ANSI_MODULES, common
import json
import pandas as pd
import copy 

# IMPORT DU SOUS-ROUTEUR
from app.routers import ansi_51 as ansi_51_router

router = APIRouter(prefix="/protection", tags=["Protection Coordination (PC)"])

# --- INCLUSION DES SOUS-MODULES ---
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

# --- NEW ENDPOINT: COMMON RUN ---

@router.post("/common/run")
async def run_common_parameters(token: str = Depends(get_current_token)):
    """
    Executes the 'Common' analysis (Electrical Parameters, Inrush, Topology) for all plans.
    Does NOT run specific ANSI codes (50/51/67), only gathers base data.
    URL: POST /protection/common/run
    """
    config = get_config_from_session(token)
    files = session_manager.get_files(token)
    # [context:flow] Build global map of transformers for Inrush calculation
    global_tx_map = common.build_global_transformer_map(files)
    
    results = []
    
    for filename, content in files.items():
        if not common.is_supported_protection(filename): continue
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        # [context:flow] Resolve topology per file to avoid conflicts
        # Use deepcopy to ensure we don't pollute the global config object during iteration
        file_config = copy.deepcopy(config)
        topology_manager.resolve_all(file_config, dfs)
        
        for plan in file_config.plans:
            try:
                # [decision:logic] Extract electrical params (In, Ik, Inrush) using common lib
                data_settings = common.get_electrical_parameters(plan, file_config, dfs, global_tx_map)
                
                # Basic status check
                status = "ok"
                if data_settings.get("kVnom_busfrom") == 0: status = "warning (kV=0)"

                results.append({
                    "plan_id": plan.id,
                    "plan_type": plan.type,
                    "source_file": filename,
                    "status": status,
                    "topology": {
                        "origin": plan.topology_origin,
                        "bus_from": plan.bus_from,
                        "bus_to": plan.bus_to
                    },
                    "common_data": data_settings
                })
            except Exception as e:
                results.append({
                    "plan_id": plan.id,
                    "source_file": filename,
                    "status": "error",
                    "error": str(e)
                })
                
    return {"status": "success", "count": len(results), "results": results}


# --- GLOBAL RUN (L'Orchestrateur) ---

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
