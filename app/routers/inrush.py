
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Query
from app.schemas.inrush_schema import InrushRequest, GlobalInrushResponse
from app.calculations import inrush_calculator
from app.core.security import get_current_token
from app.services import session_manager
import json
from typing import Optional

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

def get_config(target, is_proj) -> InrushRequest:
    files = session_manager.get_files(target, is_proj)
    if not files: raise HTTPException(400, "Empty")
    tgt = files.get("config.json")
    if not tgt:
        for n, c in files.items():
            if n.lower().endswith(".json"): tgt = c; break
    if not tgt: raise HTTPException(404, "No config")
    try: return InrushRequest(**json.loads(tgt))
    except: raise HTTPException(422, "Invalid Config")

@router.post("/calculate", response_model=GlobalInrushResponse)
async def calculate_via_session(token: str = Depends(get_current_token), project_id: Optional[str] = Query(None)):
    target, is_proj = (project_id, True) if project_id else (token, False)
    if is_proj and not session_manager.can_access_project(token, project_id): raise HTTPException(403, "Access Denied")

    req = get_config(target, is_proj)
    if not req.transformers: raise HTTPException(400, "List empty")
    data = inrush_calculator.process_inrush_request(req.transformers)
    return {"status": "success", "source": "session", "count": len(data["details"]), "summary": data["summary"], "details": data["details"]}

@router.post("/calculate-json", response_model=GlobalInrushResponse)
async def calculate_via_json(request: InrushRequest, token: str = Depends(get_current_token)):
    # JSON body doesn't depend on storage
    data = inrush_calculator.process_inrush_request(request.transformers)
    return {"status": "success", "source": "json", "count": len(data["details"]), "summary": data["summary"], "details": data["details"]}

@router.post("/calculate-config", response_model=GlobalInrushResponse)
async def calculate_via_upload(file: UploadFile = File(...), token: str = Depends(get_current_token)):
    try:
        content = await file.read()
        req = InrushRequest(**json.loads(content))
    except: raise HTTPException(422, "Invalid File")
    data = inrush_calculator.process_inrush_request(req.transformers)
    return {"status": "success", "source": "upload", "count": len(data["details"]), "summary": data["summary"], "details": data["details"]}
