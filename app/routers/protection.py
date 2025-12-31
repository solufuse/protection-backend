
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
from app.calculations.ansi_code import common as common_lib
from app.routers import ansi_51 as ansi_51_router
from app.routers import common as common_router
from app.calculations.file_utils import is_protection_file

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

def extract_data_from_memory(files: Dict[str, bytes]) -> Dict[str, pd.DataFrame]:
    merged = {}
    for f, content in files.items():
        if is_protection_file(f):
            try:
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

def load_config_from_files(files: Dict[str, bytes]) -> ProjectConfig:
    tgt = files.get("config.json")
    if not tgt:
        for n, c in files.items():
            if n.lower().endswith(".json") and "lf_results" not in n:
                tgt = c; break
    
    if not tgt: raise HTTPException(404, "config.json not found")
    
    try:
        return ProjectConfig(**json.loads(tgt))
    except Exception as e:
        raise HTTPException(422, f"Config Error: {str(e)}")

@router.post("/run")
async def run_global(
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_dir = resolve_protection_path(user, project_id, db)
    
    # 1. Load Data
    files = load_workspace_files(target_dir)
    if not files: raise HTTPException(400, "Workspace empty")

    # 2. Context
    config = load_config_from_files(files)
    global_tx_map = common_lib.build_global_transformer_map(files)
    
    # 3. DataFrames
    dfs = extract_data_from_memory(files)
    
    # 4. Calculate
    config_updated = topology_manager.resolve_all(config, dfs)
    
    results = []
    for plan in config_updated.plans:
        res = {"plan_id": plan.id, "ansi_results": {}}
        for func in plan.active_functions:
            if func in AVAILABLE_ANSI_MODULES:
                try:
                    # [CRITICAL FIX] Pass 'config' (ProjectConfig) and 'global_tx_map'
                    res["ansi_results"][func] = AVAILABLE_ANSI_MODULES[func].calculate(
                        plan, config, dfs, global_tx_map
                    )
                except TypeError:
                    # Fallback au cas où un autre module n'est pas encore à jour
                    res["ansi_results"][func] = AVAILABLE_ANSI_MODULES[func].calculate(
                        plan, config.settings, dfs
                    )
                except Exception as e: 
                    res["ansi_results"][func] = {"error": str(e)}
        results.append(res)
        
    return {"status": "success", "results": results}
