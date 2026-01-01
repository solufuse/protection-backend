
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Project
from ..auth import get_current_user
import traceback

router = APIRouter()
STORAGE_ROOT = "/app/storage"

# --- DEPENDENCIES ---
def require_super_admin(user: User = Depends(get_current_user)):
    if not user or user.global_role != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin rights required")
    return user

def get_dir_size(path):
    total = 0
    try:
        if not os.path.exists(path): return 0
        for entry in os.scandir(path):
            if entry.is_file(): 
                total += entry.stat().st_size
            elif entry.is_dir(): 
                total += get_dir_size(entry.path)
    except Exception:
        pass
    return total

# --- ROUTES ---

@router.get("/stats")
def get_global_storage_stats(user: User = Depends(require_super_admin)):
    """ [+] [INFO] Dashboard de santé du disque dur. """
    if not os.path.exists(STORAGE_ROOT):
        try: os.makedirs(STORAGE_ROOT, exist_ok=True)
        except: return {"error": "Storage root missing"}
    
    try:
        total, used, free = shutil.disk_usage(STORAGE_ROOT)
        app_usage = get_dir_size(STORAGE_ROOT)
        project_count = len([d for d in os.listdir(STORAGE_ROOT) if os.path.isdir(os.path.join(STORAGE_ROOT, d))])
        
        return {
            "disk_total_gb": total // (2**30),
            "disk_free_gb": free // (2**30),
            "app_usage_mb": round(app_usage / (2**20), 2),
            "projects_count": project_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/audit")
def storage_audit(db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    """ [+] [INFO] Compare DB vs Disk. Returns list of folders with status. """
    if not os.path.exists(STORAGE_ROOT): return []

    try:
        known_project_ids = {str(p.id) for p in db.query(Project).all()}
        # Only active users should keep temp storage usually, but let's list all known UIDs
        known_user_uids = {str(u.firebase_uid) for u in db.query(User).all() if u.firebase_uid}
        
        audit_results = []
        
        for folder_name in os.listdir(STORAGE_ROOT):
            folder_path = os.path.join(STORAGE_ROOT, folder_name)
            if not os.path.isdir(folder_path): continue
            
            status = "active"
            
            # Check matches
            is_known_project = folder_name in known_project_ids
            is_known_user = folder_name in known_user_uids
            
            # Simple heuristic: If it's not a known project ID AND not a known User UID -> Orphan
            if not is_known_project and not is_known_user:
                status = "orphan" 
                
            audit_results.append({
                "folder": folder_name,
                "size_mb": round(get_dir_size(folder_path) / (2**20), 2),
                "status": status,
                "type": "project" if is_known_project else ("user_temp" if is_known_user else "unknown")
            })
            
        return audit_results

    except Exception as e:
        print(f"AUDIT ERROR: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")

@router.delete("/orphans", summary="Bulk Delete Orphans")
def cleanup_orphans(
    confirm: bool = Query(False, description="Must be set to true to execute"),
    db: Session = Depends(get_db), 
    user: User = Depends(require_super_admin)
):
    """
    [!] [CRITICAL] DANGER ZONE.
    Deletes ALL folders marked as 'orphan' in the audit.
    Cannot be undone.
    """
    if not confirm:
        raise HTTPException(400, "You must set confirm=true to execute bulk delete.")
        
    audit_data = storage_audit(db, user)
    deleted_count = 0
    deleted_folders = []
    errors = []
    
    for item in audit_data:
        if item["status"] == "orphan":
            folder_name = item["folder"]
            full_path = os.path.join(STORAGE_ROOT, folder_name)
            
            # Double check safety (don't delete root)
            if full_path == STORAGE_ROOT: continue
            
            try:
                shutil.rmtree(full_path)
                deleted_count += 1
                deleted_folders.append(folder_name)
            except Exception as e:
                errors.append(f"{folder_name}: {str(e)}")
                
    return {
        "status": "success", 
        "deleted_count": deleted_count, 
        "deleted_folders": deleted_folders,
        "errors": errors
    }

@router.delete("/{folder_id}")
def force_delete_folder(folder_id: str, user: User = Depends(require_super_admin)):
    """ [!] [CRITICAL] Manual single folder delete. """
    if ".." in folder_id or folder_id.startswith("/"):
        raise HTTPException(400, "Invalid path")
        
    target_path = os.path.join(STORAGE_ROOT, folder_id)
    if not os.path.exists(target_path):
        raise HTTPException(404, "Folder not found")
        
    try:
        shutil.rmtree(target_path)
        return {"status": "deleted", "path": target_path}
    except Exception as e:
        raise HTTPException(500, f"Deletion failed: {str(e)}")
