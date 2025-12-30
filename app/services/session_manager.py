
import os
import shutil
import json
import datetime
from typing import List, Dict, Union

# [context:flow] : Users stay in root /app/storage for compatibility
BASE_USER_DIR = "/app/storage"
# [context:flow] : Projects get their own dedicated subdirectory
BASE_PROJECT_DIR = "/app/storage/projects"
ACCESS_FILE = "access.json"

# --- HELPER INTERNAL ---

def _get_target_dir(target_id: str, is_project: bool) -> str:
    base = BASE_PROJECT_DIR if is_project else BASE_USER_DIR
    path = os.path.join(base, target_id)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

# --- ACL MANAGEMENT (ACCESS CONTROL) ---

def create_project(owner_uid: str, project_id: str) -> bool:
    project_dir = _get_target_dir(project_id, is_project=True)
    access_path = os.path.join(project_dir, ACCESS_FILE)
    
    if os.path.exists(access_path):
        return False

    # [decision:logic] Generate real timestamp
    now_iso = datetime.datetime.now().isoformat()

    access_data = {
        "owner": owner_uid,
        "members": [owner_uid],
        "created_at": now_iso,
        "is_public": False
    }
    
    with open(access_path, 'w') as f:
        json.dump(access_data, f, indent=2)
    return True

def can_access_project(user_uid: str, project_id: str) -> bool:
    project_dir = _get_target_dir(project_id, is_project=True)
    access_path = os.path.join(project_dir, ACCESS_FILE)
    
    if not os.path.exists(access_path):
        return False
        
    try:
        with open(access_path, 'r') as f:
            data = json.load(f)
        if data.get("owner") == user_uid: return True
        if user_uid in data.get("members", []): return True
        return False
    except Exception as e:
        print(f"[legacy:warning] ACL Read Error: {e}")
        return False

# --- FILE OPERATIONS ---

def get_absolute_file_path(target_id: str, filename: str, is_project: bool = False) -> str:
    target_dir = _get_target_dir(target_id, is_project)
    return os.path.join(target_dir, os.path.basename(filename))

def get_files(target_id: str, is_project: bool = False) -> Dict[str, bytes]:
    target_dir = _get_target_dir(target_id, is_project)
    files_content = {}
    
    if os.path.exists(target_dir):
        for root, dirs, files in os.walk(target_dir):
            for name in files:
                if name.startswith('.'): continue
                if name == ACCESS_FILE: continue 
                
                full_path = os.path.join(root, name)
                rel_path = os.path.relpath(full_path, target_dir).replace("\\", "/")
                try:
                    with open(full_path, 'rb') as f:
                        files_content[rel_path] = f.read()
                except Exception as e:
                    print(f"Error reading {rel_path}: {e}")
                
    return files_content

def add_file(target_id: str, filename: str, content: bytes, is_project: bool = False):
    file_path = get_absolute_file_path(target_id, filename, is_project)
    with open(file_path, 'wb') as f:
        f.write(content)

def remove_file(target_id: str, filename: str, is_project: bool = False):
    file_path = get_absolute_file_path(target_id, filename, is_project)
    if os.path.exists(file_path):
        os.remove(file_path)

def clear_session(target_id: str, is_project: bool = False):
    target_dir = _get_target_dir(target_id, is_project)
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
        os.makedirs(target_dir, exist_ok=True)
