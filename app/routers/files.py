
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

# [!] HELPER: Transforme un dossier Guest en dossier Permanent
def vaccine_folder(target_dir: str, is_guest: bool):
    """
    Si l'utilisateur n'est PAS un guest, on regarde s'il y a un marqueur .guest
    et on le supprime. Cela rend le dossier permanent et immunisé contre le nettoyage.
    """
    if not is_guest and os.path.exists(target_dir):
        marker = os.path.join(target_dir, ".guest")
        if os.path.exists(marker):
            try:
                os.remove(marker)
                print(f"[INFO] Account upgraded: Removed guest marker for {target_dir}")
            except Exception as e:
                print(f"[ERROR] Failed to remove marker: {e}")

@router.post("/files/upload")
def upload_files(files: List[UploadFile] = File(...), user: dict = Depends(get_user_info)):
    
    # 1. Permission & Quota Check
    target_dir = check_guest_restrictions(user['uid'], user['is_guest'], action="upload")

    # 2. [FIX] VACCINE: Si l'utilisateur est connecté Google, on sauve le dossier
    vaccine_folder(target_dir, user['is_guest'])

    # 3. TAGGING (Seulement si c'est encore un guest)
    if user['is_guest']:
        marker_path = os.path.join(target_dir, ".guest")
        if not os.path.exists(marker_path):
            with open(marker_path, "w") as f:
                f.write("Guest folder.")

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
    
    # [FIX] VACCINE: Même juste en listant les fichiers, si on est connecté, on sauve le dossier
    vaccine_folder(target_dir, user['is_guest'])

    if not os.path.exists(target_dir):
        return []
    # On cache le fichier .guest
    return [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f)) and not f.startswith('.')]
