from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from firebase_admin import firestore, storage
import requests
import io
import json
import uuid
import sys
import os

# Import relatif propre
from app.utils.db_converter import extract_data_from_db

# Je nomme ce router explicitement pour l'auto-loader
router = APIRouter(prefix="/files", tags=["Cloud File Processing"])
db = firestore.client()

class FileProcessRequest(BaseModel):
    user_id: str
    file_url: str
    file_type: str

class ProcessResponse(BaseModel):
    status: str
    message: str
    doc_id: str | None = None

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
        doc_data["raw_data"] = data
        doc_ref = collection_ref.document()
        doc_ref.set(doc_data)
    else:
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
        response = requests.get(file_url)
        response.raise_for_status()
        file_in_memory = io.BytesIO(response.content)
        extracted_content = extract_data_from_db(file_in_memory)
        doc_id = save_smartly(user_id, extracted_content, file_type)
        return doc_id
    except Exception as e:
        error_ref = db.collection("users").document(user_id).collection("errors").document()
        error_ref.set({"error": str(e), "file_url": file_url})
        raise e

@router.post("/process", response_model=ProcessResponse)
async def process_file_endpoint(request: FileProcessRequest, background_tasks: BackgroundTasks):
    try:
        if not request.file_url.startswith("http"):
             raise HTTPException(status_code=400, detail="Invalid URL")
        background_tasks.add_task(process_and_save, request.user_id, request.file_url, request.file_type)
        return ProcessResponse(status="accepted", message="Processing started.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
