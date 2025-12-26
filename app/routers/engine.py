from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
import json
import pandas as pd
import io

router = APIRouter(prefix="/engine-pc", tags=["Protection Coordination (PC)"])

# --- HELPERS ---
def is_supported(fname: str) -> bool:
    e = fname.lower()
    return e.endswith('.si2s') or e.endswith('.mdb') or e.endswith('.lf1s')

def get_merged_dataframes_for_calc(token: str):
    files = session_manager.get_files(token)
    if not files: return {}
    merged_dfs = {}
    for name, content in files.items():
        if is_supported(name):
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
    # We ALWAYS need the network files (.si2s, .lf1s) from the session
    dfs_dict = get_merged_dataframes_for_calc(token)
    
    # topology_manager handles if dfs_dict is empty (pure config simulation mode)
    config_updated = topology_manager.resolve_all(config, dfs_dict)
    
    return {
        "status": "success",
        "engine": "Protection Coordination (PC)",
        "project": config_updated.project_name,
        "plans": config_updated.plans
    }

def get_config_from_session(token: str) -> ProjectConfig:
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="Empty session.")
    
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
        raise HTTPException(status_code=422, detail=f"Invalid Session Config JSON: {e}")

# --- 1. VIA SESSION DATA ---
@router.post("/run")
async def run_via_session(token: str = Depends(get_current_token)):
    """
    Uses 'config.json' and network files from RAM Session.
    """
    config = get_config_from_session(token)
    return _execute_calculation_logic(config, token)

# --- 2. VIA JSON BODY ---
@router.post("/run-json")
async def run_via_json(config: ProjectConfig, token: str = Depends(get_current_token)):
    """
    Uses config sent in Body + network files in Session.
    """
    return _execute_calculation_logic(config, token)

# --- 3. VIA FILE UPLOAD ---
@router.post("/run-config")
async def run_via_file_upload(
    file: UploadFile = File(...), 
    token: str = Depends(get_current_token)
):
    """
    Uses uploaded config file + network files in Session.
    """
    content = await file.read()
    try: 
        text_content = content.decode('utf-8')
        valid_config = ProjectConfig(**json.loads(text_content))
    except Exception as e: 
        raise HTTPException(status_code=422, detail=f"Invalid config file: {e}")
        
    return _execute_calculation_logic(valid_config, token)

# --- Data Explorer ---
def _collect_explorer_data(token, table_search, filename_filter):
    files = session_manager.get_files(token)
    if not files: return {}
    results = {}
    for fname, content in files.items():
        if filename_filter and filename_filter.lower() not in fname.lower(): continue
        if not is_supported(fname): continue
        dfs = db_converter.extract_data_from_db(content)
        if dfs:
            file_results = {}
            for table_name, df in dfs.items():
                if table_search and table_search.upper() not in table_name.upper(): continue
                file_results[table_name] = df
            if file_results: results[fname] = file_results
    return results

@router.get("/data-explorer")
def explore_db_data(  # <--- RENAMED from explore_si2s_data
    table_search: Optional[str] = Query(None),
    filename: Optional[str] = Query(None),
    token: str = Depends(get_current_token)
):
    """
    Explore contents of loaded database files (SI2S, LF1S, MDB).
    """
    raw_data = _collect_explorer_data(token, table_search, filename)
    if not raw_data: raise HTTPException(status_code=404, detail="No data found.")
    preview_data = {}
    for fname, tables in raw_data.items():
        preview_data[fname] = {}
        for t_name, df in tables.items():
            preview_data[fname][t_name] = {"rows": len(df), "columns": list(df.columns)}
    return {"data": preview_data}
