
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from typing import List
import shutil
import os
import time
from ..guest_guard import check_guest_restrictions
from firebase_admin import auth
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(tags=["Files"])
security = HTTPBearer()

def get_user_info(creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        decoded = auth.verify_id_token(creds.credentials)
        uid = decoded['uid']
        is_guest = decoded.get("firebase", {}).get("sign_in_provider") == "anonymous"
        return {"uid": uid, "is_guest": is_guest}
    except:
        raise HTTPException(401, "Invalid Authentication Token")

@router.post("/files/upload")
def upload_files(files: List[UploadFile] = File(...), user: dict = Depends(get_user_info)):
    
    # 1. Permission & Quota Check
    target_dir = check_guest_restrictions(user['uid'], user['is_guest'], action="upload")

    # [!] [CRITICAL] : TAGGING GUEST FOLDERS
    # If user is guest, verify/create the marker file
    if user['is_guest']:
        marker_path = os.path.join(target_dir, ".guest")
        if not os.path.exists(marker_path):
            with open(marker_path, "w") as f:
                f.write("This folder belongs to a temporary guest user.")

    saved_files = []
    
    for file in files:
        if user['is_guest']:
            # Block Archives
            ext = os.path.splitext(file.filename)[1].lower()
            if ext in ['.zip', '.rar', '.7z']:
                raise HTTPException(status_code=403, detail=f"🔒 RESTRICTED: Guests cannot upload archives ({ext}).")

            # Check Limit (10)
            current_count = len([f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f))])
            if current_count >= 10:
                 break 

        file_path = os.path.join(target_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file.filename)

    return {
        "status": "success", 
        "saved": saved_files, 
        "guest_warning": "Limit Reached" if user['is_guest'] and len(saved_files) < len(files) else None
    }

@router.get("/files/list")
def list_files(user: dict = Depends(get_user_info)):
    target_dir = os.path.join("/app/storage", user['uid'])
    if not os.path.exists(target_dir):
        return []
    # Don't list the hidden .guest file
    return [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f)) and not f.startswith('.')]
