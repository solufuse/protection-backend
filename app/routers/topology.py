
import os
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.calculations import topology_setup, topology_graph
from app.calculations.file_utils import is_database_file
from ..database import get_db
from ..auth import get_current_user
from .common import get_storage_path, load_workspace_files

router = APIRouter(prefix="/topology", tags=["Topology Analysis"])

ANALYSIS_TYPES = Literal['incomer', 'bus', 'transformer', 'cable', 'coupling', 'incomer_breaker']

class FileListPayload(BaseModel):
    filenames: List[str]

@router.post("/analyze")
async def analyze_topology_endpoint(
    project_id: Optional[str] = Query(None),
    file_type: Literal['all', 'si2s', 'lf1s'] = Query('all'),
    analysis_types: Optional[List[ANALYSIS_TYPES]] = Query(None),
    user=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    Analyzes project topology for all files, identifying key components.
    """
    target_path = get_storage_path(user, project_id, db)
    files = load_workspace_files(target_path)
    if not files:
        raise HTTPException(status_code=404, detail="No files found in the workspace.")

    all_results = []
    processed_files_count = 0
    for filename, content in files.items():
        if not is_database_file(filename):
            continue

        file_ext = filename.lower().split('.')[-1]
        if file_type != 'all' and file_ext != file_type:
            continue

        processed_files_count += 1
        result = topology_setup.analyze_topology(content, filename)
        
        if result.get("status") == "success":
            if analysis_types:
                filtered_analysis = {key: val for key, val in result.items() if key.replace('_analysis', '') in analysis_types or key in ['status', 'message', 'topology']}
                for atype in analysis_types:
                    if f'{atype}_analysis' not in filtered_analysis:
                        filtered_analysis[f'{atype}_analysis'] = []
                all_results.append({"file": filename, "analysis": filtered_analysis})
            else:
                all_results.append({"file": filename, "analysis": result})

    if processed_files_count == 0:
        raise HTTPException(status_code=404, detail=f"No files of type '{file_type}' found.")
    if not all_results:
        raise HTTPException(status_code=404, detail=f"No topology data could be extracted from processed '{file_type}' files.")

    return {"status": "success", "results": all_results}

@router.get("/diagram/single/{filename:path}")
async def get_single_diagram(
    filename: str,
    project_id: Optional[str] = Query(None),
    user=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    Generates a topology diagram for a single specified file.
    """
    target_path = get_storage_path(user, project_id, db)
    
    # We use load_workspace_files and then pick the one we want.
    # This is simpler than crafting a single file path.
    files = load_workspace_files(target_path)
    content = files.get(filename)

    if content is None:
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in the project.")

    analysis_result = topology_setup.analyze_topology(content, filename)
    if analysis_result.get("status") != "success":
        raise HTTPException(status_code=400, detail=f"Could not analyze topology for {filename}.")
        
    diagram = topology_graph.build_diagram(analysis_result)
    return {"file": filename, "diagram": diagram}

@router.post("/diagram/bulk")
async def get_bulk_diagrams(
    payload: FileListPayload,
    project_id: Optional[str] = Query(None),
    user=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    Generates topology diagrams for a specific list of files.
    """
    target_path = get_storage_path(user, project_id, db)
    files = load_workspace_files(target_path)
    
    all_diagrams = []
    for filename in payload.filenames:
        content = files.get(filename)
        if content is None:
            # You might want to collect these errors instead of failing all
            continue 

        analysis_result = topology_setup.analyze_topology(content, filename)
        if analysis_result.get("status") == "success":
            diagram = topology_graph.build_diagram(analysis_result)
            all_diagrams.append({"file": filename, "diagram": diagram})

    if not all_diagrams:
        raise HTTPException(status_code=404, detail="Could not generate any diagrams for the specified files.")

    return {"status": "success", "results": all_diagrams}

@router.get("/diagram/all")
async def get_all_diagrams(
    project_id: Optional[str] = Query(None),
    file_type: Literal['all', 'si2s', 'lf1s'] = Query('all'),
    user=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    Generates topology diagrams for all project files, with optional type filtering.
    """
    target_path = get_storage_path(user, project_id, db)
    files = load_workspace_files(target_path)
    if not files:
        raise HTTPException(status_code=404, detail="No files found in the workspace.")

    all_diagrams = []
    for filename, content in files.items():
        if not is_database_file(filename):
            continue

        file_ext = filename.lower().split('.')[-1]
        if file_type != 'all' and file_ext != file_type:
            continue

        analysis_result = topology_setup.analyze_topology(content, filename)
        if analysis_result.get("status") == "success":
            diagram = topology_graph.build_diagram(analysis_result)
            all_diagrams.append({"file": filename, "diagram": diagram})

    if not all_diagrams:
        raise HTTPException(status_code=404, detail="Could not generate any diagrams.")

    return {"status": "success", "results": all_diagrams}
