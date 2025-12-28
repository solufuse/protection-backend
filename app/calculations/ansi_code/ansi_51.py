
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
    """Scanne les fichiers pour avoir les infos statiques des transfos (MVA, Taps)."""
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
                    curr_min = global_map[tid]["MinTap"]
                    if abs(val_min) > abs(curr_min): global_map[tid]["MinTap"] = val_min
                        
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
    Logique ANSI 51 avec traçabilité des colonnes brutes et formules explicites.
    """
    bus_amont = plan.bus_from
    bus_aval = plan.bus_to
    
    # 1. Extraction Données Électriques
    data_from = find_bus_data(dfs_dict, bus_amont) or {}
    data_to = find_bus_data(dfs_dict, bus_aval) or {}
    
    kvnom_busfrom = float(data_from.get("kVnom", 0) or 0)
    kvnom_busto = float(data_to.get("kVnom", 0) or 0)
    
    # Extraction des courants de court-circuit spécifiques (ETAP Columns)
    # Ik3ph = Triphasé symétrique
    # IkLL = Biphasé (Phase-Phase)
    # IkLG = Monophasé (Phase-Terre / Homopolaire)
    
    # Bus Amont
    from_ik3ph = float(data_from.get("Ik3ph", 0) or 0)
    from_ikLL = float(data_from.get("IkLL", 0) or 0) 
    from_ikLG = float(data_from.get("IkLG", 0) or 0) 
    
    # Bus Aval
    to_ik3ph = float(data_to.get("Ik3ph", 0) or 0)
    to_ikLL = float(data_to.get("IkLL", 0) or 0)
    to_ikLG = float(data_to.get("IkLG", 0) or 0)

    # 2. Structure Data Settings
    data_settings = {"type": plan.type}
    formulas_section = {}
    
    # >>>> TRANSFORMATEUR <<<<
    if plan.type.upper() == "TRANSFORMER":
        
        tx_id = plan.related_source if plan.related_source else plan.id.replace("CB_", "")
        tx_data = global_tx_map.get(tx_id, {})
        
        mva_tx = float(tx_data.get("MVA", 0))
        maxmva_tx = float(tx_data.get("MaxMVA", 0))
        min_tap = float(tx_data.get("MinTap", 0)) 
        step_tap = float(tx_data.get("StepTap", 0))
        
        # Calcul Tension au Tap Min
        try:
            percent_drop = 0
            if step_tap != 0 and abs(min_tap) > 1: 
                percent_drop = (abs(min_tap) * abs(step_tap)) / 100.0
            else:
                percent_drop = abs(min_tap) / 100.0
                
            if percent_drop > 0.3: percent_drop = 0
            
            kvnom_busfrom_tap_min = kvnom_busfrom * (1 - percent_drop)
        except: 
            kvnom_busfrom_tap_min = kvnom_busfrom
        
        # Courants Nominaux
        in_prim = calc_In(mva_tx, kvnom_busfrom) # In @ Un
        in_sec = calc_In(mva_tx, kvnom_busto)    # In @ Sec
        in_prim_tap = calc_In(mva_tx, kvnom_busfrom_tap_min) # In @ Un-Tap
        
        # --- COURANTS RAMENES (Referred Currents) ---
        ratio_u = kvnom_busto / kvnom_busfrom if kvnom_busfrom else 0
        
        ikLL_sec_ref_prim = to_ikLL * ratio_u
        ik3ph_sec_ref_prim = to_ik3ph * ratio_u

        data_settings.update({
            # Données Plaque
            "mva_tx [MVA]": mva_tx,
            "maxmva_tx [MaxMVA]": maxmva_tx,
            "kVnom_busfrom": kvnom_busfrom,
            "kVnom_busto": kvnom_busto,
            "Min%Tap_val [Min%Tap]": min_tap,
            
            # Courants Nominaux Calculés
            "In_prim_Un": round(in_prim, 2),        
            "In_prim_TapMin": round(in_prim_tap, 2),
            "In_prim_TapMin_Formula": "S / (sqrt(3) * U_min_tap)",
            "U_min_tap_Formula": f"{kvnom_busfrom} * (1 - {round(percent_drop*100, 2)}%)",
            
            "In_sec_Un": round(in_sec, 2),          
            
            # Courants Court-Circuit (Noms ETAP Explicites)
            "Isc_2ph_min_prim [IkLL]": from_ikLL,       
            "Isc_zero_min_prim [IkLG]": from_ikLG,      
            
            "Isc_2ph_min_sec_ref": round(ikLL_sec_ref_prim, 3), 
            "Isc_2ph_min_sec_ref_Formula": "IkLL_sec * (U_sec / U_prim)",
            "Isc_2ph_min_sec_ref_RawValues": f"{to_ikLL} * ({kvnom_busto}/{kvnom_busfrom})",
            
            "Isc_3ph_max_sec_ref": round(ik3ph_sec_ref_prim, 3),
            "Isc_3ph_max_sec_ref_Formula": "Ik3ph_sec * (U_sec / U_prim)",
            "Isc_3ph_max_sec_ref_RawValues": f"{to_ik3ph} * ({kvnom_busto}/{kvnom_busfrom})",
            
            "inrush_50ms": "TBD",
            "inrush_900ms": "TBD"
        })
        
        std_51 = settings.std_51
        formulas_section["F_I1_overloads"] = {
            "Fdata_si2s": f"In_prim_TapMin={round(in_prim_tap,2)}A",
            "Fcalculation": f"{std_51.coeff_stab_max} * {round(in_prim_tap,2)}",
            "Fremark": "Seuil Surcharge (1.2 x In_régleur)"
        }

    else:
        # Autres
        data_settings.update({
            "status": "BASIC_INFO",
            "kVnom": kvnom_busfrom,
            "Isc_3ph [Ik3ph]": from_ik3ph,
            "Isc_2ph [IkLL]": from_ikLL,
            "Isc_zero [IkLG]": from_ikLG
        })

    # --- RESULTAT ---
    
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
                ds = res.get("data_settings", {})
                if res["status"] == "error_topology": continue
                if ds.get("kVnom_busfrom", 0) == 0 and ds.get("kVnom", 0) == 0: continue 

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
            try: ws.column_dimensions[col[0].column_letter].width = 25
            except: pass
    return output.getvalue()
