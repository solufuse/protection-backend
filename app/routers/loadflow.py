from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.security import get_current_token
from app.services import session_manager
from app.calculations import loadflow_calculator
from app.schemas.loadflow_schema import LoadflowSettings, LoadflowResponse
import json
import pandas as pd
import io

router = APIRouter(prefix="/loadflow", tags=["Loadflow Analysis"])

# --- HELPER ---
def get_lf_config_from_session(token: str) -> LoadflowSettings:
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="Session vide.")
    
    target_content = None
    if "config.json" in files: target_content = files["config.json"]
    else:
        for name, content in files.items():
            if name.lower().endswith(".json"):
                target_content = content
                break
    
    if target_content is None: raise HTTPException(status_code=404, detail="Aucun config.json trouvé.")

    try:
        if isinstance(target_content, bytes): text_content = target_content.decode('utf-8')
        else: text_content = target_content
        data = json.loads(text_content)
        if "loadflow_settings" not in data:
            raise HTTPException(status_code=400, detail="La section 'loadflow_settings' est manquante")
        return LoadflowSettings(**data["loadflow_settings"])
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Config Loadflow invalide : {e}")

# --- ROUTES ---

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

@router.get("/export-win")
async def export_winners(
    format: str = Query("xlsx", regex="^(xlsx|json)$"),
    token: str = Depends(get_current_token)
):
    """
    Export UNIQUEMENT les gagnants (Structure: 2 onglets Resume/Details).
    """
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    data = loadflow_calculator.analyze_loadflow(files, config, only_winners=True)
    
    if format == "json":
        return JSONResponse(content=data, headers={"Content-Disposition": "attachment; filename=winners.json"})

    # Excel Logic (2 onglets)
    results = data.get("results", [])
    summary_rows = []
    transfo_rows = []
    for res in results:
        fname = res["filename"]
        summary_rows.append({
            "Fichier": fname, "MW Flow": res.get("mw_flow"), "Mvar Flow": res.get("mvar_flow"),
            "Delta": res.get("delta_target"), "Swing": res.get("swing_bus_found", {}).get("script")
        })
        for tx_id, tx_data in res.get("transformers", {}).items():
            transfo_rows.append({
                "Fichier": fname, "ID": tx_id, "Tap": getattr(tx_data, "tap", None),
                "MW": getattr(tx_data, "mw", None), "Mvar": getattr(tx_data, "mvar", None),
                "Amp": getattr(tx_data, "amp", None), "kV": getattr(tx_data, "kv", None)
            })
            
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Resume", index=False)
        pd.DataFrame(transfo_rows).to_excel(writer, sheet_name="Details", index=False)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=winners.xlsx"})


@router.get("/export")
async def export_all_files(
    format: str = Query("xlsx", regex="^(xlsx|json)$"),
    token: str = Depends(get_current_token)
):
    """
    Export TOUT (Gagnants et Perdants) dans un SEUL tableau unifié.
    """
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    # On récupère TOUS les fichiers (only_winners=False)
    data = loadflow_calculator.analyze_loadflow(files, config, only_winners=False)
    
    if format == "json":
        return JSONResponse(
            content=data,
            headers={"Content-Disposition": "attachment; filename=loadflow_full_export.json"}
        )

    # --- FLATTEN LOGIC (Tout dans un seul tableau) ---
    results = data.get("results", [])
    flat_rows = []

    for res in results:
        # Infos communes au fichier
        base_info = {
            "Fichier": res["filename"],
            "Status": "Gagnant" if res.get("is_winner") else "Non retenu",
            "MW Flow Global": res.get("mw_flow"),
            "Mvar Flow Global": res.get("mvar_flow"),
            "Ecart Cible": res.get("delta_target"),
            "Swing Bus": res.get("swing_bus_found", {}).get("script"),
        }
        
        transformers = res.get("transformers", {})
        
        # Si aucun transfo trouvé, on ajoute quand même une ligne pour le fichier
        if not transformers:
            row = base_info.copy()
            row["Info"] = "Aucun transfo trouvé"
            flat_rows.append(row)
        else:
            # Une ligne par transformateur
            for tx_id, tx_data in transformers.items():
                row = base_info.copy()
                
                # Ajout des données du transfo
                row.update({
                    "Transfo ID": tx_id,
                    "Tap": getattr(tx_data, "tap", None),
                    "MW (Tx)": getattr(tx_data, "mw", None),
                    "Mvar (Tx)": getattr(tx_data, "mvar", None),
                    "Amp (A)": getattr(tx_data, "amp", None),
                    "Tension (kV)": getattr(tx_data, "kv", None),
                    "Volt Mag": getattr(tx_data, "volt_mag", None),
                    "Power Factor": getattr(tx_data, "pf", None)
                })
                flat_rows.append(row)

    # Création du DataFrame unique
    df_final = pd.DataFrame(flat_rows)
    
    # Export Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, sheet_name="Resultats_Complets", index=False)
        
        # Auto-width
        for column in writer.sheets["Resultats_Complets"].columns:
            try:
                writer.sheets["Resultats_Complets"].column_dimensions[column[0].column_letter].width = 18
            except: pass

    output.seek(0)
    
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=loadflow_full_export.xlsx"}
    )
