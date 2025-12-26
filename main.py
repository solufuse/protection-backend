from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import firebase_admin
from firebase_admin import credentials, firestore, storage
import requests
import io
import json
import os
import uuid
import sys

# Import local simple
from db_converter import extract_data_from_db

# --- CONFIGURATION & INIT ---

app = FastAPI(title="Solufuse Backend API", version="1.5.0-stable")

# --- CORS (INDISPENSABLE) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- FIREBASE INIT ---
def init_firebase():
    if not firebase_admin._apps:
        # Dokploy Env Var Strategy
        firebase_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
        if firebase_json:
            try:
                print("🔑 Attempting to load credentials from env var...")
                cred_dict = json.loads(firebase_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialized via FIREBASE_CREDENTIALS_JSON")
                return
            except Exception as e:
                print(f"❌ Error loading Firebase JSON from env: {e}")
        
        # Cloud Run / Default Strategy
        try:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized via ApplicationDefault")
        except Exception as e:
            print(f"❌ Failed to init Firebase: {e}")
            raise RuntimeError("Could not initialize Firebase Credentials.")

init_firebase()
db = firestore.client()

# --- MODELS ---

class FileProcessRequest(BaseModel):
    user_id: str = Field(..., description="ID Utilisateur")
    file_url: str = Field(..., description="URL du fichier Storage")
    file_type: str = Field(..., description="Extension du fichier")

class ProcessResponse(BaseModel):
    status: str
    message: str
    doc_id: str | None = None

# --- LOGIQUE METIER ---

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
        error_ref.set({
            "error": str(e), 
            "file_url": file_url,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        raise e

# --- ENDPOINTS ---

# J'ai remis l'URL /process-file (plus simple)
# MAIS j'ai aussi gardé /files/process pour compatibilité si tu as déjà changé ton frontend
@app.post("/process-file", response_model=ProcessResponse)
@app.post("/files/process", response_model=ProcessResponse)
async def process_file_endpoint(request: FileProcessRequest, background_tasks: BackgroundTasks):
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

@app.get("/")
def health_check():
    return {"status": "ok", "service": "Solufuse Backend Stable"}
