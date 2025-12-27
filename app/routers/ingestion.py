from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime
import os
import json
import uuid
import requests
import tempfile
import shutil
import zipfile
import io
import pandas as pd
import asyncio # Nécessaire pour le délai

try:
    from app.firebase_config import db, bucket
    from app.core.db_converter import DBConverter
    from app.core.memory import SESSIONS
except ImportError:
    from firebase_config import db, bucket
    from core.db_converter import DBConverter
    from core.memory import SESSIONS

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

class IngestionRequest(BaseModel):
    user_id: str
    file_url: str
    file_type: str

ALLOWED_EXTENSIONS = {'.json', '.si2s', '.mdb', '.sqlite', '.lf1s', '.xml'}

# --- FONCTION DE SAUVEGARDE DIFFÉRÉE ---
async def delayed_cloud_upload(user_id, file_path, result_data, file_meta, delay=60):
    """
    Attend X secondes avant d'envoyer les données vers Firebase.
    """
    print(f"   ⏳ Waiting {delay}s before Cloud upload for {file_meta['original_name']}...")
    await asyncio.sleep(delay)
    
    try:
        # 1. Upload Raw File
        blob_raw = bucket.blob(file_meta['raw_file_path'])
        blob_raw.upload_from_filename(file_path)

        # 2. Upload JSON Result
        blob_proc = bucket.blob(file_meta['storage_path'])
        blob_proc.upload_from_string(json.dumps(result_data, default=str), content_type='application/json')

        # 3. Update Firestore
        final_meta = file_meta.copy()
        if 'data_preview' in final_meta: del final_meta['data_preview']
        
        db.collection('users').document(user_id).collection('configurations').document().set(final_meta)
        
        print(f"   ☁️  Delayed Cloud Sync Complete: {file_meta['original_name']}")
        
        # Nettoyage du fichier temporaire après l'upload cloud
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        print(f"   ❌ Delayed Upload Failed: {e}")

def process_single_file(user_id, file_path, original_filename, background_tasks: BackgroundTasks):
    try:
        # 1. CONVERSION IMMÉDIATE
        result_data = DBConverter.convert_to_json(file_path, original_filename)
        _, ext = os.path.splitext(original_filename)

        # IDs et Chemins
        raw_uuid = str(uuid.uuid4())
        result_uuid = str(uuid.uuid4())
        raw_storage_path = f"raw_uploads/{user_id}/{raw_uuid}{ext}"
        proc_storage_path = f"processed/{user_id}/{result_uuid}.json"

        # 2. STOCKAGE RAM IMMÉDIAT (Pour ton dév)
        if user_id not in SESSIONS: SESSIONS[user_id] = []
        
        file_meta = {
            'id': result_uuid,
            'created_at': datetime.utcnow(),
            'source_type': ext.replace('.', ''),
            'original_name': original_filename,
            'processed': True,
            'storage_path': proc_storage_path,
            'raw_file_path': raw_storage_path,
            'preview_available': True,
            'data_preview': result_data # Dispo en RAM tout de suite
        }
        
        SESSIONS[user_id].insert(0, file_meta)
        print(f"   🧠 RAM Updated: {original_filename} (Cloud sync scheduled in 60s)")

        # 3. PROGRAMMATION DE LA TÂCHE DIFFÉRÉE
        # On doit garder une copie locale du fichier le temps du délai
        # On crée un dossier 'buffer' pour stocker les fichiers en attente
        buffer_dir = "/tmp/solufuse_buffer"
        if not os.path.exists(buffer_dir): os.makedirs(buffer_dir)
        persistent_temp_path = os.path.join(buffer_dir, f"{raw_uuid}{ext}")
        shutil.copy(file_path, persistent_temp_path)

        background_tasks.add_task(delayed_cloud_upload, user_id, persistent_temp_path, result_data, file_meta, 60)

    except Exception as e:
        print(f"   ❌ Error: {e}")

def process_file_task(req: IngestionRequest, background_tasks: BackgroundTasks):
    temp_dir = tempfile.mkdtemp()
    try:
        download_path = os.path.join(temp_dir, "input")
        with requests.get(req.file_url, stream=True) as r:
            with open(download_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        
        if zipfile.is_zipfile(download_path):
            with zipfile.ZipFile(download_path, 'r') as z:
                for m in sorted(z.namelist()):
                    if not m.startswith('__') and os.path.splitext(m)[1].lower() in ALLOWED_EXTENSIONS:
                        z.extract(m, temp_dir)
                        process_single_file(req.user_id, os.path.join(temp_dir, m), os.path.basename(m), background_tasks)
        else:
            process_single_file(req.user_id, download_path, f"uploaded.{req.file_type}", background_tasks)
    except Exception as e: print(f"Task Error: {e}")
    finally:
        # On ne supprime le temp_dir que si on a fini de copier les fichiers vers le buffer
        shutil.rmtree(temp_dir)

@router.post("/process")
async def start(req: IngestionRequest, bt: BackgroundTasks):
    # On passe bt à process_file_task pour qu'il puisse ajouter des tâches différées
    bt.add_task(process_file_task, req, bt)
    return {"status": "started", "mode": "RAM-First with 60s Cloud Buffer"}

# Rest of the endpoints (preview, download) remain the same...
# (Ils chercheront en RAM d'abord, puis Cloud en fallback)
@router.get("/preview/{doc_id}")
async def preview(doc_id: str, user_id: str):
    if user_id in SESSIONS:
        for f in SESSIONS[user_id]:
            if f.get('id') == doc_id or doc_id in f.get('storage_path', ''):
                if 'data_preview' in f: return f['data_preview']
    doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
    if not doc.exists: raise HTTPException(404)
    return json.loads(bucket.blob(doc.to_dict()['storage_path']).download_as_string())

@router.get("/download/{doc_id}/{format}")
async def download(doc_id: str, format: str, user_id: str):
    target_data = None
    original_name = "download"
    if user_id in SESSIONS:
        for f in SESSIONS[user_id]:
             if f.get('id') == doc_id or doc_id in f.get('storage_path', ''):
                original_name = f.get('original_name', 'download')
                if format != 'raw' and 'data_preview' in f: target_data = f['data_preview']
                break
    if not target_data and format != 'raw':
        doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
        if doc.exists:
            meta = doc.to_dict()
            original_name = meta.get('original_name', 'download')
            target_data = json.loads(bucket.blob(meta['storage_path']).download_as_string())
    fname = os.path.splitext(original_name)[0]
    if format == 'raw':
        doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
        if not doc.exists: raise HTTPException(404, "Still in buffer...")
        return StreamingResponse(io.BytesIO(bucket.blob(doc.to_dict()['raw_file_path']).download_as_string()), media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename={original_name}"})
    if format == 'json' and target_data:
        return StreamingResponse(io.BytesIO(json.dumps(target_data, default=str).encode()), media_type="application/json", headers={"Content-Disposition": f"attachment; filename={fname}.json"})
    elif format == 'xlsx' and target_data:
        # Import local pour éviter les soucis circulaires
        from app.routers.ingestion import json_to_excel_bytes
        return StreamingResponse(json_to_excel_bytes(target_data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={fname}.xlsx"})
    raise HTTPException(404)

@router.get("/download-all/{format}")
async def download_all(format: str, user_id: str):
    docs = db.collection('users').document(user_id).collection('configurations').stream()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as z:
        for doc in docs:
            meta = doc.to_dict()
            try:
                name = meta.get('original_name', doc.id)
                if format == 'raw' and meta.get('raw_file_path'):
                    z.writestr(name, bucket.blob(meta['raw_file_path']).download_as_string())
                elif meta.get('storage_path'):
                    content = json.loads(bucket.blob(meta['storage_path']).download_as_string())
                    if format == 'json': z.writestr(f"{os.path.splitext(name)[0]}.json", json.dumps(content, default=str))
            except: pass
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=export.zip"})
