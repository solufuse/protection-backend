import pandas as pd
import math
from app.calculations import si2s_converter
from app.schemas.loadflow_schema import TransformerData

def analyze_loadflow(files_content: dict, settings) -> dict:
    print("🚀 DÉBUT ANALYSE LOADFLOW (TOPOLOGY MODE)")
    results = []
    
    target = settings.target_mw
    tol = settings.tolerance_mw
    best_file = None
    min_delta = float('inf')

    for filename, content in files_content.items():
        ext = filename.lower()
        if not (ext.endswith('.lf1s') or ext.endswith('.si2s') or ext.endswith('.mdb') or ext.endswith('.json')):
            continue

        print(f"\n📂 Analyse fichier : {filename}")

        res = {
            "filename": filename,
            "is_valid": False,
            "swing_bus_found": None,
            "mw_flow": None,
            "transformers": {},
            "delta_target": None,
            "status_color": "red",
            "is_winner": False
        }

        try:
            # 1. Extraction et Aplatissement (Gestion du wrapper 'data')
            dfs = si2s_converter.extract_data_from_si2s(content)
            if dfs and "data" in dfs and isinstance(dfs["data"], dict):
                dfs = dfs["data"]
        except Exception as e:
            print(f"❌ Erreur lecture : {e}")
            dfs = None
            
        if not dfs:
            results.append(res)
            continue
            
        res["is_valid"] = True
        
        # --- 2. RECUPERATION DES TABLES (Case Insensitive) ---
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

        # Nettoyage des noms de colonnes (strip espaces)
        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # --- 3. ANALYSE DU SWING BUS (MW CIBLE) ---
        target_bus_id = settings.swing_bus_id
        if df_lfr is not None:
            # Identification des colonnes clés
            col_id_any = next((c for c in df_lfr.columns if c.upper() in ['ID', 'BUSID', 'IDFROM']), None)
            col_mw = next((c for c in df_lfr.columns if c.upper() in ['LFMW', 'MW', 'MWLOADING', 'P (MW)']), None)
            
            # Auto-detection Swing si non fourni
            if not target_bus_id and col_id_any:
                col_type = next((c for c in df_lfr.columns if 'TYPE' in c.upper()), None)
                if col_type:
                    swing_rows = df_lfr[df_lfr[col_type].astype(str).str.upper().str.contains('SWNG|SWING')]
                    if not swing_rows.empty:
                        target_bus_id = swing_rows.iloc[0][col_id_any]
                        res["swing_bus_found"] = target_bus_id

            # Lecture de la valeur MW
            if target_bus_id and col_mw:
                # On cherche le bus dans IDFrom, IDTo ou ID
                cols_search = [c for c in df_lfr.columns if c.upper() in ['ID', 'IDFROM', 'IDTO']]
                mask = pd.Series(False, index=df_lfr.index)
                for c in cols_search: mask |= (df_lfr[c] == target_bus_id)
                
                rows = df_lfr[mask]
                if not rows.empty:
                    try: res["mw_flow"] = float(str(rows.iloc[0][col_mw]).replace(',', '.'))
                    except: pass

        # --- 4. SCAN DES TRANSFOS (TOPOLOGIE) ---
        if df_tx is not None and df_lfr is not None:
            
            # Colonnes IXFMR2
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID']), None)
            col_from = next((c for c in df_tx.columns if c.upper() in ['FROMBUS', 'FROMID', 'FROMTO']), None)
            col_to = next((c for c in df_tx.columns if c.upper() in ['TOBUS', 'TOID', 'IDTO']), None)
            
            # Colonnes LFR (Resultats)
            col_lfr_from = next((c for c in df_lfr.columns if c.upper() == 'IDFROM'), None)
            col_lfr_to = next((c for c in df_lfr.columns if c.upper() == 'IDTO'), None)
            
            # Colonnes de Valeurs LFR
            col_tap = next((c for c in df_lfr.columns if c.upper() == 'TAP'), None)
            col_mw_val = next((c for c in df_lfr.columns if c.upper() == 'LFMW'), None)
            col_mvar = next((c for c in df_lfr.columns if c.upper() == 'LFMVAR'), None)
            col_amp = next((c for c in df_lfr.columns if c.upper() == 'LFAMP'), None)
            col_kv = next((c for c in df_lfr.columns if c.upper() == 'KV'), None)
            col_volt = next((c for c in df_lfr.columns if c.upper() == 'VOLTMAG'), None)
            col_pf = next((c for c in df_lfr.columns if c.upper() == 'LFPF'), None)

            if col_id_tx and col_from and col_to and col_lfr_from and col_lfr_to:
                
                # Pour chaque transfo défini dans le projet
                for idx, row_tx in df_tx.iterrows():
                    tx_id = str(row_tx[col_id_tx])
                    bus_from = str(row_tx[col_from])
                    bus_to = str(row_tx[col_to])
                    
                    # On cherche la ligne correspondante dans LFR
                    # Une branche est définie par ses deux extrémités
                    mask_normal = (df_lfr[col_lfr_from] == bus_from) & (df_lfr[col_lfr_to] == bus_to)
                    mask_reverse = (df_lfr[col_lfr_from] == bus_to) & (df_lfr[col_lfr_to] == bus_from)
                    
                    matches = df_lfr[mask_normal | mask_reverse]
                    
                    if not matches.empty:
                        # LOGIQUE DE SELECTION DE LA LIGNE
                        # S'il y a plusieurs lignes (ex: aller/retour), on prend celle où Tap != 0
                        selected_row = matches.iloc[0]
                        if col_tap:
                            for _, r in matches.iterrows():
                                try:
                                    if float(str(r[col_tap]).replace(',', '.')) != 0:
                                        selected_row = r
                                        break
                                except: pass
                        
                        # Extraction des données
                        data = TransformerData()
                        try:
                            if col_tap: data.tap = float(str(selected_row[col_tap]).replace(',', '.'))
                            if col_mw_val: data.mw = float(str(selected_row[col_mw_val]).replace(',', '.'))
                            if col_mvar: data.mvar = float(str(selected_row[col_mvar]).replace(',', '.'))
                            if col_amp: data.amp = float(str(selected_row[col_amp]).replace(',', '.'))
                            if col_kv: data.kv = float(str(selected_row[col_kv]).replace(',', '.'))
                            if col_volt: data.volt_mag = float(str(selected_row[col_volt]).replace(',', '.'))
                            if col_pf: data.pf = float(str(selected_row[col_pf]).replace(',', '.'))
                        except: pass
                        
                        # On ajoute ce transfo au résultat
                        res["transformers"][tx_id] = data

        # --- 5. CALCUL DU VAINQUEUR ---
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
