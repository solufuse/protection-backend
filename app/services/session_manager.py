
# Session Manager (RAM Memory)
# Compatible with call: session_manager.get_files(token)

session_store = {}

def get_files(token: str):
    """Retrieves files for a given token"""
    return session_store.get(token, {})

def add_file(token: str, filename: str, content: bytes):
    """Adds a file"""
    if token not in session_store:
        session_store[token] = {}
    session_store[token][filename] = content

def remove_file(token: str, filename: str):
    """Removes a file"""
    if token in session_store and filename in session_store[token]:
        del session_store[token][filename]

def clear_session(token: str):
    """Clears the session"""
    session_store[token] = {}
