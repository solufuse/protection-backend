
import os
import shutil
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker
from ..guest_guard import check_guest_restrictions

router = APIRouter()

# Helper pour déterminer le dossier cible (Session vs Projet)
def get_target_path(user, project_id: Optional[str], db: Session, action: str = "read"):
    
    # CAS 1 : C'est un PROJET
    if project_id:
        # Vérification des permissions (RBAC) via la DB
        checker = ProjectAccessChecker(required_role="viewer" if action == "read" else "editor")
        checker(project_id, user, db)
        
        # Le dossier est simplement l'ID du projet dans /app/storage
        # (Assure-toi que projects.py crée bien les dossiers ici)
        project_dir = os.path.join("/app/storage", project_id)
        if not os.path.exists(project_dir):
            os.makedirs(project_dir, exist_ok=True)
        return project_dir

    # CAS 2 : C'est la SESSION UTILISATEUR (Guest ou Perso)
    else:
        # On utilise le Guest Guard existant pour gérer le dossier perso
        # On suppose que l'utilisateur est un objet User (DB), on prend son firebase_uid
        uid = user.firebase_uid
        # On détermine si c'est un guest via l'email (ou un champ is_guest si dispo)
        is_guest = (user.email is None) 
        
        return check_guest_restrictions(uid, is_guest, action="upload" if action == "write" else "read")

# --- 1. UPLOAD (Dual Mode: Session / Project) ---
@router.post("/upload")
def upload_files(
    files: List[UploadFile] = File(...), 
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    
    saved_files = []
    for file in files:
        file_path = os.path.join(target_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file.filename)
        
    return {"status": "success", "saved": saved_files, "context": "project" if project_id else "session"}

# --- 2. LIST (Dual Mode) ---
@router.get("/details") # Pour compatibilité Frontend
@router.get("/list")
def list_files(
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="read")
    
    if not os.path.exists(target_dir):
        return {"files": []}
        
    files_info = []
    for f in os.listdir(target_dir):
        full_path = os.path.join(target_dir, f)
        if os.path.isfile(full_path) and not f.startswith('.'):
            files_info.append({
                "filename": f,
                "path": f, # Le frontend attend parfois 'path'
                "size": os.path.getsize(full_path),
                # "uploaded_at": ... (On pourrait ajouter la date ici)
            })
            
    return {"files": files_info}

# --- 3. DELETE (RESTORED!) ---
@router.delete("/file/{filename}")
def delete_file(
    filename: str,
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    file_path = os.path.join(target_dir, filename)
    
    # Sécurité basique anti ".."
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")

    if not os.path.exists(file_path):
        raise HTTPException(404, "File not found")
        
    os.remove(file_path)
    return {"status": "deleted", "filename": filename}

# --- 4. CLEAR (Optional) ---
@router.delete("/clear")
def clear_files(
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = get_target_path(user, project_id, db, action="write")
    
    # On vide le dossier
    for f in os.listdir(target_dir):
        file_path = os.path.join(target_dir, f)
        if os.path.isfile(file_path):
            os.remove(file_path)
            
    return {"status": "cleared"}
