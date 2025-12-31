
import os
import json
import io
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from app.schemas.protection import ProjectConfig
from app.calculations.ansi_code import ansi_51
from app.calculations import db_converter, topology_manager
from app.calculations.file_utils import is_protection_file  # [UPDATED IMPORT]

from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker
from ..guest_guard import check_guest_restrictions

router = APIRouter(prefix="/ansi_51", tags=["ANSI 51"])

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

def run_batch_internal(config: ProjectConfig, files: Dict[str, bytes]):
    results = []
    
    # [USE CENTRAL FILTER]
    net_files = {k: v for k, v in files.items() if is_protection_file(k)}
    
    for fname, content in net_files.items():
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        topology_manager.resolve_all(config, dfs)
        
        for plan in config.plans:
            if "51" in plan.active_functions or "ANSI 51" in plan.active_functions:
                try:
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

@router.post("/run")
async def run_ansi_51_only(
    include_data: bool = False, 
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    path = get_storage_path(user, project_id, db)
    files = load_workspace_files(path)
    if not files: raise HTTPException(400, "Workspace empty")
    
    config = get_config_from_files(files)
    final_results = run_batch_internal(config, files)

    return {"status": "success", "total_scenarios": len(final_results), "results": final_results}

@router.get("/export")
async def export_ansi_51(
    format: str = "xlsx", 
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    path = get_storage_path(user, project_id, db)
    files = load_workspace_files(path)
    config = get_config_from_files(files)
    results = run_batch_internal(config, files)
    
    if format == "json":
        return JSONResponse({"results": results}, headers={"Content-Disposition": "attachment; filename=ansi_51.json"})
    
    try:
        excel_bytes = ansi_51.generate_excel(results)
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=ansi_51.xlsx"}
        )
    except AttributeError:
        return JSONResponse({"error": "Excel export not available"}, status_code=501)
