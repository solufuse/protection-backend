
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
async def analyze_topology(
    project_id: Optional[str] = Query(None), 
    user=Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    Analyzes the topology of a project by reading iConnect data from relevant files.
    It scans the user's session or project workspace for database files,
    extracts the 'iConnect' sheet, and returns the structured topology data.
    """
    # Determine the correct storage path (user session or project folder)
    target_path = get_storage_path(user, project_id, db)
    # Load all files from that path
    files = load_workspace_files(target_path)
    if not files:
        raise HTTPException(status_code=404, detail="No files found in the workspace.")

    all_results = []
    # Iterate through each file in the workspace
    for filename, content in files.items():
        # Process only if it's a recognized database file
        if is_database_file(filename):
            # Use the setup script to extract topology from the iConnect tab
            result = topology_setup.extract_topology_from_iconnect(content)
            # If successful, add the findings to our results list
            if result.get("status") == "success":
                all_results.append({
                    "file": filename,
                    "topology": result.get("data", [])
                })

    # If no topology data was found in any file, raise an error
    if not all_results:
        raise HTTPException(
            status_code=404, 
            detail="No topology data could be extracted. Check for valid .SI2S or .LF1S files with an 'iConnect' tab."
        )

    # Return the successful results
    return {"status": "success", "results": all_results}
