from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.security import get_current_token
from app.services import session_manager
from app.calculations import loadflow_calculator
from app.schemas.loadflow_schema import LoadflowSettings, LoadflowResponse
import json
import pandas as pd
import io
import zipfile

router = APIRouter(prefix="/loadflow", tags=["Loadflow Analysis"])

def get_lf_config_from_session(token: str) -> LoadflowSettings:
    """
    Helper: Retrieves and parses 'config.json' from the user's session.
    """
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="Session empty.")
    
    target_content = None
    if "config.json" in files: target_content = files["config.json"]
    else:
        for name, content in files.items():
            if name.lower().endswith(".json"): target_content = content; break
    
    if target_content is None: raise HTTPException(status_code=404, detail="No config.json found.")

    try:
        if isinstance(target_content, bytes): text_content = target_content.decode('utf-8')
        else: text_content = target_content
        data = json.loads(text_content)
        if "loadflow_settings" not in data: raise HTTPException(status_code=400, detail="Missing 'loadflow_settings' section.")
        return LoadflowSettings(**data["loadflow_settings"])
    except Exception as e: raise HTTPException(status_code=422, detail=f"Invalid config: {e}")

# --- INTERNAL HELPER FOR EXCEL ---
def generate_flat_excel(data: dict, filename: str):
    """
    Generates a flattened Excel file (one row per transformer) from the analysis results.
    """
    results = data.get("results", [])
    flat_rows = []

    for res in results:
        sc = res.get("study_case", {})
        base_info = {
            "File": res["filename"],
            "Study ID": sc.get("id"),
            "Config": sc.get("config"),
            "Revision": sc.get("revision"),
            "Status": "Winner" if res.get("is_winner") else "Rejected",
            "Victory Reason": res.get("victory_reason"),
            "MW Flow": res.get("mw_flow"),
            "Mvar Flow": res.get("mvar_flow"),
            "Delta Target": res.get("delta_target"),
            "Swing Bus": res.get("swing_bus_found", {}).get("script"),
        }
        transformers = res.get("transformers", {})
        if not transformers:
            row = base_info.copy(); row["Info"] = "No transformers"; flat_rows.append(row)
        else:
            for tx_id, tx_data in transformers.items():
                row = base_info.copy()
                row.update({
                    "Transfo ID": tx_id,
                    "Tap": getattr(tx_data, "tap", None),
                    "MW (Tx)": getattr(tx_data, "mw", None),
                    "Mvar (Tx)": getattr(tx_data, "mvar", None),
                    "Amp (A)": getattr(tx_data, "amp", None),
                    "kV": getattr(tx_data, "kv", None),
                    "Volt Mag": getattr(tx_data, "volt_mag", None),
                    "PF": getattr(tx_data, "pf", None)
                })
                flat_rows.append(row)

    df_final = pd.DataFrame(flat_rows)
    cols_order = ["File", "Study ID", "Config", "Revision", "Status", "Victory Reason", "MW Flow", "Delta Target"]
    existing_cols = [c for c in cols_order if c in df_final.columns]
    other_cols = [c for c in df_final.columns if c not in existing_cols]
    if not df_final.empty: df_final = df_final[existing_cols + other_cols]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, sheet_name="Results", index=False)
        for col in writer.sheets["Results"].columns:
            try: writer.sheets["Results"].column_dimensions[col[0].column_letter].width = 18
            except: pass
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={filename}"})

# --- API ROUTES ---

@router.post("/run", response_model=LoadflowResponse)
async def run_loadflow_session(token: str = Depends(get_current_token)):
    """
    Run Loadflow Analysis on ALL files in the current session.
    
    Returns:
        JSON object containing detailed results for every file (Winners and Losers).
    """
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    return loadflow_calculator.analyze_loadflow(files, config, only_winners=False)

@router.post("/run-win", response_model=LoadflowResponse)
async def run_loadflow_winners_only(token: str = Depends(get_current_token)):
    """
    Run Loadflow Analysis and return ONLY the winning files.
    
    Returns:
        JSON object containing only the best file for each scenario group (Study ID + Config).
    """
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    return loadflow_calculator.analyze_loadflow(files, config, only_winners=True)

@router.get("/export")
async def export_all_files(
    format: str = Query("xlsx", regex="^(xlsx|json)$", description="Output format: 'xlsx' or 'json'"),
    token: str = Depends(get_current_token)
):
    """
    Download a global report of ALL files (Winners and Losers).
    
    - **xlsx**: Returns a flattened Excel table (one row per transformer).
    - **json**: Returns the full JSON response file.
    """
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    data = loadflow_calculator.analyze_loadflow(files, config, only_winners=False)
    
    if format == "json":
        return JSONResponse(content=data, headers={"Content-Disposition": "attachment; filename=loadflow_export_all.json"})
    return generate_flat_excel(data, "loadflow_export_all.xlsx")

@router.get("/export-win")
async def export_winners_flat(
    format: str = Query("xlsx", regex="^(xlsx|json)$", description="Output format: 'xlsx' or 'json'"),
    token: str = Depends(get_current_token)
):
    """
    Download a report of ONLY the WINNING files.
    
    - **xlsx**: Returns a flattened Excel table (one row per transformer).
    - **json**: Returns the filtered JSON response file.
    """
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    data = loadflow_calculator.analyze_loadflow(files, config, only_winners=True)
    
    if format == "json":
        return JSONResponse(content=data, headers={"Content-Disposition": "attachment; filename=loadflow_export_winners.json"})
    return generate_flat_excel(data, "loadflow_export_winners.xlsx")

@router.get("/export-l1fs")
async def export_winners_l1fs(token: str = Depends(get_current_token)):
    """
    Download a ZIP archive containing the source files (.LF1S) of the winners.
    
    Useful to retrieve the best configuration files directly.
    """
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    analysis = loadflow_calculator.analyze_loadflow(files, config, only_winners=True)
    winners = analysis.get("results", [])
    
    if not winners: raise HTTPException(status_code=404, detail="No winners found.")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for win in winners:
            fname = win.get("filename")
            if fname in files:
                content = files[fname]
                if isinstance(content, (dict, list)): content = json.dumps(content, indent=2)
                zip_file.writestr(fname, content)

    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=loadflow_winners_source.zip"})
