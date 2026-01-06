
import pandas as pd
from app.calculations import db_converter

def get_col_name(df, candidates):
    """Finds the first matching column name from a list of candidates."""
    for col in candidates:
        for df_col in df.columns:
            if df_col.upper() == col.upper():
                return df_col
    return None

def extract_topology_from_iconnect(file_content: bytes) -> dict:
    """
    Analyzes file content, finds the 'iConnect' data table, and extracts
    topology information from it, focusing on ID, Type, From, and ToSec columns.

    Args:
        file_content: The content of the file to analyze.

    Returns:
        A dictionary containing the extracted topology data or an error message.
    """
    dataframes = db_converter.extract_data_from_db(file_content)
    if not dataframes:
        return {"status": "error", "message": "Could not extract dataframes from file."}

    # Find the iConnect dataframe (using logic from topology_manager.py)
    df_iconnect = None
    iconnect_key = None
    for key in dataframes.keys():
        if key.upper() == 'ICONNECT':
            df_iconnect = dataframes[key]
            iconnect_key = key
            break
    if df_iconnect is None:
        for key in dataframes.keys():
            if key.upper() in ['CONNECT', 'PD_LINK', 'LN_LINK']:
                df_iconnect = dataframes[key]
                iconnect_key = key
                break
    
    if df_iconnect is None:
        return {"status": "error", "message": "Could not find 'iConnect' data table."}

    # Identify column names
    id_col = get_col_name(df_iconnect, ['ID', 'NAME', 'DEVICE ID'])
    type_col = get_col_name(df_iconnect, ['TYPE', 'DEVICE TYPE'])
    from_col = get_col_name(df_iconnect, ['FROM', 'FROMBUS', 'FROM BUS'])
    tosec_col = get_col_name(df_iconnect, ['TOSEC', 'TO SEC'])

    if not all([id_col, from_col, tosec_col]):
        return {
            "status": "error",
            "message": f"Essential columns missing in '{iconnect_key}'. Required: ID, From, ToSec. Found: id={id_col}, from={from_col}, tosec={tosec_col}."
        }

    # Extract data
    topology_data = []
    for _, row in df_iconnect.iterrows():
        entry = {
            "id": row[id_col] if pd.notna(row[id_col]) else None,
            "from_bus": row[from_col] if pd.notna(row[from_col]) else None,
            "to_bus": row[tosec_col] if pd.notna(row[tosec_col]) else None,
            "type": row[type_col] if type_col and pd.notna(row[type_col]) else "N/A"
        }
        topology_data.append(entry)

    return {
        "status": "success",
        "message": f"Extracted {len(topology_data)} entries from '{iconnect_key}'.",
        "data": topology_data
    }
