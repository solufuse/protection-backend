
import os
import json
import datetime
from typing import Optional, List, Literal, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.calculations import topology_setup, topology_graph
from app.calculations.file_utils import is_database_file
from ..database import get_db
from ..auth import get_current_user
from ..core.storage import get_target_path
from .common import load_workspace_files

router = APIRouter(prefix="/topology", tags=["Topology Analysis"])

ANALYSIS_TYPES = Literal['incomer', 'bus', 'transformer', 'cable', 'coupling', 'incomer_breaker']

class FileListPayload(BaseModel):
    filenames: List[str]

async def _run_and_save_topology(
    basename: str,
    files_to_process: Dict[str, bytes],
    target_path: str,
    analysis_types: Optional[List[ANALYSIS_TYPES]] = None
):
    if len(basename) > 20:
        raise HTTPException(400, "Basename too long (max 20 characters).")

    safe_basename = "".join([c for c in basename if c.isalnum() or c in ('-', '_')])
    if not safe_basename: safe_basename = "result"

    all_results = []
    for filename, content in files_to_process.items():
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

    if not all_results:
        raise HTTPException(status_code=404, detail="No topology data could be extracted from the provided files.")

    results_to_save = {"status": "success", "results": all_results}

    archive_dir = os.path.join(target_path, "topology_results")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{safe_basename}_{timestamp}.json"
    output_path = os.path.join(archive_dir, output_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(jsonable_encoder(results_to_save), f, indent=2, default=str)

    return {
        "status": "saved",
        "folder": "topology_results",
        "filename": output_filename,
        "full_path": f"/topology_results/{output_filename}"
    }

async def _build_and_save_diagrams(
    basename: str,
    files_to_process: Dict[str, bytes],
    target_path: str
):
    if len(basename) > 20:
        raise HTTPException(400, "Basename too long (max 20 characters).")
    safe_basename = "".join([c for c in basename if c.isalnum() or c in ('-', '_')])
    if not safe_basename: safe_basename = "diagram_result"

    all_diagrams = []
    for filename, content in files_to_process.items():
        analysis_result = topology_setup.analyze_topology(content, filename)
        if analysis_result.get("status") == "success":
            diagram = topology_graph.build_diagram(analysis_result)
            all_diagrams.append({"file": filename, "diagram": diagram})

    if not all_diagrams:
        raise HTTPException(status_code=404, detail="Could not generate any diagrams for the provided files.")

    results_to_save = {"status": "success", "results": all_diagrams}
    archive_dir = os.path.join(target_path, "diagram_results")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{safe_basename}_{timestamp}.json"
    output_path = os.path.join(archive_dir, output_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(jsonable_encoder(results_to_save), f, indent=2, default=str)

    return {
        "status": "saved",
        "folder": "diagram_results",
        "filename": output_filename,
        "full_path": f"/diagram_results/{output_filename}"
    }

@router.post("/run-and-save/bulk", description="Run analysis on a list of files and save results.")
async def run_save_topology_bulk(
    payload: FileListPayload,
    basename: str = "topo_res_b",
    project_id: Optional[str] = Query(None),
    analysis_types: Optional[List[ANALYSIS_TYPES]] = Query(None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_path = get_target_path(user, project_id, db, action="write")
    files = load_workspace_files(target_path)
    if not files:
        raise HTTPException(status_code=404, detail="No files found in the workspace.")

    files_to_process = {fname: files[fname] for fname in payload.filenames if fname in files}
    if not files_to_process:
        raise HTTPException(status_code=404, detail="None of the specified files were found.")

    return await _run_and_save_topology(basename, files_to_process, target_path, analysis_types)

@router.post("/analyze")
async def analyze_topology_endpoint(
    project_id: Optional[str] = Query(None),
    file_type: Literal['all', 'si2s', 'lf1s'] = Query('all'),
    analysis_types: Optional[List[ANALYSIS_TYPES]] = Query(None),
    user=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    '''
    Analyzes project topology for all files, identifying key components.
    '''
    target_path = get_target_path(user, project_id, db, action="read")
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

@router.post("/diagram/save", description="Generates and saves topology diagrams for a specific list of files.")
async def save_diagrams(
    payload: FileListPayload,
    basename: str = "diag_res_b",
    project_id: Optional[str] = Query(None),
    user=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    target_path = get_target_path(user, project_id, db, action="write")
    files = load_workspace_files(target_path)
    
    files_to_process = {fname: files[fname] for fname in payload.filenames if fname in files}
    if not files_to_process:
        raise HTTPException(status_code=404, detail="None of the specified files were found.")

    return await _build_and_save_diagrams(basename, files_to_process, target_path)
