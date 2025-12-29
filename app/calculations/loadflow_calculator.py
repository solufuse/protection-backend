import pandas as pd
import math
import os
from app.calculations import db_converter # [+] [INFO] Replacement of obsolete si2s_converter
from app.schemas.loadflow_schema import TransformerData, SwingBusInfo, StudyCaseInfo

def analyze_loadflow(files_content: dict, settings, only_winners: bool = False) -> dict:
    """
    Core logic for Loadflow Analysis.

    Features:
    - Multi-Scenario Support: Groups files by Study Case ID + Config.
    - Battle Logic: Determines winner based on (1) Tolerance Check, (2) Precision, (3) Proximity.
    - Silent Mode: Minimal logging to avoid spamming production logs.
    """
    # [?] [THOUGHT] Logic remains the same, only the data extraction layer is updated for compatibility.
    print(f"🚀 START ANALYSIS (Multi-Scenario Strategy - Silent Mode)")
    results = []
    
    target = settings.target_mw
    tol = settings.tolerance_mw
    
    # Dictionary to track the champion for each scenario group.
    # Key: (StudyID, Config) -> Value: {filename, delta, valid, reason}
    champions = {}
    
    file_count = 0

    for filename, content in files_content.items():
        clean_name = os.path.basename(filename)
        ext = clean_name.lower()
        
        # Filter temp files
        # [decision:logic] Only .lf1s and .mdb are officially targeted for Loadflow. .si2s are excluded.
        if clean_name.startswith('~$') or not (ext.endswith('.lf1s') or ext.endswith('.mdb')):
            continue
            
        file_count += 1

        res = {
            "filename": filename,
            "is_valid": False,
            "study_case": {"id": None, "config": None, "revision": None},
            "swing_bus_found": { "config": settings.swing_bus_id, "script": None },
            "mw_flow": None,
            "mvar_flow": None,
            "transformers": {},
            "delta_target": None,
            "status_color": "red",
            "is_winner": False,
            "victory_reason": None
        }

        # --- 1. DATA EXTRACTION ---
        try:
            dfs = db_converter.extract_data_from_db(content)
        except: dfs = None
            
        if not dfs:
            results.append(res); continue
            
        res["is_valid"] = True
        
        # --- 2. EXTRACT STUDY CASE METADATA ---
        study_id = "Unknown"; study_cfg = "Unknown"; study_rev = "Unknown"
        if "ILFStudyCase" in dfs:
            val = dfs["ILFStudyCase"]
            df_study = pd.DataFrame(val) if isinstance(val, list) else val
            if df_study is not None and not df_study.empty:
                df_study.columns = [str(c).strip() for c in df_study.columns]
                if "ID" in df_study.columns: study_id = str(df_study.iloc[0]["ID"])
                if "Config" in df_study.columns: study_cfg = str(df_study.iloc[0]["Config"])
                if "Revision" in df_study.columns: study_rev = str(df_study.iloc[0]["Revision"])
        res["study_case"] = {"id": study_id, "config": study_cfg, "revision": study_rev}

        # --- 3. PREPARE DATAFRAMES ---
        df_lfr = None; df_tx = None
        for k in dfs.keys():
            key_upper = k.upper()
            if key_upper in ['LFR', 'BUSLOADSUMMARY']:
                val = dfs[k]; df_lfr = pd.DataFrame(val) if isinstance(val, list) else val
            elif 'IXFMR2' in key_upper:
                val = dfs[k]; df_tx = pd.DataFrame(val) if isinstance(val, list) else val

        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # --- 4. SWING BUS FLOW ---
        target_bus_id = settings.swing_bus_id
        if df_lfr is not None:
            col_id_any = next((c for c in df_lfr.columns if c.upper() in ['ID', 'BUSID', 'IDFROM']), None)
            if not target_bus_id and col_id_any:
                col_type = next((c for c in df_lfr.columns if 'TYPE' in c.upper()), None)
                if col_type:
                    swing_rows = df_lfr[df_lfr[col_type].astype(str).str.upper().str.contains('SWNG|SWING')]
                    if not swing_rows.empty: target_bus_id = str(swing_rows.iloc[0][col_id_any])
            res["swing_bus_found"]["script"] = target_bus_id

            if target_bus_id:
                col_mw = next((c for c in df_lfr.columns if c.upper() in ['LFMW', 'MW', 'MWLOADING', 'P (MW)']), None)
                col_mvar = next((c for c in df_lfr.columns if c.upper() in ['LFMVAR', 'MVAR']), None)
                cols_search = [c for c in df_lfr.columns if c.upper() in ['ID', 'IDFROM', 'IDTO']]
                mask = pd.Series(False, index=df_lfr.index)
                for c in cols_search: mask |= (df_lfr[c] == target_bus_id)
                rows = df_lfr[mask]
                if not rows.empty:
                    row = rows.iloc[0]
                    if col_mw:
                        try: res["mw_flow"] = float(str(row[col_mw]).replace(',', '.'))
                        except: pass
                    if col_mvar:
                        try: res["mvar_flow"] = float(str(row[col_mvar]).replace(',', '.'))
                        except: pass

        # --- 5. TRANSFORMERS ---
        if df_tx is not None and df_lfr is not None:
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID']), None)
            col_from = next((c for c in df_tx.columns if c.upper() in ['FROMBUS', 'FROMID', 'FROMTO']), None)
            col_to = next((c for c in df_tx.columns if c.upper() in ['TOBUS', 'TOID', 'IDTO']), None)
            col_lfr_from = next((c for c in df_lfr.columns if c.upper() == 'IDFROM'), None)
            col_lfr_to = next((c for c in df_lfr.columns if c.upper() == 'IDTO'), None)
            col_tap = next((c for c in df_lfr.columns if c.upper() == 'TAP'), None)
            col_mw_val = next((c for c in df_lfr.columns if c.upper() == 'LFMW'), None)
            col_mvar_val = next((c for c in df_lfr.columns if c.upper() == 'LFMVAR'), None)
            col_amp = next((c for c in df_lfr.columns if c.upper() == 'LFAMP'), None)
            col_kv = next((c for c in df_lfr.columns if c.upper() == 'KV'), None)
            col_volt = next((c for c in df_lfr.columns if c.upper() == 'VOLTMAG'), None)
            col_pf = next((c for c in df_lfr.columns if c.upper() == 'LFPF'), None)

            if col_id_tx and col_from and col_to and col_lfr_from and col_lfr_to:
                for idx, row_tx in df_tx.iterrows():
                    tx_id = str(row_tx[col_id_tx])
                    bus_from = str(row_tx[col_from])
                    bus_to = str(row_tx[col_to])
                    mask_normal = (df_lfr[col_lfr_from] == bus_from) & (df_lfr[col_lfr_to] == bus_to)
                    mask_reverse = (df_lfr[col_lfr_from] == bus_to) & (df_lfr[col_lfr_to] == bus_from)
                    matches = df_lfr[mask_normal | mask_reverse]
                    if not matches.empty:
                        selected_row = matches.iloc[0]
                        if col_tap:
                            for _, r in matches.iterrows():
                                try:
                                    if float(str(r[col_tap]).replace(',', '.')) != 0:
                                        selected_row = r; break
                                except: pass
                        data = TransformerData()
                        try:
                            if col_tap: data.tap = float(str(selected_row[col_tap]).replace(',', '.'))
                            if col_mw_val: data.mw = float(str(selected_row[col_mw_val]).replace(',', '.'))
                            if col_mvar_val: data.mvar = float(str(selected_row[col_mvar_val]).replace(',', '.'))
                            if col_amp: data.amp = float(str(selected_row[col_amp]).replace(',', '.'))
                            if col_kv: data.kv = float(str(selected_row[col_kv]).replace(',', '.'))
                            if col_volt: data.volt_mag = float(str(selected_row[col_volt]).replace(',', '.'))
                            if col_pf: data.pf = float(str(selected_row[col_pf]).replace(',', '.'))
                        except: pass
                        
                        # [!] [CRITICAL] Convert to dict using ALIASES (Tap, LFMW...) to ensure correct JSON keys
                        res["transformers"][tx_id] = data.dict(by_alias=True)

        # --- 6. BATTLE LOGIC ---
        if res["mw_flow"] is not None:
            delta = abs(res["mw_flow"] - target)
            res["delta_target"] = round(delta, 3)
            candidate_is_valid = delta <= tol
            
            if candidate_is_valid: res["status_color"] = "green"
            elif delta <= (tol * 2): res["status_color"] = "orange"
            else: res["status_color"] = "red"
            
            group_key = (study_id, study_cfg)
            current_champ = champions.get(group_key)
            is_new_king = False; reason = ""
            
            if current_champ is None:
                is_new_king = True; reason = "First candidate"
            else:
                champ_valid = current_champ["valid"]
                champ_delta = current_champ["delta"]
                if candidate_is_valid and not champ_valid:
                    is_new_king = True; reason = "Validity (Green beats Red)"
                elif candidate_is_valid and champ_valid:
                    if delta < champ_delta:
                        is_new_king = True; reason = f"Precision ({delta} < {champ_delta})"
                elif not candidate_is_valid and not champ_valid:
                    if delta < champ_delta:
                        is_new_king = True; reason = f"Proximity ({delta} < {champ_delta})"

            if is_new_king:
                champions[group_key] = {
                    "filename": filename,
                    "delta": delta,
                    "valid": candidate_is_valid,
                    "reason": reason
                }

        results.append(res)

    # --- 7. FINALIZE ---
    win_count = 0
    for r in results:
        s_id = r["study_case"]["id"]
        s_cfg = r["study_case"]["config"]
        group_key = (s_id, s_cfg)
        champ = champions.get(group_key)
        if champ and champ["filename"] == r["filename"]:
            r["is_winner"] = True
            r["victory_reason"] = champ["reason"]
            win_count += 1
    
    print(f"✅ ANALYSIS COMPLETE. {file_count} files processed. {win_count} winners identified.")

    if only_winners:
        results = [r for r in results if r.get("is_winner") is True]

    return {
        "status": "success",
        "best_file": None,
        "results": results
    }
