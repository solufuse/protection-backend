import sqlite3
import pandas as pd
import tempfile
import os
import io

def extract_data_from_db(file_content: bytes):
    """
    Extracts all tables from a SQLite-based database (SI2S, LF1S) 
    and returns a dictionary of DataFrames.
    """
    # 1. Create a temporary file because sqlite3 requires a disk path
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db_tmp") as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name

    data_frames = {}
    
    try:
        # 2. Connect to the database
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        
        # 3. List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        # 4. Read each table into Pandas
        for table in tables:
            try:
                df = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
                data_frames[table] = df
            except Exception as e:
                print(f"Error reading table {table}: {e}")
                
        conn.close()
        
    except Exception as e:
        print(f"Global SQLite error: {e}")
        return None
        
    finally:
        # 5. Cleanup (Remove temp file)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
    return data_frames

def generate_excel_bytes(data_frames: dict) -> io.BytesIO:
    """
    Takes the DataFrame dictionary and returns an Excel file in memory (BytesIO).
    """
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not data_frames:
            # Create an empty sheet if nothing to write
            pd.DataFrame({'Info': ['File Empty or Unreadable']}).to_excel(writer, sheet_name='Error')
        else:
            for table_name, df in data_frames.items():
                # Excel limits sheet names to 31 chars
                sheet_name = table_name[:31]
                
                # Handle duplicate names (rare but possible)
                count = 1
                base_name = sheet_name
                while sheet_name in writer.book.sheetnames:
                    sheet_name = f"{base_name[:28]}_{count}"
                    count += 1
                
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    # Rewind pointer to the beginning of the memory file
    output.seek(0)
    return output
