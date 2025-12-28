
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional, Dict, Any
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
# Import the new ANSI package
from app.calculations.ansi_code import AVAILABLE_ANSI_MODULES
import json
import pandas as pd
import io

router = APIRouter(prefix="/protection", tags=["Protection Coordination (PC)"])

# --- HELPERS ---
def is_supported(fname: str) -> bool:
    e = fname.lower()
    return e.endswith('.si2s') or e.endswith('.mdb') or e.endswith('.lf1s')

def get_merged_dataframes_for_calc(token: str):
    """
    Reads all relevant files from session and merges them into a dictionary of DataFrames.
    """
    files = session_manager.get_files(token)
    if not files: return {}
    merged_dfs = {}
    for name, content in files.items():
        if is_supported(name):
            # Extract data using existing db_converter
            dfs = db_converter.extract_data_from_db(content)
            if dfs:
                for t, df in dfs.items():
                    if t not in merged_dfs: merged_dfs[t] = []
                    merged_dfs[t].append(df)
    final = {}
    for k, v in merged_dfs.items():
        try: final[k] = pd.concat(v, ignore_index=True)
        except: final[k] = v[0]
    return final

def _execute_calculation_logic(config: ProjectConfig, token: str):
    """
    Orchestrator function:
    1. Loads data (SI2S).
    2. Resolves topology.
    3. Iterates over each Protection Plan.
    4. Calls the relevant ANSI modules (51, 67, etc.) dynamically.
    """
    dfs_dict = get_merged_dataframes_for_calc(token)
    
    # 1. Topology Resolution
    config_updated = topology_manager.resolve_all(config, dfs_dict)
    
    # 2. Calculation Loop per Plan
    global_results = []
    
    for plan in config_updated.plans:
        plan_result = {
            "plan_id": plan.id,
            "ansi_results": {}
        }
        
        # Iterate over active functions requested by the user (e.g., ["51", "67"])
        for func_code in plan.active_functions:
            if func_code in AVAILABLE_ANSI_MODULES:
                module = AVAILABLE_ANSI_MODULES[func_code]
                
                # Execute the specific ANSI calculation
                try:
                    res = module.calculate(plan, config.settings, dfs_dict)
                    plan_result["ansi_results"][func_code] = res
                except Exception as e:
                    plan_result["ansi_results"][func_code] = {"error": str(e)}
            else:
                plan_result["ansi_results"][func_code] = {"status": "not_implemented"}
                
        global_results.append(plan_result)
    
    return {
        "status": "success",
        "engine": "Protection Coordination (PC) - Modular ANSI",
        "project": config_updated.project_name,
        "config_summary": config_updated.plans,
        "calculation_results": global_results
    }

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
        if isinstance(target_content, bytes):
            text_content = target_content.decode('utf-8')
        else:
            text_content = target_content  
        data = json.loads(text_content)
        return ProjectConfig(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid Config JSON: {e}")

# --- ROUTES ---

@router.post("/run")
async def run_via_session(token: str = Depends(get_current_token)):
    config = get_config_from_session(token)
    return _execute_calculation_logic(config, token)

@router.post("/run-json")
async def run_via_json(config: ProjectConfig, token: str = Depends(get_current_token)):
    return _execute_calculation_logic(config, token)

@router.post("/run-config")
async def run_via_file_upload(file: UploadFile = File(...), token: str = Depends(get_current_token)):
    content = await file.read()
    try: 
        text_content = content.decode('utf-8')
        valid_config = ProjectConfig(**json.loads(text_content))
    except Exception as e: 
        raise HTTPException(status_code=422, detail=f"Invalid config file: {e}")
        
    return _execute_calculation_logic(valid_config, token)

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
        if not is_supported(fname): continue
        
        dfs = db_converter.extract_data_from_db(content)
        if dfs:
            file_results = {}
            for table_name, df in dfs.items():
                if table_search and table_search.upper() not in table_name.upper(): continue
                file_results[table_name] = {"rows": len(df), "columns": list(df.columns)}
            if file_results: results[fname] = file_results
            
    return {"data": results}
