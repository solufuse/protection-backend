from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import io
import sys

# Note: Ensure db_converter.py is present in the repo later.
# from db_converter import extract_data_from_db

# --- CONFIGURATION & INIT ---

app = FastAPI(title="Solufuse Backend API", version="1.0.0")

# Initialize Firebase Admin SDK
# Using ApplicationDefault for Cloud Run environment
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

# --- CORE LOGIC ---

def process_and_save(user_id: str, file_url: str, file_type: str):
    try:
        print(f"Starting process for user: {user_id}, type: {file_type}")
        
        # 1. Download file into memory (RAM)
        response = requests.get(file_url)
        response.raise_for_status()
        
        # Wrap binary content in BytesIO
        file_in_memory = io.BytesIO(response.content)
        
        # 2. Extract data (Mocking logic)
        # result_data = extract_data_from_db(file_in_memory)
        print("Extracting data from memory...")
        result_data = {
            "processed": True,
            "source_type": file_type,
            "data_summary": "Extracted content placeholder"
        }
        
        # 3. Save to Firestore
        doc_ref = db.collection("users").document(user_id).collection("configurations").document()
        doc_ref.set(result_data)
        
        print(f"Data saved to Firestore: {doc_ref.id}")
        return doc_ref.id

    except Exception as e:
        print(f"Error processing file: {str(e)}")
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
