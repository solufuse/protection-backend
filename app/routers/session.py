from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.core.security import get_current_token
from app.services import session_manager
from typing import List
import zipfile
import io
import os

router = APIRouter(prefix="/session", tags=["Session RAM"])

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), token: str = Depends(get_current_token)):
    """
    Uploads files to the shared RAM session.
    
    Features:
    - Supports multiple file uploads.
    - Automatically unzips .zip files to store individual contents.
    - Stores files in memory (session_manager) linked to the user's token.
    """
    count = 0
    for file in files:
        content = await file.read()
        
        # Automatic ZIP handling
        if file.filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        # Skip directories and macOS metadata
                        if not name.endswith("/") and "__MACOSX" not in name:
                            session_manager.add_file(token, name, z.read(name))
                            count += 1
            except:
                # If extraction fails, store the zip file as is
                session_manager.add_file(token, file.filename, content)
                count += 1
        else:
            # Standard file storage
            session_manager.add_file(token, file.filename, content)
            count += 1
            
    # Retrieve current state to confirm upload
    current_files = session_manager.get_files(token)
    return {"message": f"{count} files added.", "total_files": len(current_files)}

@router.get("/details")
def get_details(token: str = Depends(get_current_token)):
    """
    Retrieves the list of files currently stored in the active session.
    Returns metadata including file size, full path, and short filename.
    """
    files = session_manager.get_files(token)
    
    files_info = []
    if files:
        for name, content in files.items():
            size = len(content) if isinstance(content, bytes) else len(str(content))
            files_info.append({
                "path": name,                          # Full path (e.g., FOLDER/file.lf1s)
                "filename": os.path.basename(name),    # Short name (e.g., file.lf1s)
                "size": size,
                "content_type": "application/octet-stream"
            })
        
    return {
        "active": True,
        "file_count": len(files_info),
        "files": files_info
    }

@router.delete("/file/{filename:path}")
def delete_file(filename: str, token: str = Depends(get_current_token)):
    """ 
    Deletes a specific file from the session.
    Note: 'filename' parameter matches the full path key stored in the session.
    """
    files = session_manager.get_files(token)
    if not files or filename not in files:
        raise HTTPException(status_code=404, detail="File not found in session")
    
    session_manager.remove_file(token, filename)
    return {"status": "deleted", "filename": filename}

@router.delete("/clear")
def clear_session(token: str = Depends(get_current_token)):
    """ 
    Clears the entire session memory for the current user.
    Removes all uploaded files and configurations.
    """
    session_manager.clear_session(token)
    return {"status": "cleared", "message": "Session memory cleared."}
