
import pandas as pd
from app.calculations import db_converter

def get_col_name(df, candidates):
    """Finds the first matching column name from a list of candidates."""
    for col in candidates:
        for df_col in df.columns:
            if df_col.upper() == col.upper():
                return df_col
    return None

def analyze_topology(file_content: bytes, filename: str) -> dict:
    """
    Analyzes file content to extract topology and identify the grid incomer.

    Args:
        file_content: The content of the file to analyze.
        filename: The name of the file, used to determine the analysis logic.

    Returns:
        A dictionary with the topology data and incomer information.
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
    type_col = get_col_name(df_iconnect, ['TYPE'])
    from_col = get_col_name(df_iconnect, ['FROM', 'FROMBUS'])
    tosec_col = get_col_name(df_iconnect, ['TOSEC'])
    if not all([id_col, from_col, tosec_col]):
        return {"status": "error", "message": "Essential columns missing from iConnect."}

    iconnect_nodes = set(df_iconnect[id_col].unique()) | set(df_iconnect[from_col].unique()) | set(df_iconnect[tosec_col].unique())

    # --- 2. Identify Incomer based on file type ---
    incomer_info = []
    file_ext = filename.lower().split('.')[-1]

    if file_ext == 'si2s':
        df_iutility = next((df for name, df in dataframes.items() if name.upper() == 'IUTILITY'), None)
        if df_iutility is not None:
            bus_col = get_col_name(df_iutility, ['CONNECTEDBUS'])
            if bus_col:
                for _, row in df_iutility.iterrows():
                    if row[bus_col] in iconnect_nodes:
                        entry = row.to_dict()
                        entry['topology_calculated'] = 'INCOMER'
                        incomer_info.append(entry)

    elif file_ext == 'lf1s':
        df_lfsource = next((df for name, df in dataframes.items() if name.upper() == 'LFSOURCELOAD'), None)
        if df_lfsource is not None:
            id_term_bus_col = get_col_name(df_lfsource, ['IDTERMBUS'])
            kv_col = get_col_name(df_lfsource, ['RATEDKV', 'BUSNOMINALKV'])
            if id_term_bus_col and kv_col:
                matched_sources = df_lfsource[df_lfsource[id_term_bus_col].isin(iconnect_nodes)].copy()
                if not matched_sources.empty:
                    matched_sources['voltage_level'] = pd.to_numeric(matched_sources[kv_col], errors='coerce').fillna(0)
                    # Sort by voltage (desc) to find the highest voltage -> Incomer
                    sorted_sources = matched_sources.sort_values(by='voltage_level', ascending=False)
                    
                    # Assign voltage level ranks
                    voltage_ranks = {kv: rank for rank, kv in enumerate(sorted(sorted_sources['voltage_level'].unique(), reverse=True), 1)}
                    sorted_sources['voltage_rank'] = sorted_sources['voltage_level'].map(voltage_ranks)

                    for _, row in sorted_sources.iterrows():
                        entry = row.to_dict()
                        if row['voltage_rank'] == 1:
                            entry['topology_calculated'] = 'INCOMER'
                        else:
                            entry['topology_calculated'] = f'LEVEL_{row["voltage_rank"]}'
                        incomer_info.append(entry)

    # --- 3. Consolidate Results ---
    topology_data = df_iconnect.to_dict(orient='records')

    return {
        "status": "success",
        "message": f"Analyzed {len(topology_data)} topology entries.",
        "topology": topology_data,
        "incomer_analysis": incomer_info
    }
