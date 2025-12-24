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
def get_merged_dataframes_for_calc(token: str):
    """Fusionne pour le calcul topologique (interne)"""
    files = session_manager.get_files(token)
    if not files: return {}
    merged_dfs = {}
    for name, content in files.items():
        if name.lower().endswith('.si2s') or name.lower().endswith('.mdb'):
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
    config_updated = topology_manager.resolve_all(config, dfs_dict)
    return {
        "status": "success",
        "engine": "Protection Coordination (PC)",
        "project": config_updated.project_name,
        "plans": config_updated.plans
    }

# --- ROUTES STANDARD ---
@router.post("/run")
async def run_study_json(config: ProjectConfig, token: str = Depends(get_current_token)):
    return _execute_calculation_logic(config, token)

@router.post("/run-file")
async def run_study_file(file: UploadFile = File(...), token: str = Depends(get_current_token)):
    content = await file.read()
    try: valid_config = ProjectConfig(**json.loads(content))
    except Exception as e: raise HTTPException(status_code=422, detail=f"Erreur config: {e}")
    return _execute_calculation_logic(valid_config, token)

# --- DATA EXPLORER & EXPORT ---

def _collect_explorer_data(token, table_search, filename_filter):
    """Récupère les données brutes par fichier"""
    files = session_manager.get_files(token)
    if not files: return {}
    
    results = {}
    
    for fname, content in files.items():
        # Filtre Fichier
        if filename_filter and filename_filter.lower() not in fname.lower():
            continue
        if not (fname.lower().endswith('.si2s') or fname.lower().endswith('.mdb')):
            continue

        dfs = si2s_converter.extract_data_from_si2s(content)
        if not dfs: continue
        
        file_results = {}
        for table_name, df in dfs.items():
            # Filtre Table
            if table_search and table_search.upper() not in table_name.upper():
                continue
            file_results[table_name] = df
            
        if file_results:
            results[fname] = file_results
            
    return results

@router.get("/data-explorer")
def explore_si2s_data(
    table_search: Optional[str] = Query(None, description="Filtre sur le nom de la table"),
    filename: Optional[str] = Query(None, description="Filtre sur un fichier spécifique"),
    export_format: Optional[str] = Query(None, regex="^(json|xlsx)$", description="Format d'export (laisser vide pour voir le JSON)"),
    token: str = Depends(get_current_token)
):
    """
    🔍 EXPLORATEUR & EXPORT
    - **Visualisation** : Laisser `export_format` vide.
    - **Téléchargement** : Mettre `export_format=xlsx` ou `json`.
    """
    
    # 1. Récupération des DataFrames bruts
    raw_data = _collect_explorer_data(token, table_search, filename)
    
    if not raw_data:
        raise HTTPException(status_code=404, detail="Aucune donnée trouvée avec ces filtres.")

    # --- MODE EXPORT EXCEL ---
    if export_format == "xlsx":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            
            # On doit regrouper par Table pour faire des onglets Excel propres
            # Structure cible : { "IConnect": [df_fichier1, df_fichier2], ... }
            tables_aggregated = {}
            
            for fname, tables in raw_data.items():
                for t_name, df in tables.items():
                    # On ajoute une colonne pour savoir de quel fichier ça vient
                    df_copy = df.copy()
                    df_copy.insert(0, "_SourceFile", fname)
                    
                    if t_name not in tables_aggregated:
                        tables_aggregated[t_name] = []
                    tables_aggregated[t_name].append(df_copy)
            
            # Écriture des onglets
            for t_name, df_list in tables_aggregated.items():
                # Excel limite nom onglet à 31 cars
                sheet_name = t_name[:31]
                full_df = pd.concat(df_list, ignore_index=True)
                
                # Gestion doublons onglets (rare mais possible avec le substring)
                count = 1
                base = sheet_name
                while sheet_name in writer.book.sheetnames:
                    sheet_name = f"{base[:28]}_{count}"
                    count += 1
                    
                full_df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        output.seek(0)
        filename_dl = f"explorer_export_{table_search if table_search else 'full'}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename_dl}"}
        )

    # --- MODE EXPORT JSON (Fichier) ---
    elif export_format == "json":
        # On convertit les DataFrames en dict pour le JSON
        json_ready = {}
        for fname, tables in raw_data.items():
            json_ready[fname] = {}
            for t_name, df in tables.items():
                # Conversion safe pour JSON
                json_ready[fname][t_name] = df.where(pd.notnull(df), None).to_dict(orient="records")
                
        filename_dl = f"explorer_export_{table_search if table_search else 'full'}.json"
        return JSONResponse(
            content=json_ready,
            headers={"Content-Disposition": f"attachment; filename={filename_dl}"}
        )

    # --- MODE VISUALISATION (Défaut) ---
    else:
        # Version allégée pour l'affichage (Max 20 lignes)
        preview_data = {}
        for fname, tables in raw_data.items():
            preview_data[fname] = {}
            for t_name, df in tables.items():
                preview_data[fname][t_name] = {
                    "rows": len(df),
                    "columns": list(df.columns),
                    "preview": df.head(20).where(pd.notnull(df), None).to_dict(orient="records")
                }
                
        return {
            "mode": "preview",
            "filters": {"filename": filename, "table": table_search},
            "data": preview_data
        }
