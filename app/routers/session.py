
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
    Upload fichiers vers le stockage persistent (/app/storage).
    Gère l'extraction automatique des ZIP en préservant l'arborescence.
    """
    count = 0
    for file in files:
        content = await file.read()
        
        # Gestion ZIP automatique
        if file.filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        # On ignore les dossiers (terminant par /) et les fichiers macOS cachés
                        if not name.endswith("/") and "__MACOSX" not in name:
                            session_manager.add_file(token, name, z.read(name))
                            count += 1
            except:
                # Si échec extraction, on garde le zip tel quel
                session_manager.add_file(token, file.filename, content)
                count += 1
        else:
            session_manager.add_file(token, file.filename, content)
            count += 1
            
    return {"message": f"{count} fichiers sauvegardés dans le stockage."}

@router.get("/details")
def get_details(token: str = Depends(get_current_token)):
    """
    Liste les fichiers présents sur le disque (/app/storage).
    Renvoie le chemin complet (path) pour l'affichage Frontend.
    """
    storage_dir = "/app/storage"
    files_info = []
    
    if os.path.exists(storage_dir):
        for root, dirs, files in os.walk(storage_dir):
            for name in files:
                if name.startswith('.'): continue
                
                full_path = os.path.join(root, name)
                
                # Calcul du chemin relatif (ex: NORMAL/dossier/fichier.lf1s)
                rel_path = os.path.relpath(full_path, storage_dir)
                rel_path = rel_path.replace("\\", "/") # Pour compatibilité
                
                size = os.path.getsize(full_path)
                
                files_info.append({
                    "path": rel_path,
                    "filename": name,
                    "size": size,
                    "content_type": "application/octet-stream"
                })
        
    return {
        "active": True,
        "storage_mode": "DISK_PERSISTENT",
        "file_count": len(files_info),
        "files": files_info
    }

@router.delete("/file/{path:path}")
def delete_file(path: str, token: str = Depends(get_current_token)):
    """ 
    Supprime un fichier spécifique.
    Note: path:path permet de capturer les slashes dans l'URL (ex: dossier/fichier.txt)
    """
    session_manager.remove_file(token, path)
    return {"status": "deleted", "path": path}

@router.delete("/clear")
def clear_session(token: str = Depends(get_current_token)):
    """ Vide tout le dossier de stockage """
    session_manager.clear_session(token)
    return {"status": "cleared", "message": "Stockage vidé."}
