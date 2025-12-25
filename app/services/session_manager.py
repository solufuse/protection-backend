
# Gestionnaire de Session (Mémoire RAM)
# Compatible avec l'appel: session_manager.get_files(token)

session_store = {}

def get_files(token: str):
    """Récupère les fichiers pour un token donné"""
    return session_store.get(token, {})

def add_file(token: str, filename: str, content: bytes):
    """Ajoute un fichier"""
    if token not in session_store:
        session_store[token] = {}
    session_store[token][filename] = content

def remove_file(token: str, filename: str):
    """Supprime un fichier"""
    if token in session_store and filename in session_store[token]:
        del session_store[token][filename]

def clear_session(token: str):
    """Vide la session"""
    session_store[token] = {}
