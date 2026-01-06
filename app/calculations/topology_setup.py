
import pandas as pd
from app.calculations import db_converter

def get_col_name(df, candidates):
    """Finds the first matching column name from a list of candidates."""
    if df is None:
        return None
    for col in candidates:
        for df_col in df.columns:
            if df_col.upper() == col.upper():
                return df_col
    return None

def analyze_topology(file_content: bytes, filename: str) -> dict:
    """
    Analyzes file content to extract topology and identify key components like
    incomers, transformers, cables, buses, and couplings.
    """
    dataframes = db_converter.extract_data_from_db(file_content)
    if not dataframes:
        return {"status": "error", "message": "Could not extract dataframes from file."}

    # --- 1. Extract Base Topology from iConnect ---
    df_iconnect = next((df for name, df in dataframes.items() if name.upper() == 'ICONNECT'), None)
    if df_iconnect is None:
        df_iconnect = next((df for name, df in dataframes.items() if name.upper() in ['CONNECT', 'PD_LINK', 'LN_LINK']), None)
    
    if df_iconnect is None:
        return {"status": "error", "message": "Could not find 'iConnect' or equivalent data table."}

    id_col = get_col_name(df_iconnect, ['ID', 'NAME'])
    from_col = get_col_name(df_iconnect, ['FROM', 'FROMBUS'])
    tosec_col = get_col_name(df_iconnect, ['TOSEC', 'TOBUS', 'TO'])
    type_col = get_col_name(df_iconnect, ['TYPE'])
    if not all([id_col, from_col, tosec_col]):
        return {"status": "error", "message": "Essential columns missing from iConnect."}

    iconnect_nodes = set(df_iconnect[id_col].unique()) | set(df_iconnect[from_col].unique()) | set(df_iconnect[tosec_col].unique())

    # --- Dataframes for other components ---
    df_iutility = next((df for name, df in dataframes.items() if name.upper() == 'IUTILITY'), None)
    df_lfsource = next((df for name, df in dataframes.items() if name.upper() == 'LFSOURCELOAD'), None)
    df_ixfmr2 = next((df for name, df in dataframes.items() if name.upper() in ['IXFMR2', 'XFMR2']), None)
    df_icable = next((df for name, df in dataframes.items() if name.upper() in ['ICABLE', 'CABLE']), None)
    df_ibus = next((df for name, df in dataframes.items() if name.upper() in ['IBUS', 'BUS']), None)

    # --- 2. Identify Incomer and Incomer Buses ---
    incomer_info = []
    incomer_buses = set()
    file_ext = filename.lower().split('.')[-1]

    if file_ext == 'si2s' and df_iutility is not None:
        bus_col_util = get_col_name(df_iutility, ['CONNECTEDBUS'])
        if bus_col_util:
            for _, row in df_iutility.iterrows():
                bus_name = row[bus_col_util]
                if bus_name in iconnect_nodes:
                    entry = row.to_dict()
                    entry['topology_calculated'] = 'INCOMER'
                    incomer_info.append(entry)
                    incomer_buses.add(bus_name)

    elif file_ext == 'lf1s' and df_lfsource is not None:
        id_term_bus_col = get_col_name(df_lfsource, ['IDTERMBUS'])
        kv_col = get_col_name(df_lfsource, ['RATEDKV', 'BUSNOMINALKV'])
        if id_term_bus_col and kv_col:
            matched_sources = df_lfsource[df_lfsource[id_term_bus_col].isin(iconnect_nodes)].copy()
            if not matched_sources.empty:
                matched_sources['voltage_level'] = pd.to_numeric(matched_sources[kv_col], errors='coerce').fillna(0)
                sorted_sources = matched_sources.sort_values(by='voltage_level', ascending=False)
                voltage_ranks = {kv: rank for rank, kv in enumerate(sorted(sorted_sources['voltage_level'].unique(), reverse=True), 1)}
                sorted_sources['voltage_rank'] = sorted_sources['voltage_level'].map(voltage_ranks)
                for _, row in sorted_sources.iterrows():
                    entry = row.to_dict()
                    if row['voltage_rank'] == 1:
                        entry['topology_calculated'] = 'INCOMER'
                        incomer_buses.add(row[id_term_bus_col])
                    else:
                        entry['topology_calculated'] = f'LEVEL_{row["voltage_rank"]}'
                    incomer_info.append(entry)
    
    # --- 3. Identify Buses ---
    bus_info = []
    bus_voltage_map = {}
    if df_ibus is not None:
        bus_id_col = get_col_name(df_ibus, ['IDBUS', 'ID'])
        bus_kv_col = get_col_name(df_ibus, ['BASEKV', 'NOMLKV'])
        if bus_id_col:
            for _, row in df_ibus.iterrows():
                if row[bus_id_col] in iconnect_nodes:
                    entry = row.to_dict()
                    entry['topology_calculated'] = 'BUS'
                    bus_info.append(entry)
            if bus_kv_col:
                temp_map = df_ibus.set_index(bus_id_col)[bus_kv_col].to_dict()
                bus_voltage_map = {str(k): v for k, v in temp_map.items()}


    # --- 4. Identify Transformers ---
    transformer_info = []
    if df_ixfmr2 is not None:
        xfmr_id_col = get_col_name(df_ixfmr2, ['ID', 'NAME'])
        xfmr_from_col = get_col_name(df_ixfmr2, ['FROMBUS', 'FROM'])
        xfmr_to_col = get_col_name(df_ixfmr2, ['TOBUS', 'TO'])
        prim_kv_col = get_col_name(df_ixfmr2, ['PRIMKV'])
        sec_kv_col = get_col_name(df_ixfmr2, ['SECKV'])
        if all([xfmr_id_col, xfmr_from_col, xfmr_to_col]):
            for _, row in df_ixfmr2.iterrows():
                if (row[xfmr_id_col] in iconnect_nodes or row[xfmr_from_col] in iconnect_nodes or row[xfmr_to_col] in iconnect_nodes):
                    entry = row.to_dict()
                    entry['topology_calculated'] = 'TRANSFORMER'
                    if prim_kv_col and pd.notna(row[prim_kv_col]): entry['primary_voltage_kV'] = row[prim_kv_col]
                    if sec_kv_col and pd.notna(row[sec_kv_col]): entry['secondary_voltage_kV'] = row[sec_kv_col]
                    transformer_info.append(entry)

    # --- 5. Identify Cables ---
    cable_info = []
    if df_icable is not None:
        cable_id_col = get_col_name(df_icable, ['ID', 'NAME'])
        cable_from_col = get_col_name(df_icable, ['FROMBUS', 'FROM'])
        cable_to_col = get_col_name(df_icable, ['TOBUS', 'TO'])
        if all([cable_id_col, cable_from_col, cable_to_col]):
            for _, row in df_icable.iterrows():
                if (row[cable_id_col] in iconnect_nodes or row[cable_from_col] in iconnect_nodes or row[cable_to_col] in iconnect_nodes):
                    entry = row.to_dict()
                    entry['topology_calculated'] = 'CABLE'
                    cable_info.append(entry)

    # --- 6. Identify Couplings and Incomer Breakers ---
    coupling_info = []
    incomer_breaker_info = []
    if type_col and bus_voltage_map:
        for _, row in df_iconnect.iterrows():
            is_breaker = False
            if pd.notna(row[type_col]) and ('CB' in row[type_col].upper() or 'TIE' in row[type_col].upper()):
                is_breaker = True
            
            if is_breaker:
                from_bus = row[from_col]
                to_bus = row[tosec_col]
                
                from_voltage = bus_voltage_map.get(from_bus)
                to_voltage = bus_voltage_map.get(to_bus)

                if from_voltage is not None and from_voltage == to_voltage:
                    entry = row.to_dict()
                    if from_bus in incomer_buses or to_bus in incomer_buses:
                        entry['topology_calculated'] = 'INCOMER_BREAKER'
                        incomer_breaker_info.append(entry)
                    else:
                        entry['topology_calculated'] = 'COUPLING'
                        entry['coupling_voltage_kV'] = from_voltage
                        coupling_info.append(entry)

    # --- 7. Consolidate Results ---
    topology_data = df_iconnect.to_dict(orient='records')

    return {
        "status": "success",
        "message": f"Analyzed {len(topology_data)} topology entries.",
        "topology": topology_data,
        "incomer_analysis": incomer_info,
        "bus_analysis": bus_info,
        "transformer_analysis": transformer_info,
        "cable_analysis": cable_info,
        "coupling_analysis": coupling_info,
        "incomer_breaker_analysis": incomer_breaker_info
    }
