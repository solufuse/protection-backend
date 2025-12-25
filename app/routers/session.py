from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.core.session_manager import session_store
from app.core.security import get_current_token
from typing import List
import zipfile
import io

router = APIRouter(prefix="/session", tags=["Session RAM"])

# --- 1. UPLOAD (Existante) ---
@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...), user_id: str = Depends(get_current_token)):
    """
    Upload fichiers vers la RAM. Gère l'extraction automatique des ZIP.
    """
    if user_id not in session_store:
        session_store[user_id] = {}

    count = 0
    for file in files:
        content = await file.read()
        
        # Gestion ZIP automatique
        if file.filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        if not name.endswith("/") and "__MACOSX" not in name:
                            session_store[user_id][name] = z.read(name)
                            count += 1
            except:
                # Si échec extraction, on garde le zip tel quel
                session_store[user_id][file.filename] = content
                count += 1
        else:
            session_store[user_id][file.filename] = content
            count += 1
            
    return {"message": f"{count} fichiers ajoutés en mémoire.", "total_files": len(session_store[user_id])}

# --- 2. DETAILS (Existante) ---
@router.get("/details")
def get_details(user_id: str = Depends(get_current_token)):
    if user_id not in session_store:
        return {"active": False, "file_count": 0, "files": []}
    
    files_info = []
    for name, content in session_store[user_id].items():
        files_info.append({
            "filename": name,
            "size": len(content),
            "content_type": "application/octet-stream"
        })
        
    return {
        "active": True,
        "file_count": len(files_info),
        "files": files_info
    }

# --- 3. DELETE ONE (Nouvelle) ---
@router.delete("/file/{filename}")
def delete_file(filename: str, user_id: str = Depends(get_current_token)):
    """ Supprime un fichier spécifique de la RAM """
    # On vérifie si l'utilisateur a une session
    if user_id not in session_store:
        raise HTTPException(status_code=404, detail="Session vide")
    
    # On cherche le fichier (attention aux encodages URL)
    # Parfois le filename arrive encodé, mais FastAPI gère souvent le décodage.
    # On vérifie l'existence directe
    if filename in session_store[user_id]:
        del session_store[user_id][filename]
        return {"status": "deleted", "filename": filename, "remaining": len(session_store[user_id])}
    
    raise HTTPException(status_code=404, detail=f"Fichier '{filename}' introuvable en session")

# --- 4. CLEAR ALL (Nouvelle - C'est celle qui manquait !) ---
@router.delete("/clear")
def clear_session(user_id: str = Depends(get_current_token)):
    """ Vide toute la mémoire de l'utilisateur """
    session_store[user_id] = {}
    return {"status": "cleared", "message": "Mémoire session vidée."}
