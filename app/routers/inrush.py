from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from app.schemas.inrush_schema import InrushRequest, GlobalInrushResponse
from app.calculations import inrush_calculator
from app.core.security import get_current_token
from app.services import session_manager
import json

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

# --- HELPER (With Robust Logic V2) ---
def get_config_from_session(token: str) -> InrushRequest:
    files = session_manager.get_files(token)
    if not files:
        raise HTTPException(status_code=400, detail="Empty session. Please upload a config.json.")
    
    target_content = None
    if "config.json" in files:
        target_content = files["config.json"]
    else:
        for name, content in files.items():
            if name.lower().endswith(".json"):
                target_content = content
                break
    
    if target_content is None:
        raise HTTPException(status_code=404, detail="No 'config.json' found in session.")

    try:
        # Decode Bytes -> String
        if isinstance(target_content, bytes):
            text_content = target_content.decode('utf-8')
        else:
            text_content = target_content
        
        # Pydantic V2 handles the rest thanks to the permissive schema we set up
        data = json.loads(text_content)
        return InrushRequest(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid Session JSON: {e}")

# --- 1. VIA SESSION DATA ---
@router.post("/calculate", response_model=GlobalInrushResponse)
async def calculate_via_session(token: str = Depends(get_current_token)):
    """
    Calculation using 'config.json' stored in RAM Session.
    """
    request = get_config_from_session(token)
    
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Empty list in config.json.")

    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "source": "session_data",
        "count": len(data["details"]),
        "summary": data["summary"],
        "details": data["details"]
    }

# --- 2. VIA JSON BODY ---
@router.post("/calculate-json", response_model=GlobalInrushResponse)
async def calculate_via_json(
    request: InrushRequest, 
    token: str = Depends(get_current_token)
):
    """
    Calculation by sending configuration in request Body.
    """
    if not request.transformers:
        raise HTTPException(status_code=400, detail="Empty list.")
        
    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "source": "json_body",
        "count": len(data["details"]),
        "summary": data["summary"],
        "details": data["details"]
    }

# --- 3. VIA FILE UPLOAD (Config Download) ---
@router.post("/calculate-config", response_model=GlobalInrushResponse)
async def calculate_via_file_upload(
    file: UploadFile = File(...),
    token: str = Depends(get_current_token)
):
    """
    Calculation by uploading a specific 'config.json' for this run.
    """
    try:
        content = await file.read()
        text_content = content.decode('utf-8')
        data_json = json.loads(text_content)
        request = InrushRequest(**data_json)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid file: {e}")

    data = inrush_calculator.process_inrush_request(request.transformers)
    
    return {
        "status": "success",
        "source": "file_upload",
        "count": len(data["details"]),
        "summary": data["summary"],
        "details": data["details"]
    }
