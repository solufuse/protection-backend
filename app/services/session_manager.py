
import os
import shutil

# Racine du Volume Dokploy
BASE_STORAGE_DIR = "/app/storage"

def _get_user_dir(token: str):
    """Retourne le chemin vers le dossier spécifique de l'utilisateur"""
    # Le token EST l'ID utilisateur (uid) grâce à security.py
    user_dir = os.path.join(BASE_STORAGE_DIR, token)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)
    return user_dir

def get_files(token: str):
    """
    Récupère uniquement les fichiers du dossier de l'utilisateur courant.
    Renvoie un dictionnaire { 'dossier/fichier.ext': bytes }
    """
    user_dir = _get_user_dir(token)
    files_content = {}
    
    # On ne scanne que le dossier de cet utilisateur
    for root, dirs, files in os.walk(user_dir):
        for name in files:
            if name.startswith('.'): continue
            
            full_path = os.path.join(root, name)
            
            # Le chemin relatif doit être propre à l'utilisateur (sans son ID devant)
            rel_path = os.path.relpath(full_path, user_dir)
            rel_path = rel_path.replace("\\", "/")
            
            try:
                with open(full_path, 'rb') as f:
                    files_content[rel_path] = f.read()
            except Exception as e:
                print(f"⚠️ Erreur lecture {rel_path}: {e}")
                
    return files_content

def add_file(token: str, filename: str, content: bytes):
    """Ecrit le fichier dans le dossier de l'utilisateur"""
    user_dir = _get_user_dir(token)
    
    # Construction du chemin complet
    full_path = os.path.join(user_dir, filename)
    
    # Création des sous-dossiers si nécessaire (ex: user_id/NORMAL/...)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    with open(full_path, 'wb') as f:
        f.write(content)

def remove_file(token: str, filename: str):
    """Supprime un fichier de l'utilisateur"""
    user_dir = _get_user_dir(token)
    full_path = os.path.join(user_dir, filename)
    if os.path.exists(full_path):
        os.remove(full_path)

def clear_session(token: str):
    """Vide uniquement le dossier de l'utilisateur"""
    user_dir = _get_user_dir(token)
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)
        # On recrée le dossier vide tout de suite après
        os.makedirs(user_dir, exist_ok=True)
