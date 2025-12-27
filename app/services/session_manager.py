import os
import shutil

# On définit le chemin absolu ici pour tout le monde
# "/app/storage" est le standard pour un conteneur Docker où WORKDIR=/app
BASE_STORAGE_DIR = "/app/storage"

def get_user_storage_path(token: str) -> str:
    """Retourne le chemin absolu du dossier utilisateur"""
    path = os.path.join(BASE_STORAGE_DIR, token)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

def get_absolute_file_path(token: str, filename: str) -> str:
    """Retourne le chemin absolu d'un fichier spécifique"""
    user_dir = get_user_storage_path(token)
    return os.path.join(user_dir, os.path.basename(filename))

def get_files(token: str):
    """
    Récupère le contenu des fichiers pour le traitement en mémoire.
    """
    user_dir = get_user_storage_path(token)
    files_content = {}
    
    if os.path.exists(user_dir):
        for root, dirs, files in os.walk(user_dir):
            for name in files:
                if name.startswith('.'): continue
                full_path = os.path.join(root, name)
                # Chemin relatif pour l'identification (ex: "mon_dossier/fic.txt")
                rel_path = os.path.relpath(full_path, user_dir).replace("\\", "/")
                try:
                    with open(full_path, 'rb') as f:
                        files_content[rel_path] = f.read()
                except Exception as e:
                    print(f"Error reading {rel_path}: {e}")
                
    return files_content

def add_file(token: str, filename: str, content: bytes):
    file_path = get_absolute_file_path(token, filename)
    with open(file_path, 'wb') as f:
        f.write(content)

def remove_file(token: str, filename: str):
    file_path = get_absolute_file_path(token, filename)
    if os.path.exists(file_path):
        os.remove(file_path)

def clear_session(token: str):
    user_dir = get_user_storage_path(token)
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)
        os.makedirs(user_dir, exist_ok=True)
