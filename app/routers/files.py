
import os
import shutil
import zipfile
import io
import datetime
import uuid
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import get_current_user, QUOTAS
from ..models import User
from ..core.storage import get_target_path

router = APIRouter()

# --- HELPER ---
def count_files_recursive(directory: str) -> int:
    total_files = 0
    if not os.path.exists(directory): return 0
    try:
        for root, dirs, files in os.walk(directory):
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
    
    user_quota = QUOTAS.get(user.global_role, QUOTAS["guest"])
    max_files = user_quota["max_files"]
    
    if max_files != -1 and count_files_recursive(target_dir) + len(files) > max_files:
        msg = f"Quota exceeded. Limit: {max_files} files."
        if user.global_role == "guest": msg += " Create an account for more."
        elif user.global_role == "user": msg += " Upgrade to Nitro."
        raise HTTPException(status_code=403, detail=msg)

    saved_files, count = [], 0
    submission_id = str(uuid.uuid4())[:8]
    
    for file in files:
        try:
            content = await file.read()
            
            if file.filename.endswith(".zip"):
                unzip_dir_name = os.path.splitext(file.filename)[0]
                unzip_dir = os.path.join(target_dir, f"{unzip_dir_name}_{submission_id}")
                
                if os.path.exists(unzip_dir):
                    file_path = os.path.join(target_dir, file.filename)
                    with open(file_path, "wb") as f: f.write(content)
                    saved_files.append(file.filename); count += 1
                else:
                    os.makedirs(unzip_dir, exist_ok=True)
                    try:
                        with zipfile.ZipFile(io.BytesIO(content)) as z:
                            z.extractall(unzip_dir)
                            saved_files.append(f"{unzip_dir_name}_{submission_id}/")
                            count += len(z.namelist())
                    except zipfile.BadZipFile:
                        shutil.rmtree(unzip_dir)
                        file_path = os.path.join(target_dir, file.filename)
                        with open(file_path, "wb") as f: f.write(content)
                        saved_files.append(file.filename); count += 1
            else:
                file_path = os.path.join(target_dir, file.filename)
                if os.path.exists(file_path):
                    base, ext = os.path.splitext(file.filename)
                    file_path = os.path.join(target_dir, f"{base}_{submission_id}{ext}")
                
                with open(file_path, "wb") as f: f.write(content)
                saved_files.append(os.path.basename(file_path)); count += 1
        except Exception:
            continue
            
    return {"status": "success", "saved": saved_files, "count": count}

@router.get("/details")
def list_files(project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    target_dir = get_target_path(user, project_id, db, action="read")
    if not os.path.exists(target_dir): return {"files": []}
    
    files_info = []
    
    for root, dirs, files in os.walk(target_dir):
        # Exclude dot folders
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        # Process directories
        for d in dirs:
            full_path = os.path.join(root, d)
            rel_path = os.path.relpath(full_path, target_dir).replace("\\", "/")
            try:
                stat = os.stat(full_path)
                dt_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                files_info.append({
                    "filename": d,
                    "path": rel_path,
                    "size": 0,
                    "uploaded_at": dt_str,
                    "content_type": "folder",
                    "type": "folder"
                })
            except Exception:
                continue

        # Process files
        for f in files:
            if f.startswith('.'): continue
            
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, target_dir).replace("\\", "/") 
            
            try:
                stat = os.stat(full_path)
                dt_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                c_type = "application/octet-stream"
                if f.endswith(".json"): c_type = "application/json"
                elif f.endswith(".pdf"): c_type = "application/pdf"
                
                files_info.append({
                    "filename": os.path.basename(f),
                    "path": rel_path,
                    "size": stat.st_size, 
                    "uploaded_at": dt_str, 
                    "content_type": c_type,
                    "type": "file"
                })
            except Exception:
                continue

    files_info.sort(key=lambda x: x['path'])
    return {"files": files_info}

@router.post("/download")
def download(
    filenames: List[str], 
    project_id: Optional[str] = Query(None), 
    user = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="read")
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for fname in filenames:
            if ".." in fname: continue 
            fpath = os.path.join(target_dir, fname)
            if not os.path.abspath(fpath).startswith(os.path.abspath(target_dir)): continue
            
            if os.path.exists(fpath):
                if os.path.isfile(fpath):
                    zip_file.write(fpath, arcname=fname)
                else: # It's a directory
                     for root, _, files in os.walk(fpath):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arc_path = os.path.relpath(file_path, fpath)
                            zip_file.write(file_path, arcname=os.path.join(fname, arc_path))

    zip_buffer.seek(0)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([zip_buffer.getvalue()]), 
        media_type="application/zip", 
        headers={"Content-Disposition": f"attachment; filename=solufuse_download_{timestamp}.zip"}
    )

@router.post("/delete")
def delete(
    filenames: List[str],
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    deleted, errors = [], []
    is_super_admin = (user.global_role == "super_admin")

    for fname in filenames:
        if ".." in fname: 
            errors.append({"file": fname, "error": "Invalid path"})
            continue
            
        if not is_super_admin:
             if fname.endswith((".db", ".sqlite")) or "protection.db" in fname:
                 errors.append({"file": fname, "error": "Protected system file"})
                 continue

        fpath = os.path.join(target_dir, fname)
        
        if not os.path.abspath(fpath).startswith(os.path.abspath(target_dir)): 
             errors.append({"file": fname, "error": "Path violation"})
             continue

        if os.path.exists(fpath):
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    deleted.append(fname)
                else: # It's a directory
                    shutil.rmtree(fpath)
                    deleted.append(f"{fname}/")
            except Exception as e:
                errors.append({"file": fname, "error": f"Error deleting: {e}"})
        else:
            errors.append({"file": fname, "error": "Not found"})
            
    return {"status": "completed", "deleted": deleted, "errors": errors}

@router.post("/rename")
def rename_item(
    old_path: str = Body(...),
    new_path: str = Body(...),
    project_id: Optional[str] = Query(None), 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    
    if ".." in old_path or ".." in new_path:
        raise HTTPException(status_code=400, detail="Invalid path components.")

    old_fpath = os.path.join(target_dir, old_path)
    new_fpath = os.path.join(target_dir, new_path)

    if not os.path.abspath(old_fpath).startswith(os.path.abspath(target_dir)) or \
       not os.path.abspath(new_fpath).startswith(os.path.abspath(target_dir)):
        raise HTTPException(status_code=403, detail="Path violation.")

    if not os.path.exists(old_fpath):
        raise HTTPException(status_code=404, detail=f"Source path '{old_path}' not found.")

    if os.path.exists(new_fpath):
        raise HTTPException(status_code=409, detail=f"Destination path '{new_path}' already exists.")

    try:
        os.rename(old_fpath, new_fpath)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Error renaming: {e}")

    return {"status": "success", "old_path": old_path, "new_path": new_path}

@router.post("/create-folder")
def create_folder(
    folder_path: str = Body(...),
    project_id: Optional[str] = Query(None), 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    
    if ".." in folder_path:
        raise HTTPException(status_code=400, detail="Invalid path.")

    new_dir_path = os.path.join(target_dir, folder_path)

    if not os.path.abspath(new_dir_path).startswith(os.path.abspath(target_dir)):
        raise HTTPException(status_code=403, detail="Path violation.")

    if os.path.exists(new_dir_path):
        raise HTTPException(status_code=409, detail=f"Path '{folder_path}' already exists.")

    try:
        os.makedirs(new_dir_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Error creating folder: {e}")

    return {"status": "success", "path": folder_path}
