
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Body
from fastapi.responses import FileResponse
from app.core.security import get_current_token
from app.services import session_manager
from typing import List, Optional
from firebase_admin import auth
import zipfile
import io
import os
import datetime

router = APIRouter(prefix="/session", tags=["Session Storage"])

# --- 1. PROJECT LIFECYCLE ---

@router.get("/projects")
def list_my_projects(token: str = Depends(get_current_token)):
    """List all projects where I am a member or owner."""
    return session_manager.list_projects_for_user(token)

@router.post("/project/create")
def create_project(
    project_id: str = Query(..., min_length=3),
    token: str = Depends(get_current_token)
):
    # Try to get email for better metadata
    try:
        user = auth.get_user(token)
        email = user.email
    except:
        email = "unknown"

    success = session_manager.create_project(owner_uid=token, project_id=project_id, owner_email=email)
    if not success:
        raise HTTPException(status_code=400, detail="Project already exists.")
    return {"status": "created", "project_id": project_id}

@router.delete("/project")
def delete_project_permanently(
    project_id: str = Query(...),
    token: str = Depends(get_current_token)
):
    """[DANGER] Permanently delete a project. OWNER ONLY."""
    if not session_manager.is_project_owner(token, project_id):
        raise HTTPException(403, "Only the owner can delete the project.")
    
    session_manager.delete_project_permanently(project_id)
    return {"status": "deleted", "project_id": project_id}

# --- 2. MEMBERS MANAGEMENT ---

@router.post("/project/invite")
def invite_member(
    project_id: str = Query(...),
    email: str = Query(..., description="Email of the user to invite"),
    token: str = Depends(get_current_token)
):
    # 1. Check permissions (Must be member to invite?)
    if not session_manager.can_access_project(token, project_id):
        raise HTTPException(403, "Access Denied.")
    
    # 2. Resolve Email -> UID via Firebase Admin
    try:
        user = auth.get_user_by_email(email)
        new_member_uid = user.uid
    except:
        raise HTTPException(404, f"User with email {email} not found in Firebase.")
    
    # 3. Add to ACL
    session_manager.add_member(project_id, new_member_uid)
    return {"status": "invited", "email": email, "uid": new_member_uid}

@router.delete("/project/member")
def remove_member(
    project_id: str = Query(...),
    uid_to_remove: str = Query(...),
    token: str = Depends(get_current_token)
):
    # Only owner can remove members (or member removing themselves)
    is_owner = session_manager.is_project_owner(token, project_id)
    if not is_owner and token != uid_to_remove:
        raise HTTPException(403, "Only owner can remove other members.")
        
    session_manager.remove_member(project_id, uid_to_remove)
    return {"status": "removed", "uid": uid_to_remove}

# --- 3. FILES OPERATIONS (Standard) ---

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...), 
    token: str = Depends(get_current_token),
    project_id: Optional[str] = Query(None)
):
    target_id = token
    is_project = False
    if project_id:
        if not session_manager.can_access_project(token, project_id):
            raise HTTPException(403, "Access Denied.")
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
            
    return {"message": f"{count} files saved.", "scope": "project" if is_project else "user"}

@router.get("/details")
def get_details(token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target_id = token
    is_project = False
    if project_id:
        if not session_manager.can_access_project(token, project_id):
            raise HTTPException(403, "Access Denied.")
        target_id = project_id
        is_project = True

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
                    "path": rel_path, "filename": name, "size": os.path.getsize(full_path),
                    "uploaded_at": formatted_date, "content_type": "application/octet-stream"
                })
    return {"active": True, "scope": "project" if is_project else "user", "files": files_info}

@router.get("/download")
def download_file(filename: str = Query(...), token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)): 
    target_id = token
    is_project = False
    if project_id:
        if not session_manager.can_access_project(token, project_id):
            raise HTTPException(403, "Access Denied.")
        target_id = project_id
        is_project = True

    file_path = session_manager.get_absolute_file_path(target_id, filename, is_project=is_project)
    if not os.path.exists(file_path): raise HTTPException(404, "File not found")
    return FileResponse(file_path, filename=os.path.basename(filename))

@router.delete("/file/{path:path}")
def delete_file(path: str, token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target_id = token
    is_project = False
    if project_id:
        if not session_manager.can_access_project(token, project_id):
             raise HTTPException(403, "Access Denied.")
        target_id = project_id
        is_project = True
    session_manager.remove_file(target_id, path, is_project=is_project)
    return {"status": "deleted", "path": path}

@router.delete("/clear")
def clear_session(token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target_id = token
    is_project = False
    if project_id:
        if not session_manager.can_access_project(token, project_id):
             raise HTTPException(403, "Access Denied.")
        target_id = project_id
        is_project = True
        
    session_manager.clear_session(target_id, is_project=is_project)
    return {"status": "cleared", "note": "Project files removed, ACL preserved." if is_project else "Session reset"}
