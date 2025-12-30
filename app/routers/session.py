
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from app.core.security import get_current_token
from app.services import session_manager
from typing import List, Optional
from firebase_admin import auth
import zipfile, io, os, datetime

router = APIRouter(prefix="/session", tags=["Session Storage"])

# --- PROJECT LIFECYCLE ---
@router.get("/projects")
def list_my_projects(token: str = Depends(get_current_token)):
    return session_manager.list_projects_for_user(token)

@router.post("/project/create")
def create_project(project_id: str = Query(..., min_length=3), token: str = Depends(get_current_token)):
    try:
        user = auth.get_user(token)
        email = user.email
    except: email = "unknown"
    success = session_manager.create_project(owner_uid=token, project_id=project_id, owner_email=email)
    if not success: raise HTTPException(400, "Project already exists.")
    return {"status": "created", "project_id": project_id}

@router.delete("/project")
def delete_project_permanently(project_id: str = Query(...), token: str = Depends(get_current_token)):
    if not session_manager.is_project_owner(token, project_id):
        raise HTTPException(403, "Only the owner can delete the project.")
    session_manager.delete_project_permanently(project_id)
    return {"status": "deleted", "project_id": project_id}

@router.post("/project/invite")
def invite_member(project_id: str = Query(...), email: str = Query(...), token: str = Depends(get_current_token)):
    if not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied.")
    try:
        user = auth.get_user_by_email(email)
        session_manager.add_member(project_id, user.uid)
        return {"status": "invited", "email": email}
    except: raise HTTPException(404, "User email not found in Firebase.")

@router.delete("/project/member")
def remove_member(project_id: str = Query(...), uid_to_remove: str = Query(...), token: str = Depends(get_current_token)):
    if not session_manager.is_project_owner(token, project_id) and token != uid_to_remove:
        raise HTTPException(403, "Only owner can remove others.")
    session_manager.remove_member(project_id, uid_to_remove)
    return {"status": "removed"}

# --- FILES ---
@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target_id, is_project = token, False
    if project_id:
        if not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied.")
        target_id, is_project = project_id, True
    
    count = 0
    for file in files:
        content = await file.read()
        if file.filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        if not name.endswith("/") and "__MACOSX" not in name:
                            session_manager.add_file(target_id, name, z.read(name), is_project)
                            count += 1
            except:
                session_manager.add_file(target_id, file.filename, content, is_project)
                count += 1
        else:
            session_manager.add_file(target_id, file.filename, content, is_project)
            count += 1
    return {"message": f"{count} files saved.", "scope": "project" if is_project else "user"}

@router.get("/details")
def get_details(token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target_id, is_project = token, False
    if project_id:
        if not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied.")
        target_id, is_project = project_id, True
    
    session_manager.get_files(target_id, is_project)
    base_dir = session_manager._get_target_dir(target_id, is_project)
    files_info = []
    if os.path.exists(base_dir):
        for root, dirs, files in os.walk(base_dir):
            for name in files:
                if name.startswith('.') or name == "access.json": continue
                full = os.path.join(root, name)
                try: dt = datetime.datetime.fromtimestamp(os.path.getmtime(full)).strftime("%Y-%m-%d %H:%M:%S")
                except: dt = "-"
                files_info.append({"path": os.path.relpath(full, base_dir).replace("\\", "/"), "filename": name, "size": os.path.getsize(full), "uploaded_at": dt})
    return {"active": True, "scope": "project" if is_project else "user", "files": files_info}

@router.get("/download")
def download(filename: str = Query(...), token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target_id, is_project = token, False
    if project_id:
        if not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied.")
        target_id, is_project = project_id, True
    path = session_manager.get_absolute_file_path(target_id, filename, is_project)
    if not os.path.exists(path):
        session_manager.get_files(target_id, is_project)
        if not os.path.exists(path): raise HTTPException(404, "File not found")
    return FileResponse(path, filename=os.path.basename(filename))

@router.delete("/file/{path:path}")
def delete_file(path: str, token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target_id, is_project = token, False
    if project_id:
        if not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied.")
        target_id, is_project = project_id, True
    
    # Secure Delete call
    success = session_manager.remove_file(target_id, path, is_project)
    if not success:
        return {"status": "protected", "message": "Cannot delete protected system files (access.json)."}
        
    return {"status": "deleted"}

@router.delete("/clear")
def clear(token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target_id, is_project = token, False
    if project_id:
        if not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied.")
        target_id, is_project = project_id, True
    session_manager.clear_session(target_id, is_project)
    return {"status": "cleared"}
