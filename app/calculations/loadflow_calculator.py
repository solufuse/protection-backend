import pandas as pd
import math
from app.calculations import si2s_converter

def analyze_loadflow(files_content: dict, settings) -> dict:
    print("🚀 DÉBUT ANALYSE LOADFLOW (AUTO-SCAN TOUS TRANSFOS)")
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
        
        # --- 1. RECUPERATION TABLES ---
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
        
        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # --- 2. LECTURE CIBLE MW (Inchangé) ---
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

        # --- 3. AUTO-SCAN DE TOUS LES TRANSFOS ---
        if df_tx is not None and df_lfr is not None:
            
            # Identifions les colonnes une fois pour toutes
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID']), None)
            col_from_bus_tx = next((c for c in df_tx.columns if c.upper() in ['FROMBUS', 'FROMID', 'FROMTO', 'IDFROM']), None)
            col_to_bus_tx = next((c for c in df_tx.columns if c.upper() in ['TOBUS', 'TOID', 'IDTO']), None)
            
            col_id_from_lfr = next((c for c in df_lfr.columns if c.upper() == 'IDFROM'), None)
            col_id_to_lfr = next((c for c in df_lfr.columns if c.upper() == 'IDTO'), None)
            col_tap_lfr = next((c for c in df_lfr.columns if c.upper() == 'TAP'), None)

            if col_id_tx and col_from_bus_tx and col_to_bus_tx and col_id_from_lfr and col_id_to_lfr and col_tap_lfr:
                
                # ON BOUCLE SUR CHAQUE LIGNE DE LA TABLE TRANSFO
                for index, row_tx in df_tx.iterrows():
                    
                    # 1. Extraction ID et Bus
                    tx_id = str(row_tx[col_id_tx])
                    bus_from = str(row_tx[col_from_bus_tx])
                    bus_to = str(row_tx[col_to_bus_tx])
                    
                    # 2. Recherche dans LFR (Double Match)
                    mask_normal = (df_lfr[col_id_from_lfr] == bus_from) & (df_lfr[col_id_to_lfr] == bus_to)
                    mask_reverse = (df_lfr[col_id_from_lfr] == bus_to) & (df_lfr[col_id_to_lfr] == bus_from)
                    
                    target_rows = df_lfr[mask_normal | mask_reverse]
                    
                    if not target_rows.empty:
                        found_val = None
                        # Priorité aux Taps non nuls
                        for idx_lfr, r_lfr in target_rows.iterrows():
                            try:
                                val = float(str(r_lfr[col_tap_lfr]).replace(',', '.'))
                                if val != 0:
                                    found_val = val
                                    break
                            except: pass
                        
                        # Sinon 0
                        if found_val is None:
                            try: found_val = float(str(target_rows.iloc[0][col_tap_lfr]).replace(',', '.'))
                            except: found_val = 0
                            
                        # Sauvegarde
                        res["taps"][tx_id] = found_val
                        # print(f"   🔹 Trouvé : {tx_id} -> Tap {found_val}")
                    else:
                        # Cas rare : Transfo existe mais pas dans le Loadflow (déconnecté ?)
                        res["taps"][tx_id] = None
            else:
                print("❌ Colonnes manquantes pour le scan automatique.")

        # --- 4. ANALYSE (Couleur / Winner) ---
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
