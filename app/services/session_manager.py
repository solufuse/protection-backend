
import os
import shutil
import json
import datetime
from typing import List, Dict, Union, Optional

BASE_USER_DIR = "/app/storage"
BASE_PROJECT_DIR = "/app/storage/projects"
ACCESS_FILE = "access.json"

def _get_target_dir(target_id: str, is_project: bool) -> str:
    base = BASE_PROJECT_DIR if is_project else BASE_USER_DIR
    path = os.path.join(base, target_id)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

# --- ACL & PROJECT MANAGEMENT ---

def create_project(owner_uid: str, project_id: str, owner_email: str = "") -> bool:
    project_dir = _get_target_dir(project_id, is_project=True)
    access_path = os.path.join(project_dir, ACCESS_FILE)
    
    if os.path.exists(access_path):
        return False

    access_data = {
        "owner": owner_uid,
        "owner_email": owner_email,
        "members": [owner_uid],
        "created_at": datetime.datetime.now().isoformat(),
        "is_public": False
    }
    
    with open(access_path, 'w') as f:
        json.dump(access_data, f, indent=2)
    return True

def get_project_acl(project_id: str) -> Optional[Dict]:
    project_dir = _get_target_dir(project_id, is_project=True)
    access_path = os.path.join(project_dir, ACCESS_FILE)
    if not os.path.exists(access_path): return None
    try:
        with open(access_path, 'r') as f: return json.load(f)
    except: return None

def can_access_project(user_uid: str, project_id: str) -> bool:
    acl = get_project_acl(project_id)
    if not acl: return False
    return (user_uid == acl.get("owner")) or (user_uid in acl.get("members", []))

def is_project_owner(user_uid: str, project_id: str) -> bool:
    acl = get_project_acl(project_id)
    return acl and (acl.get("owner") == user_uid)

def add_member(project_id: str, new_uid: str):
    project_dir = _get_target_dir(project_id, is_project=True)
    access_path = os.path.join(project_dir, ACCESS_FILE)
    
    acl = get_project_acl(project_id)
    if not acl: return False
    
    if new_uid not in acl["members"]:
        acl["members"].append(new_uid)
        with open(access_path, 'w') as f:
            json.dump(acl, f, indent=2)
    return True

def remove_member(project_id: str, target_uid: str):
    project_dir = _get_target_dir(project_id, is_project=True)
    access_path = os.path.join(project_dir, ACCESS_FILE)
    
    acl = get_project_acl(project_id)
    if not acl: return False
    
    if target_uid in acl["members"]:
        acl["members"].remove(target_uid)
        with open(access_path, 'w') as f:
            json.dump(acl, f, indent=2)
    return True

def list_projects_for_user(user_uid: str) -> List[Dict]:
    results = []
    if not os.path.exists(BASE_PROJECT_DIR): return []
    
    for project_id in os.listdir(BASE_PROJECT_DIR):
        acl = get_project_acl(project_id)
        if acl:
            if user_uid == acl.get("owner") or user_uid in acl.get("members", []):
                results.append({
                    "project_id": project_id,
                    "role": "owner" if user_uid == acl.get("owner") else "member",
                    "created_at": acl.get("created_at"),
                    "owner_email": acl.get("owner_email", "unknown")
                })
    return results

def delete_project_permanently(project_id: str):
    target_dir = _get_target_dir(project_id, is_project=True)
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)

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
                    with open(full_path, 'rb') as f: files_content[rel_path] = f.read()
                except: pass
    return files_content

def add_file(target_id: str, filename: str, content: bytes, is_project: bool = False):
    file_path = get_absolute_file_path(target_id, filename, is_project)
    with open(file_path, 'wb') as f: f.write(content)

def remove_file(target_id: str, filename: str, is_project: bool = False):
    file_path = get_absolute_file_path(target_id, filename, is_project)
    if os.path.exists(file_path): os.remove(file_path)

def clear_session(target_id: str, is_project: bool = False):
    target_dir = _get_target_dir(target_id, is_project)
    if is_project:
        # Safe Clear for Projects (Keep Access File)
        if os.path.exists(target_dir):
            for filename in os.listdir(target_dir):
                if filename == ACCESS_FILE: continue
                file_path = os.path.join(target_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path): os.unlink(file_path)
                    elif os.path.isdir(file_path): shutil.rmtree(file_path)
                except: pass
    else:
        # Legacy User Clear
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
            os.makedirs(target_dir, exist_ok=True)
