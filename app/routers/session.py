
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.core.security import get_current_token
from app.services import session_manager
from typing import List
import zipfile
import io
import os

router = APIRouter(prefix="/session", tags=["Session Storage"])

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), token: str = Depends(get_current_token)):
    """
    Upload vers /app/storage/{uid}/...
    """
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
    """
    Liste les fichiers de l'utilisateur courant uniquement.
    """
    # On reconstruit le chemin comme dans le service
    user_storage_dir = os.path.join("/app/storage", token)
    files_info = []
    
    if os.path.exists(user_storage_dir):
        for root, dirs, files in os.walk(user_storage_dir):
            for name in files:
                if name.startswith('.'): continue
                
                full_path = os.path.join(root, name)
                
                # Le path retourné au frontend est relatif à l'utilisateur (ex: "MonDossier/fic.txt")
                # et non absolu (ex: "/app/storage/uid/MonDossier/fic.txt")
                rel_path = os.path.relpath(full_path, user_storage_dir)
                rel_path = rel_path.replace("\\", "/")
                
                size = os.path.getsize(full_path)
                
                files_info.append({
                    "path": rel_path,
                    "filename": name,
                    "size": size,
                    "content_type": "application/octet-stream"
                })
        
    return {
        "active": True,
        "storage_mode": "USER_ISOLATED",
        "file_count": len(files_info),
        "files": files_info
    }

@router.delete("/file/{path:path}")
def delete_file(path: str, token: str = Depends(get_current_token)):
    """ Supprime un fichier dans l'espace de l'utilisateur """
    session_manager.remove_file(token, path)
    return {"status": "deleted", "path": path}

@router.delete("/clear")
def clear_session(token: str = Depends(get_current_token)):
    """ Vide le dossier de l'utilisateur """
    session_manager.clear_session(token)
    return {"status": "cleared", "message": "Espace de stockage vidé."}
