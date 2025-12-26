from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.security import get_current_token
from app.services import session_manager
from app.calculations import db_converter
import pandas as pd
import io
import json
import zipfile
import os
import re
from datetime import datetime

router = APIRouter(prefix="/ingestion", tags=["Ingestion & Export"])

# --- HELPERS ---

def get_export_metadata(token: str):
    """
    Helper: Extracts project name from config and generates current date string.
    Returns tuple: (project_name_sanitized, date_string)
    Example: ("MyProject", "2023-10-25")
    """
    files = session_manager.get_files(token)
    project_name = "Project" # Default fallback
    
    # Try to extract project name from config.json
    try:
        content = None
        if "config.json" in files:
            content = files["config.json"]
        else:
            # Fallback: look for any .json file
            for k, v in files.items():
                if k.lower().endswith(".json"):
                    content = v; break
        
        if content:
            if isinstance(content, bytes): content = content.decode('utf-8')
            data = json.loads(content)
            if "project_name" in data:
                # Sanitize the name (remove special chars)
                clean_name = re.sub(r'[\\/*?:"<>|]', "", data["project_name"])
                project_name = clean_name.replace(" ", "_")
    except:
        pass # Fail silently and use default
        
    date_str = datetime.now().strftime("%Y-%m-%d")
    return project_name, date_str

def get_specific_file(token: str, filename: str):
    """
    Retrieves a specific file from the session.
    'filename' argument can be the full path or just the name.
    """
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="No files in session.")
    
    # Direct match (Full Path)
    if filename in files:
        return filename, files[filename]
        
    # Case-insensitive search
    for existing in files.keys():
        if existing.lower() == filename.lower(): 
            return existing, files[existing]
            
    raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

def is_supported_db(filename: str) -> bool:
    """Checks if file extension is supported for conversion."""
    ext = filename.lower()
    return ext.endswith('.si2s') or ext.endswith('.mdb') or ext.endswith('.lf1s')

# --- ROUTES ---

@router.get("/preview")
def preview_data(filename: str = Query(...), token: str = Depends(get_current_token)):
    """
    Returns a preview (first 10 rows) of all tables in the database file.
    """
    real_name, content = get_specific_file(token, filename)
    
    if not is_supported_db(real_name):
         raise HTTPException(status_code=400, detail="Unsupported file format (SI2S, LF1S, MDB only).")

    dfs = db_converter.extract_data_from_db(content)
    if dfs is None: raise HTTPException(status_code=500, detail="Error reading SQLite database.")
        
    preview = {
        "path": real_name,                       # Full path (Unique ID)
        "filename": os.path.basename(real_name), # Short name (Display)
        "tables": {}
    }
    for table, df in dfs.items():
        # Replace NaN with None for valid JSON
        df_clean = df.head(10).where(pd.notnull(df), None)
        preview["tables"][table] = df_clean.to_dict(orient="records")
    return preview

@router.get("/download/{format}")
def download_single(format: str, filename: str = Query(...), token: str = Depends(get_current_token)):
    """
    Converts and downloads a single file.
    Filename format: {OriginalName}_{Project}_{Date}.xlsx
    """
    real_name, content = get_specific_file(token, filename)
    
    # Reuse DB converter
    dfs = db_converter.extract_data_from_db(content)
    if not dfs: raise HTTPException(status_code=400, detail="File empty or unreadable.")

    # Get Metadata for naming
    p_name, p_date = get_export_metadata(token)

    if format == "xlsx":
        excel_stream = db_converter.generate_excel_bytes(dfs)
        
        # Create base name from original file
        base_name = os.path.basename(real_name) 
        for ext in ['.si2s', '.lf1s', '.mdb']:
            base_name = base_name.lower().replace(ext, "")
            
        # Construct Dynamic Filename
        new_name = f"{base_name}_{p_name}_{p_date}.xlsx"
        
        return StreamingResponse(
            excel_stream, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={new_name}"}
        )
    elif format == "json":
        data = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
        
        base_name = os.path.basename(real_name)
        new_name = f"{base_name}_{p_name}_{p_date}.json"
        
        return JSONResponse(
            content={"path": real_name, "filename": base_name, "data": data},
            headers={"Content-Disposition": f"attachment; filename={new_name}"}
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid format (xlsx/json)")

@router.get("/download-all/{format}")
def download_all_zip(format: str, token: str = Depends(get_current_token)):
    """
    Batch conversion of all supported files in session.
    Filename format: INGEST_batch_{Project}_{Date}.zip
    """
    files = session_manager.get_files(token)
    if not files:
        raise HTTPException(status_code=400, detail="No files in session.")

    zip_buffer = io.BytesIO()
    files_processed = 0
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files.items():
            if not is_supported_db(filename):
                continue
                
            dfs = db_converter.extract_data_from_db(content)
            if not dfs: continue
            
            # Use short name for files inside the ZIP
            base_name = os.path.basename(filename)
            for ext in ['.si2s', '.lf1s', '.mdb']:
                base_name = base_name.lower().replace(ext, "")
            
            if format == "xlsx":
                excel_bytes = db_converter.generate_excel_bytes(dfs)
                zip_file.writestr(f"{base_name}.xlsx", excel_bytes.getvalue())
                files_processed += 1
                
            elif format == "json":
                data = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
                json_str = json.dumps(data, indent=2, default=str)
                zip_file.writestr(f"{base_name}.json", json_str)
                files_processed += 1
    
    if files_processed == 0:
        raise HTTPException(status_code=400, detail="No valid files (SI2S/LF1S) found to convert.")

    zip_buffer.seek(0)
    
    # Get Metadata for naming
    p_name, p_date = get_export_metadata(token)
    zip_name = f"INGEST_batch_{p_name}_{p_date}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_name}"}
    )
