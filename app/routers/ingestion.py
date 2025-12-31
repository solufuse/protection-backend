
import os
import io
import json
import zipfile
import pandas as pd
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user, ProjectAccessChecker
from ..guest_guard import check_guest_restrictions
from app.calculations import db_converter

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

def get_ingestion_path(user, project_id: Optional[str], db: Session, action: str = "read"):
    if project_id:
        checker = ProjectAccessChecker(required_role="viewer")
        checker(project_id, user, db)
        path = os.path.join("/app/storage", project_id)
        if not os.path.exists(path): raise HTTPException(404, "Project not found")
        return path
    else:
        uid = user.firebase_uid
        is_guest = False
        try: 
            if not user.email: is_guest = True
        except: pass
        return check_guest_restrictions(uid, is_guest, action="read")

def is_db_file(name: str): 
    return name.lower().endswith(('.si2s', '.mdb', '.lf1s', '.json'))

@router.get("/preview")
def preview_data(filename: str = Query(...), project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    base_dir = get_ingestion_path(user, project_id, db)
    file_path = os.path.join(base_dir, filename)
    if not os.path.exists(file_path): raise HTTPException(404, "File not found")
    try:
        with open(file_path, "rb") as f: content = f.read()
    except Exception as e: raise HTTPException(500, f"Read Error: {e}")

    data_to_return = {}
    if filename.lower().endswith('.json'):
        try: data_to_return = json.loads(content)
        except: raise HTTPException(400, "Invalid JSON")
    elif is_db_file(filename):
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: raise HTTPException(500, "Could not extract data from DB")
        data_to_return = {"filename": filename, "tables": {}}
        for t, df in dfs.items():
            data_to_return["tables"][t] = df.head(50).where(pd.notnull(df), None).to_dict(orient="records")
    else: raise HTTPException(400, "Format not supported")
    return Response(content=json.dumps(data_to_return, indent=2, default=str), media_type="application/json")

@router.get("/download/{format}")
def download_single(format: str, filename: str = Query(...), project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    base_dir = get_ingestion_path(user, project_id, db)
    file_path = os.path.join(base_dir, filename)
    if not os.path.exists(file_path): raise HTTPException(404, "File not found")
    with open(file_path, "rb") as f: content = f.read()
    dfs = db_converter.extract_data_from_db(content)
    if not dfs: raise HTTPException(400, "Unreadable or Empty")
    clean_name = os.path.splitext(filename)[0]
    if format == "xlsx":
        stream = db_converter.generate_excel_bytes(dfs)
        return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={clean_name}.xlsx"})
    elif format == "json":
        data = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
        json_str = json.dumps({"filename": filename, "data": data}, indent=2, default=str)
        return Response(content=json_str, media_type="application/json", headers={"Content-Disposition": f"attachment; filename={clean_name}.json"})
    raise HTTPException(400, "Invalid format")

@router.get("/download-all/{format}")
def download_all_zip(format: str, project_id: Optional[str] = Query(None), user = Depends(get_current_user), db: Session = Depends(get_db)):
    base_dir = get_ingestion_path(user, project_id, db)
    if not os.path.exists(base_dir): raise HTTPException(404, "Storage not found")
    zip_buffer = io.BytesIO()
    count = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for f in os.listdir(base_dir):
            full_path = os.path.join(base_dir, f)
            if os.path.isfile(full_path) and is_db_file(f):
                try:
                    with open(full_path, "rb") as file_obj: content = file_obj.read()
                    dfs = db_converter.extract_data_from_db(content)
                    if dfs:
                        base = os.path.splitext(f)[0]
                        if format == "xlsx": z.writestr(f"{base}.xlsx", db_converter.generate_excel_bytes(dfs).getvalue())
                        elif format == "json":
                            d = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
                            z.writestr(f"{base}.json", json.dumps(d, default=str, indent=2))
                        count += 1
                except: continue
    if count == 0: raise HTTPException(400, "No convertible files found")
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=batch_export.zip"})
