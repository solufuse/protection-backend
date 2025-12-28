
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
    
    target_df = None
    for k in dfs_dict.keys():
        if k.lower() in ["scieclgsum1", "sc_sum_1"]:
            target_df = dfs_dict[k]
            break
    
    if target_df is None: return None

    try:
        col_bus = next((c for c in target_df.columns if c.lower() == 'faultedbus'), None)
        if not col_bus: return None
        
        row = target_df[target_df[col_bus].astype(str).str.strip().str.upper() == str(bus_name).strip().upper()]
        if row.empty: return None
        
        return row.iloc[0].where(pd.notnull(row.iloc[0]), None).to_dict()
    except:
        return None

def build_global_transformer_map(files: Dict[str, bytes]) -> Dict[str, Dict]:
    """
    Scanne les fichiers pour avoir les infos statiques des transfos (MVA, Taps).
    """
    global_map = {}
    for fname, content in files.items():
        if not _is_supported_protection(fname): continue
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        xfmr_table = None
        for k in dfs.keys():
            if k.upper() in ["IXFMR2", "TRANSFORMER"]:
                xfmr_table = dfs[k]
                break
        
        if xfmr_table is not None and not xfmr_table.empty:
            for _, row in xfmr_table.iterrows():
                try:
                    tid = str(row.get("ID", "")).strip()
                    if not tid: continue
                    if tid not in global_map:
                        global_map[tid] = {"MVA": 0.0, "MaxMVA": 0.0, "MinTap": 0.0, "StepTap": 0.0}
                    
                    val_mva = float(row.get("MVA", 0) or 0)
                    if val_mva > global_map[tid]["MVA"]: global_map[tid]["MVA"] = val_mva
                    
                    val_max = float(row.get("MaxMVA", 0) or 0)
                    if val_max > global_map[tid]["MaxMVA"]: global_map[tid]["MaxMVA"] = val_max
                    
                    val_min = float(row.get("Min%Tap", 0) or 0)
                    if val_min != 0 and global_map[tid]["MinTap"] == 0: global_map[tid]["MinTap"] = val_min
                        
                    val_step = float(row.get("Step%Tap", 0) or 0)
                    if val_step != 0 and global_map[tid]["StepTap"] == 0: global_map[tid]["StepTap"] = val_step
                except: continue
    return global_map

def calc_In(mva, kv):
    if kv == 0: return 0
    return (mva * 1000) / (math.sqrt(3) * kv)

# --- CALCUL CORE ---

def calculate(plan: ProtectionPlan, settings: GlobalSettings, dfs_dict: dict, global_tx_map: dict) -> dict:
    """
    Logique ANSI 51 séparée par type d'équipement.
    """
    bus_amont = plan.bus_from
    bus_aval = plan.bus_to
    
    # Données Brutes (Communes à tous)
    data_from = find_bus_data(dfs_dict, bus_amont) or {}
    data_to = find_bus_data(dfs_dict, bus_aval) or {}
    
    # Récupération tension nominale (utile partout)
    kvnom_busfrom = float(data_from.get("kVnom", 0) or 0)
    kvnom_busto = float(data_to.get("kVnom", 0) or 0)
    
    # Isc (utile partout)
    busfrom_ipp3kph = float(data_from.get("IPPk3ph", 0) or 0)
    busto_ipp3kph = float(data_to.get("IPPk3ph", 0) or 0)
    busfrom_prefault = float(data_from.get("PreFaultNom", 100) or 100)
    busto_prefault = float(data_to.get("PreFaultNom", 100) or 100)
    
    # --- LOGIQUE SPECIFIQUE PAR TYPE ---
    data_settings = {"type": plan.type}
    formulas_section = {}
    
    # >>>> LOGIQUE TRANSFORMATEUR <<<<
    if plan.type.upper() == "TRANSFORMER":
        
        # 1. Identification Transfo
        tx_id = plan.related_source if plan.related_source else plan.id.replace("CB_", "")
        tx_data = global_tx_map.get(tx_id, {})
        
        mva_tx = float(tx_data.get("MVA", 0))
        maxmva_tx = float(tx_data.get("MaxMVA", 0))
        min_tap = float(tx_data.get("MinTap", 0))
        step_tap = float(tx_data.get("StepTap", 0))
        
        # 2. Calcul Tension Tap
        try:
            facteur_chute = (abs(min_tap) * abs(step_tap)) / 100.0 if step_tap else 0
            if facteur_chute > 0.3: facteur_chute = 0
            kvnom_busto_tap1 = kvnom_busfrom * (1 - facteur_chute) 
        except: kvnom_busto_tap1 = 0
        
        # 3. Calcul Courants
        in_from = calc_In(mva_tx, kvnom_busfrom)
        in_to = calc_In(mva_tx, kvnom_busto)
        in_from_tap = calc_In(mva_tx, kvnom_busto_tap1) 
        
        # 4. Formules Isc pondéré
        try:
            r_v = kvnom_busto / kvnom_busfrom if kvnom_busfrom else 0
            f_ipp_from = (busfrom_ipp3kph * r_v) * (busfrom_prefault / 100.0)
            f_ipp_to = (busto_ipp3kph * r_v) * (busto_prefault / 100.0)
        except: 
            f_ipp_from = 0
            f_ipp_to = 0

        # Remplissage DATA_SETTINGS (Transformers)
        data_settings.update({
            "mva_tx": mva_tx,
            "maxmva_tx": maxmva_tx,
            "kVnom_busfrom": kvnom_busfrom,
            "kVnom_busto": kvnom_busto,
            "kVnom_busto_tap1": round(kvnom_busto_tap1, 3),
            "Min%Tap_tap1": min_tap,
            "Step%Tap_tap": step_tap,
            "In_tx_busfrom": round(in_from, 2),
            "In_tx_busto": round(in_to, 2),
            "In_tx_busfrom_tap_1": round(in_from_tap, 2),
            "BusFrom_IPP3kph": busfrom_ipp3kph,
            "Busto_IPP3kph": busto_ipp3kph,
            "BusFrom_f_IPP3kph": round(f_ipp_from, 3),
            "Busto_f_IPP3kph": round(f_ipp_to, 3),
            "inrush_tx": {"inrush_50ms": "TBD", "inrush_900ms": "TBD"}
        })
        
        # Remplissage FORMULES (Transformers)
        std_51 = settings.std_51
        formulas_section["F_I1_overloads"] = {
            "Fdata_si2s": f"In_tx_busfrom={round(in_from,2)}A",
            "Fcalculation": f"{std_51.coeff_stab_max} * {round(in_from,2)}",
            "Ftime": "Long Time",
            "Fremark": "Protection surcharge"
        }

    # >>>> LOGIQUE AUTRES (INCOMER, COUPLING) <<<<
    else:
        # Pour l'instant, on met juste les bases pour éviter les crashs
        data_settings.update({
            "status": "WAITING_FOR_SPECS",
            "kVnom_busfrom": kvnom_busfrom,
            "kVnom_busto": kvnom_busto,
            "BusFrom_IPP3kph": busfrom_ipp3kph,
            "Busto_IPP3kph": busto_ipp3kph,
            # Tu pourras ajouter ici les champs spécifiques plus tard
        })
        formulas_section["F_Global"] = "Logic to be defined for this type"

    # --- RESULTAT ---
    
    # Config display
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

    status = "computed"
    comments = []
    if not bus_aval or not bus_amont: status = "error_topology"
    elif kvnom_busfrom == 0: status = "warning_data (kV=0)"

    return {
        "ansi_code": "51",
        "status": status,
        "topology_used": {"bus_from": bus_amont, "bus_to": bus_aval},
        "data_si2s": { 
             "FaultedBus_bus_from": bus_amont,
             "bus_from_data": data_from,
             "FaultedBus_bus_to": bus_aval,
             "bus_to_data": data_to
        },
        "config": config_section,
        "data_settings": data_settings,
        "formulas": formulas_section,
        "calculated_thresholds": {"pickup_amps": 0, "time_dial": 0},
        "comments": comments
    }

# --- BATCH & EXCEL (Inchangés mais réinclus pour cohérence) ---

def run_batch_logic(config: ProjectConfig, token: str) -> List[dict]:
    files = session_manager.get_files(token)
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
                res = calculate(plan, file_config.settings, dfs, global_tx_map)
                
                # Filtre Scénario Inactif
                ds = res.get("data_settings", {})
                if res["status"] == "error_topology": continue
                # Si le bus n'a pas de tension, on ignore
                if ds.get("kVnom_busfrom", 0) == 0: continue 

                res["plan_id"] = plan.id
                res["plan_type"] = plan.type
                res["source_file"] = filename
                results.append(res)
            except Exception as e:
                results.append({"plan_id": plan.id, "source_file": filename, "status": "error", "comments": [str(e)]})
    return results

def generate_excel(results: List[dict]) -> bytes:
    flat_rows = []
    for res in results:
        row = {
            "Source File": res.get("source_file"),
            "Plan ID": res.get("plan_id"),
            "Status": res.get("status"),
        }
        # Data Settings flattening
        ds = res.get("data_settings", {})
        for k, v in ds.items():
            if not isinstance(v, dict): row[f"DS_{k}"] = v
            
        flat_rows.append(row)

    df = pd.DataFrame(flat_rows)
    if "Plan ID" in df.columns: df = df.sort_values(by=["Plan ID", "Source File"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Data Settings", index=False)
        ws = writer.sheets["Data Settings"]
        for col in ws.columns:
            try: ws.column_dimensions[col[0].column_letter].width = 18
            except: pass
    return output.getvalue()
