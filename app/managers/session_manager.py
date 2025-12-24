
from datetime import datetime, timedelta

# Stockage RAM : { "token_user": { "data": {...}, "expires_at": datetime } }
_sessions = {}

def save_session(token: str, files_data: dict, config: dict):
    # Expire dans 1h
    exp = datetime.utcnow() + timedelta(hours=1)
    _sessions[token] = {
        "files": files_data,
        "config": config,
        "expires_at": exp
    }
    # Nettoyage passif des vieilles sessions
    clean_expired()

def get_session(token: str):
    sess = _sessions.get(token)
    if sess:
        if datetime.utcnow() > sess['expires_at']:
            del _sessions[token]
            return None
        return sess
    return None

def clear_session(token: str):
    if token in _sessions:
        del _sessions[token]

def clean_expired():
    now = datetime.utcnow()
    tokens_to_delete = [t for t, s in _sessions.items() if now > s['expires_at']]
    for t in tokens_to_delete:
        del _sessions[t]
