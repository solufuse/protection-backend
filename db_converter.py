import sqlite3
import pandas as pd
import tempfile
import os
from io import BytesIO

def extract_data_from_db(file_stream: BytesIO) -> dict:
    """
    Extracts all tables from a SQLite database file stream and converts them to a dictionary.
    
    Args:
        file_stream (BytesIO): The binary content of the file.
        
    Returns:
        dict: A dictionary where keys are table names and values are lists of records.
    """
    # Create a temporary file because sqlite3 requires a file path (fs) to connect
    # delete=False is used so we can close the file handle before passing the path to sqlite3
    with tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite') as tmp_file:
        tmp_file.write(file_stream.getbuffer())
        tmp_path = tmp_file.name

    conn = None
    db_data = {}

    try:
        # Connect to the temporary SQLite database
        conn = sqlite3.connect(tmp_path)
        
        # Get list of all tables
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table_name in tables:
            name = table_name[0]
            # Skip internal sqlite tables
            if name.startswith('sqlite_'):
                continue
                
            # Read table into a Pandas DataFrame
            # This handles data types better than raw cursors
            df = pd.read_sql_query(f"SELECT * FROM '{name}'", conn)
            
            # Convert NaN to None (null in JSON) to avoid JSON serialization errors
            df = df.where(pd.notnull(df), None)
            
            # Convert to list of dictionaries (records)
            db_data[name] = df.to_dict(orient='records')
            
    except Exception as e:
        print(f"Error converting DB: {e}")
        raise e
        
    finally:
        # Cleanup: Close connection and remove the temporary file to remain stateless
        if conn:
            conn.close()
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            print(f"Temporary file {tmp_path} cleaned up.")

    return db_data
