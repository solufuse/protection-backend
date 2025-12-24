# Stockage RAM
_sessions = {}

def save_files(token: str, new_files: dict):
    if token not in _sessions:
        _sessions[token] = {"files": {}}
    _sessions[token]["files"].update(new_files)
    return len(_sessions[token]["files"])

def get_files(token: str):
    session = _sessions.get(token)
    return session.get("files", {}) if session else {}

def remove_file(token: str, filename: str):
    session = _sessions.get(token)
    if session and filename in session.get("files", {}):
        del session["files"][filename]
        return True
    return False

def clear_session(token: str):
    if token in _sessions:
        del _sessions[token]
        return True
    return False

def get_session_details(token: str):
    session = _sessions.get(token)
    if not session:
        return {"active": False, "file_count": 0, "files": []}
    
    files_info = []
    for name, content in session.get("files", {}).items():
        size_kb = round(len(content) / 1024, 2)
        files_info.append({"name": name, "size_kb": size_kb})
        
    return {"active": True, "file_count": len(files_info), "files": files_info}
