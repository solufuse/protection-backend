
import pandas as pd
from app.schemas.protection import ProjectConfig, ProtectionPlan

def resolve_all(config: ProjectConfig, dfs_dict: dict) -> ProjectConfig:
    """
    SAFE MODE:
    1. Si l'utilisateur a rempli 'bus_from' -> ON GARDE.
    2. Si c'est vide -> ON CHERCHE.
    """
    available_buses = []
    for k, df in dfs_dict.items():
        cols = [c.lower() for c in df.columns]
        target_col = None
        if "faultedbus" in cols: target_col = next(c for c in df.columns if c.lower() == "faultedbus")
        elif "id" in cols: target_col = next(c for c in df.columns if c.lower() == "id")
        if target_col: available_buses.extend(df[target_col].astype(str).unique().tolist())
    available_buses = list(set(available_buses))

    for plan in config.plans:
        # Si User a défini, on note et on passe
        if plan.bus_from:
            plan.topology_origin = "manual_config"
            continue

        # Sinon, on cherche
        clean_id = plan.id.replace("CB_", "").strip()
        match_from = next((b for b in available_buses if clean_id.upper() in b.upper()), None)
        
        if match_from:
            plan.bus_from = match_from
            plan.topology_origin = "script_auto_fill"
        else:
            plan.topology_origin = "missing"

    return config
