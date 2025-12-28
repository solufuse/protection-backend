
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional, List, Dict, Any
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
from app.calculations.ansi_code import AVAILABLE_ANSI_MODULES, ansi_51
import json
import pandas as pd
import io

router = APIRouter(prefix="/protection", tags=["Protection Coordination (PC)"])

# --- HELPERS ---

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

# --- GENERIC RUN ROUTES ---

@router.post("/run")
async def run_via_session(token: str = Depends(get_current_token)):
    config = get_config_from_session(token)
    dfs_dict = get_merged_dataframes_for_calc(token)
    config_updated = topology_manager.resolve_all(config, dfs_dict)
    global_results = []
    for plan in config_updated.plans:
        plan_result = {"plan_id": plan.id, "ansi_results": {}}
        for func_code in plan.active_functions:
            if func_code in AVAILABLE_ANSI_MODULES:
                module = AVAILABLE_ANSI_MODULES[func_code]
                try:
                    res = module.calculate(plan, config.settings, dfs_dict)
                    plan_result["ansi_results"][func_code] = res
                except Exception as e:
                    plan_result["ansi_results"][func_code] = {"error": str(e)}
        global_results.append(plan_result)
    return {"status": "success", "results": global_results}

# --- ANSI 51 SPECIFIC ROUTES ---

@router.post("/ansi_51/run")
async def run_ansi_51_only(
    include_data: bool = Query(False, description="Set to True to see raw data (si2s dump and raw ETAP rows)"),
    token: str = Depends(get_current_token)
):
    """
    Exécute ANSI 51.
    Si include_data=False (défaut), masque data_si2s et les raw_data du data_settings.
    """
    config = get_config_from_session(token)
    full_results = ansi_51.run_batch_logic(config, token)
    
    if include_data:
        # On renvoie tout brut de fonderie
        final_results = full_results
        msg = "Full data included (DB rows & Raw ETAP values)."
    else:
        # On nettoie
        final_results = []
        for r in full_results:
            r_copy = r.copy()
            
            # 1. Masquer le dump SQL global
            if "data_si2s" in r_copy:
                r_copy["data_si2s"] = "Hidden (use include_data=true)"
            
            # 2. Masquer les dumps ETAP dans data_settings
            if "data_settings" in r_copy:
                ds = r_copy["data_settings"].copy()
                ds.pop("raw_data_from", None) # On retire raw_data_from
                ds.pop("raw_data_to", None)   # On retire raw_data_to
                r_copy["data_settings"] = ds
                
            final_results.append(r_copy)
        msg = "Raw data hidden for readability. Use include_data=true to debug."

    return {
        "status": "success", 
        "total_scenarios": len(final_results), 
        "info": msg,
        "results": final_results
    }

@router.get("/ansi_51/export")
async def export_ansi_51(
    format: str = Query("xlsx", pattern="^(xlsx|json)$"),
    token: str = Depends(get_current_token)
):
    config = get_config_from_session(token)
    results = ansi_51.run_batch_logic(config, token)
    
    if format == "json":
        return JSONResponse(
            content={"results": results}, 
            headers={"Content-Disposition": "attachment; filename=ansi_51_full.json"}
        )
    
    excel_bytes = ansi_51.generate_excel(results)
    
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ansi_51_full.xlsx"}
    )
