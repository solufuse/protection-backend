import pandas as pd
import numpy as np

# Helper to find values in various column name candidates
def get_col_value(row, candidates):
    for col in candidates:
        if col in row.index and pd.notna(row[col]):
            return str(row[col]).strip()
    return None

def resoudre_topologie_transformer(plan, df_xfmr_global):
    if plan.type != 'TRANSFORMER': return plan
    
    # Save initial state (User) for reporting
    user_from, user_to = plan.bus_from, plan.bus_to
    tx_id = plan.related_source
    
    plan.topology_user = {"bus_from": user_from, "bus_to": user_to, "origin": "config_manual"}
    
    if not tx_id or df_xfmr_global is None or df_xfmr_global.empty: 
        plan.topology_final = "config_user"
        return plan

    df_x = df_xfmr_global.copy()
    col_id = next((c for c in df_x.columns if c.upper() in ['ID', 'NAME', 'XFMR ID']), None)
    
    if not col_id:
        plan.topology_final = "config_user"
        return plan
        
    row_tx = df_x[df_x[col_id].astype(str).str.strip() == str(tx_id).strip()]
    
    if not row_tx.empty:
        bus_prim = get_col_value(row_tx.iloc[0], ['FromBus', 'From', 'PrimBus'])
        bus_sec = get_col_value(row_tx.iloc[0], ['ToBus', 'To', 'SecBus'])
        
        # MASTER OVERWRITE: Script data takes priority
        if bus_prim: plan.bus_from = bus_prim
        if bus_sec: plan.bus_to = bus_sec
        
        plan.topology_final = "script_topo"
        plan.topology_script = {"bus_from": bus_prim, "bus_to": bus_sec}
    else:
        plan.topology_final = "config_user"
        
    return plan

def resoudre_topologie_iconnect(plan, df_iconnect):
    if plan.type not in ['COUPLING', 'INCOMER']: return plan
    
    device_id = plan.id
    user_from, user_to = plan.bus_from, plan.bus_to
    plan.topology_user = {"bus_from": user_from, "bus_to": user_to, "origin": "config_manual"}
    
    if df_iconnect is None or df_iconnect.empty:
        plan.topology_final = "config_user"
        return plan
        
    df_c = df_iconnect.copy()
    col_id = next((c for c in df_c.columns if c.upper() in ['ID', 'NAME', 'DEVICE ID']), None)
    
    if not col_id:
        plan.topology_final = "config_user"
        return plan
        
    row = df_c[df_c[col_id].astype(str).str.strip() == str(device_id).strip()]
    
    if not row.empty:
        bus_from = get_col_value(row.iloc[0], ['From', 'FromBus', 'From Bus'])
        bus_to = get_col_value(row.iloc[0], ['ToSec', 'To Sec', 'ToBus', 'To'])
        
        # MASTER OVERWRITE
        if bus_from: plan.bus_from = bus_from
        if bus_to: plan.bus_to = bus_to
        
        plan.topology_final = "script_topo"
        plan.topology_script = {"bus_from": bus_from, "bus_to": bus_to}
    else:
        plan.topology_final = "config_user"
        
    return plan

def resolve_all(config, dfs_dict):
    # Search for Transformer table
    df_xfmr = None
    for key in dfs_dict.keys():
        if key.upper() in ['PD_XFMR2', 'XFMR2', 'IXFMR2', 'TRANSFORMERS']:
            df_xfmr = dfs_dict[key]; break
            
    # Search for Connectivity table
    df_iconnect = None
    for key in dfs_dict.keys():
        if key.upper() in ['ICONNECT', 'CONNECT', 'PD_LINK']:
            df_iconnect = dfs_dict[key]; break

    for plan in config.plans:
        if plan.type == 'TRANSFORMER':
            resoudre_topologie_transformer(plan, df_xfmr)
        elif plan.type in ['COUPLING', 'INCOMER']:
            resoudre_topologie_iconnect(plan, df_iconnect)
            
    return config
