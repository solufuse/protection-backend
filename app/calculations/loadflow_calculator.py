import pandas as pd
import math
from app.calculations import si2s_converter
from app.schemas.loadflow_schema import TransformerData

def analyze_loadflow(files_content: dict, settings) -> dict:
    print("🚀 DÉBUT ANALYSE LOADFLOW (FULL DATA EXTRACTION)")
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
            "transformers": {},  # On stocke ici les objets complets
            "delta_target": None,
            "status_color": "red",
            "is_winner": False
        }

        try:
            dfs = si2s_converter.extract_data_from_si2s(content)
            # Gestion wrapper "data"
            if dfs and "data" in dfs and isinstance(dfs["data"], dict):
                dfs = dfs["data"]
        except Exception as e:
            print(f"❌ Erreur lecture : {e}")
            dfs = None
            
        if not dfs:
            results.append(res)
            continue
            
        res["is_valid"] = True
        
        # --- PREPA TABLES ---
        df_lfr = None
        for k in dfs.keys():
            if k.upper() in ['LFR', 'BUSLOADSUMMARY', 'SUMMARY']:
                if isinstance(dfs[k], list): df_lfr = pd.DataFrame(dfs[k])
                else: df_lfr = dfs[k]
                break
        
        df_tx = None
        for k in dfs.keys():
            if 'IXFMR2' in k.upper():
                if isinstance(dfs[k], list): df_tx = pd.DataFrame(dfs[k])
                else: df_tx = dfs[k]
                break
        
        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # --- LECTURE SWING MW ---
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
                    for c in cols_id_search: mask |= (df_lfr[c] == target_bus_id)
                    rows = df_lfr[mask]
                    if not rows.empty:
                        try: res["mw_flow"] = float(str(rows.iloc[0][col_mw]).replace(',', '.'))
                        except: pass

        # --- EXTRACTION COMPLETE TRANSFOS ---
        if df_tx is not None and df_lfr is not None:
            
            # Mapping colonnes IXFMR2
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID']), None)
            col_from_bus_tx = next((c for c in df_tx.columns if c.upper() in ['FROMBUS', 'FROMID', 'FROMTO', 'IDFROM']), None)
            col_to_bus_tx = next((c for c in df_tx.columns if c.upper() in ['TOBUS', 'TOID', 'IDTO']), None)
            
            # Mapping colonnes LFR (pour identification)
            col_id_from_lfr = next((c for c in df_lfr.columns if c.upper() == 'IDFROM'), None)
            col_id_to_lfr = next((c for c in df_lfr.columns if c.upper() == 'IDTO'), None)
            
            # Mapping colonnes de VALEURS (LFR)
            col_tap = next((c for c in df_lfr.columns if c.upper() == 'TAP'), None)
            col_mw  = next((c for c in df_lfr.columns if c.upper() == 'LFMW'), None)
            col_mvar= next((c for c in df_lfr.columns if c.upper() == 'LFMVAR'), None)
            col_amp = next((c for c in df_lfr.columns if c.upper() == 'LFAMP'), None)
            col_kv  = next((c for c in df_lfr.columns if c.upper() == 'KV'), None)
            col_vmag= next((c for c in df_lfr.columns if c.upper() == 'VOLTMAG'), None)
            col_pf  = next((c for c in df_lfr.columns if c.upper() == 'LFPF'), None)

            if col_id_tx and col_from_bus_tx and col_to_bus_tx and col_id_from_lfr and col_id_to_lfr:
                
                for index, row_tx in df_tx.iterrows():
                    tx_id = str(row_tx[col_id_tx])
                    bus_from = str(row_tx[col_from_bus_tx])
                    bus_to = str(row_tx[col_to_bus_tx])
                    
                    # Double Match
                    mask_normal = (df_lfr[col_id_from_lfr] == bus_from) & (df_lfr[col_id_to_lfr] == bus_to)
                    mask_reverse = (df_lfr[col_id_from_lfr] == bus_to) & (df_lfr[col_id_to_lfr] == bus_from)
                    
                    target_rows = df_lfr[mask_normal | mask_reverse]
                    
                    if not target_rows.empty:
                        # Priorité Tap != 0 pour choisir la ligne
                        final_row = target_rows.iloc[0]
                        if col_tap:
                            for _, r in target_rows.iterrows():
                                try:
                                    if float(str(r[col_tap]).replace(',', '.')) != 0:
                                        final_row = r
                                        break
                                except: pass
                        
                        # Extraction des valeurs
                        data = TransformerData()
                        try:
                            if col_tap: data.tap = float(str(final_row[col_tap]).replace(',', '.'))
                            if col_mw:  data.mw  = float(str(final_row[col_mw]).replace(',', '.'))
                            if col_mvar:data.mvar= float(str(final_row[col_mvar]).replace(',', '.'))
                            if col_amp: data.amp = float(str(final_row[col_amp]).replace(',', '.'))
                            if col_kv:  data.kv  = float(str(final_row[col_kv]).replace(',', '.'))
                            if col_vmag:data.volt_mag = float(str(final_row[col_vmag]).replace(',', '.'))
                            if col_pf:  data.pf  = float(str(final_row[col_pf]).replace(',', '.'))
                        except: pass
                        
                        res["transformers"][tx_id] = data
            else:
                print("❌ Colonnes IDFrom/IDTo manquantes dans LFR.")

        # --- ANALYSE ---
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
