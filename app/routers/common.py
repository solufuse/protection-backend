from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
from app.calculations.ansi_code import common as common_lib # Rename to avoid conflict
import json
import copy

# Defines route /protection/common/... when included
router = APIRouter(prefix="/common", tags=["Common Analysis"])

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
async def run_common_parameters(
    include_data: bool = Query(False, description="Set to True to see raw data (si2s dump and raw ETAP rows)"),
    token: str = Depends(get_current_token)
):
    """
    Executes the 'Common' analysis (Electrical Parameters, Inrush, Topology) for all plans.
    Does NOT run specific ANSI codes (50/51/67), only gathers base data.
    URL: POST /protection/common/run
    """
    config = get_config_from_session(token)
    files = session_manager.get_files(token)
    # [context:flow] Build global map of transformers for Inrush calculation
    global_tx_map = common_lib.build_global_transformer_map(files)
    
    results = []
    
    for filename, content in files.items():
        if not common_lib.is_supported_protection(filename): continue
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: continue
        
        # [context:flow] Resolve topology per file to avoid conflicts
        file_config = copy.deepcopy(config)
        topology_manager.resolve_all(file_config, dfs)
        
        for plan in file_config.plans:
            try:
                # [decision:logic] Extract electrical params (In, Ik, Inrush) using common lib
                data_settings = common_lib.get_electrical_parameters(plan, file_config, dfs, global_tx_map)
                
                # [decision:logic] Filter raw data if not requested
                if not include_data:
                    data_settings.pop("raw_data_from", None)
                    data_settings.pop("raw_data_to", None)

                # Basic status check
                status = "ok"
                if data_settings.get("kVnom_busfrom") == 0: status = "warning (kV=0)"

                results.append({
                    "plan_id": plan.id,
                    "plan_type": plan.type,
                    "source_file": filename,
                    "status": status,
                    "topology": {
                        "origin": plan.topology_origin,
                        "bus_from": plan.bus_from,
                        "bus_to": plan.bus_to
                    },
                    "common_data": data_settings
                })
            except Exception as e:
                results.append({
                    "plan_id": plan.id,
                    "source_file": filename,
                    "status": "error",
                    "error": str(e)
                })
                
    return {"status": "success", "count": len(results), "results": results}
