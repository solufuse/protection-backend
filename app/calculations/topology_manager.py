
import pandas as pd
from app.schemas.protection import ProjectConfig, ProtectionPlan

def find_connected_buses_for_breaker(breaker_id: str, dfs: dict):
    """
    Tente de trouver les Bus connectés à un disjoncteur via les tables ETAP.
    Retourne (bus_from, bus_to) ou (None, None).
    """
    # 1. Chercher dans la table Breaker/Switch (PD_PDElement ?)
    # Note: Dans les exports simplifiés SI2S, on n'a souvent que les résultats de court-circuit.
    # On va utiliser une astuce : Chercher le disjoncteur dans les tables de résultats s'il apparait.
    
    # ASTUCE : Si on n'a pas la table de connectivité brute, on ne peut pas deviner la topologie 
    # juste avec le nom du disjoncteur, sauf si le nom du bus est explicite.
    
    # MAIS, souvent dans les SI2S, on a une table "Device" ou "Branch".
    # Supposons pour cet exemple qu'on fait une recherche "Best Effort".
    
    # Pour l'instant, on va simuler une intelligence : 
    # Si le nom du plan contient le nom d'un bus trouvé dans ScSummary, on l'associe.
    
    # --- VRAIE LOGIQUE DE PROD (Simplifiée ici car pas d'accès aux tables Brk ETAP) ---
    # On va scanner les tables de résultats (ScIecLgSum1) pour voir si on trouve des Bus
    # qui ressemblent au ID du plan (ex: plan "CB_HV0-A" -> Bus "HV0-A")
    
    found_from = None
    found_to = None
    
    # Recherche naïve basée sur les strings (efficace pour les conventions de nommage)
    target = breaker_id.replace("CB_", "").replace("Disjoncteur_", "")
    
    for table_name, df in dfs.items():
        if "faultedbus" in [c.lower() for c in df.columns]:
            col = next(c for c in df.columns if c.lower() == "faultedbus")
            # On cherche si un bus contient le nom "stripped" du disjoncteur
            # Ex: TX1-A dans "Bus TX1-A-HV"
            potential_buses = df[col].astype(str).unique()
            for bus in potential_buses:
                if target.upper() in bus.upper():
                    # Bingo potentiel
                    # Si c'est un transfo, on a souvent HV et MV
                    if "HV" in bus.upper() or "HT" in bus.upper() or "225" in bus:
                        found_from = bus
                    if "MV" in bus.upper() or "MT" in bus.upper() or "20" in bus:
                        found_to = bus
                        
    # Si on a trouvé quelque chose, on le retourne
    if found_from or found_to:
        return found_from, found_to
        
    return None, None

def resolve_all(config: ProjectConfig, dfs_dict: dict) -> ProjectConfig:
    """
    Parcourt tous les plans et tente de résoudre/écraser la topologie
    en se basant sur les données trouvées dans la DB.
    """
    
    # On scanne d'abord tous les bus disponibles dans le fichier pour référence
    available_buses = []
    for k, df in dfs_dict.items():
        if "faultedbus" in [c.lower() for c in df.columns]:
            col = next(c for c in df.columns if c.lower() == "faultedbus")
            available_buses.extend(df[col].astype(str).unique().tolist())
    available_buses = list(set(available_buses))

    for plan in config.plans:
        # LOGIQUE AUTORITAIRE : On cherche d'abord
        script_bus_from = None
        script_bus_to = None
        
        # 1. Stratégie de Matching par Nom (Name Matching)
        # Si le plan s'appelle "CB_Bus A", on cherche "Bus A" dans la DB
        clean_id = plan.id.replace("CB_", "").strip()
        
        # Recherche exacte ou partielle
        # Pour le Bus From (Amont)
        match_from = next((b for b in available_buses if clean_id.upper() in b.upper()), None)
        
        if match_from:
            # On a trouvé un candidat dans la DB
            script_bus_from = match_from
            
        # 2. Application de la Priorité (Script > Human)
        if script_bus_from:
            if plan.bus_from != script_bus_from:
                # On note le changement pour le debug
                plan.debug_info = f"Override: '{plan.bus_from}' -> '{script_bus_from}'"
            
            plan.bus_from = script_bus_from
            plan.topology_origin = "script_topo"
        else:
            # Si le script ne trouve rien, on garde la config manuelle (fallback)
            if not plan.topology_origin:
                plan.topology_origin = "manual_config"
                
        # Pour les transfos, on essaie de deviner le bus_to (Secondaire)
        if plan.type == "TRANSFORMER" and script_bus_from:
            # Souvent le secondaire a le même radical mais MV/LV
            # Ceci est une heuristique simple
            pass

    return config
