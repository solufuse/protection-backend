import os
import shutil

class SessionManager:
    def __init__(self):
        self._sessions = {}
        self.storage_root = "/app/storage"
        if not os.path.exists(self.storage_root):
            os.makedirs(self.storage_root)

    def _load_from_disk(self, token: str):
        """Charge les fichiers du disque vers la mémoire si nécessaire"""
        user_dir = os.path.join(self.storage_root, token)
        if not os.path.exists(user_dir):
            return {}
        
        loaded_files = {}
        for root, _, files in os.walk(user_dir):
            for name in files:
                full_path = os.path.join(root, name)
                try:
                    with open(full_path, "rb") as f:
                        # On utilise le nom de fichier relatif ou absolu selon la logique, 
                        # ici on garde le filename simple pour compatibilité ingestion
                        loaded_files[name] = f.read() 
                except Exception as e:
                    print(f"Error loading {name}: {e}")
        
        self._sessions[token] = loaded_files
        return loaded_files

    def get_files(self, token: str):
        # Si la session n'existe pas ou est vide, on tente de recharger du disque
        if token not in self._sessions or not self._sessions[token]:
            self._load_from_disk(token)
        return self._sessions.get(token, {})

    def add_file(self, token: str, filename: str, content: bytes):
        # 1. Mise à jour RAM
        if token not in self._sessions:
            self._sessions[token] = {}
        self._sessions[token][filename] = content
        
        # 2. Persistance Disque
        user_dir = os.path.join(self.storage_root, token)
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
        
        file_path = os.path.join(user_dir, filename)
        with open(file_path, "wb") as f:
            f.write(content)

    def remove_file(self, token: str, filename: str):
        # RAM
        if token in self._sessions and filename in self._sessions[token]:
            del self._sessions[token][filename]
        
        # Disque
        file_path = os.path.join(self.storage_root, token, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    def clear_session(self, token: str):
        self._sessions[token] = {}
        user_dir = os.path.join(self.storage_root, token)
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)

session_manager = SessionManager()
