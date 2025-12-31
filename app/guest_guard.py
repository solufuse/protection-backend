
import os
from fastapi import HTTPException

BASE_STORAGE = "/app/storage"

def get_user_storage(uid: str) -> str:
    path = os.path.join(BASE_STORAGE, uid)
    if not os.path.exists(path): os.makedirs(path, exist_ok=True)
    return path

def check_guest_restrictions(uid: str, is_guest: bool, action: str) -> str:
    user_path = get_user_storage(uid)
    if not is_guest: return user_path

    if action == "create_project":
        raise HTTPException(403, "Guests cannot create projects.")

    if action == "upload":
        files = [f for f in os.listdir(user_path) if os.path.isfile(os.path.join(user_path, f))]
        if len(files) >= 10:
            raise HTTPException(403, "Guest Quota Reached (Max 10 files).")
            
    return user_path
