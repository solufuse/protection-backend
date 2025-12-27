import os
import json
import sqlite3
import pandas as pd
from datetime import datetime

class DBConverter:
    @staticmethod
    def _parse_sqlite(file_path):
        db_data = {}
        conn = None
        try:
            conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            db_data["tables_list"] = tables
            db_data["tables_data"] = {}
            for t in tables:
                try:
                    df = pd.read_sql_query(f'SELECT * FROM "{t}"', conn)
                    db_data["tables_data"][t] = df.to_dict(orient='records')
                except: pass
            return db_data
        except Exception as e:
            return {"sqlite_error": str(e)}
        finally:
            if conn: conn.close()

    @staticmethod
    def convert_to_json(file_path, original_filename):
        ext = os.path.splitext(original_filename)[1].lower()
        base_name = os.path.splitext(original_filename)[0]
        data = {
            "project_name": base_name,
            "source_file": original_filename,
            "converted_at": datetime.utcnow().isoformat(),
            "status": "success",
            "metadata": {"type": ext},
            "raw_content": {} 
        }
        try:
            if ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    if isinstance(content, dict): data.update(content)
            elif ext in ['.sqlite', '.db', '.lf1s', '.si2s', '.mdb']:
                sqlite_content = DBConverter._parse_sqlite(file_path)
                if "tables_data" in sqlite_content and sqlite_content["tables_data"]:
                     data["raw_content"] = sqlite_content
                     data["message"] = "Parsed via SQLite Engine"
                else:
                     data["message"] = "Empty/Locked DB"
            elif ext == '.xml':
                data["logs"] = ["XML not supported"]
            else:
                data["status"] = "unsupported_format"
        except Exception as e:
            data["status"] = "error"
            data["error_details"] = str(e)
        return data
