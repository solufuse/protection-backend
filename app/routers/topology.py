
import os
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.calculations import topology_setup
from app.calculations.file_utils import is_database_file
from ..database import get_db
from ..auth import get_current_user
from .common import get_storage_path, load_workspace_files

router = APIRouter(prefix="/topology", tags=["Topology Analysis"])

@router.post("/analyze")
async def analyze_topology_endpoint(
    project_id: Optional[str] = Query(None),
    file_type: Literal['all', 'si2s', 'lf1s'] = Query(
        'all', 
        description="Specify the type of file to analyze: 'si2s', 'lf1s', or 'all'."
    ),
    user=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    Analyzes the topology of a project, including incomer and transformer detection.
    The analysis can be filtered by file type.
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
            all_results.append({
                "file": filename,
                "analysis": result
            })

    if processed_files_count == 0:
        raise HTTPException(
            status_code=404, 
            detail=f"No files of type '{file_type}' found in the workspace."
        )

    if not all_results:
        raise HTTPException(
            status_code=404, 
            detail=f"No topology data could be extracted from the processed {file_type} files. Check for valid data tables."
        )

    return {"status": "success", "results": all_results}
