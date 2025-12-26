import sqlite3
import pandas as pd
import tempfile
import os
import io
from io import BytesIO

def extract_data_from_db(file_stream: BytesIO) -> dict:
    """Convertit SQLite binaire en Dict via Pandas."""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite') as tmp_file:
        tmp_file.write(file_stream.getbuffer())
        tmp_path = tmp_file.name

    conn = None
    db_data = {}

    try:
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table_name in tables:
            name = table_name[0]
            if name.startswith('sqlite_'): continue
            df = pd.read_sql_query(f"SELECT * FROM '{name}'", conn)
            # Conversion pour JSON (NaN -> None)
            df = df.where(pd.notnull(df), None)
            db_data[name] = df.to_dict(orient='records')
            
    except Exception as e:
        print(f"Error converting DB: {e}")
        raise e
    finally:
        if conn: conn.close()
        if os.path.exists(tmp_path): os.remove(tmp_path)

    return db_data

def generate_excel_bytes(dfs_dict: dict) -> BytesIO:
    """
    Génère un fichier Excel en mémoire à partir d'un dictionnaire de données.
    """
    output = BytesIO()
    # Utilisation de XlsxWriter ou openpyxl via Pandas
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, records in dfs_dict.items():
            if not records: continue # Skip empty tables
            df = pd.DataFrame(records)
            # On tronque le nom de la feuille à 31 caractères (limite Excel)
            safe_sheet_name = sheet_name[:31]
            df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
    
    output.seek(0)
    return output
