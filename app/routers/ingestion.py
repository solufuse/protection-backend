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

# Imports Hybrides
try:
    from app.firebase_config import db, bucket
    from app.core.db_converter import DBConverter
    from app.core.memory import SESSIONS # <--- Import de la RAM
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

def json_to_excel_bytes(json_content):
    output = io.BytesIO()
    if "raw_content" in json_content and "tables_data" in json_content["raw_content"]:
        tables = json_content["raw_content"]["tables_data"]
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            if not tables: pd.DataFrame().to_excel(writer, sheet_name="Empty")
            else:
                for table_name, rows in tables.items():
                    try:
                        df = pd.DataFrame(rows)
                        sheet_name = table_name[:31]
                        base_name = sheet_name; count = 1
                        while sheet_name in writer.book.sheetnames:
                            sheet_name = f"{base_name[:28]}_{count}"; count += 1
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                    except: pass
    else:
        df = pd.json_normalize(json_content)
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Data')
    output.seek(0)
    return output

def process_single_file(user_id, file_path, original_filename):
    try:
        # A. FIREBASE SIDE (PERSISTENCE)
        raw_uuid = str(uuid.uuid4())
        _, ext = os.path.splitext(original_filename)
        
        # 1. Backup Raw
        raw_storage_path = f"raw_uploads/{user_id}/{raw_uuid}{ext}"
        bucket.blob(raw_storage_path).upload_from_filename(file_path)

        # 2. Convert
        result_data = DBConverter.convert_to_json(file_path, original_filename)
        
        # 3. Save JSON Cloud
        result_uuid = str(uuid.uuid4())
        proc_storage_path = f"processed/{user_id}/{result_uuid}.json"
        bucket.blob(proc_storage_path).upload_from_string(json.dumps(result_data, default=str), content_type='application/json')

        # 4. Save Metadata Firestore
        doc_ref = db.collection('users').document(user_id).collection('configurations').document()
        file_meta = {
            'id': doc_ref.id,
            'created_at': datetime.utcnow(),
            'source_type': ext.replace('.', ''),
            'original_name': original_filename,
            'processed': True,
            'storage_path': proc_storage_path,
            'raw_file_path': raw_storage_path,
            'preview_available': True
        }
        doc_ref.set(file_meta)

        # B. RAM SIDE (DEV BYPASS)
        # On injecte aussi les données directement en mémoire !
        if user_id not in SESSIONS: SESSIONS[user_id] = []
        
        # On ajoute une version "Light" ou "Full" en mémoire selon ton besoin
        # Ici je mets une version complète pour que tu puisses tout inspecter
        ram_copy = file_meta.copy()
        ram_copy['data_preview'] = result_data # On stocke carrément la donnée convertie !
        
        SESSIONS[user_id].insert(0, ram_copy)
        
        print(f"   ✅ Processed: {original_filename} (Saved to Cloud + RAM)")

    except Exception as e: print(f"Error: {e}")

def process_file_task(req: IngestionRequest):
    temp_dir = tempfile.mkdtemp()
    try:
        download_path = os.path.join(temp_dir, "input")
        with requests.get(req.file_url, stream=True) as r:
            with open(download_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        if zipfile.is_zipfile(download_path):
            with zipfile.ZipFile(download_path, 'r') as z:
                for m in z.namelist():
                    if not m.startswith('__') and os.path.splitext(m)[1].lower() in ALLOWED_EXTENSIONS:
                        z.extract(m, temp_dir)
                        process_single_file(req.user_id, os.path.join(temp_dir, m), os.path.basename(m))
        else:
            process_single_file(req.user_id, download_path, f"uploaded.{req.file_type}")
    except Exception as e: print(f"Task Error: {e}")
    finally: shutil.rmtree(temp_dir)

@router.post("/process")
async def start(req: IngestionRequest, bt: BackgroundTasks):
    bt.add_task(process_file_task, req)
    return {"status": "started", "mode": "hybrid (cloud+ram)"}

# Les endpoints preview/download lisent le Cloud (Prod behavior)
@router.get("/preview/{doc_id}")
async def preview(doc_id: str, user_id: str):
    doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
    if not doc.exists: raise HTTPException(404)
    return json.loads(bucket.blob(doc.to_dict()['storage_path']).download_as_string())

@router.get("/download/{doc_id}/{format}")
async def download(doc_id: str, format: str, user_id: str):
    doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
    if not doc.exists: raise HTTPException(404)
    meta = doc.to_dict()
    
    if format == 'raw':
        if not meta.get('raw_file_path'): raise HTTPException(404)
        return StreamingResponse(io.BytesIO(bucket.blob(meta['raw_file_path']).download_as_string()), media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename={meta['original_name']}"})
    
    content = json.loads(bucket.blob(meta['storage_path']).download_as_string())
    fname = os.path.splitext(meta['original_name'])[0]
    
    if format == 'json':
        return StreamingResponse(io.BytesIO(json.dumps(content, default=str).encode()), media_type="application/json", headers={"Content-Disposition": f"attachment; filename={fname}.json"})
    elif format == 'xlsx':
        return StreamingResponse(json_to_excel_bytes(content), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={fname}.xlsx"})

@router.get("/download-all/{format}")
async def download_all(format: str, user_id: str):
    docs = db.collection('users').document(user_id).collection('configurations').stream()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as z:
        for doc in docs:
            meta = doc.to_dict()
            try:
                name = meta.get('original_name', doc.id)
                clean_name = os.path.splitext(name)[0]
                if format == 'raw' and meta.get('raw_file_path'):
                    z.writestr(name, bucket.blob(meta['raw_file_path']).download_as_string())
                elif meta.get('storage_path'):
                    content = json.loads(bucket.blob(meta['storage_path']).download_as_string())
                    if format == 'json': z.writestr(f"{clean_name}.json", json.dumps(content, default=str))
                    elif format == 'xlsx': z.writestr(f"{clean_name}.xlsx", json_to_excel_bytes(content).getvalue())
            except: pass
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=export_all.zip"})
