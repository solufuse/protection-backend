import pandas as pd
import math
import os
from app.calculations import db_converter as db_conv
from app.schemas.loadflow_schema import TransformerData

def analyze_loadflow(files_content: dict, settings, only_winners: bool = False) -> dict:
    """
    Logic for Loadflow Analysis - Robust Data Extraction.
    """
    print(f"🚀 START ANALYSIS: {len(files_content)} files received.")
    results = []
    target = settings.target_mw
    tol = settings.tolerance_mw
    champions = {}

    for filename, content in files_content.items():
        clean_name = os.path.basename(filename).strip()
        # Filtre les fichiers temporaires et non supportés
        if clean_name.startswith('~$') or not clean_name.lower().endswith(('.lf1s', '.mdb')):
            continue
            
        res = {
            "filename": filename,
            "is_valid": False,
            "study_case": {"id": None, "config": None, "revision": None},
            "swing_bus_found": {"config": settings.swing_bus_id, "script": None},
            "mw_flow": None,
            "mvar_flow": None,
            "transformers": {},
            "delta_target": None,
            "status_color": "red",
            "is_winner": False,
            "victory_reason": None
        }

        try:
            # 1. Extraction via db_converter
            raw_dfs = db_conv.extract_data_from_db(content)
            
            # Gestion si les données sont encapsulées dans une clé "data"
            dfs = raw_dfs.get("data", raw_dfs) if isinstance(raw_dfs, dict) else raw_dfs
            
            if dfs and isinstance(dfs, dict) and len(dfs) > 0:
                res["is_valid"] = True
                
                # 2. Extraction Metadata (ILFStudyCase)
                for k in dfs.keys():
                    if k.upper() == 'ILFSTUDYCASE':
                        df_s = pd.DataFrame(dfs[k])
                        if not df_s.empty:
                            df_s.columns = [str(c).strip() for c in df_s.columns]
                            res["study_case"]["id"] = str(df_s.iloc[0].get("ID", "Unknown"))
                            res["study_case"]["config"] = str(df_s.iloc[0].get("Config", "Unknown"))
                
                # 3. Extraction Flux (LFR)
                df_lfr = None
                for k in dfs.keys():
                    if k.upper() in ['LFR', 'BUSLOADSUMMARY']:
                        df_lfr = pd.DataFrame(dfs[k])
                        break
                
                if df_lfr is not None and not df_lfr.empty:
                    df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
                    
                    # Détection auto du Swing Bus si vide
                    target_bus = settings.swing_bus_id
                    if not target_bus:
                        col_type = next((c for c in df_lfr.columns if 'TYPE' in c.upper()), None)
                        col_id = next((c for c in df_lfr.columns if c.upper() in ['ID', 'BUSID']), None)
                        if col_type and col_id:
                            sw_rows = df_lfr[df_lfr[col_type].astype(str).str.upper().str.contains('SWNG|SWING')]
                            if not sw_rows.empty: target_bus = str(sw_rows.iloc[0][col_id])
                    
                    res["swing_bus_found"]["script"] = target_bus
                    
                    # Lecture MW
                    if target_bus:
                        # On cherche dans la première colonne (généralement ID)
                        rows = df_lfr[df_lfr.iloc[:, 0].astype(str).str.strip() == str(target_bus).strip()]
                        if not rows.empty:
                            c_mw = next((c for c in df_lfr.columns if c.upper() in ['LFMW', 'MW']), None)
                            if c_mw:
                                val = str(rows.iloc[0][c_mw]).replace(',', '.')
                                res["mw_flow"] = pd.to_numeric(val, errors='coerce')

                # 4. Battle Logic (si MW trouvé)
                if res["mw_flow"] is not None:
                    delta = abs(res["mw_flow"] - target)
                    res["delta_target"] = round(delta, 3)
                    valid = delta <= tol
                    res["status_color"] = "green" if valid else "red"
                    
                    group_key = (res["study_case"]["id"], res["study_case"]["config"])
                    champ = champions.get(group_key)
                    if champ is None or (valid and not champ['valid']) or (delta < champ['delta']):
                        champions[group_key] = {"filename": filename, "delta": delta, "valid": valid, "reason": "Best Match"}
            else:
                print(f"⚠️ No tables found in {clean_name}")

        except Exception as e:
            print(f"❌ Error processing {clean_name}: {e}")

        results.append(res)

    # Marquage des gagnants
    for r in results:
        key = (r["study_case"]["id"], r["study_case"]["config"])
        champ = champions.get(key)
        if champ and champ["filename"] == r["filename"]:
            r["is_winner"] = True
            r["victory_reason"] = champ["reason"]

    if only_winners:
        results = [r for r in results if r.get("is_winner")]

    return {"status": "success", "results": results}
