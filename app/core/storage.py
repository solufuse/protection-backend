
import os
from typing import Optional
from sqlalchemy.orm import Session
from ..models import User
from ..auth import ProjectAccessChecker

STORAGE_ROOT = "/app/storage"

def get_target_path(user: User, project_id: Optional[str], db: Session, action: str = "read") -> str:
    """
    Determines the root storage directory based on Project ID or User Session.
    Verifies permissions via ProjectAccessChecker if a project is targeted.
    Returns the absolute path to the target directory.
    """
    if project_id:
        # Admins and moderators have direct access, otherwise check project membership.
        if user.global_role not in ["super_admin", "admin", "moderator"]:
            checker = ProjectAccessChecker(required_role="viewer" if action == "read" else "editor")
            checker(project_id, user, db)
            
        target_dir = os.path.join(STORAGE_ROOT, project_id)
    else:
        # User's private session directory for personal files.
        target_dir = os.path.join(STORAGE_ROOT, user.firebase_uid)

    # Create the directory if it doesn't exist.
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        
    return target_dir
