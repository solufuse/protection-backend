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

try:
    from app.firebase_config import db, bucket
except ImportError:
    from firebase_config import db, bucket

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

class IngestionRequest(BaseModel):
    user_id: str
    file_url: str
    file_type: str

ALLOWED_EXTENSIONS = {'.json', '.si2s', '.mdb', '.sqlite', '.lf1s', '.xml'}

# --- FONCTIONS UTILITAIRES ---
def process_single_file(user_id, file_path, original_filename):
    try:
        file_ext = os.path.splitext(original_filename)[1].lower()
        print(f"   ⚙️ Processing: {original_filename}")
        
        result_data = {
            "project_name": os.path.splitext(original_filename)[0],
            "source_file": original_filename,
            "processed_at": datetime.utcnow().isoformat(),
            "transformers": [], 
            "plans": []
        }

        if file_ext == '.json':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    if isinstance(content, dict): result_data.update(content)
            except Exception as e: print(f"Warning JSON: {e}")

        result_uuid = str(uuid.uuid4())
        result_filename = f"processed/{user_id}/{result_uuid}.json"
        
        blob = bucket.blob(result_filename)
        blob.upload_from_string(json.dumps(result_data, default=str), content_type='application/json')

        doc_ref = db.collection('users').document(user_id).collection('configurations').document()
        doc_ref.set({
            'created_at': datetime.utcnow(),
            'source_type': file_ext.replace('.', ''),
            'original_name': original_filename,
            'processed': True,
            'is_large_file': True,
            'storage_path': result_filename
        })
        print(f"   ✅ Saved to Firestore: {original_filename}")

    except Exception as e:
        print(f"   ❌ Error processing single file: {e}")

def process_file_task(req: IngestionRequest):
    if not db or not bucket: return
    temp_dir = tempfile.mkdtemp()
    download_path = os.path.join(temp_dir, f"input_download")
    try:
        with requests.get(req.file_url, stream=True) as r:
            r.raise_for_status()
            with open(download_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        
        if zipfile.is_zipfile(download_path):
            with zipfile.ZipFile(download_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    if member.startswith('__MACOSX') or member.endswith('/'): continue
                    _, ext = os.path.splitext(member)
                    if ext.lower() in ALLOWED_EXTENSIONS:
                        zip_ref.extract(member, temp_dir)
                        process_single_file(req.user_id, os.path.join(temp_dir, member), os.path.basename(member))
        else:
            original_name = "uploaded_file." + req.file_type
            process_single_file(req.user_id, download_path, original_name)
    except Exception as e: print(f"Global Error: {e}")
    finally: shutil.rmtree(temp_dir)

# --- ENDPOINTS ---

@router.post("/process")
async def start_ingestion(req: IngestionRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_file_task, req)
    return {"status": "started"}

@router.get("/download/{doc_id}/{format}")
async def download_single(doc_id: str, format: str, user_id: str):
    """Télécharge UN SEUL fichier converti"""
    doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
    if not doc.exists: raise HTTPException(404, "Fichier introuvable")
    
    meta = doc.to_dict()
    blob = bucket.blob(meta['storage_path'])
    json_content = json.loads(blob.download_as_string())
    
    filename = os.path.splitext(meta['original_name'])[0]
    
    if format == 'json':
        return StreamingResponse(
            io.BytesIO(json.dumps(json_content, indent=2, default=str).encode()),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}.json"}
        )
    elif format == 'xlsx':
        output = io.BytesIO()
        # On essaie d'aplatir le JSON pour Excel
        df = pd.json_normalize(json_content)
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Data')
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"}
        )

@router.get("/download-all/{format}")
async def download_all(format: str, user_id: str):
    """Télécharge TOUT en ZIP"""
    docs = db.collection('users').document(user_id).collection('configurations').stream()
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for doc in docs:
            meta = doc.to_dict()
            if not meta.get('storage_path'): continue
            
            try:
                blob = bucket.blob(meta['storage_path'])
                content = json.loads(blob.download_as_string())
                clean_name = os.path.splitext(meta.get('original_name', doc.id))[0]

                if format == 'json':
                    zip_file.writestr(f"{clean_name}.json", json.dumps(content, indent=2, default=str))
                elif format == 'xlsx':
                    df = pd.json_normalize(content)
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False)
                    zip_file.writestr(f"{clean_name}.xlsx", excel_buffer.getvalue())
            except Exception as e:
                print(f"Error zipping {doc.id}: {e}")

    zip_buffer.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d")
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=solufuse_export_{timestamp}_{format}.zip"}
    )
