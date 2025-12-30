
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from typing import List
import shutil
import os
from ..guest_guard import check_guest_restrictions
# On suppose que tu as une fonction get_current_user_decoded dans un auth.py ou similar
# Pour ce script, je simule l'extraction basique ou j'importe ton auth existant
from firebase_admin import auth
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(tags=["Files"])
security = HTTPBearer()

def get_user_info(creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        decoded = auth.verify_id_token(creds.credentials)
        uid = decoded['uid']
        # Détection Guest via Firebase
        is_guest = decoded.get("firebase", {}).get("sign_in_provider") == "anonymous"
        return {"uid": uid, "is_guest": is_guest}
    except:
        raise HTTPException(401, "Invalid Token")

@router.post("/files/upload")
def upload_files(files: List[UploadFile] = File(...), user: dict = Depends(get_user_info)):
    
    # [!] SÉCURITÉ GUEST ICI
    # On vérifie si l'utilisateur a le droit d'uploader
    target_dir = check_guest_restrictions(user['uid'], user['is_guest'], action="upload")

    saved_files = []
    for file in files:
        # Re-vérification à chaque fichier (au cas où il en envoie 10 d'un coup)
        if user['is_guest']:
             current_count = len([f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f))])
             if current_count >= 5:
                 break # On arrête d'enregistrer si quota atteint

        file_path = os.path.join(target_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file.filename)

    return {
        "status": "success", 
        "saved": saved_files, 
        "quota_warning": "Demo Limit Reached" if user['is_guest'] and len(saved_files) < len(files) else None
    }

@router.get("/files/list")
def list_files(user: dict = Depends(get_user_info)):
    # Lecture autorisée pour tout le monde
    target_dir = os.path.join("/app/storage", user['uid'])
    if not os.path.exists(target_dir):
        return []
    
    # On retourne la liste
    return [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f))]
