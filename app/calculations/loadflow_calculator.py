import pandas as pd
import math
from app.calculations import si2s_converter

def analyze_loadflow(files_content: dict, settings) -> dict:
    print("🚀 DÉBUT ANALYSE LOADFLOW (MODE STRICT IDFROM)")
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
        
        # --- 1. IDENTIFICATION DES TABLES ---
        df_lfr = None
        for k in dfs.keys():
            if k.upper() in ['LFR', 'BUSLOADSUMMARY', 'SUMMARY']:
                df_lfr = dfs[k]
                break
        
        df_tx = None
        for k in dfs.keys():
            if 'IXFMR2' in k.upper():
                df_tx = dfs[k]
                break
        
        # Nettoyage noms de colonnes
        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # --- 2. LECTURE DES MW (CIBLE) ---
        target_bus_id = settings.swing_bus_id
        if df_lfr is not None:
            # Pour le Swing, on cherche n'importe quelle colonne ID
            col_id_any = next((c for c in df_lfr.columns if c.upper() in ['ID', 'BUSID', 'IDFROM', 'IDTO']), None)
            
            if not target_bus_id and col_id_any:
                col_type = next((c for c in df_lfr.columns if 'TYPE' in c.upper()), None)
                if col_type:
                    swing_row = df_lfr[df_lfr[col_type].astype(str).str.upper().str.contains('SWNG|SWING')]
                    if not swing_row.empty:
                        target_bus_id = swing_row.iloc[0][col_id_any]
                        res["swing_bus_found"] = target_bus_id

            if target_bus_id:
                cols_id = [c for c in df_lfr.columns if c.upper() in ['ID', 'IDFROM', 'IDTO']]
                col_mw = next((c for c in df_lfr.columns if c.upper() in ['LFMW', 'MW', 'MWLOADING', 'P (MW)']), None)
                
                if cols_id and col_mw:
                    mask = pd.Series(False, index=df_lfr.index)
                    for c in cols_id:
                        mask |= (df_lfr[c] == target_bus_id)
                    
                    rows = df_lfr[mask]
                    if not rows.empty:
                        try:
                            res["mw_flow"] = float(str(rows.iloc[0][col_mw]).replace(',', '.'))
                        except: pass

        # --- 3. LECTURE DES TAPS (STRICTEMENT VIA IDFROM) ---
        if df_tx is not None and df_lfr is not None and settings.tap_transformers_ids:
            
            # A. Colonnes IXFMR2
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID']), None)
            col_link_bus = next((c for c in df_tx.columns if c.upper() in ['TOBUS', 'FROMTO', 'IDTO', 'SECID']), None)
            
            # B. Colonnes LFR (STRICTEMENT IDFROM)
            col_id_from = next((c for c in df_lfr.columns if c.upper() == 'IDFROM'), None)
            col_tap_lfr = next((c for c in df_lfr.columns if c.upper() == 'TAP'), None)
            
            print(f"   ℹ️ Mapping : IXFMR2[{col_link_bus}] -> LFR[{col_id_from}] -> Tap[{col_tap_lfr}]")

            if col_id_tx and col_link_bus and col_id_from and col_tap_lfr:
                for tx_id in settings.tap_transformers_ids:
                    # 1. On récupère le nom du Bus dans IXFMR2
                    row_tx = df_tx[df_tx[col_id_tx] == tx_id]
                    
                    if not row_tx.empty:
                        linked_bus_name = str(row_tx.iloc[0][col_link_bus])
                        print(f"   -> Transfo {tx_id} lié au Bus '{linked_bus_name}'")
                        
                        # 2. On cherche ce bus UNIQUEMENT dans IDFrom de LFR
                        target_row = df_lfr[df_lfr[col_id_from] == linked_bus_name]
                        
                        if not target_row.empty:
                            try:
                                raw_tap = target_row.iloc[0][col_tap_lfr]
                                val_tap = float(str(raw_tap).replace(',', '.'))
                                res["taps"][tx_id] = val_tap
                                print(f"      ✅ Tap trouvé (via IDFrom) : {val_tap}")
                            except Exception as e:
                                print(f"      ❌ Erreur valeur Tap : {e}")
                                res["taps"][tx_id] = None
                        else:
                            print(f"      ⚠️ Bus '{linked_bus_name}' introuvable dans la colonne IDFrom de LFR.")
                            res["taps"][tx_id] = None
                    else:
                        print(f"   ⚠️ Transfo {tx_id} inconnu dans IXFMR2.")
            else:
                print("❌ Colonnes manquantes (IDFrom ou Tap absents).")

        # --- 4. CALCUL DELTA ---
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
