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
    Télécharge les résultats gagnants.
    - format=xlsx : Fichier Excel (Resume + Details)
    - format=json : Fichier JSON
    """
    # 1. Calcul des résultats (Gagnants uniquement)
    config = get_lf_config_from_session(token)
    files = session_manager.get_files(token)
    data = loadflow_calculator.analyze_loadflow(files, config, only_winners=True)
    
    results = data.get("results", [])

    # --- CAS 1 : JSON ---
    if format == "json":
        # On renvoie le JSON en tant que fichier téléchargeable
        return JSONResponse(
            content=data,
            headers={"Content-Disposition": "attachment; filename=loadflow_winners.json"}
        )

    # --- CAS 2 : EXCEL ---
    elif format == "xlsx":
        # A. Préparation des données pour Pandas
        summary_rows = []
        transfo_rows = []

        for res in results:
            fname = res["filename"]
            
            # Onglet 1 : Résumé
            summary_rows.append({
                "Fichier": fname,
                "MW Flow": res.get("mw_flow"),
                "Mvar Flow": res.get("mvar_flow"),
                "Delta Cible": res.get("delta_target"),
                "Swing Bus (Config)": res.get("swing_bus_found", {}).get("config"),
                "Swing Bus (Detecté)": res.get("swing_bus_found", {}).get("script"),
            })

            # Onglet 2 : Détails Transfos
            transformers = res.get("transformers", {})
            for tx_id, tx_data in transformers.items():
                # tx_data est un objet Pydantic, on le convertit en dict
                # Note: Dans le dict retourné par calculator, c'est peut-être déjà un objet ou un dict selon l'étape
                # Le calculator renvoie des objets Pydantic dans 'transformers'
                
                # Accès attributs (compatible Pydantic v1/v2 ou dict)
                tap = getattr(tx_data, "tap", None)
                mw = getattr(tx_data, "mw", None)
                mvar = getattr(tx_data, "mvar", None)
                amp = getattr(tx_data, "amp", None)
                kv = getattr(tx_data, "kv", None)
                pf = getattr(tx_data, "pf", None)

                transfo_rows.append({
                    "Fichier Source": fname,
                    "Transfo ID": tx_id,
                    "Tap": tap,
                    "MW": mw,
                    "Mvar": mvar,
                    "Amp (A)": amp,
                    "Tension (kV)": kv,
                    "Power Factor": pf
                })

        # B. Création des DataFrames
        df_summary = pd.DataFrame(summary_rows)
        df_transfos = pd.DataFrame(transfo_rows)

        # C. Écriture dans un buffer binaire
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_summary.to_excel(writer, sheet_name="Gagnants_Resume", index=False)
            df_transfos.to_excel(writer, sheet_name="Details_Transfos", index=False)
            
            # Petit ajustement esthétique des largeurs de colonnes (Auto-width basique)
            for sheet in writer.sheets.values():
                for column in sheet.columns:
                    try:
                        sheet.column_dimensions[column[0].column_letter].width = 20
                    except: pass

        output.seek(0)

        # D. Renvoi du fichier
        return StreamingResponse(
            output, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=loadflow_winners.xlsx"}
        )
