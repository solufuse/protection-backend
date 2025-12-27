from fastapi import APIRouter, HTTPException, BackgroundTasks
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

# --- TASK: SYNC CLOUD AFTER 5 SECONDS ---
async def background_cloud_sync(user_id, buffer_path, result_data, file_meta):
    """
    Background task that waits 5 seconds, then uploads to Cloud
    ONLY if cloud is still enabled.
    """
    await asyncio.sleep(5) # Delay buffer
    
    if not CLOUD_SETTINGS.get(user_id, True):
        print(f"   💡 Cloud Disabled: Skipping sync for {file_meta['original_name']}")
        if os.path.exists(buffer_path): os.remove(buffer_path)
        return

    try:
        # 1. Upload Original Binary
        bucket.blob(file_meta['raw_file_path']).upload_from_filename(buffer_path)
        # 2. Upload Processed JSON
        bucket.blob(file_meta['storage_path']).upload_from_string(
            json.dumps(result_data, default=str), content_type='application/json'
        )
        # 3. Update Firestore
        db_meta = file_meta.copy()
        if 'data_preview' in db_meta: del db_meta['data_preview']
        db_meta['cloud_synced'] = True
        db.collection('users').document(user_id).collection('configurations').document(file_meta['id']).set(db_meta)
        
        # Update RAM status
        if user_id in SESSIONS:
            for f in SESSIONS[user_id]:
                if f['id'] == file_meta['id']: f['cloud_synced'] = True
        
        print(f"   ☁️ Cloud Sync Completed: {file_meta['original_name']}")
    except Exception as e:
        print(f"   ❌ Cloud Error: {e}")
    finally:
        if os.path.exists(buffer_path): os.remove(buffer_path)

def process_single_file(user_id, file_path, original_filename, bt: BackgroundTasks):
    # 1. CONVERSION IMMEDIATE (RAM FIRST)
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
        'cloud_synced': False,
        'data_preview': result_data 
    }

    # Injection immédiate en RAM
    if user_id not in SESSIONS: SESSIONS[user_id] = []
    SESSIONS[user_id].insert(0, file_meta)
    print(f"   🧠 Injected in RAM: {original_filename}")

    # 2. PLANIFICATION CLOUD (Si activé)
    if CLOUD_SETTINGS.get(user_id, True):
        # On sécurise une copie du fichier pour le sync asynchrone
        buffer_dir = "/tmp/solufuse_buffer"
        if not os.path.exists(buffer_dir): os.makedirs(buffer_dir)
        buffer_path = os.path.join(buffer_dir, f"sync_{f_id}{ext}")
        shutil.copy(file_path, buffer_path)
        
        bt.add_task(background_cloud_sync, user_id, buffer_path, result_data, file_meta)

@router.post("/process")
async def start_process(user_id: str, file_url: str, file_type: str, bt: BackgroundTasks):
    temp_dir = tempfile.mkdtemp()
    try:
        path = os.path.join(temp_dir, "input")
        r = requests.get(file_url); open(path, 'wb').write(r.content)
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, 'r') as z:
                for m in sorted(z.namelist()):
                    if not m.startswith('__') and not m.endswith('/'):
                        z.extract(m, temp_dir)
                        process_single_file(user_id, os.path.join(temp_dir, m), os.path.basename(m), bt)
        else:
            process_single_file(user_id, path, f"upload.{file_type}", bt)
    finally: shutil.rmtree(temp_dir)
    return {"status": "in_ram"}

@router.post("/toggle-cloud")
async def toggle_cloud(user_id: str, enabled: bool):
    CLOUD_SETTINGS[user_id] = enabled
    return {"cloud_enabled": enabled}

@router.get("/preview/{doc_id}")
async def preview(doc_id: str, user_id: str):
    if user_id in SESSIONS:
        for f in SESSIONS[user_id]:
            if f['id'] == doc_id: return f['data_preview']
    # Fallback Cloud
    doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
    if not doc.exists: raise HTTPException(404)
    return json.loads(bucket.blob(doc.to_dict()['storage_path']).download_as_string())
