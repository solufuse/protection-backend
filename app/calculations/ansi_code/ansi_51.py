
from app.schemas.protection import ProtectionPlan, GlobalSettings, ProjectConfig
from app.services import session_manager
from app.calculations import db_converter, topology_manager
from app.calculations.ansi_code import common
import pandas as pd
import io
import copy
from typing import List, Dict, Any
import traceback

def flatten_dict(d: Dict, parent_key: str = '', sep: str = '_') -> Dict:
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict): items.extend(flatten_dict(v, new_key, sep=sep).items())
        else: items.append((new_key, v))
    return dict(items)

def calculate(plan: ProtectionPlan, full_config: ProjectConfig, dfs_dict: dict, global_tx_map: dict) -> dict:
    settings = full_config.settings
    std_51 = settings.std_51
    data_settings = common.get_electrical_parameters(plan, full_config, dfs_dict, global_tx_map)
    thresholds = {"pickup_amps": 0.0, "time_dial": 0.5, "backup_amps": 0.0}
    formulas_section = {}
    
    if plan.type.upper() == "TRANSFORMER":
        in_prim_tap = data_settings.get("In_prim_TapMin", 0)
        ik2min_ref = data_settings.get("Ik2min_sec_ref", 0)
        pickup_i1 = round(std_51.coeff_stab_max * in_prim_tap, 2)
        backup_i2 = round(std_51.coeff_backup_min * (ik2min_ref * 1000), 2)
        thresholds["pickup_amps"] = pickup_i1
        thresholds["backup_amps"] = backup_i2
        formulas_section["F_I1_overloads"] = {"Fdata_si2s": f"In_prim_TapMin={in_prim_tap}A", "Fcalculation": f"{std_51.coeff_stab_max} * {in_prim_tap} = {pickup_i1} A"}
        formulas_section["F_I2_backup"] = {"Fdata_si2s": f"Ik2min_ref={round(ik2min_ref*1000, 2)}A", "Fcalculation": f"{std_51.coeff_backup_min} * {round(ik2min_ref*1000, 2)} = {backup_i2} A"}
    else:
        in_ref = data_settings.get("In_prim_Un", 0)
        pickup_i1 = round(1.0 * in_ref, 2)
        thresholds["pickup_amps"] = pickup_i1
        formulas_section["F_I1_overloads"] = {"Fdata_si2s": f"In_Ref={in_ref}A", "Fcalculation": f"1.0 * {in_ref} = {pickup_i1} A"}

    status = "computed"
    if data_settings.get("kVnom_busfrom") == 0: status = "warning_data (kV=0)"

    return {
        "ansi_code": "51", "status": status,
        "topology_used": {"bus_from": data_settings.get("Bus_Prim"), "bus_to": data_settings.get("Bus_Sec")},
        "config": { "settings": { "std_51": std_51.dict() }, "type": plan.type, "ct_primary": plan.ct_primary },
        "data_settings": data_settings, "formulas": formulas_section, "calculated_thresholds": thresholds, "comments": []
    }

def run_batch_logic(config: ProjectConfig, token: str) -> List[dict]:
    files = session_manager.get_files(token)
    global_tx_map = common.build_global_transformer_map(files)
    results = []
    for filename, content in files.items():
        if not common.is_supported_protection(filename): continue
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        file_config = copy.deepcopy(config)
        
        # PROTECTION CONTRE TOPOLOGY MANAGER
        try:
            topology_manager.resolve_all(file_config, dfs)
        except Exception as e:
            print(f"Topology Manager Error: {e}")
            # On continue quand même, avec les infos partielles du JSON
        
        for plan in file_config.plans:
            try:
                res = calculate(plan, file_config, dfs, global_tx_map)
                ds = res.get("data_settings", {})
                
                # Check error status
                if res.get("status", "").startswith("error"):
                    results.append(res)
                    continue

                if ds.get("kVnom_busfrom", 0) == 0 and ds.get("kVnom", 0) == 0: 
                    # Silent skip or log? Let's log info
                    res["status"] = "skipped (no kV)"
                    results.append(res)
                    continue 
                
                res["plan_id"] = plan.id
                res["plan_type"] = plan.type
                res["source_file"] = filename
                results.append(res)
            except Exception as e:
                # C'EST ICI QU'ON EVITE LE 500
                err_msg = str(e)
                traceback.print_exc()
                results.append({
                    "plan_id": plan.id, 
                    "source_file": filename, 
                    "status": "CRASH", 
                    "comments": [f"Internal Calculation Error: {err_msg}"]
                })
    return results

def generate_excel(results: List[dict]) -> bytes:
    flat_rows = []
    for res in results:
        row = {"Source File": res.get("source_file"), "Plan ID": res.get("plan_id"), "Type": res.get("plan_type"), "Status": res.get("status")}
        thresh = res.get("calculated_thresholds", {})
        row["Calc_Pickup_I1"] = thresh.get("pickup_amps")
        row["Calc_Backup_I2"] = thresh.get("backup_amps")
        ds = res.get("data_settings", {})
        ds_clean = {k: v for k, v in ds.items() if k not in ["raw_data_from", "raw_data_to"]}
        flat_ds = flatten_dict(ds_clean, parent_key="DS")
        row.update(flat_ds)
        
        # Ajout des erreurs dans l'excel si crash
        if "comments" in res and res["comments"]:
            row["Error_Logs"] = str(res["comments"])

        flat_rows.append(row)
    df = pd.DataFrame(flat_rows)
    if "Plan ID" in df.columns: df = df.sort_values(by=["Plan ID", "Source File"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Data Settings", index=False)
    return output.getvalue()
