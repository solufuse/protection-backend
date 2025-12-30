
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from app.core.security import get_current_token
from app.services import session_manager
from typing import List, Optional
import zipfile
import io
import os
import datetime

router = APIRouter(prefix="/session", tags=["Session Storage"])

# --- PROJECT MANAGEMENT ---

@router.post("/project/create")
def create_project(
    project_id: str = Query(..., description="Unique ID for the project (e.g. 'PRJ-001')"),
    token: str = Depends(get_current_token)
):
    success = session_manager.create_project(owner_uid=token, project_id=project_id)
    if not success:
        raise HTTPException(status_code=400, detail="Project already exists or cannot be created.")
    return {"status": "created", "project_id": project_id, "owner": token}

# --- FILE OPERATIONS ---

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...), 
    token: str = Depends(get_current_token),
    project_id: Optional[str] = Query(None)
):
    # [decision:logic] Backward compatibility: Default to User Storage if no project_id
    target_id = token
    is_project = False

    if project_id:
        if not session_manager.can_access_project(user_uid=token, project_id=project_id):
            raise HTTPException(status_code=403, detail="Access Denied to this Project.")
        target_id = project_id
        is_project = True
    
    count = 0
    for file in files:
        content = await file.read()
        if file.filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        if not name.endswith("/") and "__MACOSX" not in name:
                            session_manager.add_file(target_id, name, z.read(name), is_project=is_project)
                            count += 1
            except:
                session_manager.add_file(target_id, file.filename, content, is_project=is_project)
                count += 1
        else:
            session_manager.add_file(target_id, file.filename, content, is_project=is_project)
            count += 1
            
    return {
        "message": f"{count} files saved.", 
        "scope": "project" if is_project else "user"
    }

@router.get("/details")
def get_details(
    token: str = Depends(get_current_token),
    project_id: Optional[str] = Query(None)
):
    target_id = token
    is_project = False
    
    if project_id:
        if not session_manager.can_access_project(user_uid=token, project_id=project_id):
            raise HTTPException(status_code=403, detail="Access Denied.")
        target_id = project_id
        is_project = True

    session_manager.get_files(target_id, is_project=is_project)
    
    base_dir = session_manager._get_target_dir(target_id, is_project)
    files_info = []
    
    if os.path.exists(base_dir):
        for root, dirs, files in os.walk(base_dir):
            for name in files:
                if name.startswith('.'): continue
                if name == "access.json": continue

                full_path = os.path.join(root, name)
                rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")
                
                try:
                    timestamp = os.path.getmtime(full_path)
                    dt_object = datetime.datetime.fromtimestamp(timestamp)
                    formatted_date = dt_object.strftime("%Y-%m-%d %H:%M:%S")
                except: formatted_date = "-"

                files_info.append({
                    "path": rel_path,
                    "filename": name,
                    "size": os.path.getsize(full_path),
                    "uploaded_at": formatted_date,
                    "content_type": "application/octet-stream"
                })
    
    return {"active": True, "scope": "project" if is_project else "user", "files": files_info}

@router.get("/download")
def download_raw_file(
    filename: str = Query(...), 
    token: str = Depends(get_current_token), # [!] [CRITICAL] FIX: Now uses Depends() to verify signature
    project_id: Optional[str] = Query(None)
): 
    target_id = token
    is_project = False

    if project_id:
        if not session_manager.can_access_project(user_uid=token, project_id=project_id):
            raise HTTPException(status_code=403, detail="Access Denied.")
        target_id = project_id
        is_project = True

    file_path = session_manager.get_absolute_file_path(target_id, filename, is_project=is_project)
    
    if not os.path.exists(file_path):
         # Try reload
         session_manager.get_files(target_id, is_project=is_project)
         if not os.path.exists(file_path):
             raise HTTPException(status_code=404, detail="File not found")
             
    return FileResponse(file_path, filename=os.path.basename(filename))

@router.delete("/file/{path:path}")
def delete_file(
    path: str, 
    token: str = Depends(get_current_token),
    project_id: Optional[str] = Query(None)
):
    target_id = token
    is_project = False
    
    if project_id:
        if not session_manager.can_access_project(user_uid=token, project_id=project_id):
             raise HTTPException(status_code=403, detail="Access Denied.")
        target_id = project_id
        is_project = True

    session_manager.remove_file(target_id, path, is_project=is_project)
    return {"status": "deleted", "path": path}

@router.delete("/clear")
def clear_session(
    token: str = Depends(get_current_token),
    project_id: Optional[str] = Query(None)
):
    target_id = token
    is_project = False
    
    if project_id:
        if not session_manager.can_access_project(user_uid=token, project_id=project_id):
             raise HTTPException(status_code=403, detail="Access Denied.")
        target_id = project_id
        is_project = True
        
    session_manager.clear_session(target_id, is_project=is_project)
    return {"status": "cleared", "scope": "project" if is_project else "user"}
