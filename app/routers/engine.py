from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.core.security import get_current_token
from app.services import session_manager
from app.schemas.protection import ProjectConfig
from app.calculations import db_converter, topology_manager
import json
import pandas as pd

router = APIRouter(prefix="/engine-pc", tags=["PC"])

def get_merged_dfs(token):
    files = session_manager.get_files(token)
    merged = {}
    for n, c in files.items():
        if n.lower().endswith(('.si2s', '.mdb', '.lf1s')):
            dfs = db_converter.extract_data_from_db(c)
            if dfs:
                for t, df in dfs.items():
                    if t not in merged: merged[t] = []
                    merged[t].append(df)
    final = {}
    for k, v in merged.items():
        try: final[k] = pd.concat(v, ignore_index=True)
        except: final[k] = v[0]
    return final

@router.post("/run")
async def run_session(token: str = Depends(get_current_token)):
    files = session_manager.get_files(token)
    if "config.json" not in files: raise HTTPException(404, "config.json manquant")
    try: config = ProjectConfig(**json.loads(files["config.json"].decode()))
    except: raise HTTPException(422, "Config invalide")
    
    dfs = get_merged_dfs(token)
    updated = topology_manager.resolve_all(config, dfs)
    return {"status": "success", "plans": updated.plans}
