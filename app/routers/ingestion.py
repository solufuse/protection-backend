from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.security import get_current_token
from app.services import session_manager
from app.calculations import si2s_converter
import pandas as pd
import io
import json
import zipfile
import os

router = APIRouter(prefix="/ingestion", tags=["Ingestion & Export"])

# --- HELPERS ---
def get_specific_file(token: str, filename: str):
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="No files in session.")
    if filename not in files:
        for existing in files.keys():
            if existing.lower() == filename.lower(): return existing, files[existing]
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")
    return filename, files[filename]

def is_supported_db(filename: str) -> bool:
    ext = filename.lower()
    return ext.endswith('.si2s') or ext.endswith('.mdb') or ext.endswith('.lf1s')

# --- ROUTES ---

@router.get("/preview")
def preview_data(filename: str = Query(...), token: str = Depends(get_current_token)):
    real_name, content = get_specific_file(token, filename)
    
    if not is_supported_db(real_name):
         raise HTTPException(status_code=400, detail="Unsupported file format (SI2S, LF1S, MDB only).")

    dfs = si2s_converter.extract_data_from_si2s(content)
    if dfs is None: raise HTTPException(status_code=500, detail="Error reading SQLite.")
        
    preview = {
        "path": real_name,                       # Full path (unique ID)
        "filename": os.path.basename(real_name), # Short name (display)
        "tables": {}
    }
    for table, df in dfs.items():
        df_clean = df.head(10).where(pd.notnull(df), None)
        preview["tables"][table] = df_clean.to_dict(orient="records")
    return preview

@router.get("/download/{format}")
def download_single(format: str, filename: str = Query(...), token: str = Depends(get_current_token)):
    real_name, content = get_specific_file(token, filename)
    
    # Reuse SI2S converter
    dfs = si2s_converter.extract_data_from_si2s(content)
    if not dfs: raise HTTPException(status_code=400, detail="File empty or unreadable.")

    if format == "xlsx":
        excel_stream = si2s_converter.generate_excel_bytes(dfs)
        # Create new name based on original
        new_name = os.path.basename(real_name) # Use short name for download
        for ext in ['.si2s', '.lf1s', '.mdb']:
            new_name = new_name.lower().replace(ext, "")
        new_name += ".xlsx"
        
        return StreamingResponse(
            excel_stream, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={new_name}"}
        )
    elif format == "json":
        data = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
        return JSONResponse(content={"path": real_name, "filename": os.path.basename(real_name), "data": data})
    else:
        raise HTTPException(status_code=400, detail="Invalid format (xlsx/json)")

@router.get("/download-all/{format}")
def download_all_zip(format: str, token: str = Depends(get_current_token)):
    files = session_manager.get_files(token)
    if not files:
        raise HTTPException(status_code=400, detail="No files in session.")

    zip_buffer = io.BytesIO()
    files_processed = 0
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files.items():
            if not is_supported_db(filename):
                continue
                
            dfs = si2s_converter.extract_data_from_si2s(content)
            if not dfs: continue
            
            # Use short name for files inside ZIP
            base_name = os.path.basename(filename)
            for ext in ['.si2s', '.lf1s', '.mdb']:
                base_name = base_name.lower().replace(ext, "")
            
            if format == "xlsx":
                excel_bytes = si2s_converter.generate_excel_bytes(dfs)
                zip_file.writestr(f"{base_name}.xlsx", excel_bytes.getvalue())
                files_processed += 1
                
            elif format == "json":
                data = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
                json_str = json.dumps(data, indent=2, default=str)
                zip_file.writestr(f"{base_name}.json", json_str)
                files_processed += 1
    
    if files_processed == 0:
        raise HTTPException(status_code=400, detail="No valid files (SI2S/LF1S) found.")

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=conversion_batch.zip"}
    )
