
import os
import shutil

# C'est le dossier monté via le Volume Dokploy
STORAGE_DIR = "/app/storage"

def _ensure_storage():
    if not os.path.exists(STORAGE_DIR):
        os.makedirs(STORAGE_DIR, exist_ok=True)

def get_files(token: str):
    """
    Lit tous les fichiers du disque et les renvoie en mémoire 
    pour assurer la compatibilité avec les calculateurs existants.
    """
    _ensure_storage()
    files_content = {}
    
    # On parcourt récursivement le dossier storage
    for root, dirs, files in os.walk(STORAGE_DIR):
        for name in files:
            # On ignore les fichiers cachés (.gitkeep, .DS_Store...)
            if name.startswith('.'): continue
            
            full_path = os.path.join(root, name)
            
            # On calcule le chemin relatif (ex: "DOSSIER/fichier.xlsx")
            rel_path = os.path.relpath(full_path, STORAGE_DIR)
            # On normalise les slashes pour Linux
            rel_path = rel_path.replace("\\", "/")
            
            try:
                with open(full_path, 'rb') as f:
                    files_content[rel_path] = f.read()
            except Exception as e:
                print(f"⚠️ Erreur lecture {rel_path}: {e}")
                
    return files_content

def add_file(token: str, filename: str, content: bytes):
    """Ecrit le fichier physiquement sur le disque"""
    _ensure_storage()
    
    # Construction du chemin complet
    full_path = os.path.join(STORAGE_DIR, filename)
    
    # Création des sous-dossiers si nécessaire (ex: NORMAL/253_N_CAPA/...)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    with open(full_path, 'wb') as f:
        f.write(content)

def remove_file(token: str, filename: str):
    """Supprime un fichier spécifique"""
    full_path = os.path.join(STORAGE_DIR, filename)
    if os.path.exists(full_path):
        os.remove(full_path)

def clear_session(token: str):
    """Vide le dossier storage (Attention : destructif)"""
    if os.path.exists(STORAGE_DIR):
        for item in os.listdir(STORAGE_DIR):
            if item.startswith('.'): continue # On protège le .gitkeep
            item_path = os.path.join(STORAGE_DIR, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                print(f"Erreur suppression {item}: {e}")
