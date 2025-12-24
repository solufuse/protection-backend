from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.security import get_current_token
from app.services import session_manager
from app.calculations import si2s_converter
import pandas as pd
import io
import json
import zipfile  # <--- Nouvelle librairie standard

router = APIRouter(prefix="/ingestion", tags=["Ingestion & Export"])

# --- HELPERS ---
def get_specific_file(token: str, filename: str):
    files = session_manager.get_files(token)
    if not files: raise HTTPException(status_code=400, detail="Aucun fichier en session.")
    if filename not in files:
        for existing in files.keys():
            if existing.lower() == filename.lower(): return existing, files[existing]
        raise HTTPException(status_code=404, detail=f"Fichier '{filename}' introuvable.")
    return filename, files[filename]

# --- ROUTES ---

@router.get("/preview")
def preview_data(filename: str = Query(...), token: str = Depends(get_current_token)):
    real_name, content = get_specific_file(token, filename)
    if not (real_name.lower().endswith('.si2s') or real_name.lower().endswith('.mdb')):
         raise HTTPException(status_code=400, detail="Fichier non supporté.")

    dfs = si2s_converter.extract_data_from_si2s(content)
    if dfs is None: raise HTTPException(status_code=500, detail="Erreur lecture SQLite.")
        
    preview = {"filename": real_name, "tables": {}}
    for table, df in dfs.items():
        df_clean = df.head(10).where(pd.notnull(df), None)
        preview["tables"][table] = df_clean.to_dict(orient="records")
    return preview

@router.get("/download/{format}")
def download_single(format: str, filename: str = Query(...), token: str = Depends(get_current_token)):
    real_name, content = get_specific_file(token, filename)
    dfs = si2s_converter.extract_data_from_si2s(content)
    if not dfs: raise HTTPException(status_code=400, detail="Fichier vide.")

    if format == "xlsx":
        excel_stream = si2s_converter.generate_excel_bytes(dfs)
        new_name = real_name.lower().replace(".si2s", ".xlsx")
        return StreamingResponse(
            excel_stream, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={new_name}"}
        )
    elif format == "json":
        data = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
        return JSONResponse(content={"filename": real_name, "data": data})
    else:
        raise HTTPException(status_code=400, detail="Format invalide (xlsx/json)")

@router.get("/download-all/{format}")
def download_all_zip(format: str, token: str = Depends(get_current_token)):
    """
    Convertit TOUS les fichiers de la session et les renvoie dans un ZIP.
    """
    files = session_manager.get_files(token)
    if not files:
        raise HTTPException(status_code=400, detail="Aucun fichier en session.")

    # On prépare le ZIP en mémoire
    zip_buffer = io.BytesIO()
    
    files_processed = 0
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files.items():
            # On ne traite que les .SI2S / .mdb
            if not (filename.lower().endswith('.si2s') or filename.lower().endswith('.mdb')):
                continue
                
            # Extraction
            dfs = si2s_converter.extract_data_from_si2s(content)
            if not dfs: continue # On saute les fichiers vides
            
            # Conversion EXCEL
            if format == "xlsx":
                excel_bytes = si2s_converter.generate_excel_bytes(dfs)
                # On écrit le fichier Excel DANS le ZIP
                new_name = filename.lower().replace(".si2s", ".xlsx")
                zip_file.writestr(new_name, excel_bytes.getvalue())
                files_processed += 1
                
            # Conversion JSON
            elif format == "json":
                data = {t: df.where(pd.notnull(df), None).to_dict(orient="records") for t, df in dfs.items()}
                json_str = json.dumps(data, indent=2, default=str)
                new_name = filename.lower().replace(".si2s", ".json")
                zip_file.writestr(new_name, json_str)
                files_processed += 1
    
    if files_processed == 0:
        raise HTTPException(status_code=400, detail="Aucun fichier valide n'a pu être converti.")

    # Fin du ZIP et retour au début du stream
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=conversion_batch.zip"}
    )
