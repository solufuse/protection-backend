
import os
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.calculations import topology_setup
from app.calculations.file_utils import is_database_file
from ..database import get_db
from ..auth import get_current_user
from .common import get_storage_path, load_workspace_files

router = APIRouter(prefix="/topology", tags=["Topology Analysis"])

ANALYSIS_TYPES = Literal['incomer', 'bus', 'transformer', 'cable', 'coupling', 'incomer_breaker']

@router.post("/analyze")
async def analyze_topology_endpoint(
    project_id: Optional[str] = Query(None),
    file_type: Literal['all', 'si2s', 'lf1s'] = Query(
        'all', 
        description="Filter analysis by file type: 'si2s', 'lf1s', or 'all'."
    ),
    analysis_types: Optional[List[ANALYSIS_TYPES]] = Query(
        None, 
        description="Select specific analysis types to return."
    ),
    user=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    Analyzes project topology, identifying key components. 
    The analysis can be filtered by file type and specific analysis components.
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
            # If specific analysis types are requested, filter the results
            if analysis_types:
                filtered_analysis = {key: val for key, val in result.items() 
                                     if key.replace('_analysis', '') in analysis_types or key in ['status', 'message', 'topology']}
                
                # Ensure that if a requested type is not in the results, it returns an empty list
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
