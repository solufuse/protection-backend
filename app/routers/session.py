from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from app.core.security import get_current_token
from typing import List
import zipfile
import io
import os
from datetime import datetime

# Import de la mémoire vive et du convertisseur
try:
    from app.core.memory import SESSIONS, CLOUD_SETTINGS
    from app.core.db_converter import DBConverter
    from app.firebase_config import db, bucket
except ImportError:
    from core.memory import SESSIONS, CLOUD_SETTINGS
    from core.db_converter import DBConverter
    from firebase_config import db, bucket

router = APIRouter(prefix="/session", tags=["Session RAM & Hybrid"])

# --- HELPERS ---
def process_to_memory(user_id: str, filename: str, content: bytes):
    """
    Convertit le fichier binaire en JSON et l'injecte en RAM.
    """
    # On crée un fichier temporaire pour le convertisseur
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Conversion SQLite -> JSON
        result_data = DBConverter.convert_to_json(tmp_path, filename)
        
        if user_id not in SESSIONS:
            SESSIONS[user_id] = []
            
        file_meta = {
            "id": str(uuid.uuid4()),
            "original_name": filename,
            "created_at": datetime.utcnow(),
            "source_type": os.path.splitext(filename)[1].replace('.', ''),
            "cloud_synced": False,
            "data_preview": result_data # Donnée disponible immédiatement en RAM
        }
        
        SESSIONS[user_id].insert(0, file_meta)
        return file_meta
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# --- ENDPOINTS ---

@router.get("/details")
async def get_details(token: str = Depends(get_current_token)):
    """
    Récupère les fichiers en RAM pour l'utilisateur actuel (via Token).
    """
    user_files = SESSIONS.get(token, [])
    return {
        "active": True,
        "source": "RAM_MEMORY",
        "file_count": len(user_files),
        "files": user_files
    }

@router.post("/upload")
async def upload_to_session(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...), 
    token: str = Depends(get_current_token)
):
    """
    Upload des fichiers, extraction ZIP et injection immédiate en RAM.
    """
    count = 0
    for file in files:
        content = await file.read()
        
        if file.filename.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for name in z.namelist():
                        if not name.endswith("/") and "__MACOSX" not in name:
                            process_to_memory(token, name, z.read(name))
                            count += 1
            except Exception as e:
                print(f"ZIP Error: {e}")
        else:
            process_to_memory(token, file.filename, content)
            count += 1
            
    return {"message": f"{count} fichiers injectés en RAM.", "user_id": token}

@router.delete("/clear")
async def clear_session(token: str = Depends(get_current_token)):
    """ Vide la mémoire vive de l'utilisateur """
    if token in SESSIONS:
        SESSIONS[token] = []
    return {"status": "cleared", "user_id": token}
