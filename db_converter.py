import sqlite3
import pandas as pd
import tempfile
import os
from io import BytesIO

def extract_data_from_db(file_stream: BytesIO) -> dict:
    """
    Fonction originale restaurée : Convertit SQLite binaire en Dict via Pandas.
    """
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
            if name.startswith('sqlite_'):
                continue
            df = pd.read_sql_query(f"SELECT * FROM '{name}'", conn)
            # Gestion des valeurs null pour JSON
            df = df.where(pd.notnull(df), None)
            db_data[name] = df.to_dict(orient='records')
            
    except Exception as e:
        print(f"Error converting DB: {e}")
        raise e
        
    finally:
        if conn: conn.close()
        if os.path.exists(tmp_path): os.remove(tmp_path)

    return db_data
