import pandas as pd
import math
from app.calculations import si2s_converter

def analyze_loadflow(files_content: dict, settings) -> dict:
    print("🚀 DÉBUT ANALYSE LOADFLOW (MODE DEBUG LFR)")
    results = []
    
    target = settings.target_mw
    tol = settings.tolerance_mw
    best_file = None
    min_delta = float('inf')

    for filename, content in files_content.items():
        ext = filename.lower()
        if not (ext.endswith('.lf1s') or ext.endswith('.si2s') or ext.endswith('.mdb')):
            continue

        print(f"\n📂 Traitement fichier : {filename}")

        res = {
            "filename": filename,
            "is_valid": False,
            "swing_bus_found": None,
            "mw_flow": None,
            "mvar_flow": None,
            "taps": {},
            "delta_target": None,
            "status_color": "red",
            "is_winner": False
        }

        try:
            dfs = si2s_converter.extract_data_from_si2s(content)
        except Exception as e:
            print(f"❌ Erreur lecture SQLite : {e}")
            dfs = None
            
        if not dfs:
            results.append(res)
            continue
            
        res["is_valid"] = True
        
        # --- PREPARATION DES TABLES ---
        df_lfr = None
        for k in dfs.keys():
            if k.upper() in ['LFR', 'BUSLOADSUMMARY', 'BUS RESULTS', 'SUMMARY']:
                df_lfr = dfs[k]
                break
        
        df_tx = None
        for k in dfs.keys():
            if 'IXFMR2' in k.upper():
                df_tx = dfs[k]
                break
        
        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # --- A. LECTURE DES MW ---
        target_bus_id = settings.swing_bus_id
        if df_lfr is not None:
            col_id = next((c for c in df_lfr.columns if c.upper() in ['ID', 'BUSID', 'BUS ID', 'IDFROM']), None)
            
            if not target_bus_id and col_id:
                col_type = next((c for c in df_lfr.columns if 'TYPE' in c.upper()), None)
                if col_type:
                    swing_row = df_lfr[df_lfr[col_type].astype(str).str.upper().str.contains('SWNG|SWING')]
                    if not swing_row.empty:
                        target_bus_id = swing_row.iloc[0][col_id]
                        res["swing_bus_found"] = target_bus_id

            if target_bus_id and col_id:
                col_mw = next((c for c in df_lfr.columns if c.upper() in ['LFMW', 'MW', 'MWLOADING', 'P (MW)']), None)
                if col_mw:
                    row = df_lfr[df_lfr[col_id] == target_bus_id]
                    if not row.empty:
                        try:
                            res["mw_flow"] = float(str(row.iloc[0][col_mw]).replace(',', '.'))
                        except: pass

        # --- B. LECTURE DES TAPS (Jeu de piste) ---
        if df_tx is not None and df_lfr is not None and settings.tap_transformers_ids:
            
            # --- DEBUG CRUCIAL : AFFICHER LES COLONNES DE LFR ---
            print(f"📋 LISTE COLONNES TABLE LFR : {list(df_lfr.columns)}")
            
            # 1. Colonnes IXFMR2
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID']), None)
            col_link_bus = next((c for c in df_tx.columns if c.upper() in ['FROMTO', 'IDTO', 'TOBUS', 'SECID', 'SECONDARYBUSID']), None)
            
            # 2. Colonnes LFR (On élargit la recherche)
            col_id_lfr = next((c for c in df_lfr.columns if c.upper() in ['IDFROM', 'BUSID', 'ID']), None)
            
            # Recherche Tap élargie
            tap_candidates = ['TAP', 'TAPSETTING', 'CURRENTTAP', 'LTC', 'POSITION', 'STEP', 'FINAL_TAP', 'ADJTAP']
            col_tap_lfr = next((c for c in df_lfr.columns if c.upper() in tap_candidates), None)
            
            # Si pas trouvé, on cherche n'importe quoi qui contient "TAP"
            if not col_tap_lfr:
                 col_tap_lfr = next((c for c in df_lfr.columns if 'TAP' in c.upper()), None)

            print(f"   🔍 Colonnes LFR retenues : ID={col_id_lfr}, Tap={col_tap_lfr}")

            if col_id_tx and col_link_bus and col_id_lfr and col_tap_lfr:
                for tx_id in settings.tap_transformers_ids:
                    row_tx = df_tx[df_tx[col_id_tx] == tx_id]
                    if not row_tx.empty:
                        linked_bus_name = str(row_tx.iloc[0][col_link_bus])
                        row_lfr = df_lfr[df_lfr[col_id_lfr] == linked_bus_name]
                        if not row_lfr.empty:
                            try:
                                raw_tap = row_lfr.iloc[0][col_tap_lfr]
                                val_tap = float(str(raw_tap).replace(',', '.'))
                                res["taps"][tx_id] = val_tap
                                print(f"      ✅ OK: {tx_id} -> Bus {linked_bus_name} -> Tap {val_tap}")
                            except:
                                res["taps"][tx_id] = None
                        else:
                            print(f"      ⚠️ Bus {linked_bus_name} non trouvé dans LFR")
                            res["taps"][tx_id] = None
            else:
                print("❌ Manque colonne ID ou TAP dans LFR.")

        # --- C. ANALYSE ---
        if res["mw_flow"] is not None:
            delta = abs(res["mw_flow"] - target)
            res["delta_target"] = round(delta, 3)
            if delta <= tol: res["status_color"] = "green"
            elif delta <= (tol * 2): res["status_color"] = "orange"
            else: res["status_color"] = "red"
            current_is_valid = delta <= tol
            if best_file is None:
                best_file = filename
                min_delta = delta
            else:
                if current_is_valid and min_delta > tol:
                    min_delta = delta
                    best_file = filename
                elif (current_is_valid and min_delta <= tol) or (not current_is_valid and min_delta > tol):
                    if delta < min_delta:
                        min_delta = delta
                        best_file = filename

        results.append(res)

    if best_file:
        for r in results:
            if r["filename"] == best_file:
                r["is_winner"] = True

    return {
        "status": "success",
        "best_file": best_file,
        "results": results
    }
