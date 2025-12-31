
import os
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Query
from sqlalchemy.orm import Session

from app.schemas.inrush_schema import InrushRequest, GlobalInrushResponse
from app.calculations import inrush_calculator
from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker
from ..guest_guard import check_guest_restrictions

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

# --- [HELPER] V2 Path Resolution ---
def get_inrush_config(user, project_id: Optional[str], db: Session) -> InrushRequest:
    # 1. Determine Folder
    if project_id:
        checker = ProjectAccessChecker(required_role="viewer")
        checker(project_id, user, db)
        base_dir = os.path.join("/app/storage", project_id)
    else:
        uid = user.firebase_uid
        is_guest = False
        try:
            if not user.email: is_guest = True
        except: pass
        base_dir = check_guest_restrictions(uid, is_guest, action="read")

    if not os.path.exists(base_dir): raise HTTPException(404, "Workspace not found")

    # 2. Find Config File
    config_path = os.path.join(base_dir, "config.json")
    if not os.path.exists(config_path):
        # Search fallback
        found = False
        for f in os.listdir(base_dir):
            if f.endswith(".json"):
                config_path = os.path.join(base_dir, f)
                found = True
                break
        if not found: raise HTTPException(404, "config.json not found")

    # 3. Parse
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        return InrushRequest(**data)
    except Exception as e:
        raise HTTPException(422, f"Invalid Config: {str(e)}")

# --- ROUTES ---

@router.post("/calculate", response_model=GlobalInrushResponse)
async def calculate_via_session(
    project_id: Optional[str] = Query(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # [+] [INFO] Logic: Load config from DISK -> Calculate in RAM -> Return JSON
    req = get_inrush_config(user, project_id, db)
    
    if not req.transformers: 
        raise HTTPException(400, "Transformer list is empty in config")
        
    data = inrush_calculator.process_inrush_request(req.transformers)
    
    return {
        "status": "success", 
        "source": "project" if project_id else "session", 
        "count": len(data["details"]), 
        "summary": data["summary"], 
        "details": data["details"]
    }

@router.post("/calculate-json", response_model=GlobalInrushResponse)
async def calculate_via_json(
    request: InrushRequest, 
    user = Depends(get_current_user)
):
    # Pure calculation, no storage needed
    data = inrush_calculator.process_inrush_request(request.transformers)
    return {"status": "success", "source": "json", "count": len(data["details"]), "summary": data["summary"], "details": data["details"]}

@router.post("/calculate-config", response_model=GlobalInrushResponse)
async def calculate_via_upload(
    file: UploadFile = File(...), 
    user = Depends(get_current_user)
):
    try:
        content = await file.read()
        req = InrushRequest(**json.loads(content))
    except: 
        raise HTTPException(422, "Invalid File or JSON format")
        
    data = inrush_calculator.process_inrush_request(req.transformers)
    return {"status": "success", "source": "upload", "count": len(data["details"]), "summary": data["summary"], "details": data["details"]}
