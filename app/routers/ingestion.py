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
    from app.core.db_converter import DBConverter
except ImportError:
    from firebase_config import db, bucket
    from core.db_converter import DBConverter

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

class IngestionRequest(BaseModel):
    user_id: str
    file_url: str
    file_type: str

ALLOWED_EXTENSIONS = {'.json', '.si2s', '.mdb', '.sqlite', '.lf1s', '.xml'}

# --- FONCTIONS UTILITAIRES ---
def process_single_file(user_id, file_path, original_filename):
    try:
        print(f"   ⚙️ Processing: {original_filename}")
        result_data = DBConverter.convert_to_json(file_path, original_filename)
        
        result_uuid = str(uuid.uuid4())
        result_filename = f"processed/{user_id}/{result_uuid}.json"
        
        blob = bucket.blob(result_filename)
        blob.upload_from_string(json.dumps(result_data, default=str), content_type='application/json')

        doc_ref = db.collection('users').document(user_id).collection('configurations').document()
        doc_ref.set({
            'created_at': datetime.utcnow(),
            'source_type': os.path.splitext(original_filename)[1].replace('.', ''),
            'original_name': original_filename,
            'processed': True,
            'is_large_file': True,
            'storage_path': result_filename,
            'preview_available': True
        })
        print(f"   ✅ Saved: {original_filename}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

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

# --- HELPER POUR EXCEL (LOGIQUE DU USER) ---
def json_to_excel_bytes(json_content):
    """Reconstruit l'Excel multi-onglets à partir du JSON"""
    output = io.BytesIO()
    
    # Vérifie si c'est un fichier issu d'une conversion SQL (structure complexe)
    if "raw_content" in json_content and "tables_data" in json_content["raw_content"]:
        tables = json_content["raw_content"]["tables_data"]
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            if not tables:
                # Créer une feuille vide si pas de données
                pd.DataFrame().to_excel(writer, sheet_name="Empty")
            else:
                for table_name, rows in tables.items():
                    try:
                        df = pd.DataFrame(rows)
                        # Logique de nommage (comme dans si2s_converter.py)
                        sheet_name = table_name[:31]
                        base_name = sheet_name
                        count = 1
                        # Gestion des doublons de noms d'onglets
                        while sheet_name in writer.book.sheetnames:
                            sheet_name = f"{base_name[:28]}_{count}"
                            count += 1
                        
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                    except Exception as e:
                        print(f"Error writing sheet {table_name}: {e}")
    else:
        # Cas simple (Fichier JSON plat ou autre)
        df = pd.json_normalize(json_content)
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Data')
            
    output.seek(0)
    return output

# --- ENDPOINTS ---
@router.post("/process")
async def start_ingestion(req: IngestionRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_file_task, req)
    return {"status": "started"}

@router.get("/preview/{doc_id}")
async def preview_file(doc_id: str, user_id: str):
    doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
    if not doc.exists: raise HTTPException(404, "File not found")
    meta = doc.to_dict()
    blob = bucket.blob(meta['storage_path'])
    return json.loads(blob.download_as_string())

@router.get("/download/{doc_id}/{format}")
async def download_single(doc_id: str, format: str, user_id: str):
    doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
    if not doc.exists: raise HTTPException(404, "File not found")
    meta = doc.to_dict()
    blob = bucket.blob(meta['storage_path'])
    json_content = json.loads(blob.download_as_string())
    filename = os.path.splitext(meta['original_name'])[0]
    
    if format == 'json':
        return StreamingResponse(io.BytesIO(json.dumps(json_content, indent=2, default=str).encode()), media_type="application/json", headers={"Content-Disposition": f"attachment; filename={filename}.json"})
    elif format == 'xlsx':
        excel_bytes = json_to_excel_bytes(json_content)
        return StreamingResponse(excel_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"})

@router.get("/download-all/{format}")
async def download_all(format: str, user_id: str):
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
                    excel_bytes = json_to_excel_bytes(content)
                    zip_file.writestr(f"{clean_name}.xlsx", excel_bytes.getvalue())
            except Exception as e: print(f"Zip Error: {e}")
            
    zip_buffer.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d")
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=solufuse_export_{timestamp}_{format}.zip"})
