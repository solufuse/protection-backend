
from app.schemas.protection import ProtectionPlan, GlobalSettings
import pandas as pd

def find_bus_data(dfs_dict: dict, bus_name: str, table_names: list = ["SCIECLGSum1", "SC_SUM_1"]):
    """
    Cherche et retourne la ligne de données pour un bus donné dans les tables de court-circuit.
    """
    if not bus_name:
        return None

    target_df = None
    found_table = None
    
    # 1. Identification de la table
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

    # 2. Recherche de la ligne
    try:
        col_bus = next((c for c in target_df.columns if c.lower() == 'faultedbus'), None)
        if not col_bus:
            return {"error": f"Colonne 'FaultedBus' absente de {found_table}"}
            
        # Filtrage insensible à la casse et aux espaces
        row = target_df[target_df[col_bus].astype(str).str.strip().str.upper() == str(bus_name).strip().upper()]
        
        if row.empty:
            return None # Bus non trouvé (peut-être pas de faute simulée sur ce bus)
            
        # Conversion en dictionnaire natif (gestion des NaN pour le JSON)
        data = row.iloc[0].where(pd.notnull(row.iloc[0]), None).to_dict()
        return data

    except Exception as e:
        return {"error": f"Erreur lecture: {str(e)}"}

def calculate(plan: ProtectionPlan, settings: GlobalSettings, dfs_dict: dict) -> dict:
    """
    Logique ANSI 51 avec structure JSON étendue.
    """
    
    # --- 1. TOPOLOGIE ---
    bus_amont = plan.bus_from
    bus_aval = plan.bus_to
    
    topology_info = {
        "source_origin": plan.topology_origin,
        "bus_from": bus_amont,
        "bus_to": bus_aval
    }

    # --- 2. DATA SI2S (Fetching) ---
    data_from = find_bus_data(dfs_dict, bus_amont)
    data_to = find_bus_data(dfs_dict, bus_aval)
    
    data_si2s_section = {
        "FaultedBus_bus_from": bus_amont,
        "bus_from_data": data_from if data_from else "N/A",
        "FaultedBus_bus_to": bus_aval,
        "bus_to_data": data_to if data_to else "N/A"
    }

    # --- 3. CONFIGURATION ---
    # On récupère les facteurs définis dans config.json pour les afficher
    # On gère le cas où std_51 serait incomplet via des valeurs par défaut si besoin
    std_51_cfg = settings.std_51
    
    config_section = {
        "settings": {
            "std_51": {
                "factor_I1": std_51_cfg.coeff_stab_max, # Mapping temporaire, à ajuster selon ton modèle Pydantic
                "factor_I2": std_51_cfg.coeff_backup_min, # Idem
                # Si ton modèle GlobalSettings a des champs dynamiques, on peut les lister ici
                "details": std_51_cfg.dict()
            }
        },
        "type": plan.type,
        "ct_primary": plan.ct_primary
    }

    # --- 4. FORMULES (Squelette) ---
    # C'est ici qu'on implémentera ta logique mathématique spécifique plus tard
    formulas_section = {
        "F_I1_overloads": {
            "Fdata_si2s": "TBD (ex: Inom Transfo, Ampacity Câble)",
            "Fcalculation": f"TBD (ex: {std_51_cfg.coeff_stab_max} * Inom)",
            "Ftime": "Long Time / Inverse Curve",
            "Fremark": "Protection surcharge thermique"
        },
        "F_I2_phase_short-circuit": {
            "Fdata_si2s": "TBD (ex: Isc Min Bus Aval)",
            "Fcalculation": "TBD",
            "Ftime": "Short Time / Definite Time",
            "Fremark": "Protection court-circuit sélective"
        },
        "F_I3_phase_short-circuit": {
            "Fdata_si2s": "TBD",
            "Fcalculation": "TBD",
            "Ftime": "Instantaneous",
            "Fremark": "Protection haut débit (si applicable)"
        },
        "F_I4_phase_short-circuit": {
            "Fdata_si2s": "TBD",
            "Fcalculation": "TBD",
            "Ftime": "TBD",
            "Fremark": "Etage supplémentaire (si applicable)"
        }
    }

    # --- 5. RESULTATS FINAUX ---
    # Validation basique
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
        if data_to:
            comments.append("✅ Données Isc Bus Aval récupérées")
        else:
            comments.append("⚠️ Pas de données Isc pour le Bus Aval")

    return {
        "ansi_code": "51",
        "status": status,
        "topology_used": topology_info,
        "data_si2s": data_si2s_section,
        "config": config_section,
        "formulas": formulas_section,
        "calculated_thresholds": {
            "pickup_amps": 0.0, # Placeholder
            "time_dial": 0.0    # Placeholder
        },
        "comments": comments
    }
