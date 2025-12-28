
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse, JSONResponse
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
    Reads ALL supported files from session and merges them.
    If multiple files have the same table (e.g. SCIECLGSum1), rows are concatenated.
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
                    # Optionnel: on pourrait ajouter une colonne 'SourceFile' ici pour tracer l'origine
                    # df['SourceFile'] = name 
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
    dfs_dict = get_merged_dataframes_for_calc(token)
    config_updated = topology_manager.resolve_all(config, dfs_dict)
    
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

# --- ANSI 51 SPECIFIC LOGIC & EXPORT ---

def _run_ansi_51_logic(config: ProjectConfig, token: str) -> List[dict]:
    dfs_dict = get_merged_dataframes_for_calc(token)
    config_updated = topology_manager.resolve_all(config, dfs_dict)
    
    results = []
    for plan in config_updated.plans:
        try:
            res = ansi_51.calculate(plan, config.settings, dfs_dict)
            # Enrichissement pour l'export liste
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
    Génère un Excel complet en aplatissant toutes les données trouvées dans data_si2s.
    """
    flat_rows = []
    
    for res in results:
        # 1. Infos de base
        row = {
            "Plan ID": res.get("plan_id"),
            "Type": res.get("plan_type"),
            "Status": res.get("status"),
            "Bus From": res.get("topology_used", {}).get("bus_from"),
            "Bus To": res.get("topology_used", {}).get("bus_to"),
            "Source Origin": res.get("topology_used", {}).get("source_origin"),
        }

        # 2. Seuils calculés
        thresh = res.get("calculated_thresholds", {})
        row["Pickup (A)"] = thresh.get("pickup_amps")
        row["Time Dial"] = thresh.get("time_dial")
        
        # 3. Commentaires
        row["Comments"] = " | ".join(res.get("comments", []))

        # 4. DATA DUMP (Dynamique)
        # On va chercher tout ce qui est dans data_si2s et on l'ajoute en colonnes
        data_section = res.get("data_si2s", {})
        
        # Bus Amont
        from_data = data_section.get("bus_from_data")
        if isinstance(from_data, dict):
            for k, v in from_data.items():
                # On préfixe pour éviter les conflits de noms
                row[f"FROM_{k}"] = v
        elif isinstance(from_data, str):
             row["FROM_Info"] = from_data
        
        # Bus Aval
        to_data = data_section.get("bus_to_data")
        if isinstance(to_data, dict):
            for k, v in to_data.items():
                row[f"TO_{k}"] = v
        elif isinstance(to_data, str):
             row["TO_Info"] = to_data

        flat_rows.append(row)

    df = pd.DataFrame(flat_rows)
    
    # Ordonnancement intelligent des colonnes (Base d'abord, puis FROM, puis TO)
    base_cols = ["Plan ID", "Type", "Status", "Bus From", "Bus To", "Pickup (A)", "Time Dial"]
    all_cols = list(df.columns)
    
    # On sépare les colonnes dynamiques
    from_cols = sorted([c for c in all_cols if c.startswith("FROM_")])
    to_cols = sorted([c for c in all_cols if c.startswith("TO_")])
    other_cols = [c for c in all_cols if c not in base_cols and c not in from_cols and c not in to_cols]
    
    # Reconstitution ordonnée
    final_order = [c for c in base_cols if c in all_cols] + from_cols + to_cols + other_cols
    df = df[final_order]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="ANSI 51 Full Data", index=False)
        
        # Ajustement largeur colonnes
        worksheet = writer.sheets["ANSI 51 Full Data"]
        for col in worksheet.columns:
            try:
                col_letter = col[0].column_letter
                worksheet.column_dimensions[col_letter].width = 15
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

# --- ANSI 51 ROUTES ---

@router.post("/ansi_51/run")
async def run_ansi_51_only(token: str = Depends(get_current_token)):
    config = get_config_from_session(token)
    results = _run_ansi_51_logic(config, token)
    return {"status": "success", "count": len(results), "results": results}

@router.get("/ansi_51/export")
async def export_ansi_51(
    format: str = Query("xlsx", pattern="^(xlsx|json)$"),
    token: str = Depends(get_current_token)
):
    config = get_config_from_session(token)
    results = _run_ansi_51_logic(config, token)
    
    if format == "json":
        return JSONResponse(content={"results": results}, headers={"Content-Disposition": "attachment; filename=ansi_51_results.json"})
    
    excel_bytes = _generate_ansi51_excel(results)
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ansi_51_results.xlsx"}
    )
