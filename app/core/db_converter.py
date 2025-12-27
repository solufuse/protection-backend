import os
import json
import sqlite3
import pandas as pd
from datetime import datetime

class DBConverter:
    @staticmethod
    def _parse_sqlite(file_path):
        """
        Reads ALL tables from the SQLite database (LF1S/SI2S).
        Returns a dict: { "TableName": [{row1}, {row2}] }
        """
        db_data = {}
        conn = None
        try:
            # Connect in Read-Only mode to avoid locks
            conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. List all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            db_data["tables_list"] = tables
            db_data["tables_data"] = {}

            # 2. Extract data from each table
            for t in tables:
                try:
                    df = pd.read_sql_query(f'SELECT * FROM "{t}"', conn)
                    # Convert to list of dicts for JSON serialization
                    db_data["tables_data"][t] = df.to_dict(orient='records')
                except Exception as e:
                    print(f"⚠️ Error reading table {t}: {e}")
            
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
            # We explicitly initialize raw_content for the Frontend to find it
            "raw_content": {} 
        }

        try:
            # CAS 1: JSON
            if ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    if isinstance(content, dict): data.update(content)
            
            # CAS 2: SI2S / LF1S / SQLITE / MDB
            elif ext in ['.sqlite', '.db', '.lf1s', '.si2s', '.mdb']:
                print(f"   🔍 Analyzing SQLite structure for: {original_filename}")
                sqlite_content = DBConverter._parse_sqlite(file_path)
                
                if "tables_data" in sqlite_content and sqlite_content["tables_data"]:
                     data["raw_content"] = sqlite_content
                     data["message"] = "Successfully parsed SQLite/ETAP Database."
                else:
                     data["message"] = "Could not parse database structure (Empty or Locked)."

            # CAS 3: XML
            elif ext == '.xml':
                data["logs"] = ["XML parsing not implemented yet"]
            
            else:
                data["status"] = "unsupported_format"

        except Exception as e:
            data["status"] = "error"
            data["error_details"] = str(e)
            print(f"❌ Conversion Error: {e}")

        return data
