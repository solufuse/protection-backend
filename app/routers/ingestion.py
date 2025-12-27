from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from app.services import session_manager
from app.calculations import db_converter
from app.services.session_manager import get_absolute_file_path
from app.core.auth_utils import get_uid_from_token
import pandas as pd
import io
import json
import zipfile
import os

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

def get_file_content_via_token_raw(token_raw: str, filename: str):
    user_id = get_uid_from_token(token_raw)
    session_manager.get_files(user_id) # Reload check
    file_path = get_absolute_file_path(user_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(404, f"File not found")
    with open(file_path, "rb") as f:
        return filename, f.read()

def is_db(name): return name.lower().endswith(('.si2s', '.mdb', '.lf1s', '.json'))

@router.get("/preview")
def preview_data(filename: str = Query(...), token: str = Query(...)):
    name, content = get_file_content_via_token_raw(token, filename)
    
    data_to_return = {}

    if name.lower().endswith('.json'):
        try: data_to_return = json.loads(content)
        except: raise HTTPException(400, "Invalid JSON")
    
    elif is_db(name):
        dfs = db_converter.extract_data_from_db(content)
        if not dfs: raise HTTPException(500, "Read error")
        data_to_return = {"filename": name, "tables": {}}
        for t, df in dfs.items():
            # Conversion propre
            data_to_return["tables"][t] = df.head(50).where(pd.notnull(df), None).to_dict(orient="records")
    else:
        raise HTTPException(400, "Format not supported")

    # PRETTY PRINT : On renvoie une string formatée au lieu du JSON minifié par défaut
    json_str = json.dumps(data_to_return, indent=2, default=str)
    return Response(content=json_str, media_type="application/json")

@router.get("/download/{format}")
def download_single(format: str, filename: str = Query(...), token: str = Query(...)):
    name, content = get_file_content_via_token_raw(token, filename)
    dfs = db_converter.extract_data_from_db(content)
    if not dfs: raise HTTPException(400, "Unreadable")
    
    clean_name = name
    for ext in ['.si2s', '.lf1s', '.mdb']: clean_name = clean_name.lower().replace(ext, "")

    if format == "xlsx":
        stream = db_converter.generate_excel_bytes(dfs)
        return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={clean_name}.xlsx"})
    elif format == "json":
        data = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
        # Pretty print pour le fichier téléchargé aussi
        json_str = json.dumps({"filename": name, "data": data}, indent=2, default=str)
        return Response(content=json_str, media_type="application/json", headers={"Content-Disposition": f"attachment; filename={clean_name}.json"})
    raise HTTPException(400, "Invalid format")

@router.get("/download-all/{format}")
def download_all_zip(format: str, token: str = Query(...)):
    user_id = get_uid_from_token(token)
    files = session_manager.get_files(user_id)
    if not files: raise HTTPException(400, "Session empty")
    
    zip_buffer = io.BytesIO()
    count = 0
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            if is_db(name):
                dfs = db_converter.extract_data_from_db(content)
                if dfs:
                    base = name
                    for ext in ['.si2s', '.lf1s', '.mdb']: base = base.lower().replace(ext, "")
                    if format == "xlsx":
                        z.writestr(f"{base}.xlsx", db_converter.generate_excel_bytes(dfs).getvalue())
                    elif format == "json":
                        d = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
                        z.writestr(f"{base}.json", json.dumps(d, default=str, indent=2))
                    count += 1
    if count == 0: raise HTTPException(400, "No convertible files")
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=batch.zip"})
