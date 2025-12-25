from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from typing import List
import zipfile
import io
import os
from app.core.security import get_current_token
from app.services import session_manager

router = APIRouter(prefix="/session", tags=["Session Data"])

# 1. AUGMENTATION DE LA LIMITE (Demande utilisateur)
MAX_FILES_PER_UPLOAD = 50 

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(..., description="Fichiers .SI2S, .LF1S, .xlsx, .json ou archive .zip"),
    token: str = Depends(get_current_token)
):
    """
    Upload de fichiers vers la mémoire RAM (Session).
    - Supporte : .SI2S, .LF1S, .xlsx, .json (Config)
    - Gestion des ZIP (extraction auto)
    - Limite : 50 fichiers max par appel.
    """
    
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400, 
            detail=f"Limite dépassée : Vous ne pouvez envoyer que {MAX_FILES_PER_UPLOAD} fichiers à la fois."
        )

    files_data = {}
    
    for file in files:
        filename = file.filename
        content = await file.read()
        
        # Gestion ZIP
        if filename.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for member_name in z.namelist():
                        if member_name.endswith('/') or '__MACOSX' in member_name or member_name.startswith('.'):
                            continue
                        
                        extracted_content = z.read(member_name)
                        clean_name = os.path.basename(member_name)
                        
                        if clean_name: 
                            files_data[clean_name] = extracted_content
                            
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail=f"Le fichier {filename} est un ZIP corrompu.")
        
        # Fichiers standards (SI2S, LF1S, XLSX, JSON...)
        else:
            # On stocke tout tel quel. Le session_manager accepte les bytes.
            files_data[filename] = content
            
    # Sauvegarde en session
    total_count = session_manager.save_files(token, files_data)
    
    return {
        "status": "success", 
        "message": f"{len(files_data)} fichier(s) traité(s) et ajouté(s) en RAM.",
        "files_stored": list(files_data.keys()),
        "total_files_in_session": total_count
    }

@router.get("/details")
def get_details(token: str = Depends(get_current_token)):
    return session_manager.get_session_details(token)

@router.delete("/file/{filename}")
def delete_file(filename: str, token: str = Depends(get_current_token)):
    if not session_manager.remove_file(token, filename):
        raise HTTPException(status_code=404, detail="Fichier non trouvé en session")
    return {"status": "success", "message": f"{filename} supprimé"}

@router.post("/clear")
def clear(token: str = Depends(get_current_token)):
    session_manager.clear_session(token)
    return {"status": "success", "message": "RAM nettoyée"}
