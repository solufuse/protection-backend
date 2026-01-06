
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

# Import the new topology analysis module
from app.calculations import topology_setup
# Utility to check if a file is a database file (.SI2S, .LF1S, etc.)
from app.calculations.file_utils import is_database_file
from ..database import get_db
from ..auth import get_current_user
# Import common utilities for file and workspace handling
from .common import get_storage_path, load_workspace_files

# Define a new router for topology-related endpoints
router = APIRouter(prefix="/topology", tags=["Topology Analysis"])

@router.post("/analyze")
async def analyze_topology_endpoint(
    project_id: Optional[str] = Query(None), 
    user=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    Analyzes the topology of a project, including incomer detection,
    by reading iConnect and other relevant data from database files.
    """
    target_path = get_storage_path(user, project_id, db)
    files = load_workspace_files(target_path)
    if not files:
        raise HTTPException(status_code=404, detail="No files found in the workspace.")

    all_results = []
    for filename, content in files.items():
        if is_database_file(filename):
            # Pass both content and filename to the new analysis function
            result = topology_setup.analyze_topology(content, filename)
            if result.get("status") == "success":
                all_results.append({
                    "file": filename,
                    "analysis": result
                })

    if not all_results:
        raise HTTPException(
            status_code=404, 
            detail="No topology data could be extracted. Check for valid .SI2S or .LF1S files."
        )

    return {"status": "success", "results": all_results}
