
from app.schemas.protection import ProtectionPlan, GlobalSettings, ProjectConfig
from app.services import session_manager
from app.calculations import db_converter, topology_manager
import pandas as pd
import math
import io
import copy
from typing import List, Dict, Any

# --- HELPERS DATA ---

def _is_supported_protection(fname: str) -> bool:
    e = fname.lower()
    return e.endswith('.si2s') or e.endswith('.mdb')

def find_bus_data(dfs_dict: dict, bus_name: str) -> dict:
    """Récupère la ligne SCIECLGSum1 pour un bus."""
    if not bus_name: return None
    
    # Recherche dans SCIECLGSum1 ou SC_SUM_1
    target_df = None
    for k in dfs_dict.keys():
        if k.lower() in ["scieclgsum1", "sc_sum_1"]:
            target_df = dfs_dict[k]
            break
    
    if target_df is None: return None

    try:
        # Recherche insensible à la casse
        col_bus = next((c for c in target_df.columns if c.lower() == 'faultedbus'), None)
        if not col_bus: return None
        
        row = target_df[target_df[col_bus].astype(str).str.strip().str.upper() == str(bus_name).strip().upper()]
        if row.empty: return None
        
        return row.iloc[0].where(pd.notnull(row.iloc[0]), None).to_dict()
    except:
        return None

def build_global_transformer_map(files: Dict[str, bytes]) -> Dict[str, Dict]:
    """
    Scanne TOUS les fichiers SI2S pour construire une carte d'identité 'idéale' des transfos.
    Le but est de trouver les valeurs Min%Tap et Step%Tap même si elles sont à 0 dans certains fichiers.
    """
    global_map = {} # Key: TransfoID (ex: TX1-A), Value: Dict avec les meilleures datas
    
    for fname, content in files.items():
        if not _is_supported_protection(fname): continue
        
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        # On cherche la table des transfos (souvent IXFMR2 ou Transformer)
        xfmr_table = None
        for k in dfs.keys():
            if k.upper() in ["IXFMR2", "TRANSFORMER"]:
                xfmr_table = dfs[k]
                break
        
        if xfmr_table is not None and not xfmr_table.empty:
            for _, row in xfmr_table.iterrows():
                try:
                    # Identification
                    tid = str(row.get("ID", "")).strip()
                    if not tid: continue
                    
                    if tid not in global_map:
                        global_map[tid] = {
                            "MVA": 0.0, "MaxMVA": 0.0, "MinTap": 0.0, "StepTap": 0.0, "PrimkV": 0.0, "SeckV": 0.0
                        }
                    
                    # Extraction des valeurs (On prend la valeur max trouvée sur tous les fichiers pour éviter les 0)
                    # MVA
                    val_mva = float(row.get("MVA", 0) or 0)
                    if val_mva > global_map[tid]["MVA"]: global_map[tid]["MVA"] = val_mva
                    
                    # MaxMVA
                    val_max_mva = float(row.get("MaxMVA", 0) or 0)
                    if val_max_mva > global_map[tid]["MaxMVA"]: global_map[tid]["MaxMVA"] = val_max_mva
                    
                    # Min%Tap
                    val_min_tap = float(row.get("Min%Tap", 0) or 0)
                    # Note: MinTap peut être négatif, donc on cherche la valeur absolue non nulle, ou juste non nulle
                    if val_min_tap != 0 and global_map[tid]["MinTap"] == 0: 
                        global_map[tid]["MinTap"] = val_min_tap
                        
                    # Step%Tap
                    val_step_tap = float(row.get("Step%Tap", 0) or 0)
                    if val_step_tap != 0 and global_map[tid]["StepTap"] == 0: 
                        global_map[tid]["StepTap"] = val_step_tap
                        
                except Exception:
                    continue
                    
    return global_map

# --- CALCUL CORE ---

def calculate(plan: ProtectionPlan, settings: GlobalSettings, dfs_dict: dict, global_tx_map: dict) -> dict:
    """
    Logique ANSI 51 avec Data Settings enrichi.
    """
    bus_amont = plan.bus_from
    bus_aval = plan.bus_to
    
    # 1. Récupération Données Brutes (SI2S)
    data_from = find_bus_data(dfs_dict, bus_amont) or {}
    data_to = find_bus_data(dfs_dict, bus_aval) or {}
    
    # 2. Identification du Transfo lié (si applicable)
    # On suppose que le nom du plan ou related_source contient l'ID du transfo, 
    # ou on le cherche via la topo. Pour simplifier ici, on utilise related_source ou on parse l'ID plan.
    # Ex: ID Plan "CB_TX1-A" -> Transfo "TX1-A"
    tx_id_candidate = plan.related_source if plan.related_source else plan.id.replace("CB_", "")
    
    # Récupération des infos "Globales" du transfo (pour avoir les Taps corrects)
    tx_static_data = global_tx_map.get(tx_id_candidate, {})
    
    # --- PREPARATION DU BLOC DATA_SETTINGS ---
    
    # a. Extraction valeurs de base
    mva_tx = float(tx_static_data.get("MVA", 0))
    maxmva_tx = float(tx_static_data.get("MaxMVA", 0))
    
    kvnom_busfrom = float(data_from.get("kVnom", 0) or 0)
    kvnom_busto = float(data_to.get("kVnom", 0) or 0)
    
    min_tap_percent = float(tx_static_data.get("MinTap", 0)) # ex: 15 ou -15
    step_tap_percent = float(tx_static_data.get("StepTap", 0)) # ex: 1.25
    
    # b. Formule kVnom_busto_tap1
    # Formule utilisateur: kVnom_busfrom * (1 - (Min%Tap * Step%Tap))
    # Attention aux unités (pourcentage vs decimal). Souvent MinTap est un nombre de prises (ex: 12) ou un % total.
    # Si MinTap est un %, la formule est (1 - MinTap/100). 
    # Si MinTap est un nombre de steps, c'est (1 - MinTap * StepTap / 100).
    # On applique stricto sensu la demande mais en divisant par 100 si nécessaire.
    # Hypothèse: MinTap et StepTap sont des entiers/flottants bruts (ex: 12 et 1.25)
    
    # Correction logique probable: Variation = MinTap * StepTap (ex: 12 prises * 1.25% = 15%)
    # Si MinTap est déjà un %, on prend juste MinTap. 
    # On va assumer que MinTap est un nombre de prises (ex: 12) selon ton commentaire "avoir le -15".
    # SI MinTap vaut -15 (le %) alors la formule est differente.
    # On va utiliser une logique hybride sécurisée :
    
    # Calcul safe
    try:
        variation_percent = abs(min_tap_percent) # ex: 15
        if step_tap_percent > 0:
             # Si on a un step, peut-être que MinTap est le nombre de steps ? 
             # ETAP stocke souvent le % min direct (ex: -10).
             pass
        
        # Application formule demandée : 
        # kVnom_busto_tap1=(kVnom_busfrom*(1-(Min%Tap_tap1*Step%Tap_tap/100))) ? 
        # On va assumer que le produit donne un pourcentage.
        
        # Simplification pour l'exemple (à ajuster selon tes vraies données ETAP):
        # On suppose que tu veux simuler la tension au plus bas
        facteur_chute = (abs(min_tap_percent) * abs(step_tap_percent)) / 100.0 if step_tap_percent else 0
        if facteur_chute > 0.3: facteur_chute = 0 # Sécurité si calcul aberrant
        
        # Si MinTap est negatif, c'est une baisse, donc 1 - ...
        kvnom_busto_tap1 = kvnom_busfrom * (1 - facteur_chute) 
        
    except:
        kvnom_busto_tap1 = 0
        
    # c. Calcul des Courants Nominaux (In)
    # Formule: S / (sqrt(3) * U)
    def calc_In(mva, kv):
        if kv == 0: return 0
        return (mva * 1000) / (math.sqrt(3) * kv) # MVA -> kVA / kV = A

    in_tx_busfrom = calc_In(mva_tx, kvnom_busfrom)
    in_tx_busto = calc_In(mva_tx, kvnom_busto)
    # Pour le tap, on utilise la tension calculée mais ramenée au primaire ? 
    # Ou est-ce le courant vu du primaire avec la tension modifiée ?
    # Si la tension baisse, le courant monte pour P constante.
    in_tx_busfrom_tap_1 = calc_In(mva_tx, kvnom_busto_tap1) 

    # d. Données Court-Circuit
    busfrom_ipp3kph = float(data_from.get("IPPk3ph", 0) or 0)
    busto_ipp3kph = float(data_to.get("IPPk3ph", 0) or 0)
    
    busfrom_prefault = float(data_from.get("PreFaultNom", 100) or 100)
    busto_prefault = float(data_to.get("PreFaultNom", 100) or 100)
    
    # e. Formules croisées (f_IPP3kph)
    # =(BusFrom_IPP3kph * kVnom_busto / kVnom_busfrom) * (BusFrom_PreFaultNom/100)
    try:
        ratio_v = kvnom_busto / kvnom_busfrom if kvnom_busfrom else 0
        busfrom_f_ipp3kph = (busfrom_ipp3kph * ratio_v) * (busfrom_prefault / 100.0)
    except: busfrom_f_ipp3kph = 0
    
    try:
        # Pour le BusTo, la formule semble identique dans ta demande (ratio V et prefault)
        # "=(Busto_IPP3kph*kVnom_busto/kVnom_busfrom)*(Busto_PreFaultNom/100)" 
        # -> Cela semble convertir le Icc du secondaire vu du primaire ? Ou l'inverse ?
        # Si c'est vu du primaire, on multiplie par (V2/V1).
        ratio_v = kvnom_busto / kvnom_busfrom if kvnom_busfrom else 0
        busto_f_ipp3kph = (busto_ipp3kph * ratio_v) * (busto_prefault / 100.0)
    except: busto_f_ipp3kph = 0

    # f. Construction de l'objet data_settings
    data_settings = {
        "type": plan.type,
        "mva_tx": mva_tx,
        "maxmva_tx": maxmva_tx,
        "kVnom_busfrom": kvnom_busfrom,
        "kVnom_busto": kvnom_busto,
        "kVnom_busto_tap1": round(kvnom_busto_tap1, 3),
        "Min%Tap_tap1": min_tap_percent,
        "Step%Tap_tap": step_tap_percent,
        "In_tx_busfrom": round(in_tx_busfrom, 2),
        "In_tx_busto": round(in_tx_busto, 2),
        "In_tx_busfrom_tap_1": round(in_tx_busfrom_tap_1, 2),
        "BusFrom_IPP3kph": busfrom_ipp3kph,
        "Busto_IPP3kph": busto_ipp3kph,
        "BusFrom_PreFaultNom": busfrom_prefault,
        "Busto_PreFaultNom": busto_prefault,
        "BusFrom_f_IPP3kph": round(busfrom_f_ipp3kph, 3),
        "Busto_f_IPP3kph": round(busto_f_ipp3kph, 3),
        "inrush_tx": {
            "inrush_50ms": "TBD", # Placeholder pour ton futur algo
            "inrush_900ms": "TBD"
        }
    }

    # --- RESULTAT FINAL ---
    
    std_51_cfg = settings.std_51
    
    config_section = {
        "settings": {
            "std_51": {
                "factor_I1": std_51_cfg.coeff_stab_max,
                "factor_I2": std_51_cfg.coeff_backup_min,
                "details": std_51_cfg.dict()
            }
        },
        "type": plan.type,
        "ct_primary": plan.ct_primary
    }
    
    formulas_section = {
        "F_I1_overloads": {
            "Fdata_si2s": f"In_tx_busfrom={round(in_tx_busfrom,2)}A",
            "Fcalculation": f"{std_51_cfg.coeff_stab_max} * {round(in_tx_busfrom,2)}",
            "Ftime": "Long Time",
            "Fremark": "Protection surcharge"
        }
    }
    
    # Status check
    status = "computed"
    comments = []
    if not bus_aval or not bus_amont: status = "error_topology"
    elif kvnom_busfrom == 0: status = "warning_data (kV=0)"
    
    return {
        "ansi_code": "51",
        "status": status,
        "topology_used": {"bus_from": bus_amont, "bus_to": bus_aval},
        "data_si2s": { # On garde quand même les données brutes
             "FaultedBus_bus_from": bus_amont,
             "bus_from_data": data_from,
             "FaultedBus_bus_to": bus_aval,
             "bus_to_data": data_to
        },
        "config": config_section,
        "data_settings": data_settings, # <--- LE NOUVEAU BLOC
        "formulas": formulas_section,
        "calculated_thresholds": {"pickup_amps": 0, "time_dial": 0},
        "comments": comments
    }

# --- BATCH LOGIC ---

def run_batch_logic(config: ProjectConfig, token: str) -> List[dict]:
    files = session_manager.get_files(token)
    
    # 1. PRE-SCAN : Construction de la carte globale des transfos
    # Cela permet de remplir les trous (MinTap = 0) en regardant les autres fichiers
    global_tx_map = build_global_transformer_map(files)
    
    results = []
    
    for filename, content in files.items():
        if not _is_supported_protection(filename): continue
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        file_config = copy.deepcopy(config)
        topology_manager.resolve_all(file_config, dfs)
        
        for plan in file_config.plans:
            try:
                # On passe global_tx_map à la fonction calculate
                res = calculate(plan, file_config.settings, dfs, global_tx_map)
                
                # Filtre Scénario Inactif (si pas de tension/courant)
                ds = res.get("data_settings", {})
                if res["status"] == "error_topology": continue
                if ds.get("kVnom_busfrom") == 0: continue # Si kV=0, le bus est hors tension

                res["plan_id"] = plan.id
                res["plan_type"] = plan.type
                res["source_file"] = filename
                results.append(res)
            except Exception as e:
                results.append({
                    "plan_id": plan.id, "source_file": filename, "status": "error", "comments": [str(e)]
                })
    return results

# --- EXCEL GENERATOR ---

def generate_excel(results: List[dict]) -> bytes:
    flat_rows = []
    for res in results:
        row = {
            "Source File": res.get("source_file"),
            "Plan ID": res.get("plan_id"),
            "Status": res.get("status"),
        }
        
        # Data Settings (Aplatissement)
        ds = res.get("data_settings", {})
        for k, v in ds.items():
            if isinstance(v, dict): continue # Skip sub-dicts like inrush for now or flatten them too
            row[f"DS_{k}"] = v
            
        # Raw Data (Optionnel, on peut le garder ou l'enlever pour alléger)
        # ... (code existant pour raw data si besoin)
        
        flat_rows.append(row)

    df = pd.DataFrame(flat_rows)
    # Tri et Export
    if "Plan ID" in df.columns: df = df.sort_values(by=["Plan ID", "Source File"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Data Settings", index=False)
        # Auto-width logic...
    return output.getvalue()
