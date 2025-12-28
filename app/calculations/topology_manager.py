
import pandas as pd
from app.schemas.protection import ProjectConfig, ProtectionPlan

def resolve_all(config: ProjectConfig, dfs_dict: dict) -> ProjectConfig:
    """
    SAFE MODE:
    1. Si l'utilisateur a rempli 'bus_from'/'bus_to' dans le JSON -> ON GARDE (Priorité Absolue).
    2. Si c'est vide -> ON CHERCHE dans la base de données.
    """
    
    # 1. Scan des bus disponibles dans ETAP
    available_buses = []
    for k, df in dfs_dict.items():
        cols = [c.lower() for c in df.columns]
        target_col = None
        if "faultedbus" in cols: target_col = next(c for c in df.columns if c.lower() == "faultedbus")
        elif "id" in cols: target_col = next(c for c in df.columns if c.lower() == "id")
        
        if target_col:
            available_buses.extend(df[target_col].astype(str).unique().tolist())
    
    available_buses = list(set(available_buses))

    for plan in config.plans:
        # --- BUS FROM (Amont) ---
        if plan.bus_from:
            # CAS A : L'utilisateur a donné l'info
            plan.topology_origin = "manual_config"
            # On ne fait rien, on garde ta valeur.
        else:
            # CAS B : C'est vide, on cherche
            clean_id = plan.id.replace("CB_", "").strip()
            match_from = next((b for b in available_buses if clean_id.upper() in b.upper()), None)
            
            if match_from:
                plan.bus_from = match_from
                plan.topology_origin = "script_auto_fill"
                plan.debug_info = f"Auto-filled From: {match_from}"
            else:
                plan.topology_origin = "missing"

        # --- BUS TO (Aval) ---
        if plan.bus_to:
            # CAS A : L'utilisateur a donné l'info
            pass 
        else:
            # CAS B : C'est vide.
            # Petite tentative intelligente pour les Transfos :
            # Si on a trouvé le bus amont (ex: "Bus HV"), on cherche un bus qui ressemble mais "MV"
            if plan.type == "TRANSFORMER" and plan.bus_from:
                # Logique simple : on cherche un bus qui contient le nom du plan mais pas le nom du bus from
                pass 

    return config
