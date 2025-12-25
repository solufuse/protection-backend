import pandas as pd
import math
import os
from app.calculations import si2s_converter
from app.schemas.loadflow_schema import TransformerData, SwingBusInfo

def analyze_loadflow(files_content: dict, settings, only_winners: bool = False) -> dict:
    print(f"🚀 DÉBUT ANALYSE (AVEC RAISON VICTOIRE)")
    results = []
    
    target = settings.target_mw
    tol = settings.tolerance_mw
    
    # --- CHAMPION ACTUEL ---
    champion_file = None
    champion_delta = float('inf')
    champion_is_valid = False
    champion_reason = None # On stocke la raison ici

    # --- 1. TRAITEMENT ---
    for filename, content in files_content.items():
        # Nettoyage nom de fichier
        clean_name = os.path.basename(filename)
        ext = clean_name.lower()
        
        # FILTRE : Ignore les fichiers temporaires (~$) et les extensions non supportées
        if clean_name.startswith('~$') or not (ext.endswith('.lf1s') or ext.endswith('.si2s') or ext.endswith('.mdb') or ext.endswith('.json')):
            continue

        res = {
            "filename": filename,
            "is_valid": False,
            "swing_bus_found": { "config": settings.swing_bus_id, "script": None },
            "mw_flow": None,
            "mvar_flow": None,
            "transformers": {},
            "delta_target": None,
            "status_color": "red",
            "is_winner": False,
            "victory_reason": None
        }

        # 1. Extraction (Protection Try/Except renforcée)
        try:
            dfs = si2s_converter.extract_data_from_si2s(content)
            if dfs and "data" in dfs and isinstance(dfs["data"], dict): dfs = dfs["data"]
        except Exception as e:
            # On ignore silencieusement les erreurs de lecture pour ne pas polluer
            dfs = None
            
        if not dfs:
            results.append(res); continue
            
        res["is_valid"] = True
        
        # 2. Tables
        df_lfr = None; df_tx = None
        for k in dfs.keys():
            key_upper = k.upper()
            if key_upper in ['LFR', 'BUSLOADSUMMARY']:
                val = dfs[k]; df_lfr = pd.DataFrame(val) if isinstance(val, list) else val
            elif 'IXFMR2' in key_upper:
                val = dfs[k]; df_tx = pd.DataFrame(val) if isinstance(val, list) else val

        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # 3. MW Flow
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

        # 4. Transfos
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
                                        selected_row = r
                                        break
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
                        res["transformers"][tx_id] = data

        # --- 5. LOGIQUE BATTLE ---
        if res["mw_flow"] is not None:
            delta = abs(res["mw_flow"] - target)
            res["delta_target"] = round(delta, 3)
            candidate_is_valid = delta <= tol
            
            if candidate_is_valid: res["status_color"] = "green"
            elif delta <= (tol * 2): res["status_color"] = "orange"
            else: res["status_color"] = "red"
            
            is_new_king = False
            reason = ""
            
            if champion_file is None:
                is_new_king = True; reason = "Premier candidat"
            else:
                if candidate_is_valid and not champion_is_valid:
                    is_new_king = True; reason = "Validité (Vert bat Rouge)"
                elif candidate_is_valid and champion_is_valid:
                    if delta < champion_delta:
                        is_new_king = True; reason = f"Précision ({delta} < {champion_delta})"
                elif not candidate_is_valid and not champion_is_valid:
                    if delta < champion_delta:
                        is_new_king = True; reason = f"Proximité ({delta} < {champion_delta})"

            if is_new_king:
                print(f"   👑 NOUVEAU ROI : {filename} | {reason}")
                champion_file = filename
                champion_delta = delta
                champion_is_valid = candidate_is_valid
                champion_reason = reason # On mémorise la raison

        results.append(res)

    # --- FINALISATION ---
    final_best_result = None
    if champion_file:
        for r in results:
            if r["filename"] == champion_file:
                r["is_winner"] = True
                r["victory_reason"] = champion_reason # On l'injecte dans le résultat final
                final_best_result = r
                break
    
    if only_winners:
        results = [r for r in results if r.get("is_winner") is True]

    return {
        "status": "success",
        "best_file": champion_file,
        "best_result": final_best_result,
        "results": results
    }
