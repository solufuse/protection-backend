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

def is_supported(fname: str) -> bool:
    e = fname.lower()
    return e.endswith('.si2s') or e.endswith('.mdb') or e.endswith('.lf1s')

# --- HELPERS ---
def get_merged_dataframes_for_calc(token: str):
    files = session_manager.get_files(token)
    if not files: return {}
    merged_dfs = {}
    for name, content in files.items():
        if is_supported(name): # <--- Support LF1S ici
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

# --- DATA EXPLORER ---

def _collect_explorer_data(token, table_search, filename_filter):
    files = session_manager.get_files(token)
    if not files: return {}
    results = {}
    for fname, content in files.items():
        if filename_filter and filename_filter.lower() not in fname.lower(): continue
        
        if not is_supported(fname): continue # <--- Support LF1S

        dfs = si2s_converter.extract_data_from_si2s(content)
        if not dfs: continue
        
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
    export_format: Optional[str] = Query(None, regex="^(json|xlsx)$"),
    token: str = Depends(get_current_token)
):
    raw_data = _collect_explorer_data(token, table_search, filename)
    if not raw_data: raise HTTPException(status_code=404, detail="Aucune donnée trouvée.")

    if export_format == "xlsx":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            tables_aggregated = {}
            for fname, tables in raw_data.items():
                for t_name, df in tables.items():
                    df_copy = df.copy()
                    df_copy.insert(0, "_SourceFile", fname)
                    if t_name not in tables_aggregated: tables_aggregated[t_name] = []
                    tables_aggregated[t_name].append(df_copy)
            
            for t_name, df_list in tables_aggregated.items():
                sheet_name = t_name[:31]
                full_df = pd.concat(df_list, ignore_index=True)
                count = 1
                base = sheet_name
                while sheet_name in writer.book.sheetnames:
                    sheet_name = f"{base[:28]}_{count}"; count += 1
                full_df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=explorer_export.xlsx"}
        )

    elif export_format == "json":
        json_ready = {}
        for fname, tables in raw_data.items():
            json_ready[fname] = {}
            for t_name, df in tables.items():
                json_ready[fname][t_name] = df.where(pd.notnull(df), None).to_dict(orient="records")
        return JSONResponse(content=json_ready, headers={"Content-Disposition": "attachment; filename=explorer.json"})

    else:
        preview_data = {}
        for fname, tables in raw_data.items():
            preview_data[fname] = {}
            for t_name, df in tables.items():
                preview_data[fname][t_name] = {
                    "rows": len(df),
                    "columns": list(df.columns),
                    "preview": df.head(20).where(pd.notnull(df), None).to_dict(orient="records")
                }
        return {"mode": "preview", "filters": {"filename": filename}, "data": preview_data}
