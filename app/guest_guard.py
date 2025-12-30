
import os
from fastapi import HTTPException

BASE_STORAGE = "/app/storage"

def get_user_storage(uid: str) -> str:
    path = os.path.join(BASE_STORAGE, uid)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

def check_guest_restrictions(uid: str, is_guest: bool, action: str) -> str:
    user_path = get_user_storage(uid)

    if not is_guest:
        return user_path

    # Rule 1: Guests cannot create projects
    if action == "create_project":
        raise HTTPException(
            status_code=403, 
            detail="🔒 CREATION DENIED: Guests cannot create projects. Please sign in with Google."
        )

    # Rule 2: Strict 10-file quota (Updated)
    if action == "upload":
        files = [f for f in os.listdir(user_path) if os.path.isfile(os.path.join(user_path, f))]
        
        # [decision:quota] : Limit increased to 10 files
        if len(files) >= 10:
            raise HTTPException(
                status_code=403, 
                detail="🔒 QUOTA REACHED: Guest mode is limited to 10 files. Please sign in for unlimited storage."
            )
            
    return user_path
