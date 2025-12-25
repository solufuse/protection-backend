import pandas as pd
import math
from app.calculations import si2s_converter

def analyze_loadflow(files_content: dict, settings) -> dict:
    print("🚀 DÉBUT ANALYSE LOADFLOW (SMART STRUCTURE)")
    results = []
    
    target = settings.target_mw
    tol = settings.tolerance_mw
    best_file = None
    min_delta = float('inf')

    for filename, content in files_content.items():
        ext = filename.lower()
        if not (ext.endswith('.lf1s') or ext.endswith('.si2s') or ext.endswith('.mdb') or ext.endswith('.json')):
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
            # 1. Extraction des données brutes
            dfs = si2s_converter.extract_data_from_si2s(content)
            
            # 2. GESTION DU WRAPPER "DATA" (CORRECTION CRUCIALE)
            # Si le résultat contient une clé "data" qui contient les tables, on descend d'un niveau.
            if dfs and "data" in dfs and isinstance(dfs["data"], dict):
                print("   ℹ️ Structure imbriquée détectée (clé 'data'), on descend d'un niveau.")
                # On fusionne pour avoir accès direct aux tables
                dfs = dfs["data"]
            
        except Exception as e:
            print(f"❌ Erreur lecture données : {e}")
            dfs = None
            
        if not dfs:
            results.append(res)
            continue
            
        res["is_valid"] = True
        
        # --- 3. RECUPERATION DES TABLES ---
        df_lfr = None
        for k in dfs.keys():
            if k.upper() in ['LFR', 'BUSLOADSUMMARY', 'SUMMARY']:
                # Conversion en DataFrame si ce n'est pas déjà le cas (cas du JSON list)
                if isinstance(dfs[k], list):
                    df_lfr = pd.DataFrame(dfs[k])
                else:
                    df_lfr = dfs[k]
                break
        
        df_tx = None
        for k in dfs.keys():
            if 'IXFMR2' in k.upper():
                if isinstance(dfs[k], list):
                    df_tx = pd.DataFrame(dfs[k])
                else:
                    df_tx = dfs[k]
                break
        
        # Nettoyage des noms de colonnes
        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # Debug si tables manquantes
        if df_lfr is None: print(f"   ⚠️ Table LFR introuvable. Clés dispo: {list(dfs.keys())}")
        if df_tx is None: print(f"   ⚠️ Table IXFMR2 introuvable.")

        # --- 4. LECTURE CIBLE MW ---
        target_bus_id = settings.swing_bus_id
        if df_lfr is not None:
            col_id_any = next((c for c in df_lfr.columns if c.upper() in ['ID', 'BUSID', 'IDFROM', 'IDTO']), None)
            
            if not target_bus_id and col_id_any:
                col_type = next((c for c in df_lfr.columns if 'TYPE' in c.upper()), None)
                if col_type:
                    swing_row = df_lfr[df_lfr[col_type].astype(str).str.upper().str.contains('SWNG|SWING')]
                    if not swing_row.empty:
                        target_bus_id = swing_row.iloc[0][col_id_any]
                        res["swing_bus_found"] = target_bus_id

            if target_bus_id:
                col_mw = next((c for c in df_lfr.columns if c.upper() in ['LFMW', 'MW', 'MWLOADING', 'P (MW)']), None)
                cols_id_search = [c for c in df_lfr.columns if c.upper() in ['ID', 'IDFROM', 'IDTO']]
                if cols_id_search and col_mw:
                    mask = pd.Series(False, index=df_lfr.index)
                    for c in cols_id_search:
                        mask |= (df_lfr[c] == target_bus_id)
                    rows = df_lfr[mask]
                    if not rows.empty:
                        try: res["mw_flow"] = float(str(rows.iloc[0][col_mw]).replace(',', '.'))
                        except: pass

        # --- 5. AUTO-SCAN DES TRANSFOS ---
        if df_tx is not None and df_lfr is not None:
            
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID']), None)
            col_from_bus_tx = next((c for c in df_tx.columns if c.upper() in ['FROMBUS', 'FROMID', 'FROMTO', 'IDFROM']), None)
            col_to_bus_tx = next((c for c in df_tx.columns if c.upper() in ['TOBUS', 'TOID', 'IDTO']), None)
            
            col_id_from_lfr = next((c for c in df_lfr.columns if c.upper() == 'IDFROM'), None)
            col_id_to_lfr = next((c for c in df_lfr.columns if c.upper() == 'IDTO'), None)
            col_tap_lfr = next((c for c in df_lfr.columns if c.upper() == 'TAP'), None)

            # Debug des colonnes trouvées
            # print(f"   ℹ️ Colonnes: IXFMR2(ID={col_id_tx}, From={col_from_bus_tx}, To={col_to_bus_tx}) | LFR(From={col_id_from_lfr}, To={col_id_to_lfr}, Tap={col_tap_lfr})")

            if col_id_tx and col_from_bus_tx and col_to_bus_tx and col_id_from_lfr and col_id_to_lfr and col_tap_lfr:
                
                for index, row_tx in df_tx.iterrows():
                    tx_id = str(row_tx[col_id_tx])
                    bus_from = str(row_tx[col_from_bus_tx])
                    bus_to = str(row_tx[col_to_bus_tx])
                    
                    # Double Match dans LFR
                    mask_normal = (df_lfr[col_id_from_lfr] == bus_from) & (df_lfr[col_id_to_lfr] == bus_to)
                    mask_reverse = (df_lfr[col_id_from_lfr] == bus_to) & (df_lfr[col_id_to_lfr] == bus_from)
                    
                    target_rows = df_lfr[mask_normal | mask_reverse]
                    
                    if not target_rows.empty:
                        found_val = None
                        # Priorité Tap != 0
                        for idx_lfr, r_lfr in target_rows.iterrows():
                            try:
                                val = float(str(r_lfr[col_tap_lfr]).replace(',', '.'))
                                if val != 0:
                                    found_val = val
                                    break
                            except: pass
                        
                        if found_val is None:
                            try: found_val = float(str(target_rows.iloc[0][col_tap_lfr]).replace(',', '.'))
                            except: found_val = 0
                            
                        res["taps"][tx_id] = found_val
                        # print(f"      ✅ {tx_id}: Tap {found_val}")
                    else:
                        res["taps"][tx_id] = None
            else:
                print("❌ Colonnes manquantes dans IXFMR2 ou LFR.")
                if not col_tap_lfr and df_lfr is not None: print(f"   Colonnes LFR dispo: {list(df_lfr.columns)}")

        # --- 6. RESULTATS ---
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
