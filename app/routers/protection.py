
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse, JSONResponse, Response
from typing import Optional, List, Dict, Any
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
# Import dynamique des modules ANSI
from app.calculations.ansi_code import AVAILABLE_ANSI_MODULES, ansi_51
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

# --- GENERIC CALCULATION LOGIC ---

def _execute_calculation_logic(config: ProjectConfig, token: str):
    """
    Generic Orchestrator for all ANSI codes.
    """
    dfs_dict = get_merged_dataframes_for_calc(token)
    
    # 1. Topology Resolution
    config_updated = topology_manager.resolve_all(config, dfs_dict)
    
    # 2. Calculation Loop
    global_results = []
    
    for plan in config_updated.plans:
        plan_result = {
            "plan_id": plan.id,
            "ansi_results": {}
        }
        for func_code in plan.active_functions:
            if func_code in AVAILABLE_ANSI_MODULES:
                module = AVAILABLE_ANSI_MODULES[func_code]
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
        "engine": "Protection Coordination (PC)",
        "project": config_updated.project_name,
        "calculation_results": global_results
    }

# --- ANSI 51 SPECIFIC LOGIC ---

def _run_ansi_51_logic(config: ProjectConfig, token: str) -> List[dict]:
    """
    Runs specifically ANSI 51 logic for all plans, regardless of active_functions config.
    Used for the specific ANSI 51 endpoints.
    """
    dfs_dict = get_merged_dataframes_for_calc(token)
    config_updated = topology_manager.resolve_all(config, dfs_dict)
    
    results = []
    
    for plan in config_updated.plans:
        # We try to run ANSI 51 for every plan defined in the project
        try:
            # Call the specific module directly
            res = ansi_51.calculate(plan, config.settings, dfs_dict)
            
            # Enrich result with Plan Meta-data for easier reading in list/export
            res["plan_id"] = plan.id
            res["plan_type"] = plan.type
            results.append(res)
        except Exception as e:
            results.append({
                "plan_id": plan.id, 
                "ansi_code": "51", 
                "status": "error", 
                "comments": [str(e)]
            })
            
    return results

def _generate_ansi51_excel(results: List[dict]) -> bytes:
    """
    Generates a flattened Excel file for ANSI 51 results.
    """
    flat_rows = []
    
    for res in results:
        # Basic Info
        row = {
            "Plan ID": res.get("plan_id"),
            "Type": res.get("plan_type"),
            "Status": res.get("status"),
            "Bus From": res.get("topology_used", {}).get("bus_from"),
            "Bus To": res.get("topology_used", {}).get("bus_to"),
            "Source Origin": res.get("topology_used", {}).get("source_origin"),
        }
        
        # Thresholds
        thresholds = res.get("calculated_thresholds", {})
        row["Pickup (A)"] = thresholds.get("pickup_amps")
        row["Time Dial"] = thresholds.get("time_dial")
        
        # Comments (joined)
        row["Comments"] = " | ".join(res.get("comments", []))
        
        # Data Info (Debug)
        data_si2s = res.get("data_si2s", {})
        if isinstance(data_si2s.get("bus_to_data"), dict):
             # Example: extract a specific value if needed, e.g., Ik3ph
             row["Isc (kA)"] = data_si2s.get("bus_to_data").get("Ik3ph")
        
        flat_rows.append(row)
        
    df = pd.DataFrame(flat_rows)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="ANSI 51 Results", index=False)
        # Auto-adjust column width (basic)
        worksheet = writer.sheets["ANSI 51 Results"]
        for col in worksheet.columns:
            try:
                max_length = 0
                column = col[0].column_letter # Get the column name
                for cell in col:
                    try: 
                        if len(str(cell.value)) > max_length: max_length = len(str(cell.value))
                    except: pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column].width = adjusted_width
            except: pass
            
    return output.getvalue()

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

# --- NEW ANSI 51 ROUTES ---

@router.post("/ansi_51/run")
async def run_ansi_51_only(token: str = Depends(get_current_token)):
    """
    Runs ONLY the ANSI 51 calculation logic for the current session config.
    Useful for debugging or specific studies.
    """
    config = get_config_from_session(token)
    results = _run_ansi_51_logic(config, token)
    return {
        "status": "success",
        "count": len(results),
        "results": results
    }

@router.get("/ansi_51/export")
async def export_ansi_51(
    format: str = Query("xlsx", pattern="^(xlsx|json)$"),
    token: str = Depends(get_current_token)
):
    """
    Exports ANSI 51 results to Excel or JSON.
    """
    config = get_config_from_session(token)
    results = _run_ansi_51_logic(config, token)
    
    if format == "json":
        return JSONResponse(
            content={"results": results}, 
            headers={"Content-Disposition": "attachment; filename=ansi_51_results.json"}
        )
    
    # XLSX Export
    excel_bytes = _generate_ansi51_excel(results)
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ansi_51_results.xlsx"}
    )
