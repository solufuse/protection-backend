
import os
import json
import copy
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_token
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
from app.calculations.ansi_code import common as common_lib
from app.calculations.file_utils import is_protection_file

from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker
from ..guest_guard import check_guest_restrictions

router = APIRouter(prefix="/common", tags=["Common Analysis"])

def get_storage_path(user, project_id: Optional[str], db: Session) -> str:
    if project_id:
        checker = ProjectAccessChecker(required_role="viewer")
        checker(project_id, user, db)
        path = os.path.join("/app/storage", project_id)
        if not os.path.exists(path): raise HTTPException(404, "Project folder missing")
        return path
    else:
        uid = user.firebase_uid
        is_guest = False
        try: 
            if not user.email: is_guest = True
        except: pass
        return check_guest_restrictions(uid, is_guest, action="read")

def load_workspace_files(path: str) -> Dict[str, bytes]:
    files = {}
    if not os.path.exists(path): return files
    for f in os.listdir(path):
        full_path = os.path.join(path, f)
        if os.path.isfile(full_path):
            try:
                with open(full_path, "rb") as file_obj:
                    files[f] = file_obj.read()
            except: pass
    return files

def get_config_from_files(files: Dict[str, bytes]) -> ProjectConfig:
    tgt = files.get("config.json")
    if not tgt:
        for n, c in files.items():
            if n.lower().endswith(".json"): tgt = c; break
    if not tgt: raise HTTPException(404, "No config.json found")
    try: return ProjectConfig(**json.loads(tgt))
    except Exception as e: raise HTTPException(422, f"Invalid Config: {str(e)}")

@router.post("/run")
async def run(include_data: bool = False, project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    target_path = get_storage_path(user, project_id, db)
    files = load_workspace_files(target_path)
    if not files: raise HTTPException(400, "Workspace empty")

    config = get_config_from_files(files)
    global_tx = common_lib.build_global_transformer_map(files)
    results = []
    
    for fname, content in files.items():
        if not is_protection_file(fname): continue
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        fconfig = copy.deepcopy(config)
        topology_manager.resolve_all(fconfig, dfs)
        
        for plan in fconfig.plans:
            try:
                data = common_lib.get_electrical_parameters(plan, fconfig, dfs, global_tx)
                if not include_data:
                    data.pop("raw_data_from", None); data.pop("raw_data_to", None)
                results.append({"plan_id": plan.id, "file": fname, "common_data": data})
            except Exception as e:
                results.append({"plan_id": plan.id, "file": fname, "error": str(e)})
    return {"status": "success", "results": results}
