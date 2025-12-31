
import os
import json
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker
from ..guest_guard import check_guest_restrictions
from app.calculations import loadflow_calculator
from app.schemas.loadflow_schema import LoadflowSettings

router = APIRouter(prefix="/loadflow", tags=["Loadflow Analysis"])

# --- HELPER: Resolve Directory (Copied logic from files.py for stability) ---
def get_analysis_path(user, project_id: Optional[str], db: Session, action: str = "read"):
    # CAS 1 : PROJET
    if project_id:
        # On vérifie les permissions (Viewer suffit pour Read/Run, Editor pour Save)
        role_req = "editor" if action == "write" else "viewer"
        checker = ProjectAccessChecker(required_role=role_req)
        checker(project_id, user, db)
        
        project_dir = os.path.join("/app/storage", project_id)
        if not os.path.exists(project_dir):
            raise HTTPException(404, "Project directory not found")
        return project_dir

    # CAS 2 : SESSION / GUEST
    else:
        uid = user.firebase_uid
        is_guest = False 
        try:
            if user.email is None or user.email == "": is_guest = True
        except: pass
        
        # Pour le calcul, on considère ça comme du "read" (accès au dossier), 
        # le save vérifie "write"
        return check_guest_restrictions(uid, is_guest, action="read")

# --- HELPER: Load Files into Memory ---
def load_directory_content(path: str) -> Dict[str, bytes]:
    files_content = {}
    if not os.path.exists(path):
        return files_content
        
    for f in os.listdir(path):
        full_path = os.path.join(path, f)
        if os.path.isfile(full_path):
            # On ne charge que les extensions utiles pour éviter de saturer la RAM
            ext = f.lower().split('.')[-1]
            if ext in ['json', 'si2s', 'lf1s', 'mdb']:
                try:
                    with open(full_path, "rb") as file_obj:
                        files_content[f] = file_obj.read()
                except Exception as e:
                    print(f"[Warning] Failed to read {f}: {e}")
    return files_content

# --- HELPER: Parse Config ---
def extract_settings(files: Dict[str, bytes]) -> LoadflowSettings:
    # Cherche config.json ou un fichier qui ressemble
    config_content = files.get("config.json")
    
    # Fallback: cherche n'importe quel json qui contient 'loadflow_settings'
    if not config_content:
        for name, content in files.items():
            if name.endswith(".json"):
                try:
                    data = json.loads(content)
                    if "loadflow_settings" in data:
                        config_content = content
                        break
                except: pass
    
    if not config_content:
        raise HTTPException(400, "config.json not found in workspace")
        
    try:
        data = json.loads(config_content)
        # Gestion de la structure (parfois settings.loadflow ou root.loadflow_settings)
        settings_dict = data.get("loadflow_settings")
        if not settings_dict:
             raise ValueError("Missing 'loadflow_settings' key")
        return LoadflowSettings(**settings_dict)
    except Exception as e:
        raise HTTPException(422, f"Invalid Config Format: {str(e)}")

# --- ROUTES ---

@router.post("/run")
async def run(
    format: str = "json", 
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Identifier le dossier cible
    target_dir = get_analysis_path(user, project_id, db, action="read")
    
    # 2. Charger les fichiers en RAM
    files_map = load_directory_content(target_dir)
    if not files_map:
        raise HTTPException(400, "Workspace is empty")

    # 3. Extraire la config
    settings = extract_settings(files_map)
    
    # 4. Lancer le calcul
    # Note: analyze_loadflow attend un dict {filename: bytes}
    try:
        results = loadflow_calculator.analyze_loadflow(files_map, settings, only_winners=False)
        return results
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Calculation Engine Error: {str(e)}")

@router.post("/run-and-save")
async def run_save(
    basename: str = "lf_res", 
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Identifier le dossier (Besoin de Write pour sauvegarder)
    target_dir = get_analysis_path(user, project_id, db, action="write")
    
    # 2. Charger les fichiers
    files_map = load_directory_content(target_dir)
    if not files_map:
        raise HTTPException(400, "Workspace is empty")

    # 3. Extraire config & Calculer
    settings = extract_settings(files_map)
    try:
        results = loadflow_calculator.analyze_loadflow(files_map, settings, only_winners=False)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Calculation Engine Error: {str(e)}")
    
    # 4. Sauvegarder le résultat sur le disque
    output_filename = f"{basename}.json"
    output_path = os.path.join(target_dir, output_filename)
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(jsonable_encoder(results), f, indent=2, default=str)
    except Exception as e:
        raise HTTPException(500, f"Failed to save results: {str(e)}")
    
    return {"status": "saved", "files": [output_filename], "path": output_path}
