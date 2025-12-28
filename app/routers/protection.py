
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
import copy # IMPORTANT pour isoler les scénarios

router = APIRouter(prefix="/protection", tags=["Protection Coordination (PC)"])

# --- HELPERS ---

def is_supported(fname: str) -> bool:
    e = fname.lower()
    return e.endswith('.si2s') or e.endswith('.mdb') or e.endswith('.lf1s')

def get_merged_dataframes_for_calc(token: str):
    """
    Legacy helper: still used for generic global preview if needed.
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
        if isinstance(target_content, bytes):
            text_content = target_content.decode('utf-8')
        else:
            text_content = target_content  
        data = json.loads(text_content)
        return ProjectConfig(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid Config JSON: {e}")

# --- GENERIC LOGIC (Legacy / Global) ---
def _execute_calculation_logic(config: ProjectConfig, token: str):
    # Cette fonction fusionne tout (ancienne méthode)
    # On la garde pour l'instant pour ne pas casser les autres endpoints
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

# --- ANSI 51 MULTI-FILE LOGIC ---

def _run_ansi_51_logic(config: ProjectConfig, token: str) -> List[dict]:
    """
    Nouveau Moteur : 
    1. Récupère tous les fichiers.
    2. Pour CHAQUE fichier SI2S :
       a. Extrait les données.
       b. Résout la topologie (car les IDs peuvent changer ou être absents).
       c. Lance le calcul ANSI 51 pour tous les plans.
    3. Agglomère tous les résultats.
    """
    files = session_manager.get_files(token)
    results = []
    
    # On boucle sur chaque fichier individuellement
    for filename, content in files.items():
        if not is_supported(filename): 
            continue
            
        # 1. Extraction spécifique à CE fichier
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: 
            continue
            
        # 2. Copie propre de la config pour ne pas mélanger les topologies entre fichiers
        file_config = copy.deepcopy(config)
        
        # 3. Résolution Topologie (Spécifique à ce fichier SI2S)
        topology_manager.resolve_all(file_config, dfs)
        
        # 4. Exécution des calculs pour tous les plans sur CE fichier
        for plan in file_config.plans:
            try:
                res = ansi_51.calculate(plan, file_config.settings, dfs)
                
                # Enrichissement des métadonnées
                res["plan_id"] = plan.id
                res["plan_type"] = plan.type
                res["source_file"] = filename # <--- La clé du tri !
                
                results.append(res)
            except Exception as e:
                results.append({
                    "plan_id": plan.id,
                    "plan_type": plan.type,
                    "source_file": filename,
                    "ansi_code": "51",
                    "status": "error",
                    "comments": [f"Error in {filename}: {str(e)}"]
                })
                
    return results

def _generate_ansi51_excel(results: List[dict]) -> bytes:
    """
    Génère l'Excel avec 'Source File' en première colonne.
    """
    flat_rows = []
    
    for res in results:
        # Base info
        row = {
            "Source File": res.get("source_file"), # Priorité 1
            "Plan ID": res.get("plan_id"),
            "Type": res.get("plan_type"),
            "Status": res.get("status"),
            "Bus From": res.get("topology_used", {}).get("bus_from"),
            "Bus To": res.get("topology_used", {}).get("bus_to"),
        }

        # Thresholds
        thresh = res.get("calculated_thresholds", {})
        row["Pickup (A)"] = thresh.get("pickup_amps")
        row["Time Dial"] = thresh.get("time_dial")
        row["Comments"] = " | ".join(res.get("comments", []))

        # Data Dump (From/To)
        data_section = res.get("data_si2s", {})
        
        # Bus Amont
        from_data = data_section.get("bus_from_data")
        if isinstance(from_data, dict):
            for k, v in from_data.items():
                row[f"FROM_{k}"] = v
        
        # Bus Aval
        to_data = data_section.get("bus_to_data")
        if isinstance(to_data, dict):
            for k, v in to_data.items():
                row[f"TO_{k}"] = v

        flat_rows.append(row)

    df = pd.DataFrame(flat_rows)
    
    # Ordonnancement des colonnes
    cols = list(df.columns)
    # On force 'Source File' et 'Plan ID' au début
    prio_cols = ["Source File", "Plan ID", "Type", "Status", "Bus From", "Bus To", "Pickup (A)"]
    final_cols = [c for c in prio_cols if c in cols] + [c for c in cols if c not in prio_cols]
    
    df = df[final_cols]
    
    # Tri des lignes pour grouper par Plan puis par Fichier (optionnel mais propre)
    if "Plan ID" in df.columns and "Source File" in df.columns:
        df = df.sort_values(by=["Plan ID", "Source File"])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Multi-Scenario Results", index=False)
        # Largeur colonnes
        ws = writer.sheets["Multi-Scenario Results"]
        for col in ws.columns:
            try: ws.column_dimensions[col[0].column_letter].width = 20
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

@router.post("/ansi_51/run")
async def run_ansi_51_only(token: str = Depends(get_current_token)):
    config = get_config_from_session(token)
    results = _run_ansi_51_logic(config, token)
    return {"status": "success", "total_scenarios": len(results), "results": results}

@router.get("/ansi_51/export")
async def export_ansi_51(
    format: str = Query("xlsx", pattern="^(xlsx|json)$"),
    token: str = Depends(get_current_token)
):
    config = get_config_from_session(token)
    results = _run_ansi_51_logic(config, token)
    
    if format == "json":
        return JSONResponse(content={"results": results}, headers={"Content-Disposition": "attachment; filename=ansi_51_multi_scenario.json"})
    
    excel_bytes = _generate_ansi51_excel(results)
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ansi_51_multi_scenario.xlsx"}
    )
