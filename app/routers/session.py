from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from app.core.security import get_current_token
from typing import List
import zipfile
import io
import os
import uuid
import tempfile
import shutil
from datetime import datetime

try:
    from app.core.memory import SESSIONS
    from app.core.db_converter import DBConverter
except ImportError:
    from core.memory import SESSIONS
    from core.db_converter import DBConverter

router = APIRouter(prefix="/session", tags=["Session Manager"])

def process_and_store(user_id: str, filename: str, content: bytes):
    """Helper pour convertir et stocker un fichier en RAM"""
    ext = os.path.splitext(filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        # Conversion SQLite/LF1S -> JSON
        result_data = DBConverter.convert_to_json(tmp_path, filename)
        
        if user_id not in SESSIONS:
            SESSIONS[user_id] = []
        
        file_meta = {
            "id": str(uuid.uuid4()),
            "original_name": filename,
            "created_at": datetime.utcnow().isoformat(),
            "source_type": ext.replace('.', ''),
            "cloud_synced": False,
            "data_preview": result_data
        }
        SESSIONS[user_id].insert(0, file_meta)
        return file_meta
    finally:
        if os.path.exists(tmp_path): os.remove(tmp_path)

@router.post("/upload")
async def upload_to_session(
    files: List[UploadFile] = File(...), 
    token: str = Depends(get_current_token)
):
    """Ajoute un ou plusieurs fichiers à la RAM (Support ZIP)"""
    count = 0
    for file in files:
        content = await file.read()
        if file.filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        if not name.endswith("/") and "__MACOSX" not in name:
                            process_and_store(token, name, z.read(name))
                            count += 1
            except:
                process_and_store(token, file.filename, content)
                count += 1
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
    raise HTTPException(404, "Session non trouvée")

@router.delete("/clear")
async def clear_all(token: str = Depends(get_current_token)):
    SESSIONS[token] = []
    return {"status": "success", "message": "RAM cleared"}
