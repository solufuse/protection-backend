import pandas as pd
import math
from app.calculations import si2s_converter

def analyze_loadflow(files_content: dict, settings) -> dict:
    results = []
    
    target = settings.target_mw
    tol = settings.tolerance_mw
    
    best_file = None
    min_delta = float('inf')

    # 1. On parcourt chaque fichier en mémoire
    for filename, content in files_content.items():
        # On ne traite que les fichiers DB (LF1S / SI2S / MDB)
        ext = filename.lower()
        if not (ext.endswith('.lf1s') or ext.endswith('.si2s') or ext.endswith('.mdb')):
            continue

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

        # 2. Extraction des DataFrames (lecture directe du SQLite)
        try:
            dfs = si2s_converter.extract_data_from_si2s(content)
        except:
            dfs = None
            
        if not dfs:
            results.append(res)
            continue
            
        res["is_valid"] = True
        
        # --- A. TROUVER LE BUS CIBLE (MW) ---
        target_bus_id = settings.swing_bus_id
        df_lfr = None
        
        # Recherche intelligente de la table de résultats
        possible_tables = ['BusLoadSummary', 'LFR', 'Bus Results', 'SUMMARY']
        for t in possible_tables:
            # Recherche insensible à la casse
            found_key = next((k for k in dfs.keys() if k.upper() == t.upper()), None)
            if found_key:
                df_lfr = dfs[found_key]
                break
        
        if df_lfr is not None:
            # Nettoyage des noms de colonnes (strip et upper) pour faciliter la recherche
            df_lfr.columns = [str(c).strip() for c in df_lfr.columns]

            # 1. Auto-détection du Swing si nécessaire
            col_id = next((c for c in df_lfr.columns if c.upper() in ['ID', 'BUSID', 'BUS ID']), None)
            
            if not target_bus_id and col_id:
                col_type = next((c for c in df_lfr.columns if 'TYPE' in c.upper()), None)
                if col_type:
                    # On cherche la ligne SWNG
                    swing_row = df_lfr[df_lfr[col_type].astype(str).str.upper().str.contains('SWNG|SWING')]
                    if not swing_row.empty:
                        target_bus_id = swing_row.iloc[0][col_id]
                        res["swing_bus_found"] = target_bus_id
            
            # 2. Lecture des MW
            if target_bus_id and col_id:
                # Colonnes possibles pour les MW
                col_mw = next((c for c in df_lfr.columns if c.upper() in ['LFMW', 'MW', 'MWLOADING', 'MW LOADING', 'P (MW)']), None)
                col_mvar = next((c for c in df_lfr.columns if c.upper() in ['LFMVAR', 'MVAR', 'MVARLOADING', 'Q (MVAR)']), None)
                
                if col_mw:
                    row = df_lfr[df_lfr[col_id] == target_bus_id]
                    if not row.empty:
                        try:
                            val_str = str(row.iloc[0][col_mw]).replace(',', '.')
                            res["mw_flow"] = float(val_str)
                            
                            if col_mvar:
                                val_mvar_str = str(row.iloc[0][col_mvar]).replace(',', '.')
                                res["mvar_flow"] = float(val_mvar_str)
                        except:
                            pass

        # --- B. TROUVER LES TAPS (IXFMR2) ---
        # Table souvent appelée IXFMR2 ou 2-Winding Transformer Results
        df_tx = None
        for k in dfs.keys():
            if 'IXFMR2' in k.upper() or 'TRANSFORMER' in k.upper():
                df_tx = dfs[k]
                break
                
        if df_tx is not None and settings.tap_transformers_ids:
            df_tx.columns = [str(c).strip() for c in df_tx.columns]
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID']), None)
            # Colonne Tap: LTCTapPosition, Tap, %Tap...
            col_tap = next((c for c in df_tx.columns if 'TAP' in c.upper()), None)
            
            if col_id_tx and col_tap:
                for tx_id in settings.tap_transformers_ids:
                    row = df_tx[df_tx[col_id_tx] == tx_id]
                    if not row.empty:
                        try:
                            val_tap = float(str(row.iloc[0][col_tap]).replace(',', '.'))
                            res["taps"][tx_id] = val_tap
                        except:
                            res["taps"][tx_id] = None

        # --- C. ANALYSE DU VAINQUEUR ---
        if res["mw_flow"] is not None:
            delta = abs(res["mw_flow"] - target)
            res["delta_target"] = round(delta, 3)
            
            # Couleur
            if delta <= tol:
                res["status_color"] = "green"
            elif delta <= (tol * 2):
                res["status_color"] = "orange"
            else:
                res["status_color"] = "red"
                
            # Logique de victoire
            current_is_valid = delta <= tol
            
            if best_file is None:
                best_file = filename
                min_delta = delta
            else:
                # Si le nouveau est valide et le champion actuel ne l'est pas
                if current_is_valid and min_delta > tol:
                    min_delta = delta
                    best_file = filename
                # Si même statut, on prend le plus proche
                elif (current_is_valid and min_delta <= tol) or (not current_is_valid and min_delta > tol):
                    if delta < min_delta:
                        min_delta = delta
                        best_file = filename

        results.append(res)

    # Marquage du vainqueur
    if best_file:
        for r in results:
            if r["filename"] == best_file:
                r["is_winner"] = True

    return {
        "status": "success",
        "best_file": best_file,
        "results": results
    }
