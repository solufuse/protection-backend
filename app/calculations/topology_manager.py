
import pandas as pd
from app.schemas.protection import ProjectConfig, ProtectionPlan

def resolve_all(config: ProjectConfig, dfs_dict: dict) -> ProjectConfig:
    """
    Résout la topologie en comparant la config utilisateur (User) et la DB (Script).
    Stocke les deux valeurs pour une traçabilité complète.
    """
    
    # Scan des bus disponibles
    available_buses = []
    for k, df in dfs_dict.items():
        if "faultedbus" in [c.lower() for c in df.columns]:
            col = next(c for c in df.columns if c.lower() == "faultedbus")
            available_buses.extend(df[col].astype(str).unique().tolist())
    available_buses = list(set(available_buses))

    for plan in config.plans:
        # 1. SAUVEGARDE DE L'INTENTION UTILISATEUR (Avant toute modification)
        # On utilise setattr pour être sûr de passer même si le champ n'est pas dans le schéma initial
        if not hasattr(plan, "user_bus_from"):
            setattr(plan, "user_bus_from", plan.bus_from) # Valeur du JSON
        
        # 2. RECHERCHE SCRIPT (Detection)
        script_bus_from = None
        
        clean_id = plan.id.replace("CB_", "").strip()
        # Recherche naïve par inclusion de texte (ex: "TX1" dans "Bus TX1-HV")
        match_from = next((b for b in available_buses if clean_id.upper() in b.upper()), None)
        
        if match_from:
            script_bus_from = match_from
        
        # On stocke ce que le script a trouvé (ou None)
        setattr(plan, "script_bus_from", script_bus_from)

        # 3. ARBITRAGE (Script > User)
        if script_bus_from:
            # Le script a trouvé quelque chose -> Il gagne
            plan.bus_from = script_bus_from
            plan.topology_origin = "script"
            
            # Petit debug info pour comprendre pourquoi
            if plan.user_bus_from != script_bus_from:
                plan.debug_info = f"Override: User='{plan.user_bus_from}' -> Script='{script_bus_from}'"
            else:
                plan.debug_info = "Confirmed: Script matches User"
        else:
            # Le script n'a rien trouvé -> L'utilisateur gagne (Fallback)
            # plan.bus_from reste inchangé (valeur User)
            plan.topology_origin = "user"
            plan.debug_info = "Fallback to User (Script found nothing)"

    return config
