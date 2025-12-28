
from app.schemas.protection import ProtectionPlan, GlobalSettings, ProjectConfig
from app.services import session_manager
from app.calculations import db_converter, topology_manager
import pandas as pd
import io
import copy
from typing import List

# --- HELPER INTERNE ---
def _is_supported_protection(fname: str) -> bool:
    e = fname.lower()
    return e.endswith('.si2s') or e.endswith('.mdb')

def find_bus_data(dfs_dict: dict, bus_name: str, table_names: list = ["SCIECLGSum1", "SC_SUM_1"]):
    """
    Cherche et retourne la ligne de données pour un bus donné dans les tables de court-circuit.
    """
    if not bus_name:
        return None

    target_df = None
    found_table = None
    
    for name in table_names:
        for key in dfs_dict.keys():
            if key.lower() == name.lower():
                target_df = dfs_dict[key]
                found_table = key
                break
        if target_df is not None:
            break
            
    if target_df is None:
        return {"error": "Table SCIECLGSum1 introuvable"}

    try:
        col_bus = next((c for c in target_df.columns if c.lower() == 'faultedbus'), None)
        if not col_bus:
            return {"error": f"Colonne 'FaultedBus' absente de {found_table}"}
            
        row = target_df[target_df[col_bus].astype(str).str.strip().str.upper() == str(bus_name).strip().upper()]
        
        if row.empty:
            return None
            
        data = row.iloc[0].where(pd.notnull(row.iloc[0]), None).to_dict()
        return data

    except Exception as e:
        return {"error": f"Erreur lecture: {str(e)}"}

def calculate(plan: ProtectionPlan, settings: GlobalSettings, dfs_dict: dict) -> dict:
    """
    Logique unitaire ANSI 51 (pour UN plan et UN jeu de données).
    """
    bus_amont = plan.bus_from
    bus_aval = plan.bus_to
    
    topology_info = {
        "source_origin": plan.topology_origin,
        "bus_from": bus_amont,
        "bus_to": bus_aval
    }

    data_from = find_bus_data(dfs_dict, bus_amont)
    data_to = find_bus_data(dfs_dict, bus_aval)
    
    data_si2s_section = {
        "FaultedBus_bus_from": bus_amont,
        "bus_from_data": data_from if data_from else "N/A",
        "FaultedBus_bus_to": bus_aval,
        "bus_to_data": data_to if data_to else "N/A"
    }

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
            "Fdata_si2s": "TBD (ex: Inom Transfo, Ampacity Câble)",
            "Fcalculation": f"TBD (ex: {std_51_cfg.coeff_stab_max} * Inom)",
            "Ftime": "Long Time / Inverse Curve",
            "Fremark": "Protection surcharge thermique"
        },
        # ... (Autres formules placeholders)
    }

    status = "computed"
    comments = []
    
    if not bus_aval or not bus_amont:
        status = "error_topology"
        comments.append("❌ Topologie incomplète")
    elif isinstance(data_to, dict) and "error" in data_to:
        status = "warning_data"
        comments.append(f"⚠️ {data_to['error']}")
    else:
        comments.append(f"✅ Topologie OK : {bus_amont} -> {bus_aval}")
        if data_to: comments.append("✅ Données Isc Bus Aval récupérées")
        else: comments.append("⚠️ Pas de données Isc pour le Bus Aval")

    return {
        "ansi_code": "51",
        "status": status,
        "topology_used": topology_info,
        "data_si2s": data_si2s_section,
        "config": config_section,
        "formulas": formulas_section,
        "calculated_thresholds": {"pickup_amps": 0.0, "time_dial": 0.0},
        "comments": comments
    }

# --- LOGIQUE BATCH (ORCHESTRATEUR) ---

def run_batch_logic(config: ProjectConfig, token: str) -> List[dict]:
    """
    Exécute le calcul ANSI 51 pour tous les plans sur tous les fichiers SI2S trouvés.
    """
    files = session_manager.get_files(token)
    results = []
    
    for filename, content in files.items():
        if not _is_supported_protection(filename): 
            continue
            
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        file_config = copy.deepcopy(config)
        topology_manager.resolve_all(file_config, dfs)
        
        for plan in file_config.plans:
            try:
                # Appel de la fonction calculate définie plus haut
                res = calculate(plan, file_config.settings, dfs)
                
                res["plan_id"] = plan.id
                res["plan_type"] = plan.type
                res["source_file"] = filename
                results.append(res)
            except Exception as e:
                results.append({
                    "plan_id": plan.id,
                    "plan_type": plan.type,
                    "source_file": filename,
                    "ansi_code": "51",
                    "status": "error",
                    "comments": [f"Error in {filename}: {str(e)}"]
                })
    return results

# --- GENERATEUR EXCEL ---

def generate_excel(results: List[dict]) -> bytes:
    flat_rows = []
    for res in results:
        row = {
            "Source File": res.get("source_file"),
            "Plan ID": res.get("plan_id"),
            "Type": res.get("plan_type"),
            "Status": res.get("status"),
            "Bus From": res.get("topology_used", {}).get("bus_from"),
            "Bus To": res.get("topology_used", {}).get("bus_to"),
        }
        thresh = res.get("calculated_thresholds", {})
        row["Pickup (A)"] = thresh.get("pickup_amps")
        row["Time Dial"] = thresh.get("time_dial")
        row["Comments"] = " | ".join(res.get("comments", []))

        data_section = res.get("data_si2s", {})
        
        from_data = data_section.get("bus_from_data")
        if isinstance(from_data, dict):
            for k, v in from_data.items(): row[f"FROM_{k}"] = v
        
        to_data = data_section.get("bus_to_data")
        if isinstance(to_data, dict):
            for k, v in to_data.items(): row[f"TO_{k}"] = v

        flat_rows.append(row)

    df = pd.DataFrame(flat_rows)
    cols = list(df.columns)
    prio_cols = ["Source File", "Plan ID", "Type", "Status", "Bus From", "Bus To", "Pickup (A)"]
    final_cols = [c for c in prio_cols if c in cols] + [c for c in cols if c not in prio_cols]
    df = df[final_cols]
    
    if "Plan ID" in df.columns and "Source File" in df.columns:
        df = df.sort_values(by=["Plan ID", "Source File"])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Full Data Results", index=False)
        ws = writer.sheets["Full Data Results"]
        for col in ws.columns:
            try: ws.column_dimensions[col[0].column_letter].width = 18
            except: pass
    return output.getvalue()
