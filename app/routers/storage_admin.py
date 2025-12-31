
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Project
from ..auth import get_current_user

router = APIRouter()
STORAGE_ROOT = "/app/storage"

# AI-REMARK: DROITS DE STOCKAGE
# Seul le 'super_admin' peut manipuler les dossiers physiques directement
# pour garantir l'intégrité du serveur.

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
    """ [+] [INFO] Dashboard de santé du disque dur. """
    if not os.path.exists(STORAGE_ROOT): return {"error": "Root missing"}
    
    total, used, free = shutil.disk_usage(STORAGE_ROOT)
    app_usage = get_dir_size(STORAGE_ROOT)
    
    return {
        "disk_total_gb": total // (2**30),
        "disk_free_gb": free // (2**30),
        "app_usage_mb": round(app_usage / (2**20), 2),
        "projects_count": len([d for d in os.listdir(STORAGE_ROOT) if os.path.isdir(os.path.join(STORAGE_ROOT, d))])
    }

@router.get("/audit", dependencies=[Depends(require_super_admin)])
def storage_audit(db: Session = Depends(get_db)):
    """
    [+] [INFO] Analyse de cohérence DB vs Disque.
    [?] [THOUGHT] Identifie les dossiers 'orphan' (orphelins) à supprimer.
    """
    if not os.path.exists(STORAGE_ROOT): return []

    known_project_ids = {p.id for p in db.query(Project).all()}
    known_user_uids = {u.firebase_uid for u in db.query(User).all()}
    
    audit_results = []
    for folder_name in os.listdir(STORAGE_ROOT):
        folder_path = os.path.join(STORAGE_ROOT, folder_name)
        if not os.path.isdir(folder_path): continue
        
        status = "active"
        if folder_name not in known_project_ids and folder_name not in known_user_uids:
            status = "orphan" 
            
        audit_results.append({
            "folder": folder_name,
            "size_mb": round(get_dir_size(folder_path) / (2**20), 2),
            "status": status
        })
    return audit_results

@router.delete("/{folder_id}", dependencies=[Depends(require_super_admin)])
def force_delete_folder(folder_id: str):
    """
    [!] [CRITICAL] Suppression IRREVERSIBLE d'un dossier sur le serveur.
    [ decision:logic] Permet à l'admin de nettoyer le disque de force.
    """
    if ".." in folder_id or folder_id.startswith("/"):
        raise HTTPException(400, "ID de dossier invalide")
        
    target_path = os.path.join(STORAGE_ROOT, folder_id)
    if not os.path.exists(target_path):
        raise HTTPException(404, "Dossier introuvable sur le disque")
        
    try:
        shutil.rmtree(target_path)
        return {"status": "deleted", "path": target_path}
    except Exception as e:
        raise HTTPException(500, f"Erreur de suppression : {str(e)}")
