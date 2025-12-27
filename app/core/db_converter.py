import os
import json
import sqlite3
import pandas as pd
from datetime import datetime

class DBConverter:
    @staticmethod
    def _parse_sqlite(file_path):
        """
        Helper function to extract EVERYTHING from a SQLite database.
        Returns a dictionary where keys are table names and values are rows.
        """
        db_data = {}
        conn = None
        try:
            conn = sqlite3.connect(file_path)
            # Enable row factory to get column names
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. Get list of all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row['name'] for row in cursor.fetchall()]
            
            db_data["tables_found"] = tables

            # 2. Extract data from each table (Limit to 100 rows per table for safety)
            for table in tables:
                try:
                    cursor.execute(f"SELECT * FROM '{table}' LIMIT 100")
                    rows = cursor.fetchall()
                    # Convert row objects to dicts
                    table_data = [dict(row) for row in rows]
                    db_data[table] = table_data
                except Exception as e:
                    db_data[table] = f"Error reading table: {str(e)}"
            
            return db_data

        except Exception as e:
            return {"sqlite_error": str(e)}
        finally:
            if conn: conn.close()

    @staticmethod
    def convert_to_json(file_path, original_filename):
        """
        Universal converter with REAL SQLite support.
        """
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
            # --- CAS 1: JSON ---
            if ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    if isinstance(content, dict): data.update(content)
            
            # --- CAS 2: SQLite / LF1S (Si c'est du SQLite) ---
            # On ajoute .si2s ici au cas où ce soit un SQLite renommé (ça arrive)
            elif ext in ['.sqlite', '.db', '.lf1s', '.si2s', '.mdb']:
                
                # On tente de le lire comme du SQLite d'abord
                sqlite_content = DBConverter._parse_sqlite(file_path)
                
                # Si on a trouvé des tables, c'est que c'était bien du SQLite !
                if "tables_found" in sqlite_content and sqlite_content["tables_found"]:
                     data["raw_content"] = sqlite_content
                     data["message"] = "Successfully parsed as SQLite Database."
                else:
                     # Sinon, c'est peut-être du MDB binaire ou autre chose
                     data["message"] = "Could not parse as SQLite. Might be binary MDB or XML."
                     # (Ici on pourrait garder la simulation si besoin, ou laisser vide)

            # --- CAS 3: XML ---
            elif ext == '.xml':
                data["logs"] = ["XML parsing not implemented yet"]
            
            else:
                data["status"] = "unsupported_format"

        except Exception as e:
            data["status"] = "error"
            data["error_details"] = str(e)
            print(f"❌ Conversion Error: {e}")

        return data
