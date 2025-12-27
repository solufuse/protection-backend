from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.security import get_current_token
from app.services import session_manager
from app.calculations import db_converter
import pandas as pd
import io
import json
import zipfile

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

def get_file(token, filename):
    files = session_manager.get_files(token)
    if filename not in files: raise HTTPException(404, "File not found")
    return filename, files[filename]

def is_db(name): return name.lower().endswith(('.si2s', '.mdb', '.lf1s'))

@router.get("/preview")
def preview_data(filename: str = Query(...), token: str = Depends(get_current_token)):
    name, content = get_file(token, filename)
    if not is_db(name): raise HTTPException(400, "Preview not supported for this file type")
    dfs = db_converter.extract_data_from_db(content)
    if not dfs: raise HTTPException(500, "Could not read database")
    preview = {"filename": name, "tables": {}}
    for t, df in dfs.items():
        preview["tables"][t] = df.head(10).where(pd.notnull(df), None).to_dict(orient="records")
    return preview

@router.get("/download/{format}")
def download_single(format: str, filename: str = Query(...), token: str = Depends(get_current_token)):
    name, content = get_file(token, filename)
    dfs = db_converter.extract_data_from_db(content)
    if not dfs: raise HTTPException(400, "File unreadable")
    
    clean_name = name
    for ext in ['.si2s', '.lf1s', '.mdb']: clean_name = clean_name.lower().replace(ext, "")

    if format == "xlsx":
        stream = db_converter.generate_excel_bytes(dfs)
        return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={clean_name}.xlsx"})
    elif format == "json":
        data = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
        return JSONResponse({"filename": name, "data": data})
    raise HTTPException(400, "Invalid format")
