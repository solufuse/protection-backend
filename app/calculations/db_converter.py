import sqlite3
import pandas as pd
import tempfile
import os
import io

def extract_data_from_db(file_content: bytes):
    # Handles SI2S, LF1S, MDB (if sqlite format)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name
    data_frames = {}
    try:
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            try: data_frames[table] = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
            except: pass
        conn.close()
    except: return None
    finally:
        if os.path.exists(tmp_path): os.remove(tmp_path)
    return data_frames

def generate_excel_bytes(data_frames: dict) -> io.BytesIO:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not data_frames:
            pd.DataFrame({'Info': ['Empty']}).to_excel(writer, sheet_name='Error')
        else:
            for table_name, df in data_frames.items():
                sheet_name = table_name[:31]
                count = 1; base = sheet_name
                while sheet_name in writer.book.sheetnames:
                    sheet_name = f"{base[:28]}_{count}"; count += 1
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output
