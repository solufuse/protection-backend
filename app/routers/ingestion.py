from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime
import os
import json
import uuid
import requests
import tempfile
import shutil

# Import sécurisé
try:
    from app.firebase_config import db, bucket
except ImportError:
    from firebase_config import db, bucket

# --- CORRECTION ICI : ON FORCE LE PREFIXE ---
router = APIRouter(
    prefix="/ingestion",
    tags=["ingestion"]
)

class IngestionRequest(BaseModel):
    user_id: str
    file_url: str
    file_type: str

def process_file_task(req: IngestionRequest):
    if not db or not bucket:
        print("❌ ABORT: Firebase non initialisé.")
        return

    temp_dir = tempfile.mkdtemp()
    local_path = os.path.join(temp_dir, f"input.{req.file_type}")
    
    try:
        print(f"📥 Downloading file for user {req.user_id}...")
        # 1. DOWNLOAD
        with requests.get(req.file_url, stream=True) as r:
            r.raise_for_status()
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # 2. PROCESSING (Mock)
        print("⚙️ Processing file...")
        result_data = {
            "project_name": "Imported Project",
            "source_file": req.file_url,
            "processed_at": datetime.now().isoformat(),
            "transformers": [{"name": "TX-IMPORTED", "sn_kva": 2500}],
            "plans": []
        }
        
        # Si c'est un JSON, on le charge tel quel
        if req.file_type == 'json':
            try:
                with open(local_path, 'r') as f:
                    result_data = json.load(f)
            except: pass

        # 3. UPLOAD RESULT (JSON)
        result_filename = f"processed/{req.user_id}/{uuid.uuid4()}.json"
        blob = bucket.blob(result_filename)
        blob.upload_from_string(json.dumps(result_data), content_type='application/json')
        print(f"💾 Result uploaded to {result_filename}")

        # 4. FIRESTORE WRITE (C'est ça qui affiche le fichier sur le site)
        # On utilise une collection générique si besoin, ou la structure users/{uid}/configurations
        doc_ref = db.collection('users').document(req.user_id).collection('configurations').document()
        doc_ref.set({
            'created_at': datetime.utcnow(), 
            'source_type': req.file_type,
            'original_name': 'Imported File',
            'processed': True,
            'is_large_file': True,
            'storage_path': result_filename,
            'raw_data': None # On garde le document léger
        })
        print(f"✅ Firestore document created! ID: {doc_ref.id}")

    except Exception as e:
        print(f"❌ Error processing file: {e}")
    finally:
        shutil.rmtree(temp_dir)

@router.post("/process")
async def start_ingestion(req: IngestionRequest, background_tasks: BackgroundTasks):
    if not db:
        raise HTTPException(status_code=500, detail="Firebase Database not connected on server.")
        
    background_tasks.add_task(process_file_task, req)
    return {"status": "started", "message": "Processing started in background"}

@router.get("/download-all/{format}")
async def download_all(format: str, user_id: str):
    return {"message": "Not implemented yet"}
