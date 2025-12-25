import pandas as pd
import math
from app.calculations import si2s_converter

def analyze_loadflow(files_content: dict, settings) -> dict:
    print("🚀 DÉBUT ANALYSE LOADFLOW (LOGIQUE UTILISATEUR)")
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
        
        # --- 1. RECUPERATION DES TABLES ---
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
        
        # Nettoyage des noms de colonnes (suppression espaces)
        if df_lfr is not None: df_lfr.columns = [str(c).strip() for c in df_lfr.columns]
        if df_tx is not None: df_tx.columns = [str(c).strip() for c in df_tx.columns]

        # --- 2. LECTURE DES MW (CIBLE) - Inchangé ---
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
                # Recherche valeur MW
                col_mw = next((c for c in df_lfr.columns if c.upper() in ['LFMW', 'MW', 'MWLOADING', 'P (MW)']), None)
                # On cherche le bus dans ID, IDFrom ou IDTo
                cols_id_search = [c for c in df_lfr.columns if c.upper() in ['ID', 'IDFROM', 'IDTO']]
                
                if cols_id_search and col_mw:
                    mask = pd.Series(False, index=df_lfr.index)
                    for c in cols_id_search:
                        mask |= (df_lfr[c] == target_bus_id)
                    rows = df_lfr[mask]
                    if not rows.empty:
                        try:
                            res["mw_flow"] = float(str(rows.iloc[0][col_mw]).replace(',', '.'))
                        except: pass

        # --- 3. ALGORITHME TAP (Votre logique) ---
        # ETAPE 0 : Vérifier les colonnes requises
        if df_tx is not None and df_lfr is not None and settings.tap_transformers_ids:
            
            # Colonnes IXFMR2
            col_id_tx = next((c for c in df_tx.columns if c.upper() in ['ID', 'DEVICE ID']), None)
            
            # On cherche "FromBus" (ou variantes : FromID, FromTo)
            col_from_bus_ixfmr = next((c for c in df_tx.columns if c.upper() in ['FROMBUS', 'FROMID', 'FROMTO', 'IDFROM']), None)
            
            # Colonnes LFR
            col_id_from_lfr = next((c for c in df_lfr.columns if c.upper() == 'IDFROM'), None)
            col_tap_lfr = next((c for c in df_lfr.columns if c.upper() == 'TAP'), None)

            # Debug Log pour vérifier si on a tout
            print(f"   ℹ️ Colonnes identifiées :")
            print(f"      IXFMR2 -> ID: {col_id_tx} | FromBus: {col_from_bus_ixfmr}")
            print(f"      LFR    -> IDFrom: {col_id_from_lfr} | Tap: {col_tap_lfr}")

            if col_id_tx and col_from_bus_ixfmr and col_id_from_lfr and col_tap_lfr:
                
                for tx_id in settings.tap_transformers_ids:
                    # ETAPE 1 : IXFMR2 -> Trouver TX1-A et récupérer FromBus
                    row_tx = df_tx[df_tx[col_id_tx] == tx_id]
                    
                    if not row_tx.empty:
                        # On récupère le nom du bus (ex: "Bus_TX1-A-HV")
                        target_bus_name = str(row_tx.iloc[0][col_from_bus_ixfmr])
                        print(f"   -> {tx_id} : Le Bus 'From' est '{target_bus_name}'")
                        
                        # ETAPE 2 : LFR -> Chercher ce bus dans IDFrom
                        row_lfr = df_lfr[df_lfr[col_id_from_lfr] == target_bus_name]
                        
                        if not row_lfr.empty:
                            # ETAPE 3 : Lire le Tap
                            try:
                                raw_tap = row_lfr.iloc[0][col_tap_lfr]
                                val_tap = float(str(raw_tap).replace(',', '.'))
                                res["taps"][tx_id] = val_tap
                                print(f"      ✅ Tap trouvé : {val_tap}")
                            except Exception as e:
                                print(f"      ❌ Erreur conversion Tap ({raw_tap}) : {e}")
                                res["taps"][tx_id] = None
                        else:
                            print(f"      ⚠️ Bus '{target_bus_name}' NON TROUVÉ dans la colonne IDFrom de LFR.")
                            res["taps"][tx_id] = None
                    else:
                        print(f"   ⚠️ Transfo {tx_id} introuvable dans IXFMR2.")
            else:
                print("❌ Il manque des colonnes essentielles (FromBus dans IXFMR2 ou IDFrom/Tap dans LFR).")
                if not col_from_bus_ixfmr: print(f"   Colonnes dispo IXFMR2: {list(df_tx.columns)}")

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
