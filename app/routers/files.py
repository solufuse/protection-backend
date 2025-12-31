
import os
import shutil
import zipfile
import io
import datetime
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker
from ..guest_guard import check_guest_restrictions

router = APIRouter()

# --- HELPER: Target Path Logic ---
def get_target_path(user, project_id: Optional[str], db: Session, action: str = "read"):
    # CAS 1 : PROJET
    if project_id:
        checker = ProjectAccessChecker(required_role="viewer" if action == "read" else "editor")
        checker(project_id, user, db)
        project_dir = os.path.join("/app/storage", project_id)
        if not os.path.exists(project_dir):
            os.makedirs(project_dir, exist_ok=True)
        return project_dir

    # CAS 2 : SESSION / GUEST
    else:
        uid = user.firebase_uid
        is_guest = False 
        try:
            if user.email is None or user.email == "": is_guest = True
        except: pass
        
        return check_guest_restrictions(uid, is_guest, action="upload" if action == "write" else "read")

# --- 1. UPLOAD (Smart Unzip) ---
@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...), 
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    
    saved_files = []
    count = 0

    for file in files:
        content = await file.read()
        
        # LOGIQUE DECOMPRESSION
        if file.filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        if not name.endswith("/") and "__MACOSX" not in name and ".." not in name:
                            file_path = os.path.join(target_dir, os.path.basename(name))
                            with open(file_path, "wb") as f:
                                f.write(z.read(name))
                            saved_files.append(name)
                            count += 1
            except Exception as e:
                print(f"Zip Error: {e}")
                file_path = os.path.join(target_dir, file.filename)
                with open(file_path, "wb") as f:
                    f.write(content)
                saved_files.append(file.filename)
                count += 1
        else:
            file_path = os.path.join(target_dir, file.filename)
            with open(file_path, "wb") as f:
                f.write(content)
            saved_files.append(file.filename)
            count += 1
        
    return {
        "status": "success", 
        "saved": saved_files, 
        "count": count,
        "context": "project" if project_id else "session"
    }

# --- 2. LIST (With Date Metadata) ---
@router.get("/details")
@router.get("/list")
def list_files(
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="read")
    
    if not os.path.exists(target_dir):
        return {"files": []}
        
    files_info = []
    try:
        for f in os.listdir(target_dir):
            full_path = os.path.join(target_dir, f)
            if os.path.isfile(full_path) and not f.startswith('.'):
                stat = os.stat(full_path)
                dt_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

                files_info.append({
                    "filename": f,
                    "path": f,
                    "size": stat.st_size,
                    "uploaded_at": dt_str,
                    "content_type": "application/octet-stream"
                })
    except Exception as e:
        print(f"List Error: {e}")
        return {"files": [], "error": str(e)}
            
    files_info.sort(key=lambda x: x['uploaded_at'], reverse=True)
    return {"files": files_info}

# --- 3. DOWNLOAD (RESTORED!) ---
@router.get("/download")
def download_file(
    filename: str = Query(...),
    project_id: Optional[str] = Query(None),
    # Note: On utilise Query param 'token' pour le lien direct navigateur, 
    # ou Header Authorization pour les appels API.
    # Ici, on simplifie en supposant que l'auth passe par Header comme le reste,
    # mais pour un lien href, il faudra peut-être gérer le token en query param si le front le fait.
    user = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="read")
    file_path = os.path.join(target_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(
        path=file_path, 
        filename=filename,
        media_type='application/octet-stream'
    )

# --- 4. DELETE ---
@router.delete("/file/{filename}")
def delete_file(
    filename: str,
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    file_path = os.path.join(target_dir, filename)
    
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")

    if not os.path.exists(file_path):
        raise HTTPException(404, "File not found")
        
    os.remove(file_path)
    return {"status": "deleted", "filename": filename}

# --- 5. CLEAR ---
@router.delete("/clear")
def clear_files(
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    for f in os.listdir(target_dir):
        file_path = os.path.join(target_dir, f)
        if os.path.isfile(file_path):
            os.remove(file_path)
    return {"status": "cleared"}
