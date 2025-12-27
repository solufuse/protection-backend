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
    # FORCE RELOAD FROM DISK IF NEEDED
    files = session_manager.get_files(token)
    
    if filename not in files: 
        # Debug : log ce qu'on a
        print(f"File {filename} not found in session. Available: {list(files.keys())}")
        raise HTTPException(404, f"File '{filename}' not found in session.")
    return filename, files[filename]

def is_db(name): return name.lower().endswith(('.si2s', '.mdb', '.lf1s'))

@router.get("/preview")
def preview_data(filename: str = Query(...), token: str = Depends(get_current_token)):
    name, content = get_file(token, filename)
    if not is_db(name): raise HTTPException(400, "Format not supported")
    dfs = db_converter.extract_data_from_db(content)
    if not dfs: raise HTTPException(500, "Read error")
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

@router.get("/download-all/{format}")
def download_all_zip(format: str, token: str = Depends(get_current_token)):
    files = session_manager.get_files(token)
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
                        z.writestr(f"{base}.json", json.dumps(d, default=str))
                    count += 1
    if count == 0: raise HTTPException(400, "No convertible files")
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=batch.zip"})
