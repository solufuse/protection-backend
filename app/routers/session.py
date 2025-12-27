from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from app.core.security import get_current_token
from app.services import session_manager
from typing import List
import zipfile
import io
import os

router = APIRouter(prefix="/session", tags=["Session Storage"])

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), token: str = Depends(get_current_token)):
    count = 0
    for file in files:
        content = await file.read()
        if file.filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        if not name.endswith("/") and "__MACOSX" not in name:
                            session_manager.add_file(token, name, z.read(name))
                            count += 1
            except:
                session_manager.add_file(token, file.filename, content)
                count += 1
        else:
            session_manager.add_file(token, file.filename, content)
            count += 1
    return {"message": f"{count} files saved."}

@router.get("/details")
def get_details(token: str = Depends(get_current_token)):
    user_storage_dir = os.path.join("/app/storage", token)
    files_info = []
    if os.path.exists(user_storage_dir):
        for root, dirs, files in os.walk(user_storage_dir):
            for name in files:
                if name.startswith('.'): continue
                full_path = os.path.join(root, name)
                rel_path = os.path.relpath(full_path, user_storage_dir).replace("\\", "/")
                files_info.append({
                    "path": rel_path, "filename": name,
                    "size": os.path.getsize(full_path), "content_type": "application/octet-stream"
                })
    return {"active": True, "files": files_info}

@router.get("/download")
def download_raw_file(filename: str = Query(...), token: str = Depends(get_current_token)):
    # This endpoint is crucial for the "RAW" button in frontend
    safe_filename = os.path.basename(filename)
    file_path = os.path.join("/app/storage", token, safe_filename)
    if not os.path.exists(file_path):
         raise HTTPException(status_code=404, detail=f"File '{safe_filename}' not found.")
    return FileResponse(file_path, filename=safe_filename)

@router.delete("/file/{path:path}")
def delete_file(path: str, token: str = Depends(get_current_token)):
    session_manager.remove_file(token, path)
    return {"status": "deleted", "path": path}

@router.delete("/clear")
def clear_session(token: str = Depends(get_current_token)):
    session_manager.clear_session(token)
    return {"status": "cleared"}
