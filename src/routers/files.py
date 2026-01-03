
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

# [structure:root] : Files Router
# [context:flow] : Handles file operations (List, Upload, Download, Delete, Bulk Zip).

router = APIRouter()
STORAGE_ROOT = "/app/storage"

# --- HELPER: Target Path Logic ---
def get_target_path(user: User, project_id: Optional[str], db: Session, action: str = "read"):
    if project_id:
        if user.global_role in ["super_admin", "admin", "moderator"]:
            pass 
        else:
            checker = ProjectAccessChecker(required_role="viewer" if action == "read" else "editor")
            checker(project_id, user, db)
            
        project_dir = os.path.join(STORAGE_ROOT, project_id)
        if not os.path.exists(project_dir): os.makedirs(project_dir, exist_ok=True)
        return project_dir
    else:
        # Session (User Personal Folder)
        session_dir = os.path.join(STORAGE_ROOT, user.firebase_uid)
        if not os.path.exists(session_dir): os.makedirs(session_dir, exist_ok=True)
        return session_dir

def count_files_in_dir(directory: str) -> int:
    if not os.path.exists(directory): return 0
    return len([name for name in os.listdir(directory) if os.path.isfile(os.path.join(directory, name))])

# --- ENDPOINTS ---

# [decision:logic] : Single Source of Truth for Listing.
@router.get("/details")
def list_files(project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    target_dir = get_target_path(user, project_id, db, action="read")
    
    files_data = []
    if os.path.exists(target_dir):
        for f in os.listdir(target_dir):
            fp = os.path.join(target_dir, f)
            if os.path.isfile(fp):
                stat = os.stat(fp)
                files_data.append({
                    "filename": f,
                    "path": f, 
                    "size": stat.st_size,
                    "uploaded_at": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "content_type": "application/octet-stream"
                })
    return {"files": files_data}

@router.post("/upload")
def upload_files(
    files: List[UploadFile] = File(...), 
    project_id: Optional[str] = Query(None), 
    user = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    
    # Check Quota
    if user.is_anonymous:
        current_count = count_files_in_dir(target_dir)
        if current_count + len(files) > QUOTAS["anonymous"]["max_files"]:
             raise HTTPException(403, "Guest limit reached (Max 10 files). Please login.")

    saved_files = []
    for file in files:
        # [!] [CRITICAL] : Path Traversal Sanitization
        safe_filename = os.path.basename(file.filename)
        file_path = os.path.join(target_dir, safe_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(safe_filename)
        
    return {"uploaded": saved_files}

# [!] [CRITICAL] : Single File Download (Legacy/Link Support)
@router.get("/download")
def download_file(filename: str, project_id: Optional[str] = Query(None), token: str = Query(...)):
    # Fallback to direct download. Ideally, secure this further.
    path_to_check = ""
    if project_id:
        path_to_check = os.path.join(STORAGE_ROOT, project_id, filename)
    
    # Simple check for existence before returning
    if path_to_check and os.path.exists(path_to_check):
        return FileResponse(path_to_check, filename=filename)
        
    # If no project ID, check user sessions? Without decoding token manually here, 
    # we can't easily guess the folder. 
    # For now, if project_id is missing, this legacy link might fail for personal files 
    # unless we implemented manual JWT decoding here.
    # RECOMMENDATION: Use the /file/{filename} endpoint with Auth Header instead.
    
    raise HTTPException(404, "File not found (or legacy link expired)")

# [!] [CRITICAL] : Secure Single File Access (For Fetch/Blob operations)
@router.get("/file/{filename}")
def get_file_secure(filename: str, project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    target_dir = get_target_path(user, project_id, db, action="read")
    file_path = os.path.join(target_dir, filename)
    if not os.path.exists(file_path): raise HTTPException(404, "File not found")
    return FileResponse(file_path, filename=filename)

@router.delete("/file/{filename}")
def delete_file(filename: str, project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    if ".." in filename or "/" in filename: raise HTTPException(400, "Invalid filename")
    
    # DB File Protection
    if user.global_role != "super_admin":
        if filename.endswith(".db") or filename.endswith(".sqlite") or filename == "protection.db":
            raise HTTPException(403, "Protected system file. Only Super Admin can delete.")

    target_dir = get_target_path(user, project_id, db, action="write")
    file_path = os.path.join(target_dir, filename)
    if not os.path.exists(file_path): raise HTTPException(404, "File not found")
    os.remove(file_path)
    return {"status": "deleted", "filename": filename}

@router.delete("/clear")
def clear_files(project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    target_dir = get_target_path(user, project_id, db, action="write")
    
    if user.global_role != "super_admin":
        for f in os.listdir(target_dir):
            if f.endswith(".db") or f == "protection.db":
                 raise HTTPException(403, "Cannot clear folder containing protected DB files.")

    count = 0
    for f in os.listdir(target_dir):
        fp = os.path.join(target_dir, f)
        if os.path.isfile(fp):
            os.remove(fp)
            count += 1
    return {"status": "cleared", "count": count}

# [structure:root] : Bulk Download Endpoint
# [context:flow] : Receives list of filenames -> Zips them -> Returns single ZIP stream.
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
            if ".." in fname or "/" in fname: continue
            
            fpath = os.path.join(target_dir, fname)
            if os.path.exists(fpath):
                zip_file.write(fpath, arcname=fname)
    
    zip_buffer.seek(0)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"solufuse_bulk_{timestamp}.zip"
    
    return StreamingResponse(
        iter([zip_buffer.getvalue()]), 
        media_type="application/zip", 
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
    )
