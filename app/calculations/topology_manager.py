import pandas as pd
import numpy as np

# --- UTILITIES ---
def get_col_value(row, candidates):
    """Searches for the value in the first column found among candidates"""
    for col in candidates:
        if col in row.index and pd.notna(row[col]):
            return str(row[col]).strip()
    return None

# --- TRANSFORMER LOGIC (Unchanged) ---
def resoudre_topologie_transformer(plan, df_xfmr_global):
    if plan.type != 'TRANSFORMER': return plan
    
    user_from, user_to = plan.bus_from, plan.bus_to
    tx_id = plan.related_source
    
    if not tx_id or df_xfmr_global is None or df_xfmr_global.empty: 
        plan.topology_origin = "config_user"
        return plan

    df_x = df_xfmr_global.copy()
    col_id = next((c for c in df_x.columns if c.upper() in ['ID', 'NAME', 'XFMR ID']), None)
    
    if not col_id:
        plan.topology_origin = "config_user"
        return plan
        
    row_tx = df_x[df_x[col_id].astype(str).str.strip() == str(tx_id).strip()]
    
    if not row_tx.empty:
        # Script Priority
        bus_prim = get_col_value(row_tx.iloc[0], ['FromBus', 'From', 'PrimBus'])
        bus_sec = get_col_value(row_tx.iloc[0], ['ToBus', 'To', 'SecBus'])
        
        if bus_prim: plan.bus_from = bus_prim
        if bus_sec: plan.bus_to = bus_sec
        
        plan.topology_origin = "script_topo"
        plan.debug_info = f"Found in SI2S ({tx_id})"
        plan.meta_data = {"user_config_was": {"from": user_from, "to": user_to}}
    else:
        plan.topology_origin = "config_user"
        
    return plan

# --- COUPLING & INCOMER LOGIC (IConnect Update) ---
def resoudre_topologie_iconnect(plan, df_iconnect):
    """
    Searches specifically in the IConnect table.
    Targets: From -> bus_from, ToSec -> bus_to.
    """
    if plan.type not in ['COUPLING', 'INCOMER']: return plan
    
    device_id = plan.id
    user_from, user_to = plan.bus_from, plan.bus_to
    
    # 1. If no IConnect table found
    if df_iconnect is None or df_iconnect.empty:
        plan.topology_origin = "config_user"
        plan.debug_info = "IConnect table missing from SI2S."
        return plan
        
    # 2. ID Search
    df_c = df_iconnect.copy()
    # Looking for ID column (often just 'ID')
    col_id = next((c for c in df_c.columns if c.upper() in ['ID', 'NAME', 'DEVICE ID']), None)
    
    if not col_id:
        plan.topology_origin = "config_user"
        return plan
        
    row = df_c[df_c[col_id].astype(str).str.strip() == str(device_id).strip()]
    
    # 3. IF FOUND -> EXTRACT & OVERWRITE
    if not row.empty:
        # Looking exactly for the columns requested as priority
        # 'From' for upstream bus
        # 'ToSec' for downstream bus (IConnect specific)
        
        bus_from = get_col_value(row.iloc[0], ['From', 'FromBus', 'From Bus'])
        bus_to = get_col_value(row.iloc[0], ['ToSec', 'To Sec', 'ToBus', 'To'])
        
        if bus_from: plan.bus_from = bus_from
        if bus_to: plan.bus_to = bus_to
        
        plan.topology_origin = "script_topo"
        plan.debug_info = f"Found in IConnect ({device_id})"
        plan.meta_data = {"user_config_was": {"from": user_from, "to": user_to}}
        
    else:
        # 4. IF NOT FOUND -> USER FALLBACK
        plan.topology_origin = "config_user"
        plan.debug_info = f"Not found in IConnect"
        
    return plan

# --- ORCHESTRATOR ---
def resolve_all(config, dfs_dict):
    
    # 1. Transformers Table (IXFMR2)
    df_xfmr = None
    for key in dfs_dict.keys():
        if key.upper() in ['PD_XFMR2', 'XFMR2', 'IXFMR2', 'TRANSFORMERS']:
            df_xfmr = dfs_dict[key]; break
            
    # 2. IConnect Table (Absolute priority on name 'ICONNECT')
    df_iconnect = None
    
    # Priority search for exact "ICONNECT"
    for key in dfs_dict.keys():
        if key.upper() == 'ICONNECT':
            df_iconnect = dfs_dict[key]
            break
            
    # If "ICONNECT" not found, search synonyms (CONNECT, PD_LINK)
    if df_iconnect is None:
        for key in dfs_dict.keys():
            if key.upper() in ['CONNECT', 'PD_LINK', 'LN_LINK']:
                df_iconnect = dfs_dict[key]
                break

    # 3. Execution
    for plan in config.plans:
        if plan.type == 'TRANSFORMER':
            resoudre_topologie_transformer(plan, df_xfmr)
            
        elif plan.type in ['COUPLING', 'INCOMER']:
            # Using the new IConnect logic
            resoudre_topologie_iconnect(plan, df_iconnect)
            
    return config
