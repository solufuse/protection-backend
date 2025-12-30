
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

# [CONFIGURATION]
# Doit correspondre exactement à BASE_STORAGE dans guest_guard.py
STORAGE_ROOT = "/app/storage" 

# --- HELPER: CALCUL TAILLE DOSSIER ---
def get_size(start_path = '.'):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
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
    # Création du dossier s'il n'existe pas (pour éviter l'erreur au premier lancement)
    if not os.path.exists(STORAGE_ROOT):
        try:
            os.makedirs(STORAGE_ROOT, exist_ok=True)
        except OSError:
            return {"error": "Storage root not found and cannot be created", "path": STORAGE_ROOT}
    
    total_size = get_size(STORAGE_ROOT)
    
    # Scan projects (dossiers uniquement)
    projects_on_disk = [d for d in os.listdir(STORAGE_ROOT) if os.path.isdir(os.path.join(STORAGE_ROOT, d))]
    
    # Disk Usage global du volume
    try:
        usage = shutil.disk_usage(STORAGE_ROOT)
    except:
        usage = "unknown"

    return {
        "root_path": STORAGE_ROOT,
        "total_size_raw": total_size,
        "total_size_fmt": format_bytes(total_size),
        "total_folders": len(projects_on_disk),
        "disk_usage": usage
    }

# 2. LIST ALL FOLDERS (Physical vs DB Audit)
@router.get("/audit", dependencies=[Depends(require_super_admin)])
def audit_storage(db: Session = Depends(get_db)):
    if not os.path.exists(STORAGE_ROOT):
        return []

    # A. Ce qu'il y a sur le DISQUE
    disk_projects = []
    try:
        for item in os.listdir(STORAGE_ROOT):
            item_path = os.path.join(STORAGE_ROOT, item)
            # On ne liste que les dossiers (les UIDs sont des dossiers)
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

    # B. Ce qu'il y a dans la DB
    # On récupère tous les IDs de Users et de Projets pour comparer
    # (Note: Dans ton système actuel, les dossiers s'appellent par l'UID du user pour le stockage invité)
    
    # Liste des UIDs connus (Users)
    db_users = db.query(User).all()
    known_ids = {u.firebase_uid for u in db_users}
    
    # Liste des IDs de projets (si les projets ont leur propre dossier séparé)
    db_projects = db.query(Project).all()
    known_ids.update({p.id for p in db_projects})

    # C. Comparaison
    result = []
    for p in disk_projects:
        # Si le nom du dossier correspond à un UID User ou un ID Projet
        if p["id"] in known_ids:
            p["status"] = "active"
        else:
            p["status"] = "orphan" 
        result.append(p)
        
    return result

# 3. DELETE FOLDER (Force Cleanup)
@router.delete("/{folder_id}", dependencies=[Depends(require_super_admin)])
def force_delete_folder(folder_id: str):
    # Sécurité
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
