import sqlite3
import pandas as pd
import tempfile
import os
import io

def extract_data_from_si2s(file_content: bytes):
    """
    Extrait toutes les tables du SI2S (SQLite) et renvoie un dictionnaire de DataFrames.
    """
    # 1. Création d'un fichier temporaire car sqlite3 a besoin d'un chemin disque
    with tempfile.NamedTemporaryFile(delete=False, suffix=".SI2S") as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name

    data_frames = {}
    
    try:
        # 2. Connexion à la base de données
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
                print(f"Erreur lecture table {table}: {e}")
                
        conn.close()
        
    except Exception as e:
        print(f"Erreur globale SQLite: {e}")
        return None
        
    finally:
        # 5. Nettoyage (Suppression du fichier temp)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
    return data_frames

def generate_excel_bytes(data_frames: dict) -> io.BytesIO:
    """
    Prend le dictionnaire de DataFrames et renvoie un fichier Excel en mémoire (BytesIO).
    """
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not data_frames:
            # Créer un onglet vide si rien à écrire
            pd.DataFrame({'Info': ['Fichier Vide ou Illisible']}).to_excel(writer, sheet_name='Erreur')
        else:
            for table_name, df in data_frames.items():
                # Excel limite les noms d'onglets à 31 caractères
                sheet_name = table_name[:31]
                
                # Gestion des doublons de noms (rare mais possible)
                count = 1
                base_name = sheet_name
                while sheet_name in writer.book.sheetnames:
                    sheet_name = f"{base_name[:28]}_{count}"
                    count += 1
                
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    # Rembobiner le pointeur au début du fichier mémoire
    output.seek(0)
    return output
