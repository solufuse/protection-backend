from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional, List, Dict
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import si2s_converter, topology_manager
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
            dfs = si2s_converter.extract_data_from_si2s(content)
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
    dfs_dict = get_merged_dataframes_for_calc(token)
    
    # Note: Si dfs_dict est vide, topology_manager peut gérer ou lever une erreur.
    # On laisse passer pour l'instant au cas où config suffit.
    
    config_updated = topology_manager.resolve_all(config, dfs_dict)
    return {
        "status": "success",
        "engine": "Protection Coordination (PC)",
        "project": config_updated.project_name,
        "plans": config_updated.plans
    }

def get_config_from_session(token: str) -> ProjectConfig:
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="Session vide.")
    
    target_content = None
    if "config.json" in files:
        target_content = files["config.json"]
    else:
        for name, content in files.items():
            if name.lower().endswith(".json"):
                target_content = content
                break
    
    if target_content is None:
        raise HTTPException(status_code=404, detail="Aucun 'config.json' trouvé en session.")

    try:
        # CORRECTION : Décodage
        if isinstance(target_content, bytes):
            text_content = target_content.decode('utf-8')
        else:
            text_content = target_content
            
        data = json.loads(text_content)
        return ProjectConfig(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Config JSON invalide : {e}")

# --- ROUTES ---

@router.post("/run-json")
async def run_study_manual(config: ProjectConfig, token: str = Depends(get_current_token)):
    """
    ✅ MÉTHODE MANUELLE
    Envoyez la config dans le Body.
    """
    return _execute_calculation_logic(config, token)

@router.post("/run")
async def run_study_auto(token: str = Depends(get_current_token)):
    """
    ✅ MÉTHODE AUTO (SESSION)
    Utilise le 'config.json' et les fichiers réseaux (.si2s/.lf1s) en mémoire.
    """
    config = get_config_from_session(token)
    return _execute_calculation_logic(config, token)

# --- (Data Explorer inchangé, on ne le remet pas pour alléger le script) ---
# Mais il faut réimporter les routes explorer si on veut garder la fonctionnalité.
# Pour faire simple ici, on remet juste la route explorer minimale pour ne pas casser le fichier
# ---------------------------------------------------------------------------------
def _collect_explorer_data(token, table_search, filename_filter):
    # (Version simplifiée pour réécriture)
    files = session_manager.get_files(token)
    if not files: return {}
    results = {}
    for fname, content in files.items():
        if filename_filter and filename_filter.lower() not in fname.lower(): continue
        if not is_supported(fname): continue
        dfs = si2s_converter.extract_data_from_si2s(content)
        if dfs:
            file_results = {}
            for table_name, df in dfs.items():
                if table_search and table_search.upper() not in table_name.upper(): continue
                file_results[table_name] = df
            if file_results: results[fname] = file_results
    return results

@router.get("/data-explorer")
def explore_si2s_data(
    table_search: Optional[str] = Query(None),
    filename: Optional[str] = Query(None),
    token: str = Depends(get_current_token)
):
    raw_data = _collect_explorer_data(token, table_search, filename)
    if not raw_data: raise HTTPException(status_code=404, detail="No data.")
    
    preview_data = {}
    for fname, tables in raw_data.items():
        preview_data[fname] = {}
        for t_name, df in tables.items():
            preview_data[fname][t_name] = {"rows": len(df), "columns": list(df.columns)}
    return {"data": preview_data}
