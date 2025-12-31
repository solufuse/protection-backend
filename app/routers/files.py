
import os
import shutil
import zipfile
import io
import datetime
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker, QUOTAS
from ..models import User

router = APIRouter()
STORAGE_ROOT = "/app/storage"

# ==============================================================================
# 1. SECURITY & HELPER FUNCTIONS
# ==============================================================================

def get_target_path(user: User, project_id: Optional[str], db: Session, action: str = "read") -> str:
    """
    [+] [INFO] Determines the physical storage path based on context.
    - If project_id provided: Checks Project permissions (Viewer/Editor).
    - If no project_id: Uses User/Guest personal session folder.
    """
    
    # CASE A: PROJECT CONTEXT
    if project_id:
        # [decision:logic] Verify user has rights to this project
        required_role = "viewer" if action == "read" else "editor"
        checker = ProjectAccessChecker(required_role=required_role)
        checker(project_id, user, db)
        
        project_dir = os.path.join(STORAGE_ROOT, project_id)
        if not os.path.exists(project_dir):
            os.makedirs(project_dir, exist_ok=True)
        return project_dir
        
    # CASE B: PERSONAL/GUEST SESSION
    else:
        # [decision:logic] Guests and Users have a personal folder named after their UID
        session_dir = os.path.join(STORAGE_ROOT, user.firebase_uid)
        if not os.path.exists(session_dir):
            os.makedirs(session_dir, exist_ok=True)
        return session_dir

def count_files_in_dir(directory: str) -> int:
    """Counts non-hidden files in a directory."""
    try:
        return len([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and not f.startswith('.')])
    except:
        return 0

# ==============================================================================
# 2. ROUTES
# ==============================================================================

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...), 
    project_id: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Handles file uploads with Zip extraction and Quota enforcement.
    """
    # 1. Determine Target Path & Permissions
    target_dir = get_target_path(user, project_id, db, action="write")
    
    # 2. Check Quotas
    # [!] [CRITICAL] We check limits BEFORE processing files to save resources.
    user_quota = QUOTAS.get(user.global_role, QUOTAS["guest"])
    max_files = user_quota["max_files"]
    
    if max_files != -1:
        current_count = count_files_in_dir(target_dir)
        # Note: This is a "soft" check. It counts 1 zip as 1 upload request.
        if current_count + len(files) > max_files:
             msg = f"Quota exceeded. Limit: {max_files} files."
             if user.global_role == "guest": msg += " Create an account for more."
             elif user.global_role == "user": msg += " Upgrade to Nitro."
             raise HTTPException(status_code=403, detail=msg)

    saved_files = []
    
    # 3. Process Files
    for file in files:
        try:
            content = await file.read()
            file_path = os.path.join(target_dir, file.filename)
            
            # A. Handle ZIP Files (Auto-Unzip)
            if file.filename.endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        for name in z.namelist():
                            # Security: Prevent path traversal
                            if not name.endswith("/") and "__MACOSX" not in name and ".." not in name:
                                extracted_path = os.path.join(target_dir, os.path.basename(name))
                                with open(extracted_path, "wb") as f:
                                    f.write(z.read(name))
                                saved_files.append(name)
                except Exception as e:
                    print(f"⚠️ [ZIP ERROR] Failed to unzip {file.filename}: {e}")
                    # Fallback: Save zip as-is if extraction fails
                    with open(file_path, "wb") as f:
                        f.write(content)
                    saved_files.append(file.filename)
            
            # B. Handle Standard Files
            else:
                with open(file_path, "wb") as f:
                    f.write(content)
                saved_files.append(file.filename)
                
        except Exception as e:
            print(f"❌ [UPLOAD ERROR] {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save {file.filename}")

    return {
        "status": "success", 
        "saved_count": len(saved_files), 
        "quota_status": f"{count_files_in_dir(target_dir)}/{max_files if max_files != -1 else 'Inf'}",
        "context": "project" if project_id else "personal_session"
    }

@router.get("/list")
def list_files(
    project_id: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Lists files with metadata (Size, Date).
    Used by Frontend to display the file explorer.
    """
    target_dir = get_target_path(user, project_id, db, action="read")
    
    if not os.path.exists(target_dir):
        return {"files": []}
        
    files_info = []
    try:
        for f in os.listdir(target_dir):
            full_path = os.path.join(target_dir, f)
            
            # Only list actual files, not subdirectories or hidden files
            if os.path.isfile(full_path) and not f.startswith('.'):
                stat = os.stat(full_path)
                dt_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                
                files_info.append({
                    "filename": f,
                    "size": stat.st_size,
                    "uploaded_at": dt_str,
                    "content_type": "application/octet-stream" 
                })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Directory read error: {str(e)}")

    # Sort by newest first
    files_info.sort(key=lambda x: x['uploaded_at'], reverse=True)
    return {"files": files_info}

@router.get("/download")
def download_file(
    filename: str = Query(...),
    project_id: Optional[str] = Query(None),
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Secure file download.
    Prevents Path Traversal attacks.
    """
    # Security: Sanitization
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    target_dir = get_target_path(user, project_id, db, action="read")
    file_path = os.path.join(target_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(
        path=file_path, 
        filename=filename,
        media_type='application/octet-stream'
    )

@router.delete("/file/{filename}")
def delete_file(
    filename: str,
    project_id: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Delete a single file.
    """
    # Security: Sanitization
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    target_dir = get_target_path(user, project_id, db, action="write")
    file_path = os.path.join(target_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        os.remove(file_path)
        return {"status": "deleted", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

@router.delete("/clear")
def clear_files(
    project_id: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Wipes all files in the current folder.
    Useful for 'Reset Session' buttons.
    """
    target_dir = get_target_path(user, project_id, db, action="write")
    
    deleted_count = 0
    try:
        for f in os.listdir(target_dir):
            file_path = os.path.join(target_dir, f)
            if os.path.isfile(file_path):
                os.remove(file_path)
                deleted_count += 1
        return {"status": "cleared", "deleted_count": deleted_count}
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Clear failed: {str(e)}")
