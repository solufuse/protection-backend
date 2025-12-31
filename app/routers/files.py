
import os
import shutil
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from typing import List
from ..auth import get_current_user, QUOTAS
from ..models import User

router = APIRouter()
STORAGE_ROOT = "/app/storage"

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    folder_id: str = Form(...), # Can be Project ID or Session ID
    user: User = Depends(get_current_user)
):
    """
    [+] [INFO] Upload handler with strict File Count Quota.
    [decision:logic] Counts existing files in folder before accepting new ones.
    """
    
    # 1. Security Check (Path Traversal)
    if ".." in folder_id or folder_id.startswith("/"):
        raise HTTPException(400, "Invalid folder ID")
        
    target_path = os.path.join(STORAGE_ROOT, folder_id)
    if not os.path.exists(target_path):
        os.makedirs(target_path, exist_ok=True)
        
    # 2. Check Quotas
    user_quota = QUOTAS.get(user.global_role, QUOTAS["guest"])
    max_files = user_quota["max_files"]
    
    # [!] [CRITICAL] File Count Check
    if max_files != -1:
        # Count existing files (exclude hidden or subdirs if needed, here simple count)
        try:
            current_files = [f for f in os.listdir(target_path) if os.path.isfile(os.path.join(target_path, f))]
            current_count = len(current_files)
        except:
            current_count = 0
            
        if current_count + len(files) > max_files:
            msg = f"Quota exceeded. Limit: {max_files} files."
            if user.global_role == "guest": msg += " Create an account for more."
            elif user.global_role == "user": msg += " Upgrade to Nitro for 1000 files."
            raise HTTPException(403, msg)

    # 3. Process Upload
    saved_files = []
    for file in files:
        file_path = os.path.join(target_path, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file.filename)
        
    return {
        "status": "uploaded", 
        "count": len(saved_files), 
        "folder_id": folder_id,
        "quota_used": f"{current_count + len(saved_files)}/{max_files if max_files != -1 else 'Inf'}"
    }

@router.get("/list/{folder_id}")
def list_files(folder_id: str, user: User = Depends(get_current_user)):
    # Simple list logic
    if ".." in folder_id: raise HTTPException(400, "Invalid ID")
    path = os.path.join(STORAGE_ROOT, folder_id)
    if not os.path.exists(path): return []
    try:
        return os.listdir(path)
    except: return []
