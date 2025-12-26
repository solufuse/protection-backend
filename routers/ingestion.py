from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from firebase_admin import firestore, storage
import requests
import io
import json
import uuid
import sys
import os

# Import du convertisseur restauré
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_converter import extract_data_from_db

router = APIRouter(
    prefix="/ingestion",
    tags=["Ingestion & Parsing"]
)

db = firestore.client()

class FileProcessRequest(BaseModel):
    user_id: str = Field(..., description="ID Utilisateur")
    file_url: str = Field(..., description="URL Firebase Storage")
    file_type: str = Field(..., description="Extension (.si2s, .mdb)")

class ProcessResponse(BaseModel):
    status: str
    message: str
    doc_id: str | None = None

# --- La logique Smart Storage (Restaurée) ---
def save_smartly(user_id: str, data: dict, file_type: str) -> str:
    json_str = json.dumps(data)
    size_in_bytes = len(json_str.encode('utf-8'))
    LIMIT_BYTES = 900 * 1024 
    
    collection_ref = db.collection("users").document(user_id).collection("configurations")
    
    doc_data = {
        "processed": True,
        "source_type": file_type,
        "created_at": firestore.SERVER_TIMESTAMP,
        "is_large_file": False,
        "storage_path": None,
        "raw_data": None
    }

    if size_in_bytes < LIMIT_BYTES:
        print(f"✅ Data small ({size_in_bytes} bytes). Saving to Firestore.")
        doc_data["raw_data"] = data
        doc_ref = collection_ref.document()
        doc_ref.set(doc_data)
    else:
        print(f"⚠️ Data huge ({size_in_bytes} bytes). Offloading to Storage.")
        file_uuid = str(uuid.uuid4())
        blob_path = f"users/{user_id}/processed_results/{file_uuid}.json"
        
        bucket = storage.bucket()
        blob = bucket.blob(blob_path)
        blob.upload_from_string(json_str, content_type='application/json')
        
        doc_data["is_large_file"] = True
        doc_data["storage_path"] = blob_path
        doc_ref = collection_ref.document()
        doc_ref.set(doc_data)
        
    return doc_ref.id

def process_and_save(user_id: str, file_url: str, file_type: str):
    try:
        print(f"Starting process for user: {user_id}")
        response = requests.get(file_url)
        response.raise_for_status()
        
        file_in_memory = io.BytesIO(response.content)
        
        print("Extracting data...")
        extracted_content = extract_data_from_db(file_in_memory)
        
        doc_id = save_smartly(user_id, extracted_content, file_type)
        return doc_id

    except Exception as e:
        print(f"Error: {str(e)}")
        error_ref = db.collection("users").document(user_id).collection("errors").document()
        error_ref.set({"error": str(e), "file_url": file_url})
        raise e

# --- ENDPOINT (Compatible avec ton Frontend React) ---
# Note: J'ai ajouté l'alias /files/process pour compatibilité
@router.post("/process-file", response_model=ProcessResponse)
@router.post("/process", response_model=ProcessResponse) 
async def process_file_endpoint(request: FileProcessRequest, background_tasks: BackgroundTasks):
    """
    Endpoint principal : Télécharge, Convertit (SQLite), Sauvegarde (Firestore/Storage).
    """
    try:
        if not request.file_url.startswith("http"):
             raise HTTPException(status_code=400, detail="Invalid URL")

        background_tasks.add_task(
            process_and_save, 
            request.user_id, 
            request.file_url, 
            request.file_type
        )
        return ProcessResponse(status="accepted", message="Processing started.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
