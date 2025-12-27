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
        # Gestion des zips
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
    # Force la lecture du disque pour être sûr d'avoir les fichiers
    session_manager.get_files(token)
    
    user_storage_dir = os.path.join("/app/storage", token)
    files_info = []
    
    if os.path.exists(user_storage_dir):
        for root, dirs, files in os.walk(user_storage_dir):
            for name in files:
                if name.startswith('.'): continue
                full_path = os.path.join(root, name)
                # On renvoie le chemin relatif pour l'affichage
                rel_path = os.path.relpath(full_path, user_storage_dir).replace("\\", "/")
                files_info.append({
                    "path": rel_path,
                    "filename": name,
                    "size": os.path.getsize(full_path),
                    "content_type": "application/octet-stream"
                })
    return {"active": True, "files": files_info}

@router.get("/download")
def download_raw_file(filename: str = Query(...), token: str = Depends(get_current_token)):
    """
    Télécharge un fichier depuis /app/storage/{uid}/{filename}
    """
    # On construit le chemin absolu vers le fichier
    # Note: On utilise filename directement s'il ne contient pas de ".."
    if ".." in filename:
        raise HTTPException(status_code=400, detail="Chemin invalide.")
        
    file_path = os.path.join("/app/storage", token, filename)
    
    # Debug log (visible dans les logs serveur si besoin)
    print(f"Tentative de téléchargement : {file_path}")
    
    if not os.path.exists(file_path):
         # Dernière chance : on recharge le session_manager
         session_manager.get_files(token)
         if not os.path.exists(file_path):
             raise HTTPException(status_code=404, detail=f"Fichier introuvable sur le disque.")
             
    return FileResponse(file_path, filename=os.path.basename(filename))

@router.delete("/file/{path:path}")
def delete_file(path: str, token: str = Depends(get_current_token)):
    session_manager.remove_file(token, path)
    return {"status": "deleted", "path": path}

@router.delete("/clear")
def clear_session(token: str = Depends(get_current_token)):
    session_manager.clear_session(token)
    return {"status": "cleared"}
