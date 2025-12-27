from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from app.core.security import get_current_token
from app.services import session_manager
from app.services.session_manager import get_user_storage_path, get_absolute_file_path
from typing import List
import zipfile
import io
import os
import datetime

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
    return {"message": f"{count} fichiers sauvegardés."}

@router.get("/details")
def get_details(token: str = Depends(get_current_token)):
    user_storage_dir = get_user_storage_path(token)
    files_info = []
    
    if os.path.exists(user_storage_dir):
        for root, dirs, files in os.walk(user_storage_dir):
            for name in files:
                if name.startswith('.'): continue
                full_path = os.path.join(root, name)
                rel_path = os.path.relpath(full_path, user_storage_dir).replace("\\", "/")
                
                # Récupération de la date de modification
                timestamp = os.path.getmtime(full_path)
                dt_object = datetime.datetime.fromtimestamp(timestamp)
                formatted_date = dt_object.strftime("%Y-%m-%d %H:%M:%S")

                files_info.append({
                    "path": rel_path,
                    "filename": name,
                    "size": os.path.getsize(full_path),
                    "uploaded_at": formatted_date, # NOUVEAU CHAMP
                    "content_type": "application/octet-stream"
                })
    
    return {"active": True, "files": files_info}

@router.get("/download")
def download_raw_file(filename: str = Query(...), token: str = Query(None)): 
    # NOTE: On accepte le token en Query param pour faciliter les liens directs
    # Si token n'est pas dans Query, on pourrait le prendre via Depends(get_current_token) mais 
    # pour un lien href simple, le Query param est plus facile.
    # Dans une app stricte, on garderait le header, mais ici c'est demandé.
    
    if not token:
        raise HTTPException(status_code=401, detail="Token missing in query")

    file_path = get_absolute_file_path(token, filename)
    
    if not os.path.exists(file_path):
         raise HTTPException(status_code=404, detail="File not found")
             
    return FileResponse(file_path, filename=os.path.basename(filename))

@router.delete("/file/{path:path}")
def delete_file(path: str, token: str = Depends(get_current_token)):
    session_manager.remove_file(token, path)
    return {"status": "deleted", "path": path}

@router.delete("/clear")
def clear_session(token: str = Depends(get_current_token)):
    session_manager.clear_session(token)
    return {"status": "cleared"}
