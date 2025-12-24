from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from typing import List
import zipfile
import io
import os
from app.core.security import get_current_token
from app.services import session_manager

router = APIRouter(prefix="/session", tags=["Session Data"])

MAX_FILES_PER_UPLOAD = 10

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(..., description="Fichiers .SI2S, .xlsx ou une archive .zip"),
    token: str = Depends(get_current_token)
):
    """
    Upload de fichiers vers la mémoire RAM (Session).
    - Supporte la sélection multiple.
    - Supporte les fichiers .zip (extraction automatique).
    - Limite : 10 fichiers max par appel.
    """
    
    # 1. Vérification de la limite
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400, 
            detail=f"Limite dépassée : Vous ne pouvez envoyer que {MAX_FILES_PER_UPLOAD} fichiers à la fois."
        )

    files_data = {}
    
    for file in files:
        filename = file.filename
        content = await file.read()
        
        # 2. Gestion intelligente du ZIP
        if filename.lower().endswith('.zip'):
            try:
                # On ouvre le zip en mémoire
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for member_name in z.namelist():
                        # On ignore les dossiers
                        if member_name.endswith('/'):
                            continue
                            
                        # On ignore les fichiers cachés du Mac (__MACOSX)
                        if '__MACOSX' in member_name or member_name.startswith('.'):
                            continue
                        
                        # Lecture du fichier dans le zip
                        extracted_content = z.read(member_name)
                        
                        # On aplatit le nom (enlève les dossiers) pour simplifier le stockage
                        # ex: "mon_dossier/test.si2s" devient "test.si2s"
                        clean_name = os.path.basename(member_name)
                        
                        if clean_name: # Si le nom n'est pas vide
                            files_data[clean_name] = extracted_content
                            
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail=f"Le fichier {filename} est un ZIP corrompu.")
        
        # 3. Fichier normal (SI2S, XLSX...)
        else:
            files_data[filename] = content
            
    # Sauvegarde en session
    total_count = session_manager.save_files(token, files_data)
    
    return {
        "status": "success", 
        "message": f"{len(files_data)} fichier(s) traité(s) et ajouté(s) en RAM.",
        "files_extracted": list(files_data.keys()),
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
