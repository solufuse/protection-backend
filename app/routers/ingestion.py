from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import requests
import io

# Imports des services (La logique est ailleurs !)
from app.services.converter import extract_data_from_db
from app.services.storage import save_smartly, log_error

router = APIRouter(prefix="/files", tags=["File Ingestion"])

class FileProcessRequest(BaseModel):
    user_id: str
    file_url: str
    file_type: str

class ProcessResponse(BaseModel):
    status: str
    message: str

def process_background_task(user_id: str, file_url: str, file_type: str):
    """Orchestrator function running in background."""
    try:
        # 1. Download
        response = requests.get(file_url)
        response.raise_for_status()
        
        # 2. Convert
        extracted_content = extract_data_from_db(io.BytesIO(response.content))
        
        # 3. Save
        save_smartly(user_id, extracted_content, file_type)
        
    except Exception as e:
        print(f"Error: {e}")
        log_error(user_id, str(e), file_url)

@router.post("/process", response_model=ProcessResponse)
async def trigger_ingestion(request: FileProcessRequest, background_tasks: BackgroundTasks):
    if not request.file_url.startswith("http"):
         raise HTTPException(status_code=400, detail="Invalid URL")

    background_tasks.add_task(
        process_background_task, 
        request.user_id, 
        request.file_url, 
        request.file_type
    )

    return ProcessResponse(status="accepted", message="Processing started.")
