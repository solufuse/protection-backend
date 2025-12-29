
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
    
    # [decision:logic] EXECUTE COMMON SCRIPT LOGIC
    # This extracts In, Ik, Inrush, etc. using the shared 'common' library
    common_data = common.get_electrical_parameters(plan, full_config, dfs_dict, global_tx_map)
    
    thresholds_structure = {}
    
    if plan.type.upper() == "TRANSFORMER":
        # --- DATA EXTRACTION FROM COMMON ---
        in_prim_tap = common_data.get("In_prim_TapMin", 0)
        ik2min_ref = common_data.get("Ik2min_sec_ref", 0)
        mva_tx = common_data.get("mva_tx [MVA]", 0)
        min_tap = common_data.get("Min%Tap_val [Min%Tap]", 0)
        inrush_900 = common_data.get("inrush_900ms", 0)

        # --- I1 (OVERLOAD) ---
        pickup_i1 = round(std_51.factor_I1 * in_prim_tap, 2)
        
        thresholds_structure["I1_overloads"] = {
            "I1_data_si2s": {
                "mva_tx": mva_tx,
                "Min_Tap_Percent": min_tap,
                "In_prim_TapMin": in_prim_tap,
                "inrush_900ms": inrush_900
            },
            "I1_report": {
                "pickup_amps": pickup_i1,
                "time_dial": std_51.time_dial_I1.value, 
                "curve_type": std_51.time_dial_I1.curve,
                "equation_logic": f"Factor_I1 ({std_51.factor_I1}) * In_prim_TapMin",
                "calculated_formula": f"{std_51.factor_I1} * {in_prim_tap} = {pickup_i1} A"
            }
        }

        # --- I2 (BACKUP) ---
        backup_i2 = round(std_51.factor_I2 * (ik2min_ref * 1000), 2)
        
        thresholds_structure["I2_backup"] = {
            "I2_data_si2s": {
                "Ik2min_sec_ref_kA": ik2min_ref,
                "Backup_Factor": std_51.factor_I2
            },
            "I2_report": {
                "pickup_amps": backup_i2,
                "time_dial": std_51.time_dial_I2.value,
                "curve_type": std_51.time_dial_I2.curve,
                "equation_logic": f"Factor_I2 ({std_51.factor_I2}) * Ik2min_sec_ref",
                "calculated_formula": f"{std_51.factor_I2} * {round(ik2min_ref*1000, 2)} = {backup_i2} A"
            }
        }

    else:
        # --- CAS HORS TRANSFO (Incomer / Coupling) ---
        in_ref = common_data.get("In_prim_Un", 0)
        pickup_i1 = round(1.0 * in_ref, 2)
        
        thresholds_structure["I1_overloads"] = {
            "I1_data_si2s": { "In_Ref": in_ref },
            "I1_report": {
                "pickup_amps": pickup_i1,
                "time_dial": std_51.time_dial_I1.value,
                "curve_type": std_51.time_dial_I1.curve,
                "equation_logic": "1.0 * In_Ref",
                "calculated_formula": f"1.0 * {in_ref} = {pickup_i1} A"
            }
        }

    status = "computed"
    if common_data.get("kVnom_busfrom") == 0: status = "warning_data (kV=0)"

    # Topology Reporting
    topo_origin = getattr(plan, "topology_origin", "unknown")

    return {
        "ansi_code": "51",
        "status": status,
        "topology_used": {
            "origin": topo_origin,
            "bus_from": common_data.get("Bus_Prim"),
            "bus_to": common_data.get("Bus_Sec")
        },
        "config": { 
            "settings": { "std_51": std_51.dict() }, 
            "type": plan.type, 
            "ct_primary": plan.ct_primary 
        },
        "thresholds": thresholds_structure,
        # [!] KEY RENAMED TO 'common_data' TO MATCH /protection/common/run
        "common_data": common_data, 
        "comments": []
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
        
        try:
            topology_manager.resolve_all(file_config, dfs)
        except Exception as e:
            print(f"Topology Error (Non-blocking): {e}")

        for plan in file_config.plans:
            try:
                res = calculate(plan, file_config, dfs, global_tx_map)
                
                if res.get("status", "").startswith("error"):
                    results.append(res)
                    continue
                
                ds = res.get("common_data", {})
                if ds.get("kVnom_busfrom", 0) == 0 and ds.get("kVnom", 0) == 0: 
                    continue 
                
                res["plan_id"] = plan.id
                res["plan_type"] = plan.type
                res["source_file"] = filename
                results.append(res)
            except Exception as e:
                traceback.print_exc()
                results.append({
                    "plan_id": plan.id, 
                    "source_file": filename, 
                    "status": "CRASH", 
                    "comments": [f"Error: {str(e)}"]
                })
    return results

def generate_excel(results: List[dict]) -> bytes:
    flat_rows = []
    for res in results:
        topo = res.get("topology_used", {})
        row = {
            "Source File": res.get("source_file"),
            "Plan ID": res.get("plan_id"),
            "Type": res.get("plan_type"),
            "Status": res.get("status"),
            "Topo_Origin": topo.get("origin"),
            "Topo_BusFrom": topo.get("bus_from")
        }
        
        thresholds = res.get("thresholds", {})
        
        # I1
        i1 = thresholds.get("I1_overloads", {}).get("I1_report", {})
        row["I1_Pickup"] = i1.get("pickup_amps")
        row["I1_TimeDial"] = i1.get("time_dial")
        row["I1_Curve"] = i1.get("curve_type")
        row["I1_Formula"] = i1.get("calculated_formula")
        
        # I2
        i2 = thresholds.get("I2_backup", {}).get("I2_report", {})
        row["I2_Pickup"] = i2.get("pickup_amps")
        row["I2_TimeDial"] = i2.get("time_dial")
        row["I2_Curve"] = i2.get("curve_type")
        row["I2_Formula"] = i2.get("calculated_formula")

        # Electrical Data (From common_data)
        ds = res.get("common_data", {})
        ds_clean = {k: v for k, v in ds.items() if k not in ["raw_data_from", "raw_data_to"]}
        flat_ds = flatten_dict(ds_clean, parent_key="DS")
        row.update(flat_ds)
        
        if "comments" in res and res["comments"]:
            row["Error_Logs"] = str(res["comments"])

        flat_rows.append(row)
    
    df = pd.DataFrame(flat_rows)
    if "Plan ID" in df.columns: df = df.sort_values(by=["Plan ID", "Source File"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Protection Data", index=False)
        for col in writer.sheets["Protection Data"].columns:
            try: writer.sheets["Protection Data"].column_dimensions[col[0].column_letter].width = 18
            except: pass

    return output.getvalue()
