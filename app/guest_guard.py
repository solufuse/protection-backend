
import os
from fastapi import HTTPException

STORAGE_ROOT = "/data"  # Dossier monté physiquement

def check_guest_restrictions(uid: str, is_guest: bool, action: str = "upload"):
    user_dir = os.path.join(STORAGE_ROOT, uid)
    
    # 1. Create Directory if needed
    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)
        # Mark as guest folder if creating new guest
        if is_guest:
            with open(os.path.join(user_dir, ".guest"), "w") as f:
                f.write("temporary")

    # 2. Check Quota (Only for Guests)
    if is_guest and action == "upload":
        # Count files
        files = [f for f in os.listdir(user_dir) if os.path.isfile(os.path.join(user_dir, f))]
        if len(files) >= 10:
            raise HTTPException(status_code=403, detail="Guest Limit Reached (Max 10 files). Please Login.")
            
    return user_dir
