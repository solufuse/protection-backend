
from app.schemas.protection import ProtectionPlan, GlobalSettings
import pandas as pd
import math

def find_bus_data(dfs_dict: dict, bus_name: str, table_names: list = ["SCIECLGSum1", "SC_SUM_1"]):
    """
    Cherche les données d'un bus spécifique dans les tables de court-circuit fournies.
    """
    if not bus_name:
        return None

    # 1. Trouver la table disponible
    target_df = None
    found_table_name = None
    for name in table_names:
        # Recherche insensible à la casse
        for key in dfs_dict.keys():
            if key.lower() == name.lower():
                target_df = dfs_dict[key]
                found_table_name = key
                break
        if target_df is not None:
            break
    
    if target_df is None:
        return {"error": f"Tables {table_names} introuvables dans le fichier source."}

    # 2. Chercher la ligne du bus (colonne FaultedBus)
    # On nettoie les espaces et on met en majuscules pour comparer
    try:
        # On suppose que la colonne s'appelle 'FaultedBus' (standard ETAP)
        col_bus = next((c for c in target_df.columns if c.lower() == 'faultedbus'), None)
        if not col_bus:
            return {"error": f"Colonne 'FaultedBus' introuvable dans {found_table_name}"}

        # Filtrage
        row = target_df[target_df[col_bus].astype(str).str.strip().str.upper() == str(bus_name).strip().upper()]
        
        if row.empty:
            return None # Bus non trouvé dans l'étude CC
        
        # Conversion en dictionnaire (première ligne trouvée)
        return row.iloc[0].to_dict()

    except Exception as e:
        return {"error": f"Erreur lors de la lecture: {str(e)}"}

def calculate(plan: ProtectionPlan, settings: GlobalSettings, dfs_dict: dict) -> dict:
    """
    ANSI 51 Calculation Logic avec Data Fetching
    """
    
    results = {
        "ansi_code": "51",
        "status": "TBD",
        "topology_used": {},
        "data_si2s": {},
        "config": {},
        "formulas": {},
        "calculated_thresholds": {"pickup_amps": 0, "time_dial": 0},
        "comments": []
    }

    # --- 1. TOPOLOGIE ---
    bus_amont = plan.bus_from
    bus_aval = plan.bus_to
    
    results["topology_used"] = {
        "source_origin": plan.topology_origin,
        "bus_from": bus_amont,
        "bus_to": bus_aval
    }

    if not bus_aval or not bus_amont:
        results["status"] = "error_topology"
        results["comments"].append("❌ Erreur : Bus Amont ou Aval manquant.")
        return results

    results["comments"].append(f"✅ Topologie OK : {bus_amont} -> {bus_aval}")

    # --- 2. DATA SI2S (EXTRACTION) ---
    # On va chercher la ligne complète pour le bus amont et le bus aval
    data_from = find_bus_data(dfs_dict, bus_amont)
    data_to = find_bus_data(dfs_dict, bus_aval)
    
    results["data_si2s"] = {
        "bus_from_tag": bus_amont,
        "bus_from_data": data_from if data_from else "Données non trouvées dans SCIECLGSum1",
        "bus_to_tag": bus_aval,
        "bus_to_data": data_to if data_to else "Données non trouvées dans SCIECLGSum1"
    }

    # --- 3. CONFIG & SETTINGS ---
    # On injecte les réglages utilisés pour référence
    results["config"] = {
        "settings": {
            "std_51": settings.std_51.dict()
        },
        "type": plan.type # TRANSFORMER, FEEDER, etc.
    }

    # --- 4. FORMULAS (PLACEHOLDERS) ---
    # Structure demandée pour les calculs futurs
    results["formulas"] = {
        "F_I1_overloads": {
            "Fdata_si2s": "A définir (ex: Inom du transfo, Ampacity du câble)",
            "Fcalculation": "A définir (ex: 1.2 * Inom)",
            "Ftime": "A définir (ex: courbe inverse)",
            "Fremark": "Protection contre les surcharges"
        },
        "F_I2_phase_short_circuit": {
             "Fdata_si2s": "A définir (ex: Isc_min bus aval)",
             "Fcalculation": "A définir (ex: 0.8 * Isc_min)",
             "Ftime": "Instantaneous ou Short Time",
             "Fremark": "Protection court-circuit (sélectivité)"
        },
        # Tu peux ajouter I3, I4 ici...
    }

    # --- 5. CALCUL (SIMULATION) ---
    # Si on a trouvé les données, on met le statut à 'computed' (même si le calcul est fake pour l'instant)
    if data_to and isinstance(data_to, dict) and "error" not in data_to:
        results["status"] = "computed"
        
        # Exemple d'utilisation d'une valeur réelle extraite
        # Imaginons qu'on veuille Isc 3ph (Ik3ph)
        if "Ik3ph" in data_to:
            isc_val = data_to["Ik3ph"]
            results["comments"].append(f"ℹ️ Info: Isc 3ph sur bus aval = {isc_val} kA")
    else:
        results["status"] = "warning_no_data"
        results["comments"].append("⚠️ Attention : Impossible de récupérer les données électriques pour le calcul.")

    return results
