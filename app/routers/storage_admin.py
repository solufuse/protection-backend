
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Project
from ..auth import get_current_user
from pydantic import BaseModel
from typing import List, Dict

router = APIRouter()

# CONFIGURATION
STORAGE_ROOT = "/data"  # Le dossier racine monté dans Docker (ou ./data en local)

# --- HELPER: CALCUL TAILLE DOSSIER ---
def get_size(start_path = '.'):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size

def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"

# --- DEPENDENCY: SUPER ADMIN ONLY ---
def require_super_admin(user: User = Depends(get_current_user)):
    if not user or user.global_role != "super_admin":
        raise HTTPException(status_code=403, detail="Storage Admin Access Required")
    return user

# 1. GLOBAL STATS (Dashboard View)
@router.get("/stats", dependencies=[Depends(require_super_admin)])
def get_storage_stats():
    if not os.path.exists(STORAGE_ROOT):
        return {"error": "Storage root not found", "path": STORAGE_ROOT}
    
    total_size = get_size(STORAGE_ROOT)
    
    # Scan projects
    projects_on_disk = [d for d in os.listdir(STORAGE_ROOT) if os.path.isdir(os.path.join(STORAGE_ROOT, d))]
    
    return {
        "root_path": STORAGE_ROOT,
        "total_size_raw": total_size,
        "total_size_fmt": format_bytes(total_size),
        "total_folders": len(projects_on_disk),
        "disk_usage": shutil.disk_usage(STORAGE_ROOT) # Info système global (Free/Used)
    }

# 2. LIST ALL FOLDERS (Physical vs DB Audit)
@router.get("/audit", dependencies=[Depends(require_super_admin)])
def audit_storage(db: Session = Depends(get_db)):
    if not os.path.exists(STORAGE_ROOT):
        return []

    # 1. Ce qu'il y a sur le DISQUE
    disk_projects = []
    try:
        for item in os.listdir(STORAGE_ROOT):
            item_path = os.path.join(STORAGE_ROOT, item)
            if os.path.isdir(item_path):
                size = get_size(item_path)
                disk_projects.append({
                    "id": item,
                    "size_fmt": format_bytes(size),
                    "size_raw": size,
                    "status": "unknown"
                })
    except Exception as e:
        raise HTTPException(500, f"Disk Scan Error: {str(e)}")

    # 2. Ce qu'il y a dans la DB
    db_projects = db.query(Project).all()
    db_ids = {p.id for p in db_projects}

    # 3. Comparaison (Recherche des orphelins)
    result = []
    for p in disk_projects:
        if p["id"] in db_ids:
            p["status"] = "active" # Sain
        else:
            p["status"] = "orphan" # Dangereux (Prend de la place pour rien)
        result.append(p)
        
    return result

# 3. DELETE FOLDER (Force Cleanup)
@router.delete("/{folder_id}", dependencies=[Depends(require_super_admin)])
def force_delete_folder(folder_id: str):
    # Sécurité : Empêcher de supprimer la racine ou des dossiers système
    if ".." in folder_id or folder_id.startswith("/") or folder_id in [".", "lost+found"]:
        raise HTTPException(400, "Invalid folder ID")
        
    target_path = os.path.join(STORAGE_ROOT, folder_id)
    
    if not os.path.exists(target_path):
        raise HTTPException(404, "Folder not found on disk")
        
    try:
        shutil.rmtree(target_path)
        return {"status": "deleted", "path": target_path}
    except Exception as e:
        raise HTTPException(500, f"Delete failed: {str(e)}")
