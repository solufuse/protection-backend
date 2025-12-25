import pandas as pd
import math
from app.calculations import si2s_converter

def analyze_loadflow(files_content: dict, settings) -> dict:
    print("🚀 DÉBUT ANALYSE LOADFLOW")
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
        
        # --- A. BUS CIBLE (MW) ---
        # (Code inchangé pour la partie MW, on se concentre sur les Taps)
        df_lfr = None
        possible_tables = ['BusLoadSummary', 'LFR', 'Bus Results', 'SUMMARY']
        for t in possible_tables:
            found_key = next((k for k in dfs.keys() if k.upper() == t.upper()), None)
            if found_key:
                df_lfr = dfs[found_key]
                break
        
        if df_lfr is not None:
            df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
            col_id = next((c for c in df_lfr.columns if c.upper() in ['ID', 'BUSID', 'BUS ID']), None)
            target_bus_id = settings.swing_bus_id
            
            if not target_bus_id and col_id:
                col_type = next((c for c in df_lfr.columns if 'TYPE' in c.upper()), None)
                if col_type:
                    swing_row = df_lfr[df_lfr[col_type].astype(str).str.upper().str.contains('SWNG|SWING')]
                    if not swing_row.empty:
                        target_bus_id = swing_row.iloc[0][col_id]
                        res["swing_bus_found"] = target_bus_id
            
            if target_bus_id and col_id:
                col_mw = next((c for c in df_lfr.columns if c.upper() in ['LFMW', 'MW', 'MWLOADING', 'MW LOADING', 'P (MW)']), None)
                if col_mw:
                    row = df_lfr[df_lfr[col_id] == target_bus_id]
                    if not row.empty:
                        try:
                            val_str = str(row.iloc[0][col_mw]).replace(',', '.')
                            res["mw_flow"] = float(val_str)
                        except: pass

        # --- B. LE CŒUR DU PROBLÈME : LES TAPS ---
        df_tx = None
        # Recherche de la table IXFMR2
        for k in dfs.keys():
            if 'IXFMR2' in k.upper():
                df_tx = dfs[k]
                print(f"✅ Table IXFMR2 trouvée sous le nom : {k}")
                break
        
        # Fallback si pas de IXFMR2 explicite
        if df_tx is None:
             for k in dfs.keys():
                if 'TRANSFORMER' in k.upper() and 'RESULT' in k.upper():
                    df_tx = dfs[k]
                    print(f"⚠️ IXFMR2 introuvable, utilisation de : {k}")
                    break

        if df_tx is not None and settings.tap_transformers_ids:
            # DEBUG : AFFICHER LES COLONNES
            print(f"📋 Colonnes disponibles dans IXFMR2 : {list(df_tx.columns)}")
            
            df_tx.columns = [str(c).strip() for c in df_tx.columns]
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID', 'DEVICEID']), None)
            
            # RECHERCHE SPÉCIFIQUE DE "LTCTapPosition"
            # On cherche une colonne qui contient "LTC" et "TAP"
            col_tap = next((c for c in df_tx.columns if 'LTC' in c.upper() and 'TAP' in c.upper()), None)
            
            if col_tap:
                print(f"🎯 Colonne TAP identifiée : {col_tap}")
            else:
                print("⚠️ Aucune colonne avec 'LTC' et 'TAP'. Recherche fallback...")
                # Fallback sur Adjusted Tap ou Final Tap, mais on évite 'Tap' tout court qui vaut souvent 0
                col_tap = next((c for c in df_tx.columns if c.upper() in ['ADJTAP', 'FINALTAP', 'TAPSETTING']), None)

            if col_id_tx and col_tap:
                for tx_id in settings.tap_transformers_ids:
                    row = df_tx[df_tx[col_id_tx] == tx_id]
                    if not row.empty:
                        try:
                            raw_val = row.iloc[0][col_tap]
                            val_tap = float(str(raw_val).replace(',', '.'))
                            res["taps"][tx_id] = val_tap
                            print(f"   -> Transfo {tx_id} : {val_tap} (brut: {raw_val})")
                        except Exception as e:
                            print(f"   -> Erreur lecture {tx_id}: {e}")
                            res["taps"][tx_id] = None
                    else:
                        print(f"   -> Transfo {tx_id} NON TROUVÉ dans la table.")
            else:
                print(f"❌ Impossible de trouver ID ({col_id_tx}) ou TAP ({col_tap})")

        # --- C. ANALYSE ---
        if res["mw_flow"] is not None:
            delta = abs(res["mw_flow"] - target)
            res["delta_target"] = round(delta, 3)
            
            if delta <= tol:
                res["status_color"] = "green"
            elif delta <= (tol * 2):
                res["status_color"] = "orange"
            else:
                res["status_color"] = "red"
                
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
