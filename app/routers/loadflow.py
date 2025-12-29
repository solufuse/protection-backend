from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.encoders import jsonable_encoder # [+] [INFO] Fix for correct JSON dumping
from app.core.security import get_current_token
from app.services import session_manager
from app.calculations import loadflow_calculator
from app.schemas.loadflow_schema import LoadflowSettings
import json
import pandas as pd
import io
import zipfile

# Define the router
router = APIRouter(prefix="/loadflow", tags=["Loadflow Analysis"])

# --- HELPERS ---

def is_supported_loadflow(fname: str) -> bool:
    e = fname.lower()
    return e.endswith('.lf1s') or e.endswith('.mdb') or e.endswith('.si2s')

def get_lf_config_from_session(token: str) -> LoadflowSettings:
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
        if "loadflow_settings" not in data: raise HTTPException(status_code=400, detail="Missing 'loadflow_settings'.")
        return LoadflowSettings(**data["loadflow_settings"])
    except Exception as e: raise HTTPException(status_code=422, detail=f"Invalid config: {e}")

def _generate_excel_bytes(data: dict) -> bytes:
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
                
                # Check if tx_data is dict (from new calculator) or object
                if isinstance(tx_data, dict):
                    # Use keys from Aliases
                    tap_val = tx_data.get("Tap")
                    mw_val = tx_data.get("LFMW")
                    mvar_val = tx_data.get("LFMvar")
                    amp_val = tx_data.get("LFAmp")
                    kv_val = tx_data.get("kV")
                    volt_val = tx_data.get("VoltMag")
                    pf_val = tx_data.get("LFPF")
                else:
                    # Fallback (old object style)
                    tap_val = getattr(tx_data, "tap", None)
                    mw_val = getattr(tx_data, "mw", None)
                    mvar_val = getattr(tx_data, "mvar", None)
                    amp_val = getattr(tx_data, "amp", None)
                    kv_val = getattr(tx_data, "kv", None)
                    volt_val = getattr(tx_data, "volt_mag", None)
                    pf_val = getattr(tx_data, "pf", None)

                row.update({
                    "Transfo ID": tx_id,
                    "Tap": tap_val,
                    "MW (Tx)": mw_val,
                    "Mvar (Tx)": mvar_val,
                    "Amp (A)": amp_val,
                    "kV": kv_val,
                    "Volt Mag": volt_val,
                    "PF": pf_val
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
            
    return output.getvalue()

def generate_flat_excel(data: dict, filename: str):
    excel_content = _generate_excel_bytes(data)
    return StreamingResponse(
        io.BytesIO(excel_content), 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- ENDPOINTS ---

@router.post("/run")
async def run_loadflow_session(
    format: str = Query("json", pattern="^(xlsx|json)$"), 
    token: str = Depends(get_current_token)
):
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    data = loadflow_calculator.analyze_loadflow(files, config, only_winners=False)
    
    if format == "xlsx":
        return generate_flat_excel(data, "loadflow_export_all.xlsx")
    
    return data

@router.post("/run-win")
async def run_loadflow_winners_only(
    format: str = Query("json", pattern="^(xlsx|json)$"), 
    token: str = Depends(get_current_token)
):
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    data = loadflow_calculator.analyze_loadflow(files, config, only_winners=True)
    
    if format == "xlsx":
        return generate_flat_excel(data, "loadflow_export_winners.xlsx")
        
    return data

@router.post("/run-and-save")
async def run_and_save_loadflow(
    basename: str = Query("loadflow_results", description="Base name for the output files"),
    token: str = Depends(get_current_token)
):
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    
    data = loadflow_calculator.analyze_loadflow(files, config, only_winners=False)
    
    # 3. Save JSON File
    # [!] [CRITICAL] Use jsonable_encoder to handle Pydantic/Dict objects properly before dumping
    json_content = jsonable_encoder(data)
    json_filename = f"{basename}.json"
    json_bytes = json.dumps(json_content, indent=2, default=str).encode('utf-8')
    session_manager.add_file(token, json_filename, json_bytes)
    
    # 4. Save XLSX File
    xlsx_filename = f"{basename}.xlsx"
    xlsx_bytes = _generate_excel_bytes(data)
    session_manager.add_file(token, xlsx_filename, xlsx_bytes)
    
    return {
        "status": "success",
        "message": f"Calculation complete. Saved files to user storage.",
        "files_saved": [json_filename, xlsx_filename],
        "data_summary": f"{len(data.get('results', []))} files analyzed."
    }
