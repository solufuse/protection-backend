
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
        session_dir = os.path.join(STORAGE_ROOT, user.firebase_uid)
        if not os.path.exists(session_dir): os.makedirs(session_dir, exist_ok=True)
        return session_dir

def count_files_in_dir(directory: str) -> int:
    try:
        return len([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and not f.startswith('.')])
    except: return 0

# --- ENDPOINTS ---

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), project_id: Optional[str] = Query(None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target_dir = get_target_path(user, project_id, db, action="write")
    
    user_quota = QUOTAS.get(user.global_role, QUOTAS["guest"])
    max_files = user_quota["max_files"]
    
    if max_files != -1:
        current_count = count_files_in_dir(target_dir)
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
            if file.filename.endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        for name in z.namelist():
                            if not name.endswith("/") and "__MACOSX" not in name and ".." not in name:
                                file_path = os.path.join(target_dir, os.path.basename(name))
                                with open(file_path, "wb") as f: f.write(z.read(name))
                                saved_files.append(name); count += 1
                except:
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
    target_dir = get_target_path(user, project_id, db, action="read")
    if not os.path.exists(target_dir): return {"files": []}
    files_info = []
    
    # 1. Scan Root
    for f in os.listdir(target_dir):
        full_path = os.path.join(target_dir, f)
        if os.path.isfile(full_path) and not f.startswith('.'):
            try:
                stat = os.stat(full_path)
                dt_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                files_info.append({
                    "filename": f, 
                    "path": f,
                    "size": stat.st_size, 
                    "uploaded_at": dt_str, 
                    "content_type": "application/octet-stream"
                })
            except: pass

    # 2. Scan 'loadflow_results' subdirectory [FIX FOR HISTORY]
    lf_dir = os.path.join(target_dir, "loadflow_results")
    if os.path.exists(lf_dir) and os.path.isdir(lf_dir):
        for f in os.listdir(lf_dir):
            full_path = os.path.join(lf_dir, f)
            if os.path.isfile(full_path) and not f.startswith('.'):
                try:
                    stat = os.stat(full_path)
                    dt_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    files_info.append({
                        "filename": f"loadflow_results/{f}", # Relative path for frontend
                        "path": f"loadflow_results/{f}",
                        "size": stat.st_size, 
                        "uploaded_at": dt_str, 
                        "content_type": "application/json"
                    })
                except: pass

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
            if ".." in fname: continue # Basic security
            # Handle possible subfolders like loadflow_results/foo.json
            fpath = os.path.join(target_dir, fname)
            # Ensure path is within target_dir
            if not os.path.abspath(fpath).startswith(os.path.abspath(target_dir)): continue
            
            if os.path.exists(fpath):
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
        # Security check: prevent escaping root
        if not os.path.abspath(fpath).startswith(os.path.abspath(target_dir)): 
             errors.append(f"{fname}: Path violation")
             continue

        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                deleted.append(fname)
            except Exception as e:
                errors.append(f"{fname}: Error")
        else:
            errors.append(f"{fname}: Not found")
            
    return {"status": "completed", "deleted": deleted, "errors": errors}

@router.get("/download")
def download_file(filename: str = Query(...), project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    if ".." in filename: raise HTTPException(400, "Invalid filename")
    target_dir = get_target_path(user, project_id, db, action="read")
    file_path = os.path.join(target_dir, filename)
    if not os.path.abspath(file_path).startswith(os.path.abspath(target_dir)): raise HTTPException(403, "Access denied")
    if not os.path.exists(file_path): raise HTTPException(404, "File not found")
    return FileResponse(path=file_path, filename=os.path.basename(filename), media_type='application/octet-stream')

@router.delete("/file/{filename:path}") # Use :path to allow slashes (e.g. loadflow_results/foo.json)
def delete_file(filename: str, project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    if ".." in filename: raise HTTPException(400, "Invalid filename")
    if user.global_role != "super_admin":
        if filename.endswith(".db") or filename.endswith(".sqlite") or filename == "protection.db":
            raise HTTPException(403, "Protected system file. Only Super Admin can delete.")
    target_dir = get_target_path(user, project_id, db, action="write")
    file_path = os.path.join(target_dir, filename)
    if not os.path.abspath(file_path).startswith(os.path.abspath(target_dir)): raise HTTPException(403, "Access denied")
    if not os.path.exists(file_path): raise HTTPException(404, "File not found")
    os.remove(file_path)
    return {"status": "deleted", "filename": filename}

@router.delete("/clear")
def clear_files(project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    target_dir = get_target_path(user, project_id, db, action="write")
    if user.global_role != "super_admin":
        for f in os.listdir(target_dir):
            if f.endswith(".db") or f == "protection.db":
                 raise HTTPException(403, "Folder contains protected database. Cannot clear.")
    # Standard cleanup
    for f in os.listdir(target_dir):
        fp = os.path.join(target_dir, f)
        if os.path.isfile(fp): os.remove(fp)
    
    # Also clear loadflow results if allowed? Let's keep it safe and just clear root files for now or folders
    # If the user wants to clear everything, we should probably clear subdirs too.
    # For now, let's keep it simple as provided in original but with safety.
    return {"status": "cleared"}
