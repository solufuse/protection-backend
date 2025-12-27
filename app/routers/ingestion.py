from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
import os, json, uuid, requests, tempfile, shutil, zipfile, io, asyncio
from datetime import datetime
import pandas as pd

try:
    from app.firebase_config import db, bucket
    from app.core.db_converter import DBConverter
    from app.core.memory import SESSIONS, CLOUD_SETTINGS
except ImportError:
    from firebase_config import db, bucket
    from core.db_converter import DBConverter
    from core.memory import SESSIONS, CLOUD_SETTINGS

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

# --- CLOUD SYNC TASK (5s DELAY) ---
async def background_cloud_sync(user_id, file_path, result_data, file_meta):
    # Wait 5 seconds (Priority is RAM)
    await asyncio.sleep(5)
    
    # Check if Cloud is still enabled for this user
    if not CLOUD_SETTINGS.get(user_id, True):
        print(f"   🚫 Cloud disabled for {user_id}. Aborting sync for {file_meta['original_name']}")
        if os.path.exists(file_path): os.remove(file_path)
        return

    try:
        # Upload to Storage
        bucket.blob(file_meta['raw_file_path']).upload_from_filename(file_path)
        bucket.blob(file_meta['storage_path']).upload_from_string(
            json.dumps(result_data, default=str), content_type='application/json'
        )
        # Save to Firestore
        db_meta = file_meta.copy()
        if 'data_preview' in db_meta: del db_meta['data_preview']
        db_meta['cloud_synced'] = True
        db.collection('users').document(user_id).collection('configurations').document(file_meta['id']).set(db_meta)
        
        # Update RAM status to show it's now in cloud
        if user_id in SESSIONS:
            for f in SESSIONS[user_id]:
                if f['id'] == file_meta['id']: f['cloud_synced'] = True
                
        print(f"   ☁️ Cloud Sync Success: {file_meta['original_name']}")
    except Exception as e: print(f"   ❌ Cloud Sync Error: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

def process_single_file(user_id, file_path, original_filename, bt: BackgroundTasks):
    # 1. IMMEDIATE CONVERSION
    result_data = DBConverter.convert_to_json(file_path, original_filename)
    f_id = str(uuid.uuid4())
    _, ext = os.path.splitext(original_filename)

    file_meta = {
        'id': f_id,
        'created_at': datetime.utcnow(),
        'source_type': ext.replace('.', ''),
        'original_name': original_filename,
        'storage_path': f"processed/{user_id}/{f_id}.json",
        'raw_file_path': f"raw_uploads/{user_id}/{f_id}{ext}",
        'cloud_synced': False, # Status for UI
        'data_preview': result_data 
    }

    # 2. IMMEDIATE RAM UPDATE
    if user_id not in SESSIONS: SESSIONS[user_id] = []
    SESSIONS[user_id].insert(0, file_meta)
    print(f"   🧠 RAM Ready: {original_filename}")

    # 3. SCHEDULE CLOUD SYNC (If enabled)
    if CLOUD_SETTINGS.get(user_id, True):
        buffer_path = os.path.join("/tmp", f"sync_{f_id}{ext}")
        shutil.copy(file_path, buffer_path)
        bt.add_task(background_cloud_sync, user_id, buffer_path, result_data, file_meta)

# --- ENDPOINTS ---

@router.post("/process")
async def start_process(req: { "user_id": str, "file_url": str, "file_type": str }, bt: BackgroundTasks):
    temp_dir = tempfile.mkdtemp()
    try:
        path = os.path.join(temp_dir, "input")
        r = requests.get(req['file_url']); open(path, 'wb').write(r.content)
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, 'r') as z:
                for m in z.namelist():
                    if not m.startswith('__'):
                        z.extract(m, temp_dir)
                        process_single_file(req['user_id'], os.path.join(temp_dir, m), m, bt)
        else:
            process_single_file(req['user_id'], path, f"file.{req['file_type']}", bt)
    finally: shutil.rmtree(temp_dir)
    return {"status": "ok"}

@router.post("/toggle-cloud")
async def toggle_cloud(user_id: str, enabled: bool):
    """Permet d'activer ou désactiver l'envoi vers Firebase"""
    CLOUD_SETTINGS[user_id] = enabled
    return {"user_id": user_id, "cloud_enabled": enabled}

@router.get("/preview/{doc_id}")
async def preview(doc_id: str, user_id: str):
    if user_id in SESSIONS:
        for f in SESSIONS[user_id]:
            if f['id'] == doc_id: return f['data_preview']
    # Fallback Firebase
    doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
    if not doc.exists: raise HTTPException(404)
    return json.loads(bucket.blob(doc.to_dict()['storage_path']).download_as_string())
