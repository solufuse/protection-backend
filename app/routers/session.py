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
    Upload fichiers vers la RAM partagée avec le Loadflow.
    """
    count = 0
    for file in files:
        content = await file.read()
        
        # Gestion ZIP automatique
        if file.filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        if not name.endswith("/") and "__MACOSX" not in name:
                            # On utilise le service partagé
                            session_manager.add_file(token, name, z.read(name))
                            count += 1
            except:
                # Si échec extraction, on garde le zip tel quel
                session_manager.add_file(token, file.filename, content)
                count += 1
        else:
            session_manager.add_file(token, file.filename, content)
            count += 1
            
    # On récupère le total pour confirmer
    current_files = session_manager.get_files(token)
    return {"message": f"{count} fichiers ajoutés.", "total_files": len(current_files)}

@router.get("/details")
def get_details(token: str = Depends(get_current_token)):
    files = session_manager.get_files(token)
    
    files_info = []
    if files:
        for name, content in files.items():
            size = len(content) if isinstance(content, bytes) else len(str(content))
            files_info.append({
                "filename": name,
                "short_name": os.path.basename(name), # <--- Ajout du nom court
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
    """ Supprime un fichier spécifique """
    files = session_manager.get_files(token)
    if not files or filename not in files:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    
    session_manager.remove_file(token, filename)
    return {"status": "deleted", "filename": filename}

@router.delete("/clear")
def clear_session(token: str = Depends(get_current_token)):
    """ Vide toute la mémoire """
    session_manager.clear_session(token)
    return {"status": "cleared", "message": "Mémoire session vidée."}
