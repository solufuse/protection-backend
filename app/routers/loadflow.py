
import os
import json
import datetime
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker
from ..guest_guard import check_guest_restrictions
from app.calculations import loadflow_calculator
from app.schemas.loadflow_schema import LoadflowSettings
from app.calculations.file_utils import is_loadflow_file

router = APIRouter(prefix="/loadflow", tags=["Loadflow Analysis"])

def get_analysis_path(user, project_id: Optional[str], db: Session, action: str = "read"):
    if project_id:
        role_req = "editor" if action == "write" else "viewer"
        checker = ProjectAccessChecker(required_role=role_req)
        checker(project_id, user, db)
        project_dir = os.path.join("/app/storage", project_id)
        if not os.path.exists(project_dir): raise HTTPException(404, "Project directory not found")
        return project_dir
    else:
        uid = user.firebase_uid
        is_guest = False 
        try:
            if user.email is None or user.email == "": is_guest = True
        except: pass
        return check_guest_restrictions(uid, is_guest, action="read")

def load_directory_content(path: str) -> Dict[str, bytes]:
    files_content = {}
    if not os.path.exists(path): return files_content
    for f in os.listdir(path):
        full_path = os.path.join(path, f)
        if os.path.isfile(full_path):
            if is_loadflow_file(f) or f.endswith('.json'):
                try:
                    with open(full_path, "rb") as file_obj:
                        files_content[f] = file_obj.read()
                except: pass
    return files_content

def extract_settings(files: Dict[str, bytes]) -> LoadflowSettings:
    config_content = files.get("config.json")
    if not config_content:
        for name, content in files.items():
            if name.endswith(".json"):
                try:
                    data = json.loads(content)
                    if "loadflow_settings" in data:
                        config_content = content; break
                except: pass
    if not config_content: raise HTTPException(400, "config.json not found")
    try:
        data = json.loads(config_content)
        settings_dict = data.get("loadflow_settings")
        if not settings_dict: raise ValueError("Missing 'loadflow_settings'")
        return LoadflowSettings(**settings_dict)
    except Exception as e: raise HTTPException(422, f"Invalid Config: {str(e)}")

@router.post("/run")
async def run(format: str = "json", project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    target_dir = get_analysis_path(user, project_id, db, action="read")
    files_map = load_directory_content(target_dir)
    if not files_map: raise HTTPException(400, "Workspace is empty")
    settings = extract_settings(files_map)
    try: return loadflow_calculator.analyze_loadflow(files_map, settings, only_winners=False)
    except Exception as e: raise HTTPException(500, f"Calculation Error: {str(e)}")

@router.post("/run-and-save")
async def run_save(basename: str = "lf_res", project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Run loadflow analysis and archive the result in a 'loadflow_results' subfolder.
    Includes validation for filename length and timestamp generation.
    """
    # 1. Validation (Max 20 chars)
    if len(basename) > 20:
        raise HTTPException(400, "Basename too long (max 20 characters).")
    
    # 2. Basic cleaning to prevent path injection
    safe_basename = "".join([c for c in basename if c.isalnum() or c in ('-', '_')])
    if not safe_basename: safe_basename = "result"
    
    # 3. Get Base Directory (Project or Session)
    target_dir = get_analysis_path(user, project_id, db, action="write")
    
    # 4. Load Files & Calculate
    files_map = load_directory_content(target_dir)
    if not files_map: raise HTTPException(400, "Workspace is empty")
    
    settings = extract_settings(files_map)
    try: 
        results = loadflow_calculator.analyze_loadflow(files_map, settings, only_winners=False)
    except Exception as e: 
        raise HTTPException(500, f"Calculation Error: {str(e)}")
    
    # 5. Archive Logic: Create folder and generate Timestamped filename
    # [structure:storage] Isolate results in 'loadflow_results' to keep root clean
    archive_dir = os.path.join(target_dir, "loadflow_results")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_basename}_{timestamp}.json"
    output_path = os.path.join(archive_dir, filename)
    
    # 6. Save File
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(jsonable_encoder(results), f, indent=2, default=str)
        
    return {
        "status": "saved", 
        "folder": "loadflow_results",
        "filename": filename,
        "full_path": f"/loadflow_results/{filename}"
    }
