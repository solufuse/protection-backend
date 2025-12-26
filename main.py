from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import firebase_admin
from firebase_admin import credentials, firestore, storage
import requests
import io
import json
import uuid
import sys

# Import the converter module (assumed to be present from previous step)
from db_converter import extract_data_from_db

# --- CONFIGURATION & INIT ---

app = FastAPI(title="Solufuse Backend API", version="1.1.0")

# Initialize Firebase Admin SDK
# Note: For Storage to work with default bucket, ensure App Engine is enabled 
# or pass {'storageBucket': 'your-project-id.appspot.com'} if not auto-detected.
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- PYDANTIC MODELS (v2) ---

class FileProcessRequest(BaseModel):
    user_id: str = Field(..., description="The unique ID of the user in Firestore")
    file_url: str = Field(..., description="The download URL from Firebase Storage")
    file_type: str = Field(..., description="Type of file (e.g., 'si2s', 'mdb')")

class ProcessResponse(BaseModel):
    status: str
    message: str
    doc_id: str | None = None

# --- HELPER FUNCTIONS ---

def save_smartly(user_id: str, data: dict, file_type: str) -> str:
    """
    Analyzes the size of the data.
    - If < 900KB: Saves directly to Firestore.
    - If > 900KB: Uploads JSON to Storage and saves the path in Firestore.
    
    Returns:
        str: The ID of the Firestore document created.
    """
    
    # 1. Serialize data to measure size
    json_str = json.dumps(data)
    size_in_bytes = len(json_str.encode('utf-8'))
    
    # Firestore limit is 1MiB (1,048,576 bytes). We use 900KB as a safety margin.
    LIMIT_BYTES = 900 * 1024 
    
    collection_ref = db.collection("users").document(user_id).collection("configurations")
    
    # Base document metadata
    doc_data = {
        "processed": True,
        "source_type": file_type,
        "created_at": firestore.SERVER_TIMESTAMP,
        "is_large_file": False,
        "storage_path": None,
        "raw_data": None
    }

    if size_in_bytes < LIMIT_BYTES:
        print(f"✅ Data is small ({size_in_bytes} bytes). Saving to Firestore.")
        doc_data["raw_data"] = data
        doc_ref = collection_ref.document()
        doc_ref.set(doc_data)
        
    else:
        print(f"⚠️ Data is huge ({size_in_bytes} bytes). Offloading to Storage.")
        
        # Define storage path for the JSON result
        file_uuid = str(uuid.uuid4())
        blob_path = f"users/{user_id}/processed_results/{file_uuid}.json"
        
        # Upload to Firebase Storage
        bucket = storage.bucket() # Uses default bucket
        blob = bucket.blob(blob_path)
        blob.upload_from_string(json_str, content_type='application/json')
        
        # Update metadata for Firestore
        doc_data["is_large_file"] = True
        doc_data["storage_path"] = blob_path
        # We do NOT include "raw_data" here to keep the document light
        
        doc_ref = collection_ref.document()
        doc_ref.set(doc_data)
        
    return doc_ref.id

# --- CORE LOGIC ---

def process_and_save(user_id: str, file_url: str, file_type: str):
    """
    Downloads, processes, and saves result using smart storage strategy.
    """
    try:
        print(f"Starting process for user: {user_id}, type: {file_type}")
        
        # 1. Download file into memory (RAM)
        response = requests.get(file_url)
        response.raise_for_status()
        
        file_in_memory = io.BytesIO(response.content)
        
        # 2. Extract data via db_converter
        print("Extracting data via db_converter...")
        extracted_content = extract_data_from_db(file_in_memory)
        
        # 3. Save result (Handle size limits automatically)
        doc_id = save_smartly(user_id, extracted_content, file_type)
        
        print(f"Process completed. Document ID: {doc_id}")
        return doc_id

    except Exception as e:
        print(f"Error processing file: {str(e)}")
        
        # Log error to Firestore
        error_ref = db.collection("users").document(user_id).collection("errors").document()
        error_ref.set({
            "error": str(e), 
            "file_url": file_url,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        raise e

# --- ENDPOINTS ---

@app.post("/process-file", response_model=ProcessResponse)
async def process_file_endpoint(request: FileProcessRequest, background_tasks: BackgroundTasks):
    try:
        if not request.file_url.startswith("http"):
             raise HTTPException(status_code=400, detail="Invalid URL format")

        background_tasks.add_task(
            process_and_save, 
            request.user_id, 
            request.file_url, 
            request.file_type
        )

        return ProcessResponse(
            status="accepted", 
            message="File processing started in background."
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def health_check():
    return {"status": "ok", "service": "Solufuse Backend"}
