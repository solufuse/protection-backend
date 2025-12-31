
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Project
from ..auth import get_current_user

router = APIRouter()
STORAGE_ROOT = "/app/storage"

def require_super_admin(user: User = Depends(get_current_user)):
    if not user or user.global_role != "super_admin":
        raise HTTPException(status_code=403, detail="Accès admin stockage requis")
    return user

def get_dir_size(path):
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(): total += entry.stat().st_size
            elif entry.is_dir(): total += get_dir_size(entry.path)
    except: pass
    return total

@router.get("/stats", dependencies=[Depends(require_super_admin)])
def get_global_storage_stats():
    """Donne une vue d'ensemble de l'utilisation du disque."""
    if not os.path.exists(STORAGE_ROOT): return {"error": "Root missing"}
    
    total, used, free = shutil.disk_usage(STORAGE_ROOT)
    app_usage = get_dir_size(STORAGE_ROOT)
    
    return {
        "disk_total_gb": total // (2**30),
        "disk_free_gb": free // (2**30),
        "app_usage_mb": round(app_usage / (2**20), 2),
        "projects_folders": len([d for d in os.listdir(STORAGE_ROOT) if os.path.isdir(os.path.join(STORAGE_ROOT, d))])
    }

@router.get("/audit", dependencies=[Depends(require_super_admin)])
def storage_audit(db: Session = Depends(get_db)):
    """Identifie les dossiers qui ne sont plus reliés à rien en base de données."""
    if not os.path.exists(STORAGE_ROOT): return []

    # Liste des IDs valides (Projets et Users pour le mode session)
    known_project_ids = {p.id for p in db.query(Project).all()}
    known_user_uids = {u.firebase_uid for u in db.query(User).all()}
    
    audit_results = []
    for folder_name in os.listdir(STORAGE_ROOT):
        folder_path = os.path.join(STORAGE_ROOT, folder_name)
        if not os.path.isdir(folder_path): continue
        
        status = "active"
        if folder_name not in known_project_ids and folder_name not in known_user_uids:
            status = "orphan" # Dossier inutile
            
        audit_results.append({
            "folder": folder_name,
            "size_mb": round(get_dir_size(folder_path) / (2**20), 2),
            "status": status
        })
    return audit_results
