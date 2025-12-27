from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.core.security import get_current_token
from typing import List
import zipfile
import io
import os
import uuid
import tempfile
import json
from datetime import datetime

try:
    from app.core.memory import SESSIONS
    from app.core.db_converter import DBConverter
except ImportError:
    from core.memory import SESSIONS
    from core.db_converter import DBConverter

router = APIRouter(prefix="/session", tags=["Session Manager"])

ALLOWED_EXTENSIONS = {'.json', '.si2s', '.lf1s', '.sqlite', '.db'}

def process_and_store(user_id: str, filename: str, content: bytes):
    """Analyse le type de fichier et l'injecte en RAM"""
    ext = os.path.splitext(filename)[1].lower()
    
    # On crée un fichier temporaire pour que DBConverter puisse le lire
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        data_preview = {}
        
        # 1. Traitement selon l'extension
        if ext == '.json':
            try:
                data_preview = json.loads(content.decode('utf-8'))
            except:
                data_preview = {"error": "Invalid JSON content"}
        
        elif ext in ['.si2s', '.lf1s', '.sqlite', '.db']:
            # Utilise le moteur SQLite que nous avons construit
            data_preview = DBConverter.convert_to_json(tmp_path, filename)
        
        else:
            data_preview = {"message": "Fichier binaire stocké sans conversion"}

        # 2. Structure pour la RAM
        if user_id not in SESSIONS:
            SESSIONS[user_id] = []
            
        file_meta = {
            "id": str(uuid.uuid4()),
            "original_name": filename,
            "created_at": datetime.utcnow().isoformat(),
            "source_type": ext.replace('.', ''),
            "cloud_synced": False,
            "data_preview": data_preview
        }
        
        SESSIONS[user_id].insert(0, file_meta)
        return file_meta

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@router.post("/upload")
async def upload_to_session(
    files: List[UploadFile] = File(...), 
    token: str = Depends(get_current_token)
):
    """Supporte ZIP, JSON, SI2S, LF1S"""
    count = 0
    for file in files:
        content = await file.read()
        
        # Cas du ZIP
        if file.filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        # On filtre les fichiers inutiles et on vérifie l'extension
                        ext = os.path.splitext(name)[1].lower()
                        if not name.endswith("/") and "__MACOSX" not in name and ext in ALLOWED_EXTENSIONS:
                            process_and_store(token, name, z.read(name))
                            count += 1
            except Exception as e:
                print(f"Erreur ZIP: {e}")
        
        # Cas des fichiers directs
        else:
            process_and_store(token, file.filename, content)
            count += 1
            
    return {"status": "success", "added": count, "user_id": token}

@router.get("/details")
async def get_details(token: str = Depends(get_current_token)):
    return {"files": SESSIONS.get(token, [])}

@router.delete("/file/{file_id}")
async def delete_file(file_id: str, token: str = Depends(get_current_token)):
    if token in SESSIONS:
        SESSIONS[token] = [f for f in SESSIONS[token] if f['id'] != file_id]
        return {"status": "deleted", "id": file_id}
    return {"status": "error", "message": "Session empty"}

@router.delete("/clear")
async def clear_all(token: str = Depends(get_current_token)):
    SESSIONS[token] = []
    return {"status": "success"}
