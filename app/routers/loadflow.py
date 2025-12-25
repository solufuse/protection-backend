from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.security import get_current_token
from app.services import session_manager
from app.calculations import loadflow_calculator
from app.schemas.loadflow_schema import LoadflowSettings, LoadflowResponse
import json
import pandas as pd
import io
import zipfile  # <--- Module nécessaire pour créer le ZIP

router = APIRouter(prefix="/loadflow", tags=["Loadflow Analysis"])

def get_lf_config_from_session(token: str) -> LoadflowSettings:
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="Session vide.")
    
    target_content = None
    if "config.json" in files: target_content = files["config.json"]
    else:
        for name, content in files.items():
            if name.lower().endswith(".json"): target_content = content; break
    
    if target_content is None: raise HTTPException(status_code=404, detail="Aucun config.json trouvé.")

    try:
        if isinstance(target_content, bytes): text_content = target_content.decode('utf-8')
        else: text_content = target_content
        data = json.loads(text_content)
        if "loadflow_settings" not in data: raise HTTPException(status_code=400, detail="Manque loadflow_settings")
        return LoadflowSettings(**data["loadflow_settings"])
    except Exception as e: raise HTTPException(status_code=422, detail=f"Config invalide: {e}")

# --- ROUTES EXISTANTES ---

@router.post("/run", response_model=LoadflowResponse)
async def run_loadflow_session(token: str = Depends(get_current_token)):
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    return loadflow_calculator.analyze_loadflow(files, config, only_winners=False)

@router.post("/run-win", response_model=LoadflowResponse)
async def run_loadflow_winners_only(token: str = Depends(get_current_token)):
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    return loadflow_calculator.analyze_loadflow(files, config, only_winners=True)

@router.get("/export")
async def export_all_files(
    format: str = Query("xlsx", regex="^(xlsx|json)$"),
    token: str = Depends(get_current_token)
):
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    data = loadflow_calculator.analyze_loadflow(files, config, only_winners=False)
    
    if format == "json":
        return JSONResponse(content=data, headers={"Content-Disposition": "attachment; filename=loadflow_export.json"})

    # Excel Flatten Logic
    results = data.get("results", [])
    flat_rows = []
    for res in results:
        sc = res.get("study_case", {})
        base_info = {
            "Fichier": res["filename"],
            "Etude ID": sc.get("id"), "Config": sc.get("config"), "Revision": sc.get("revision"),
            "Status": "Gagnant" if res.get("is_winner") else "Non retenu",
            "Raison Victoire": res.get("victory_reason"),
            "MW Flow": res.get("mw_flow"), "Mvar Flow": res.get("mvar_flow"), "Ecart Cible": res.get("delta_target"),
            "Swing Bus": res.get("swing_bus_found", {}).get("script"),
        }
        transformers = res.get("transformers", {})
        if not transformers:
            row = base_info.copy(); row["Info"] = "Aucun transfo"; flat_rows.append(row)
        else:
            for tx_id, tx_data in transformers.items():
                row = base_info.copy()
                row.update({
                    "Transfo ID": tx_id,
                    "Tap": getattr(tx_data, "tap", None),
                    "MW (Tx)": getattr(tx_data, "mw", None),
                    "Mvar (Tx)": getattr(tx_data, "mvar", None),
                    "Amp (A)": getattr(tx_data, "amp", None),
                    "Tension (kV)": getattr(tx_data, "kv", None),
                    "Volt Mag": getattr(tx_data, "volt_mag", None),
                    "PF": getattr(tx_data, "pf", None)
                })
                flat_rows.append(row)

    df_final = pd.DataFrame(flat_rows)
    cols = ["Fichier", "Etude ID", "Config", "Revision", "Status", "Raison Victoire", "MW Flow", "Ecart Cible"]
    other_cols = [c for c in df_final.columns if c not in cols]
    if not df_final.empty: df_final = df_final[cols + other_cols]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, sheet_name="Resultats", index=False)
        for col in writer.sheets["Resultats"].columns:
            try: writer.sheets["Resultats"].column_dimensions[col[0].column_letter].width = 18
            except: pass
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=loadflow_export.xlsx"})

# --- NOUVELLE ROUTE ZIP ---

@router.get("/export-l1fs")
async def export_winners_l1fs(token: str = Depends(get_current_token)):
    """
    Télécharge une archive ZIP contenant uniquement les fichiers .LF1S gagnants.
    """
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    
    # 1. On récupère la liste des gagnants
    analysis = loadflow_calculator.analyze_loadflow(files, config, only_winners=True)
    winners = analysis.get("results", [])
    
    if not winners:
        raise HTTPException(status_code=404, detail="Aucun fichier gagnant trouvé.")

    # 2. Création du ZIP en mémoire
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for win in winners:
            fname = win.get("filename")
            
            # On récupère le contenu brut du fichier depuis la session
            if fname in files:
                file_content = files[fname]
                
                # ZipFile attend des bytes ou str
                # Si le contenu est un dict (json parsé), on le remet en str
                if isinstance(file_content, (dict, list)):
                    file_content = json.dumps(file_content, indent=2)
                
                zip_file.writestr(fname, file_content)

    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer, 
        media_type="application/zip", 
        headers={"Content-Disposition": "attachment; filename=gagnants_loadflow.zip"}
    )
