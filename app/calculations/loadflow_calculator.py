import pandas as pd
import math
from app.calculations import si2s_converter

def analyze_loadflow(files_content: dict, settings) -> dict:
    print("🚀 DÉBUT ANALYSE LOADFLOW (MODE INDIRECT)")
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
        # 1. Table Résultats (LFR / BusLoadSummary)
        df_lfr = None
        for k in dfs.keys():
            if k.upper() in ['LFR', 'BUSLOADSUMMARY', 'BUS RESULTS', 'SUMMARY']:
                df_lfr = dfs[k]
                break
        
        # 2. Table Transfos (IXFMR2)
        df_tx = None
        for k in dfs.keys():
            if 'IXFMR2' in k.upper():
                df_tx = dfs[k]
                break
        
        # Nettoyage des colonnes (strip espaces)
        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # --- A. LECTURE DES MW (Cible) ---
        target_bus_id = settings.swing_bus_id
        if df_lfr is not None:
            col_id = next((c for c in df_lfr.columns if c.upper() in ['ID', 'BUSID', 'BUS ID', 'IDFROM']), None)
            
            # Auto-detection Swing
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

        # --- B. LECTURE DES TAPS (Jeu de piste : IXFMR2 -> LFR) ---
        if df_tx is not None and df_lfr is not None and settings.tap_transformers_ids:
            
            # 1. Colonnes IXFMR2
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID']), None)
            # On cherche la colonne qui contient le Bus "Destination" (FromTo, ToBus, SecID...)
            col_link_bus = next((c for c in df_tx.columns if c.upper() in ['FROMTO', 'IDTO', 'TOBUS', 'SECID', 'SECONDARYBUSID', 'IDSEC']), None)
            
            # 2. Colonnes LFR
            col_id_lfr = next((c for c in df_lfr.columns if c.upper() in ['IDFROM', 'BUSID', 'ID']), None)
            col_tap_lfr = next((c for c in df_lfr.columns if c.upper() in ['TAP', 'TAPSETTING', 'CURRENTTAP']), None)

            print(f"   🔍 Colonnes IXFMR2 : ID={col_id_tx}, Link={col_link_bus}")
            print(f"   🔍 Colonnes LFR    : ID={col_id_lfr}, Tap={col_tap_lfr}")

            if col_id_tx and col_link_bus and col_id_lfr and col_tap_lfr:
                for tx_id in settings.tap_transformers_ids:
                    # ETAPE 1 : Trouver le Bus lié dans IXFMR2
                    row_tx = df_tx[df_tx[col_id_tx] == tx_id]
                    if not row_tx.empty:
                        linked_bus_name = str(row_tx.iloc[0][col_link_bus])
                        print(f"   -> Transfo {tx_id} est lié au bus : {linked_bus_name}")
                        
                        # ETAPE 2 : Trouver ce Bus dans LFR pour lire le Tap
                        row_lfr = df_lfr[df_lfr[col_id_lfr] == linked_bus_name]
                        if not row_lfr.empty:
                            try:
                                raw_tap = row_lfr.iloc[0][col_tap_lfr]
                                val_tap = float(str(raw_tap).replace(',', '.'))
                                res["taps"][tx_id] = val_tap
                                print(f"      ✅ Tap trouvé dans LFR : {val_tap}")
                            except Exception as e:
                                print(f"      ❌ Erreur conversion Tap : {e}")
                                res["taps"][tx_id] = None
                        else:
                            print(f"      ⚠️ Bus {linked_bus_name} introuvable dans LFR.")
                            res["taps"][tx_id] = None
                    else:
                        print(f"   ⚠️ Transfo {tx_id} introuvable dans IXFMR2.")
            else:
                print("❌ Impossible de faire le lien : Colonnes manquantes.")
                if not col_link_bus: print(f"   Colonnes dispo IXFMR2: {list(df_tx.columns)}")

        # --- C. ANALYSE (Couleur & Vainqueur) ---
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
