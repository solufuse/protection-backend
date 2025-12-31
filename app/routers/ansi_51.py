
import os
import json
import io
import pandas as pd
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from app.schemas.protection import ProjectConfig
from app.calculations.ansi_code import ansi_51
from app.calculations import db_converter, topology_manager

from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker
from ..guest_guard import check_guest_restrictions

router = APIRouter(prefix="/ansi_51", tags=["ANSI 51"])

# --- [HELPER] Path Resolution V2 (Duplicated for independence) ---
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
    except Exception as e: raise HTTPException(422, f"Invalid Config: {e}")

# --- INTERNAL LOGIC (Replaces legacy library call) ---
def run_batch_internal(config: ProjectConfig, files: Dict[str, bytes]):
    results = []
    
    # 1. Identify Network Files
    net_files = {k: v for k, v in files.items() if k.lower().endswith(('.si2s', '.mdb', '.lf1s'))}
    
    # 2. Process each file
    for fname, content in net_files.items():
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        # Resolve Topology
        topology_manager.resolve_all(config, dfs)
        
        for plan in config.plans:
            # Check if ANSI 51 is active
            if "51" in plan.active_functions or "ANSI 51" in plan.active_functions:
                try:
                    # Calculate
                    res = ansi_51.calculate(plan, config.settings, dfs)
                    results.append({
                        "file": fname,
                        "plan_id": plan.id,
                        "status": "success",
                        "data_51": res
                    })
                except Exception as e:
                    results.append({
                        "file": fname, 
                        "plan_id": plan.id, 
                        "status": "error", 
                        "error": str(e)
                    })
    return results

# --- ROUTES ---

@router.post("/run")
async def run_ansi_51_only(
    include_data: bool = False, 
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Load Data
    path = get_storage_path(user, project_id, db)
    files = load_workspace_files(path)
    if not files: raise HTTPException(400, "Workspace empty")
    
    config = get_config_from_files(files)
    
    # 2. Run Calculation (Internal V2 Logic)
    final_results = run_batch_internal(config, files)

    return {"status": "success", "total_scenarios": len(final_results), "results": final_results}

@router.get("/export")
async def export_ansi_51(
    format: str = "xlsx", 
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Load Data
    path = get_storage_path(user, project_id, db)
    files = load_workspace_files(path)
    config = get_config_from_files(files)
    
    # 2. Calculate
    results = run_batch_internal(config, files)
    
    # 3. Export
    if format == "json":
        return JSONResponse(
            {"results": results}, 
            headers={"Content-Disposition": "attachment; filename=ansi_51.json"}
        )
    
    # Generate Excel (Assuming library has this helper, if not we catch error)
    try:
        excel_bytes = ansi_51.generate_excel(results)
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=ansi_51.xlsx"}
        )
    except AttributeError:
        # Fallback if library missing generate_excel
        return JSONResponse({"error": "Excel export not available in this version"}, status_code=501)
