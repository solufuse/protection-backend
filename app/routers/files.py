
import os
import shutil
import zipfile
import io
import datetime
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker, QUOTAS
from ..models import User

router = APIRouter()
STORAGE_ROOT = "/app/storage"

# --- HELPER: Target Path Logic ---
def get_target_path(user: User, project_id: Optional[str], db: Session, action: str = "read"):
    """
    Determines the root storage directory based on Project ID or User Session.
    Verifies permissions via ProjectAccessChecker if a project is targeted.
    """
    if project_id:
        # Admin Override
        if user.global_role in ["super_admin", "admin", "moderator"]:
            pass 
        else:
            # Standard Permission Check
            checker = ProjectAccessChecker(required_role="viewer" if action == "read" else "editor")
            checker(project_id, user, db)
            
        project_dir = os.path.join(STORAGE_ROOT, project_id)
        if not os.path.exists(project_dir): os.makedirs(project_dir, exist_ok=True)
        return project_dir
    else:
        # User Private Session
        session_dir = os.path.join(STORAGE_ROOT, user.firebase_uid)
        if not os.path.exists(session_dir): os.makedirs(session_dir, exist_ok=True)
        return session_dir

def count_files_recursive(directory: str) -> int:
    """ [GENERIC] Counts all files in directory and subdirectories. """
    total_files = 0
    if not os.path.exists(directory): return 0
    try:
        for root, dirs, files in os.walk(directory):
            # Skip hidden folders
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if not f.startswith('.'):
                    total_files += 1
    except: pass
    return total_files

# --- ENDPOINTS ---

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), project_id: Optional[str] = Query(None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target_dir = get_target_path(user, project_id, db, action="write")
    
    # Quota Check (Recursive)
    user_quota = QUOTAS.get(user.global_role, QUOTAS["guest"])
    max_files = user_quota["max_files"]
    
    if max_files != -1:
        current_count = count_files_recursive(target_dir)
        if current_count + len(files) > max_files:
            msg = f"Quota exceeded. Limit: {max_files} files."
            if user.global_role == "guest": msg += " Create an account for more."
            elif user.global_role == "user": msg += " Upgrade to Nitro."
            raise HTTPException(status_code=403, detail=msg)

    saved_files = []
    count = 0
    
    for file in files:
        try:
            content = await file.read()
            # [Feature] Auto-unzip functionality
            if file.filename.endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        for name in z.namelist():
                            if not name.endswith("/") and "__MACOSX" not in name and ".." not in name:
                                # Safe path join
                                file_path = os.path.join(target_dir, os.path.basename(name))
                                with open(file_path, "wb") as f: f.write(z.read(name))
                                saved_files.append(name); count += 1
                except:
                    # Fallback if zip is corrupted: save as is
                    file_path = os.path.join(target_dir, file.filename)
                    with open(file_path, "wb") as f: f.write(content)
                    saved_files.append(file.filename); count += 1
            else:
                file_path = os.path.join(target_dir, file.filename)
                with open(file_path, "wb") as f: f.write(content)
                saved_files.append(file.filename); count += 1
        except: continue
        
    return {"status": "success", "saved": saved_files, "count": count}

@router.get("/details")
def list_files(project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    [GENERIC] Recursively lists all files in the target directory (Project or Session).
    Returns paths relative to the project root (e.g., 'loadflow_results/run1.json').
    """
    target_dir = get_target_path(user, project_id, db, action="read")
    if not os.path.exists(target_dir): return {"files": []}
    
    files_info = []
    
    # Generic Recursive Walk
    for root, dirs, files in os.walk(target_dir):
        # Filter hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for f in files:
            if f.startswith('.'): continue
            
            full_path = os.path.join(root, f)
            # Calculate relative path for frontend (e.g. "subfolder/file.txt")
            rel_path = os.path.relpath(full_path, target_dir)
            
            # Normalize slashes for Windows compatibility if dev env differs
            rel_path = rel_path.replace("\\", "/") 
            
            try:
                stat = os.stat(full_path)
                dt_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                
                # Determine basic content type
                c_type = "application/octet-stream"
                if f.endswith(".json"): c_type = "application/json"
                elif f.endswith(".pdf"): c_type = "application/pdf"
                
                files_info.append({
                    "filename": rel_path,  # This now supports 'folder/file.ext'
                    "path": rel_path,
                    "size": stat.st_size, 
                    "uploaded_at": dt_str, 
                    "content_type": c_type
                })
            except Exception as e:
                # Skip unreadable files
                continue

    # Sort by newest first
    files_info.sort(key=lambda x: x['uploaded_at'], reverse=True)
    return {"files": files_info}

@router.post("/bulk-download")
def bulk_download(
    filenames: List[str], 
    project_id: Optional[str] = Query(None), 
    user = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="read")
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for fname in filenames:
            # Security: Prevent escaping root
            if ".." in fname: continue 
            
            fpath = os.path.join(target_dir, fname)
            
            # Additional Security Check using abspath
            if not os.path.abspath(fpath).startswith(os.path.abspath(target_dir)):
                continue
            
            if os.path.exists(fpath) and os.path.isfile(fpath):
                # Archive name matches the relative structure
                zip_file.write(fpath, arcname=fname)
                
    zip_buffer.seek(0)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([zip_buffer.getvalue()]), 
        media_type="application/zip", 
        headers={"Content-Disposition": f"attachment; filename=solufuse_bulk_{timestamp}.zip"}
    )

@router.post("/bulk-delete")
def bulk_delete(
    filenames: List[str],
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    deleted = []
    errors = []
    
    is_super_admin = (user.global_role == "super_admin")

    for fname in filenames:
        if ".." in fname: 
            errors.append(f"{fname}: Invalid path")
            continue
            
        if not is_super_admin:
             if fname.endswith(".db") or fname.endswith(".sqlite") or fname == "protection.db":
                 errors.append(f"{fname}: Protected system file")
                 continue

        fpath = os.path.join(target_dir, fname)
        
        # Security: Scope Check
        if not os.path.abspath(fpath).startswith(os.path.abspath(target_dir)): 
             errors.append(f"{fname}: Path violation")
             continue

        if os.path.exists(fpath):
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    deleted.append(fname)
                else:
                    errors.append(f"{fname}: Not a file")
            except Exception as e:
                errors.append(f"{fname}: Error deleting")
        else:
            errors.append(f"{fname}: Not found")
            
    return {"status": "completed", "deleted": deleted, "errors": errors}

@router.get("/download")
def download_file(filename: str = Query(...), project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    # Support subdirectories by checking path validity
    if ".." in filename: raise HTTPException(400, "Invalid filename")
    
    target_dir = get_target_path(user, project_id, db, action="read")
    file_path = os.path.join(target_dir, filename)
    
    # Security: Ensure we don't serve files outside project dir
    if not os.path.abspath(file_path).startswith(os.path.abspath(target_dir)): 
        raise HTTPException(403, "Access denied")
        
    if not os.path.exists(file_path) or not os.path.isfile(file_path): 
        raise HTTPException(404, "File not found")
        
    return FileResponse(path=file_path, filename=os.path.basename(filename), media_type='application/octet-stream')

@router.delete("/file/{filename:path}")
def delete_file(filename: str, project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    # The ':path' type in FastAPI allows slashes in the filename argument
    if ".." in filename: raise HTTPException(400, "Invalid filename")
    
    if user.global_role != "super_admin":
        if filename.endswith(".db") or filename.endswith(".sqlite") or filename == "protection.db":
            raise HTTPException(403, "Protected system file.")
            
    target_dir = get_target_path(user, project_id, db, action="write")
    file_path = os.path.join(target_dir, filename)
    
    # Security Check
    if not os.path.abspath(file_path).startswith(os.path.abspath(target_dir)): 
        raise HTTPException(403, "Access denied")
        
    if not os.path.exists(file_path): raise HTTPException(404, "File not found")
    
    try:
        os.remove(file_path)
    except OSError:
        raise HTTPException(500, "Could not delete file")
        
    return {"status": "deleted", "filename": filename}

@router.delete("/clear")
def clear_files(project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Clears all files. Does NOT remove subdirectories to preserve structure (like loadflow_results),
    unless specifically requested (safest approach is to keep folders).
    """
    target_dir = get_target_path(user, project_id, db, action="write")
    
    if user.global_role != "super_admin":
        # Check protection on root files
        for f in os.listdir(target_dir):
            if f.endswith(".db") or f == "protection.db":
                 raise HTTPException(403, "Folder contains protected database. Cannot clear.")
                 
    count = 0
    # Clean only files in root to avoid destroying organized subfolders by accident
    # If users want to delete result files, they can use bulk delete or specific logic.
    for f in os.listdir(target_dir):
        fp = os.path.join(target_dir, f)
        if os.path.isfile(fp): 
            try:
                os.remove(fp)
                count += 1
            except: pass
            
    return {"status": "cleared", "deleted_count": count}
