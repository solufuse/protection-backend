
from fastapi import APIRouter, UploadFile, File, HTTPException
import shutil
import os
from typing import List

router = APIRouter()

UPLOAD_DIR = "/data/temp" # Temp storage for guests

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    saved_files = []
    
    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file.filename)
        
    return {"status": "uploaded", "files": saved_files}

@router.get("/list")
def list_files():
    if not os.path.exists(UPLOAD_DIR):
        return []
    return os.listdir(UPLOAD_DIR)
