
import pandas as pd
from app.schemas.protection import ProjectConfig, ProtectionPlan

def resolve_all(config: ProjectConfig, dfs_dict: dict) -> ProjectConfig:
    """
    ROLLBACK VERSION (SAFE MODE).
    Règle d'or : On ne touche JAMAIS à une valeur saisie par l'utilisateur.
    On ne remplit que les champs vides (None ou "").
    """
    
    # 1. Préparer la liste de tous les bus connus dans ETAP pour la recherche
    available_buses = []
    for k, df in dfs_dict.items():
        # On cherche la colonne 'FaultedBus' ou 'Bus ID'
        cols = [c.lower() for c in df.columns]
        target_col = None
        if "faultedbus" in cols: target_col = next(c for c in df.columns if c.lower() == "faultedbus")
        elif "id" in cols: target_col = next(c for c in df.columns if c.lower() == "id")
        
        if target_col:
            available_buses.extend(df[target_col].astype(str).unique().tolist())
    
    # Nettoyage et unicité
    available_buses = list(set(available_buses))

    for plan in config.plans:
        # --- LOGIQUE BUS FROM ---
        if plan.bus_from:
            # CAS 1 : L'utilisateur a donné une info. ON LA GARDE.
            plan.topology_origin = "manual_config"
            # On ne fait RIEN d'autre.
        else:
            # CAS 2 : C'est vide. Le script essaie de trouver.
            clean_id = plan.id.replace("CB_", "").strip()
            
            # Recherche : est-ce qu'un bus contient le nom du plan ? (Ex: "TX1" dans "Bus TX1-HV")
            match_from = next((b for b in available_buses if clean_id.upper() in b.upper()), None)
            
            if match_from:
                plan.bus_from = match_from
                plan.topology_origin = "script_auto_fill"
                plan.debug_info = f"Auto-filled: Found '{match_from}' matching '{clean_id}'"
            else:
                plan.topology_origin = "missing"
                plan.debug_info = "Script found nothing"

        # --- LOGIQUE BUS TO (Secondaire) ---
        if plan.bus_to:
            # CAS 1 : L'utilisateur a donné une info. ON LA GARDE.
            pass
        else:
            # CAS 2 : C'est vide.
            # Pour un transfo, si on a trouvé le primaire, on essaie de deviner le secondaire
            # (Souvent même nom mais avec MV, 20kV, etc.)
            if plan.type == "TRANSFORMER" and plan.bus_from:
                # Logique très simple : on cherche un autre bus qui a le même radical mais "MV" ou "20"
                # Ceci est optionnel, on peut laisser vide pour l'instant pour éviter les bêtises.
                pass

    return config
