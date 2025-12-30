
import os
from fastapi import HTTPException

BASE_STORAGE = "/app/storage"

def get_user_storage(uid: str) -> str:
    """
    [decision:logic] : Unified storage path. Everyone gets a folder based on UID.
    No separation between 'guest' and 'auth' folders to simplify transitions.
    """
    path = os.path.join(BASE_STORAGE, uid)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

def check_guest_restrictions(uid: str, is_guest: bool, action: str) -> str:
    """
    [!] [CRITICAL] : Enforces strict limits for Guest users.
    Returns the user path if allowed, raises HTTPException if denied.
    """
    user_path = get_user_storage(uid)

    # [+] [INFO] : Full members (not guests) have no restrictions.
    if not is_guest:
        return user_path

    # --- GUEST RULES ---
    
    # Rule 1: Guests cannot create projects (folders)
    if action == "create_project":
        raise HTTPException(
            status_code=403, 
            detail="🔒 CREATION DENIED: Guests cannot create projects. Please sign in with Google."
        )

    # Rule 2: Strict 5-file quota
    if action == "upload":
        # Count existing files in the root of user directory
        files = [f for f in os.listdir(user_path) if os.path.isfile(os.path.join(user_path, f))]
        
        # [decision:quota] : Limit set to 5 files for demo purposes
        if len(files) >= 5:
            raise HTTPException(
                status_code=403, 
                detail="🔒 QUOTA REACHED: Guest mode is limited to 5 files. Please sign in for unlimited storage."
            )
            
    return user_path
