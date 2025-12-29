from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations.ansi_code import ansi_51
import json
import io

router = APIRouter(prefix="/ansi_51", tags=["ANSI 51"])

def get_config_from_session(token: str) -> ProjectConfig:
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="Session is empty.")
    
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
        if isinstance(target_content, bytes): text_content = target_content.decode('utf-8')
        else: text_content = target_content  
        data = json.loads(text_content)
        return ProjectConfig(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid Config JSON: {e}")

@router.post("/run")
async def run_ansi_51_only(
    include_data: bool = Query(False, description="Set to True to see raw data (si2s dump and raw ETAP rows)"),
    token: str = Depends(get_current_token)
):
    """
    Exécute uniquement le module ANSI 51 (qui inclut le script 'Common').
    URL: POST /protection/ansi_51/run
    """
    config = get_config_from_session(token)
    full_results = ansi_51.run_batch_logic(config, token)
    
    if include_data:
        final_results = full_results
        msg = "Full data included (DB rows & Raw ETAP values)."
    else:
        final_results = []
        for r in full_results:
            r_copy = r.copy()
            # Clean up raw data if present
            if "data_si2s" in r_copy:
                r_copy["data_si2s"] = "Hidden (use include_data=true)"
            
            # [!] FILTERING COMMON DATA
            if "common_data" in r_copy:
                ds = r_copy["common_data"].copy()
                ds.pop("raw_data_from", None)
                ds.pop("raw_data_to", None)
                r_copy["common_data"] = ds
            
            final_results.append(r_copy)
        msg = "Raw data hidden for readability. Use include_data=true to debug."

    return {
        "status": "success", 
        "total_scenarios": len(final_results), 
        "info": msg,
        "results": final_results
    }

@router.get("/export")
async def export_ansi_51(
    format: str = Query("xlsx", pattern="^(xlsx|json)$"),
    token: str = Depends(get_current_token)
):
    """
    Export spécifique ANSI 51.
    URL: GET /protection/ansi_51/export
    """
    config = get_config_from_session(token)
    results = ansi_51.run_batch_logic(config, token)
    
    if format == "json":
        return JSONResponse(
            content={"results": results}, 
            headers={"Content-Disposition": "attachment; filename=ansi_51_full.json"}
        )
    
    excel_bytes = ansi_51.generate_excel(results)
    
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ansi_51_full.xlsx"}
    )
