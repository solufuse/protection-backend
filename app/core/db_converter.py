import os
import json
import sqlite3
import pandas as pd
from datetime import datetime

class DBConverter:
    @staticmethod
    def _parse_sqlite(file_path):
        """
        Extrait TOUTES les tables comme dans tes scripts locaux.
        Renvoie un dictionnaire { "NomTable": [ligne1, ligne2...], ... }
        """
        db_data = {}
        conn = None
        try:
            # Mode Read-Only comme dans ton script lf1s
            conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row # Pour avoir les noms de colonnes
            cursor = conn.cursor()
            
            # 1. Lister les tables (Ta méthode)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            db_data["tables_list"] = tables
            db_data["tables_data"] = {}

            # 2. Boucle d'extraction (Ta méthode adaptée pour le Cloud)
            for t in tables:
                try:
                    # On utilise Pandas pour lire proprement, puis on convertit en dict pour le JSON
                    df = pd.read_sql_query(f'SELECT * FROM "{t}"', conn)
                    
                    # Conversion en dictionnaire pour stockage JSON
                    # orient='records' donne : [{"col1": val, "col2": val}, ...]
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
            "raw_content": {} 
        }

        try:
            # CAS 1: JSON
            if ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    if isinstance(content, dict): data.update(content)
            
            # CAS 2: SI2S / LF1S / SQLITE (Ta logique)
            elif ext in ['.sqlite', '.db', '.lf1s', '.si2s', '.mdb']:
                sqlite_content = DBConverter._parse_sqlite(file_path)
                
                if "tables_list" in sqlite_content and sqlite_content["tables_list"]:
                     data["raw_content"] = sqlite_content
                     data["message"] = "Successfully parsed SQLite/ETAP Database."
                else:
                     data["message"] = "Could not parse database structure."

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
