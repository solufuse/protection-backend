from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from app.core.security import get_current_token
from app.services import session_manager
# On importe les fonctions utilitaires pour garantir la cohérence des chemins
from app.services.session_manager import get_user_storage_path, get_absolute_file_path
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
                files_info.append({
                    "path": rel_path, # Path utilisé pour la suppression
                    "filename": name, # Nom d'affichage
                    "size": os.path.getsize(full_path),
                    "content_type": "application/octet-stream"
                })
    
    return {"active": True, "files": files_info}

# --- C'EST CETTE FONCTION QUI MANQUAIT ---
@router.get("/download")
def download_raw_file(filename: str = Query(...), token: str = Depends(get_current_token)):
    # Utilisation de la fonction centralisée pour trouver le fichier
    file_path = get_absolute_file_path(token, filename)
    
    if not os.path.exists(file_path):
         # Debug log pour les logs serveur
         print(f"❌ File not found: {file_path}")
         raise HTTPException(status_code=404, detail="Fichier introuvable sur le disque.")
         
    return FileResponse(file_path, filename=os.path.basename(filename))

@router.delete("/file/{path:path}")
def delete_file(path: str, token: str = Depends(get_current_token)):
    session_manager.remove_file(token, path)
    return {"status": "deleted", "path": path}

@router.delete("/clear")
def clear_session(token: str = Depends(get_current_token)):
    session_manager.clear_session(token)
    return {"status": "cleared"}
