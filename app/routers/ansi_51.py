
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations.ansi_code import ansi_51
import json, io

router = APIRouter(prefix="/ansi_51", tags=["ANSI 51"])

def get_config(target_id: str, is_project: bool) -> ProjectConfig:
    files = session_manager.get_files(target_id, is_project)
    if not files: raise HTTPException(400, "Session is empty.")
    tgt = files.get("config.json")
    if not tgt:
        for n, c in files.items():
            if n.lower().endswith(".json"): tgt = c; break
    if not tgt: raise HTTPException(404, "No config.json found.")
    try:
        txt = tgt.decode('utf-8') if isinstance(tgt, bytes) else tgt
        return ProjectConfig(**json.loads(txt))
    except Exception as e: raise HTTPException(422, f"Invalid Config: {e}")

@router.post("/run")
async def run_ansi_51_only(
    include_data: bool = Query(False),
    token: str = Depends(get_current_token),
    project_id: str = Query(None)
):
    target, is_proj = (project_id, True) if project_id else (token, False)
    if is_proj and not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied")

    config = get_config(target, is_proj)
    # Update: passing is_project flag to logic (logic file needs update too)
    full_results = ansi_51.run_batch_logic(config, target, is_proj)
    
    final_results = []
    for r in full_results:
        r_copy = r.copy()
        if not include_data:
            if "data_si2s" in r_copy: r_copy["data_si2s"] = "Hidden"
            if "common_data" in r_copy:
                ds = r_copy["common_data"].copy()
                ds.pop("raw_data_from", None)
                ds.pop("raw_data_to", None)
                r_copy["common_data"] = ds
        final_results.append(r_copy)

    return {"status": "success", "total_scenarios": len(final_results), "results": final_results}

@router.get("/export")
async def export_ansi_51(
    format: str = Query("xlsx", pattern="^(xlsx|json)$"),
    token: str = Depends(get_current_token),
    project_id: str = Query(None)
):
    target, is_proj = (project_id, True) if project_id else (token, False)
    if is_proj and not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied")

    config = get_config(target, is_proj)
    results = ansi_51.run_batch_logic(config, target, is_proj)
    
    if format == "json":
        return JSONResponse({"results": results}, headers={"Content-Disposition": "attachment; filename=ansi_51.json"})
    
    return StreamingResponse(
        io.BytesIO(ansi_51.generate_excel(results)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ansi_51.xlsx"}
    )
