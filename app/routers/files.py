
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from typing import List
import shutil
import os
from ..guest_guard import check_guest_restrictions
from firebase_admin import auth
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(tags=["Files"])
security = HTTPBearer()

def get_user_info(creds: HTTPAuthorizationCredentials = Depends(security)):
    """
    [decision:auth] : Extracts UID and checks if the provider is 'anonymous'.
    """
    try:
        decoded = auth.verify_id_token(creds.credentials)
        uid = decoded['uid']
        # Check sign_in_provider to detect guests
        is_guest = decoded.get("firebase", {}).get("sign_in_provider") == "anonymous"
        return {"uid": uid, "is_guest": is_guest}
    except:
        raise HTTPException(401, "Invalid Authentication Token")

@router.post("/files/upload")
def upload_files(files: List[UploadFile] = File(...), user: dict = Depends(get_user_info)):
    
    # [!] [CRITICAL] : Enforce Guest Restrictions BEFORE processing files
    target_dir = check_guest_restrictions(user['uid'], user['is_guest'], action="upload")

    saved_files = []
    
    for file in files:
        # [?] [THOUGHT] : Re-check limit for every file in the batch loop
        if user['is_guest']:
             current_count = len([f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f))])
             if current_count >= 5:
                 break # Stop saving if limit reached mid-batch

        file_path = os.path.join(target_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file.filename)

    return {
        "status": "success", 
        "saved": saved_files, 
        "message": "Upload successful",
        "guest_warning": "Demo Limit Reached (5 files)" if user['is_guest'] and len(saved_files) < len(files) else None
    }

@router.get("/files/list")
def list_files(user: dict = Depends(get_user_info)):
    # [+] [INFO] : Read access is allowed for everyone
    target_dir = os.path.join("/app/storage", user['uid'])
    
    if not os.path.exists(target_dir):
        return []
    
    # Return list of files only (no folders)
    return [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f))]
