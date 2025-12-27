import pandas as pd
import math
import os
# CORRECTION ICI : Utilisation de db_converter
from app.calculations import db_converter
from app.schemas.loadflow_schema import TransformerData, SwingBusInfo, StudyCaseInfo

def analyze_loadflow(files_content: dict, settings, only_winners: bool = False) -> dict:
    print(f"🚀 START ANALYSIS (Multi-Scenario Strategy)")
    results = []
    target = settings.target_mw
    tol = settings.tolerance_mw
    champions = {}
    file_count = 0

    for filename, content in files_content.items():
        clean_name = os.path.basename(filename)
        ext = clean_name.lower()
        # Filtre extensions
        if clean_name.startswith('~$') or not (ext.endswith('.lf1s') or ext.endswith('.si2s') or ext.endswith('.mdb') or ext.endswith('.json')):
            continue  
        file_count += 1

        res = {
            "filename": filename,
            "is_valid": False,
            "study_case": {"id": None, "config": None, "revision": None},
            "swing_bus_found": { "config": settings.swing_bus_id, "script": None },
            "mw_flow": None, "mvar_flow": None, "transformers": {}, "delta_target": None,
            "status_color": "red", "is_winner": False, "victory_reason": None
        }

        try:
            # CORRECTION ICI : Appel à db_converter
            dfs = db_converter.extract_data_from_db(content)
            
            # Gestion cas particulier où le résultat serait encapsulé (legacy)
            if dfs and "data" in dfs and isinstance(dfs["data"], dict): 
                dfs = dfs["data"]
        except Exception as e: 
            print(f"Error reading DB {filename}: {e}")
            dfs = None
            
        if not dfs: 
            results.append(res)
            continue
            
        res["is_valid"] = True
        
        # --- 2. EXTRACT STUDY CASE ---
        study_id = "Unknown"; study_cfg = "Unknown"; study_rev = "Unknown"
        if "ILFStudyCase" in dfs:
            val = dfs["ILFStudyCase"]
            df_study = pd.DataFrame(val) if isinstance(val, list) else val
            if df_study is not None and not df_study.empty:
                # Normalize columns
                df_study.columns = [str(c).strip() for c in df_study.columns]
                if "ID" in df_study.columns: study_id = str(df_study.iloc[0]["ID"])
                if "Config" in df_study.columns: study_cfg = str(df_study.iloc[0]["Config"])
                if "Revision" in df_study.columns: study_rev = str(df_study.iloc[0]["Revision"])
        
        res["study_case"] = {"id": study_id, "config": study_cfg, "revision": study_rev}

        # --- 3. PREPARE DATAFRAMES ---
        df_lfr = None
        df_tx = None
        
        for k in dfs.keys():
            key_upper = k.upper()
            if key_upper in ['LFR', 'BUSLOADSUMMARY']:
                val = dfs[k]
                df_lfr = pd.DataFrame(val) if isinstance(val, list) else val
            elif 'IXFMR2' in key_upper:
                val = dfs[k]
                df_tx = pd.DataFrame(val) if isinstance(val, list) else val
        
        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # --- 4. SWING BUS FLOW ---
        target_bus_id = settings.swing_bus_id
        
        # A. Auto-detect if not configured
        if df_lfr is not None:
            col_id_any = next((c for c in df_lfr.columns if c.upper() in ['ID', 'BUSID', 'IDFROM']), None)
            
            if not target_bus_id and col_id_any:
                col_type = next((c for c in df_lfr.columns if 'TYPE' in c.upper()), None)
                if col_type:
                    # Look for 'Swing' or 'Swng'
                    swing_rows = df_lfr[df_lfr[col_type].astype(str).str.upper().str.contains('SWNG|SWING')]
                    if not swing_rows.empty:
                        target_bus_id = str(swing_rows.iloc[0][col_id_any])
            
            res["swing_bus_found"]["script"] = target_bus_id

            # B. Read MW Flow
            if target_bus_id:
                # Try to find the row for this bus
                col_mw = next((c for c in df_lfr.columns if c.upper() in ['LFMW', 'MW', 'MWLOADING', 'P (MW)']), None)
                col_mvar = next((c for c in df_lfr.columns if c.upper() in ['LFMVAR', 'MVAR', 'MVARLOADING', 'Q (MVAR)']), None)
                
                cols_search = [c for c in df_lfr.columns if c.upper() in ['ID', 'IDFROM', 'IDTO']]
                
                mask = pd.Series(False, index=df_lfr.index)
                for c in cols_search:
                    mask |= (df_lfr[c].astype(str) == str(target_bus_id))
                
                rows = df_lfr[mask]
                if not rows.empty:
                    row = rows.iloc[0]
                    if col_mw:
                        try: res["mw_flow"] = float(str(row[col_mw]).replace(',', '.'))
                        except: pass
                    if col_mvar:
                        try: res["mvar_flow"] = float(str(row[col_mvar]).replace(',', '.'))
                        except: pass

        # --- 5. EXTRACT TRANSFORMERS ---
        if df_tx is not None:
            # Basic extraction logic for transformers
            pass 

        # --- 6. BATTLE LOGIC (Determines Winner) ---
        if res["mw_flow"] is not None:
            delta = abs(res["mw_flow"] - target)
            res["delta_target"] = round(delta, 3)
            
            candidate_is_valid = delta <= tol
            
            if candidate_is_valid:
                res["status_color"] = "green"
            elif delta <= (tol * 2):
                res["status_color"] = "orange"
            else:
                res["status_color"] = "red"
            
            # Tournament Logic
            group_key = (study_id, study_cfg)
            current_champ = champions.get(group_key)
            
            is_new_king = False
            reason = ""
            
            if current_champ is None:
                is_new_king = True
                reason = "First candidate"
            else:
                champ_valid = current_champ["valid"]
                champ_delta = current_champ["delta"]
                
                if candidate_is_valid and not champ_valid:
                    is_new_king = True
                    reason = "Validity (Winner is valid, previous wasn't)"
                elif candidate_is_valid and champ_valid:
                    if delta < champ_delta:
                        is_new_king = True
                        reason = "Precision (Better delta)"
                elif not candidate_is_valid and not champ_valid:
                    if delta < champ_delta:
                        is_new_king = True
                        reason = "Proximity (Both invalid, but closer)"

            if is_new_king:
                champions[group_key] = {
                    "filename": filename,
                    "delta": delta,
                    "valid": candidate_is_valid,
                    "reason": reason
                }

        results.append(res)

    # --- 7. FINALIZE WINNERS ---
    for r in results:
        s_id = r["study_case"]["id"]
        s_cfg = r["study_case"]["config"]
        
        champ = champions.get((s_id, s_cfg))
        if champ and champ["filename"] == r["filename"]:
            r["is_winner"] = True
            r["victory_reason"] = champ["reason"]
    
    if only_winners:
        results = [r for r in results if r.get("is_winner") is True]
        
    return {"status": "success", "results": results}
