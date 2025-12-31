
import os
import json
import pandas as pd
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_token
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
from app.calculations.ansi_code import AVAILABLE_ANSI_MODULES
from app.routers import ansi_51 as ansi_51_router
from app.routers import common as common_router
from app.calculations.file_utils import is_protection_file # [UPDATED IMPORT]

from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker
from ..guest_guard import check_guest_restrictions

router = APIRouter(prefix="/protection", tags=["Protection Coordination (PC)"])
router.include_router(ansi_51_router.router)
router.include_router(common_router.router)

def resolve_protection_path(user, project_id: Optional[str], db: Session) -> str:
    if project_id:
        checker = ProjectAccessChecker(required_role="viewer")
        checker(project_id, user, db)
        path = os.path.join("/app/storage", project_id)
        if not os.path.exists(path): raise HTTPException(404, "Project directory missing")
        return path
    else:
        uid = user.firebase_uid
        is_guest = False
        try: 
            if not user.email: is_guest = True
        except: pass
        return check_guest_restrictions(uid, is_guest, action="read")

def load_data_from_disk(path: str) -> Dict[str, pd.DataFrame]:
    merged = {}
    if not os.path.exists(path): return {}
    
    for f in os.listdir(path):
        # [USE CENTRAL FILTER]
        if is_protection_file(f):
            full_path = os.path.join(path, f)
            try:
                with open(full_path, "rb") as file_obj:
                    content = file_obj.read()
                
                dfs = db_converter.extract_data_from_db(content)
                if dfs:
                    for t, df in dfs.items():
                        if t not in merged: merged[t] = []
                        df['SourceFilename'] = f 
                        merged[t].append(df)
            except Exception as e:
                print(f"[Warn] Skipped {f}: {e}")

    final = {}
    for k, v in merged.items():
        try: final[k] = pd.concat(v, ignore_index=True)
        except: final[k] = v[0]
    return final

def load_config_from_disk(path: str) -> ProjectConfig:
    config_path = os.path.join(path, "config.json")
    if not os.path.exists(config_path):
        for f in os.listdir(path):
            if f.endswith(".json") and "lf_results" not in f:
                config_path = os.path.join(path, f)
                break
    
    if not os.path.exists(config_path):
        raise HTTPException(404, "config.json not found in workspace")
        
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        return ProjectConfig(**data)
    except Exception as e:
        raise HTTPException(422, f"Config Error: {str(e)}")

@router.post("/run")
async def run_global(
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = resolve_protection_path(user, project_id, db)
    config = load_config_from_disk(target_dir)
    dfs = load_data_from_disk(target_dir)
    
    config_updated = topology_manager.resolve_all(config, dfs)
    
    results = []
    for plan in config_updated.plans:
        res = {"plan_id": plan.id, "ansi_results": {}}
        for func in plan.active_functions:
            if func in AVAILABLE_ANSI_MODULES:
                try: 
                    res["ansi_results"][func] = AVAILABLE_ANSI_MODULES[func].calculate(plan, config.settings, dfs)
                except Exception as e: 
                    res["ansi_results"][func] = {"error": str(e)}
        results.append(res)
        
    return {"status": "success", "results": results}
