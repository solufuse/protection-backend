
from app.schemas.protection import ProtectionPlan, GlobalSettings
import pandas as pd

def calculate(plan: ProtectionPlan, settings: GlobalSettings, dfs_dict: dict) -> dict:
    """
    Executes the ANSI 51 (Time Overcurrent) calculation logic.
    STRICT RULE: Uses bus_from and bus_to determined by topology_manager.
    """
    
    results = {
        "ansi_code": "51",
        "status": "TBD",
        "topology_used": {},
        "calculated_thresholds": {},
        "comments": []
    }

    # 1. RECUPERATION DE LA TOPOLOGIE (Priorité absolue au topology_manager)
    # Le plan a déjà été enrichi par topology_manager.resolve_all() avant d'arriver ici.
    bus_amont = plan.bus_from
    bus_aval = plan.bus_to
    
    results["topology_used"] = {
        "source_origin": plan.topology_origin, # ex: 'script_topo' ou 'config_user'
        "bus_from": bus_amont,
        "bus_to": bus_aval
    }

    if not bus_aval:
        results["status"] = "error"
        results["comments"].append("❌ Erreur Topologie : Aucun bus aval identifié par le Topology Manager.")
        return results

    results["comments"].append(f"✅ Topologie OK : Protection située entre {bus_amont} et {bus_aval}.")

    # 2. EXEMPLE : RECUPERATION DONNEES ELECTRIQUES (Placeholder)
    # Ici, on irait chercher dans dfs_dict['LF_BUS'] ou 'CC_BUS' les infos du bus_aval
    # ex: Isc_max sur bus_aval
    
    # coeff_stab = settings.std_51.coeff_stab_max
    # results["comments"].append(f"Utilisation Coeff Stab: {coeff_stab}")

    # TODO: Coder la vraie logique physique ici en utilisant bus_aval
    
    results["status"] = "computed"
    results["calculated_thresholds"] = {
        "pickup_amps": 0.0, # A calculer
        "time_dial": 0.0    # A calculer
    }

    return results
