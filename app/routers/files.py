
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
    try:
        decoded = auth.verify_id_token(creds.credentials)
        uid = decoded['uid']
        is_guest = decoded.get("firebase", {}).get("sign_in_provider") == "anonymous"
        return {"uid": uid, "is_guest": is_guest}
    except:
        raise HTTPException(401, "Invalid Authentication Token")

@router.post("/files/upload")
def upload_files(files: List[UploadFile] = File(...), user: dict = Depends(get_user_info)):
    
    # 1. Check Global Guest Restrictions
    target_dir = check_guest_restrictions(user['uid'], user['is_guest'], action="upload")

    saved_files = []
    
    for file in files:
        if user['is_guest']:
            # Block Archives
            ext = os.path.splitext(file.filename)[1].lower()
            if ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
                raise HTTPException(status_code=403, detail=f"🔒 RESTRICTED: Guests cannot upload archives ({ext}).")

            # Re-check quota count (Limit 10)
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
        "message": "Upload successful",
        "guest_warning": "Limit Reached (10 files)" if user['is_guest'] and len(saved_files) < len(files) else None
    }

@router.get("/files/list")
def list_files(user: dict = Depends(get_user_info)):
    target_dir = os.path.join("/app/storage", user['uid'])
    if not os.path.exists(target_dir):
        return []
    return [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f))]
