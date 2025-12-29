
import sqlite3
import pandas as pd
import tempfile
import os
import io
from typing import Dict, Any, List
from app.schemas.protection import ProjectConfig

# --- LOGIQUE D'EXTRACTION FICHIER (Même logique que SI2S) ---

def extract_data_from_lf1s(file_content: bytes) -> Dict[str, pd.DataFrame]:
    """
    Extrait toutes les tables du fichier LF1S (SQLite) et renvoie un dictionnaire de DataFrames.
    """
    # 1. Création d'un fichier temporaire (.LF1S)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".LF1S") as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name

    data_frames = {}
    
    try:
        # 2. Connexion à la base de données SQLite
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        
        # 3. Lister toutes les tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        # 4. Lire chaque table vers Pandas
        for table in tables:
            try:
                df = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
                data_frames[table] = df
            except Exception as e:
                print(f"Erreur lecture table {table} dans LF1S: {e}")
                
        conn.close()
        
    except Exception as e:
        print(f"Erreur globale SQLite (LF1S): {e}")
        return {}
        
    finally:
        # 5. Nettoyage
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
    return data_frames

def generate_excel_bytes(data_frames: dict) -> io.BytesIO:
    """
    Prend le dictionnaire de DataFrames et renvoie un fichier Excel en mémoire.
    """
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not data_frames:
            pd.DataFrame({'Info': ['Fichier Vide ou Illisible']}).to_excel(writer, sheet_name='Erreur')
        else:
            for table_name, df in data_frames.items():
                # Limitation Excel : max 31 char pour le nom de l'onglet
                sheet_name = table_name[:31]
                count = 1
                base_name = sheet_name
                # Gestion des doublons de noms d'onglets
                while sheet_name in writer.book.sheetnames:
                    sheet_name = f"{base_name[:28]}_{count}"
                    count += 1
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    output.seek(0)
    return output

# --- CLASS CONVERTER (Gestion de la Config JSON) ---

class LoadFlowConverter:
    """
    Converter class dedicated to Load Flow (LF1S) requirements.
    Handles 'config.json' mapping via ProjectConfig.
    """

    def __init__(self, config: ProjectConfig):
        self.config = config

    def get_loadflow_settings(self) -> Dict[str, Any]:
        """
        Extracts simulation parameters (target MW, tolerance).
        """
        if not self.config.loadflow_settings:
            return {"target_mw": 0.0, "tolerance_mw": 0.1}
        
        return {
            "target_mw": self.config.loadflow_settings.target_mw,
            "tolerance_mw": self.config.loadflow_settings.tolerance_mw
        }

    def get_network_components(self) -> Dict[str, List[Any]]:
        """
        Extracts physical components relevant to Load Flow from JSON config.
        """
        return {
            "transformers": self.config.transformers,
            "links": self.config.links_data,
        }

    def convert(self) -> Dict[str, Any]:
        """
        Main entry point to get the full dataset for the Load Flow engine.
        """
        return {
            "settings": self.get_loadflow_settings(),
            "topology": self.get_network_components(),
            "project_name": self.config.project_name
        }
