from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from app.core.security import get_current_token
from typing import List
import zipfile
import io
import os
import uuid
import tempfile
import shutil
import asyncio
import json
from datetime import datetime

try:
    from app.core.memory import SESSIONS, CLOUD_SETTINGS
    from app.core.db_converter import DBConverter
    from app.firebase_config import db, bucket
except ImportError:
    from core.memory import SESSIONS, CLOUD_SETTINGS
    from core.db_converter import DBConverter
    from firebase_config import db, bucket

router = APIRouter(prefix="/session", tags=["Session Hybrid"])

# --- CLOUD SYNC TASK ---
async def background_cloud_sync(user_id, buffer_path, result_data, file_meta):
    await asyncio.sleep(5)
    if not CLOUD_SETTINGS.get(user_id, True):
        if os.path.exists(buffer_path): os.remove(buffer_path)
        return
    try:
        bucket.blob(file_meta['raw_file_path']).upload_from_filename(buffer_path)
        bucket.blob(file_meta['storage_path']).upload_from_string(
            json.dumps(result_data, default=str), content_type='application/json'
        )
        db_meta = file_meta.copy()
        if 'data_preview' in db_meta: del db_meta['data_preview']
        db_meta['cloud_synced'] = True
        db.collection('users').document(user_id).collection('configurations').document(file_meta['id']).set(db_meta)
        if user_id in SESSIONS:
            for f in SESSIONS[user_id]:
                if f['id'] == file_meta['id']: f['cloud_synced'] = True
    finally:
        if os.path.exists(buffer_path): os.remove(buffer_path)

# --- PROCESSOR ---
def process_to_ram(user_id: str, filename: str, content: bytes, bt: BackgroundTasks):
    ext = os.path.splitext(filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        result_data = DBConverter.convert_to_json(tmp_path, filename)
        f_id = str(uuid.uuid4())
        file_meta = {
            "id": f_id,
            "original_name": filename,
            "created_at": datetime.utcnow(),
            "source_type": ext.replace('.', ''),
            "cloud_synced": False,
            "storage_path": f"processed/{{user_id}}/{{f_id}}.json",
            "raw_file_path": f"raw_uploads/{{user_id}}/{{f_id}}{{ext}}",
            "data_preview": result_data
        }
        
        if user_id not in SESSIONS: SESSIONS[user_id] = []
        SESSIONS[user_id].insert(0, file_meta)

        if CLOUD_SETTINGS.get(user_id, True):
            buffer_dir = "/tmp/solufuse_buffer"
            if not os.path.exists(buffer_dir): os.makedirs(buffer_dir)
            b_path = os.path.join(buffer_dir, f"sync_{f_id}{ext}")
            shutil.copy(tmp_path, b_path)
            bt.add_task(background_cloud_sync, user_id, b_path, result_data, file_meta)
            
        return file_meta
    finally:
        if os.path.exists(tmp_path): os.remove(tmp_path)

# --- ENDPOINTS ---

@router.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...), 
    token: str = Depends(get_current_token)
):
    count = 0
    for file in files:
        content = await file.read()
        if file.filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                for name in z.namelist():
                    if not name.endswith("/") and "__MACOSX" not in name:
                        process_to_ram(token, name, z.read(name), background_tasks)
                        count += 1
        else:
            process_to_ram(token, file.filename, content, background_tasks)
            count += 1
    return {"message": f"{count} fichiers injectés en RAM", "user_id": token}

@router.get("/details")
async def get_details(token: str = Depends(get_current_token)):
    return {"user_id": token, "files": SESSIONS.get(token, [])}

@router.delete("/clear")
async def clear_session(token: str = Depends(get_current_token)):
    if token in SESSIONS: SESSIONS[token] = []
    return {"status": "success", "message": "RAM Cleared", "user_id": token}
