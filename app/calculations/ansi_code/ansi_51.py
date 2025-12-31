from app.schemas.protection import ProtectionPlan, GlobalSettings, ProjectConfig
from app.calculations import db_converter, topology_manager
from app.calculations.ansi_code import common
import pandas as pd
import io
import copy
from typing import List, Dict, Any
import traceback
import re

def flatten_dict(d: Dict, parent_key: str = '', sep: str = '_') -> Dict:
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict): items.extend(flatten_dict(v, new_key, sep=sep).items())
        else: items.append((new_key, v))
    return dict(items)

def parse_ct_value(ct_str: str) -> float:
    try:
        match = re.search(r"(\d+)", str(ct_str))
        return float(match.group(1)) if match else 0.0
    except: return 0.0

def calculate(plan: ProtectionPlan, full_config: ProjectConfig, dfs_dict: dict, global_tx_map: dict) -> dict:
    
    # 1. Select Settings by Type
    ptype = plan.type.upper()
    if ptype == "TRANSFORMER":
        std_51 = full_config.settings.ansi_51.transformer
    elif ptype == "INCOMER":
        std_51 = full_config.settings.ansi_51.incomer
    elif ptype == "COUPLING":
        std_51 = full_config.settings.ansi_51.coupling
    else:
        std_51 = full_config.settings.ansi_51.transformer

    # 2. Electrical Data
    common_data = common.get_electrical_parameters(plan, full_config, dfs_dict, global_tx_map)
    thresholds_structure = {}
    ct_prim_val = parse_ct_value(plan.ct_primary)

    # --- TRANSFORMER LOGIC ---
    if ptype == "TRANSFORMER":
        in_prim_tap = common_data.get("In_prim_TapMin", 0)
        ik2min_ref = common_data.get("Ik2min_sec_ref", 0)
        mva_tx = common_data.get("mva_tx [MVA]", 0)
        min_tap = common_data.get("Min%Tap_val [Min%Tap]", 0)
        inrush_900 = common_data.get("inrush_900ms", 0)
        inrush_50 = common_data.get("inrush_50ms", 0)
        ik3max_sec_ref = common_data.get("Ik3max_sec_ref", 0)
        
        # Primary SC (kA -> A)
        ik2min_prim_raw = 0
        for k, v in common_data.items():
            if "Ik2min_prim" in k and isinstance(v, (int, float)):
                ik2min_prim_raw = v; break
        ik2min_prim_amps = ik2min_prim_raw * 1000 if ik2min_prim_raw < 500 else ik2min_prim_raw

        # I1 (Thermal)
        pickup_i1 = round(std_51.factor_I1 * in_prim_tap, 2)
        thresholds_structure["I1_overloads"] = {
            "I1_data_si2s": {
                "mva_tx": mva_tx, "Min_Tap_Percent": min_tap, "In_prim_TapMin": in_prim_tap, "inrush_900ms": inrush_900
            },
            "I1_report": {
                "pickup_amps": pickup_i1, "time_dial": std_51.time_dial_I1.value, "curve_type": std_51.time_dial_I1.curve,
                "calculated_formula": f"{std_51.factor_I1} * {in_prim_tap} = {pickup_i1} A",
                "methodology_note": f"Thermal Overload: Set to {int((std_51.factor_I1-1)*100)}% above max nominal current ({in_prim_tap}A)."
            }
        }

        # I2 (Backup)
        if ik2min_ref > 0:
            backup_i2 = round(std_51.factor_I2 * (ik2min_ref * 1000), 2)
            thresholds_structure["I2_backup"] = {
                "I2_data_si2s": { "Ik2min_sec_ref_kA": ik2min_ref, "Backup_Factor": std_51.factor_I2 },
                "I2_report": {
                    "pickup_amps": backup_i2, "time_dial": std_51.time_dial_I2.value, "curve_type": std_51.time_dial_I2.curve,
                    "calculated_formula": f"{std_51.factor_I2} * {round(ik2min_ref*1000, 2)} = {backup_i2} A",
                    "methodology_note": f"Distance Backup: Set to {int(std_51.factor_I2*100)}% of min end-of-line SC ({round(ik2min_ref*1000, 2)}A)."
                }
            }
            
        # I4 Context
        i4_base_current = in_prim_tap
        i4_base_name = "In_Transfo"
        i4_data_context = {
            "CT_Primary": ct_prim_val,
            "In_Transfo_Max": in_prim_tap,
            "Limit_Low_Inrush_50ms": inrush_50,
            "Limit_Low_IkSec_Max": round(ik3max_sec_ref * 1000, 2) if ik3max_sec_ref else 0,
            "Limit_High_IkPrim_Min": round(ik2min_prim_amps, 2)
        }

    # --- GENERIC LOGIC ---
    else:
        in_ref = common_data.get("In_prim_Un", 0) or ct_prim_val
        pickup_i1 = round(std_51.factor_I1 * in_ref, 2)
        thresholds_structure["I1_overloads"] = {
            "I1_data_si2s": { "In_Ref": in_ref },
            "I1_report": {
                "pickup_amps": pickup_i1, "time_dial": std_51.time_dial_I1.value, "curve_type": std_51.time_dial_I1.curve,
                "calculated_formula": f"{std_51.factor_I1} * {in_ref} = {pickup_i1} A",
                "methodology_note": f"Standard: Set based on nominal current ({in_ref}A)."
            }
        }
        i4_base_current = ct_prim_val
        i4_base_name = "CT_Primary"
        i4_data_context = {"CT_Primary": ct_prim_val}

    # --- I4 (HIGH SET) ---
    if std_51.factor_I4 > 2.0: 
        # [!] GENERIC LOGIC: Uses Config Factor * Base
        highset_i4 = round(std_51.factor_I4 * i4_base_current, 2)
        
        meth_text = "High-Set Instantaneous."
        if ptype == "TRANSFORMER":
            meth_text = "Ampere Selectivity: Must be > Inrush ({}A) and > Max Secondary SC ({}A), but < Min Primary SC ({}A). Based on {}.".format(
                i4_data_context.get("Limit_Low_Inrush_50ms"),
                i4_data_context.get("Limit_Low_IkSec_Max"),
                i4_data_context.get("Limit_High_IkPrim_Min"),
                i4_base_name
            )

        thresholds_structure["I4_highset"] = {
            "I4_data": i4_data_context,
            "I4_report": {
                "pickup_amps": highset_i4, "time_dial": std_51.time_dial_I4.value, "curve_type": std_51.time_dial_I4.curve,
                "calculated_formula": f"{std_51.factor_I4} * {i4_base_current} ({i4_base_name}) = {highset_i4} A",
                "methodology_note": meth_text
            }
        }

    status = "computed"
    if common_data.get("kVnom_busfrom") == 0: status = "warning_data (kV=0)"

    return {
        "ansi_code": "51",
        "status": status,
        "topology_used": {
            "origin": getattr(plan, "topology_origin", "unknown"),
            "bus_from": common_data.get("Bus_Prim"),
            "bus_to": common_data.get("Bus_Sec")
        },
        "config": { 
            "settings_used": std_51.dict(), 
            "type": plan.type, 
            "ct_primary": plan.ct_primary 
        },
        "thresholds": thresholds_structure,
        "common_data": common_data, 
        "comments": []
    }

def run_batch_logic(config: ProjectConfig, files: Dict[str, bytes]) -> List[dict]:
    global_tx_map = common.build_global_transformer_map(files)
    results = []
    
    for filename, content in files.items():
        if not common.is_supported_protection(filename): continue
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        file_config = copy.deepcopy(config)
        try: topology_manager.resolve_all(file_config, dfs)
        except Exception as e: print(f"Topology Error: {e}")

        for plan in file_config.plans:
            try:
                res = calculate(plan, file_config, dfs, global_tx_map)
                if res.get("status", "").startswith("error"): results.append(res); continue
                ds = res.get("common_data", {})
                if ds.get("kVnom_busfrom", 0) == 0 and ds.get("kVnom", 0) == 0: continue 
                
                res["plan_id"] = plan.id; res["plan_type"] = plan.type; res["source_file"] = filename
                results.append(res)
            except Exception as e:
                traceback.print_exc()
                results.append({"plan_id": plan.id, "source_file": filename, "status": "CRASH", "comments": [f"Error: {str(e)}"]})
    return results

def generate_excel(results: List[dict]) -> bytes:
    flat_rows = []
    for res in results:
        topo = res.get("topology_used", {})
        row = {
            "Source File": res.get("source_file"), "Plan ID": res.get("plan_id"), "Type": res.get("plan_type"),
            "Status": res.get("status"), "Topo_Origin": topo.get("origin")
        }
        thresholds = res.get("thresholds", {})
        
        def add_th(key, prefix):
            rep = thresholds.get(key, {}).get(f"{prefix}_report", {})
            if rep:
                row[f"{prefix}_Pickup"] = rep.get("pickup_amps")
                row[f"{prefix}_Time"] = rep.get("time_dial")
                row[f"{prefix}_Curve"] = rep.get("curve_type")
                row[f"{prefix}_Formula"] = rep.get("calculated_formula")
                row[f"{prefix}_Note"] = rep.get("methodology_note")

        add_th("I1_overloads", "I1")
        add_th("I2_backup", "I2")
        add_th("I4_highset", "I4")

        ds = res.get("common_data", {})
        ds_clean = {k: v for k, v in ds.items() if k not in ["raw_data_from", "raw_data_to"]}
        flat_ds = flatten_dict(ds_clean, parent_key="DS")
        row.update(flat_ds)
        flat_rows.append(row)
    
    df = pd.DataFrame(flat_rows)
    if "Plan ID" in df.columns: df = df.sort_values(by=["Plan ID", "Source File"])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Protection Data", index=False)
        for col in writer.sheets["Protection Data"].columns:
            try: writer.sheets["Protection Data"].column_dimensions[col[0].column_letter].width = 25
            except: pass
    return output.getvalue()