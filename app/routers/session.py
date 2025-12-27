from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from app.core.security import get_current_token
from app.core.memory import SESSIONS, CLOUD_SETTINGS
from app.core.db_converter import DBConverter
from app.firebase_config import db, bucket
from typing import List
import zipfile
import io
import os
import uuid
import tempfile
import json
from datetime import datetime

router = APIRouter(prefix="/session", tags=["Session Sync"])

def sync_file_to_ram_and_cloud(user_id: str, filename: str, content: bytes, bt: BackgroundTasks):
    """
    Injection RAM immédiate + Programmation Sync Cloud
    """
    ext = os.path.splitext(filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # 1. Conversion RAM (Instantané)
        result_data = DBConverter.convert_to_json(tmp_path, filename)
        f_id = str(uuid.uuid4())
        
        file_meta = {
            "id": f_id,
            "original_name": filename,
            "created_at": datetime.utcnow().isoformat(),
            "source_type": ext.replace('.', ''),
            "cloud_synced": False,
            "data_preview": result_data,
            "storage_path": f"processed/{user_id}/{f_id}.json",
            "raw_file_path": f"raw_uploads/{user_id}/{f_id}{ext}"
        }

        if user_id not in SESSIONS:
            SESSIONS[user_id] = []
        SESSIONS[user_id].insert(0, file_meta)

        # 2. Backup Cloud (5s delay) - On crée une tâche de fond
        if CLOUD_SETTINGS.get(user_id, True):
            # On passe par l'ingestion asynchrone pour ne pas bloquer
            from app.routers.ingestion import background_cloud_sync
            
            # Copie buffer pour le délai
            buffer_dir = "/tmp/session_buffer"
            if not os.path.exists(buffer_dir): os.makedirs(buffer_dir)
            b_path = os.path.join(buffer_dir, f"sync_{f_id}{ext}")
            shutil.copy(tmp_path, b_path)
            
            bt.add_task(background_cloud_sync, user_id, b_path, result_data, file_meta)
            
        return file_meta
    finally:
        if os.path.exists(tmp_path): os.remove(tmp_path)

@router.post("/upload")
async def upload_to_session(
    bt: BackgroundTasks,
    files: List[UploadFile] = File(...), 
    token: str = Depends(get_current_token)
):
    """Upload direct vers RAM + Sync Cloud automatique"""
    added = 0
    for file in files:
        content = await file.read()
        if file.filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                for name in z.namelist():
                    if not name.endswith("/") and "__MACOSX" not in name:
                        sync_file_to_ram_and_cloud(token, name, z.read(name), bt)
                        added += 1
        else:
            sync_file_to_ram_and_cloud(token, file.filename, content, bt)
            added += 1
    return {"status": "synchronized", "count": added}

@router.get("/details")
async def get_details(token: str = Depends(get_current_token)):
    """La vérité est ici : ce qui est en RAM est prioritaire"""
    return {
        "user_id": token,
        "files": SESSIONS.get(token, []),
        "cloud_enabled": CLOUD_SETTINGS.get(token, True)
    }

@router.delete("/clear")
async def clear_session(token: str = Depends(get_current_token)):
    SESSIONS[token] = []
    # On pourrait aussi vider Firestore ici si on voulait une purge totale
    return {"status": "cleared"}
