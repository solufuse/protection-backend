from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import requests
import io
import json
import zipfile
import pandas as pd

# Imports Services
from app.services.converter import extract_data_from_db, generate_excel_bytes
from app.services.storage import save_smartly, log_error, db as firestore_db # On accède à Firestore

router = APIRouter(prefix="/ingestion", tags=["Ingestion & Export"])

# --- MODELS ---
class FileProcessRequest(BaseModel):
    user_id: str
    file_url: str
    file_type: str

class ProcessResponse(BaseModel):
    status: str
    message: str

# --- HELPERS ---
def fetch_file_from_url(url: str) -> io.BytesIO:
    """Télécharge un fichier depuis une URL (Firebase Storage)"""
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        return io.BytesIO(resp.content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Impossible de télécharger le fichier: {str(e)}")

# --- ROUTES ---

@router.post("/process", response_model=ProcessResponse)
async def trigger_ingestion(request: FileProcessRequest, background_tasks: BackgroundTasks):
    """Endpoint asynchrone pour traiter et sauvegarder (Logic existante)."""
    if not request.file_url.startswith("http"):
         raise HTTPException(status_code=400, detail="Invalid URL")

    # Fonction interne pour le background
    def process_background_task(user_id, file_url, file_type):
        try:
            file_stream = fetch_file_from_url(file_url)
            extracted_content = extract_data_from_db(file_stream)
            save_smartly(user_id, extracted_content, file_type)
        except Exception as e:
            log_error(user_id, str(e), file_url)

    background_tasks.add_task(
        process_background_task, 
        request.user_id, 
        request.file_url, 
        request.file_type
    )
    return ProcessResponse(status="accepted", message="Processing started.")

@router.get("/preview")
def preview_data(file_url: str = Query(..., description="URL publique ou signée du fichier Storage")):
    """Aperçu en direct d'un fichier stocké sur Firebase Storage."""
    content = fetch_file_from_url(file_url)
    
    # Extraction
    try:
        dfs_dict = extract_data_from_db(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier illisible ou format incorrect.")

    preview = {"tables": {}}
    for table, records in dfs_dict.items():
        # On limite à 10 lignes pour la preview
        preview["tables"][table] = records[:10]
        
    return preview

@router.get("/download/{format}")
def download_single(format: str, file_url: str = Query(...), filename: str = "export"):
    """Télécharge et convertit à la volée (XLSX/JSON) depuis Storage."""
    content = fetch_file_from_url(file_url)
    
    # 1. Extraction
    dfs_dict = extract_data_from_db(content)
    if not dfs_dict: 
        raise HTTPException(status_code=400, detail="Fichier vide.")

    # 2. Conversion
    if format == "xlsx":
        excel_stream = generate_excel_bytes(dfs_dict)
        return StreamingResponse(
            excel_stream, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"}
        )
    elif format == "json":
        return JSONResponse(content={"filename": filename, "data": dfs_dict})
    else:
        raise HTTPException(status_code=400, detail="Format invalide (xlsx/json)")

@router.get("/download-all/{format}")
def download_all_zip(format: str, user_id: str = Query(...)):
    """
    Récupère TOUTES les configurations récentes de l'utilisateur dans Firestore 
    et en fait un ZIP.
    """
    # 1. Récupération des fichiers depuis Firestore (Smart Storage)
    docs = firestore_db.collection("users").document(user_id).collection("configurations")\
        .order_by("created_at", direction=firestore_db.Query.DESCENDING).limit(5).stream()
    
    files_processed = 0
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for doc in docs:
            config = doc.to_dict()
            if not config.get('processed'): continue
            
            # Récupération des données (Directe ou Storage)
            data = {}
            if config.get('is_large_file'):
                # TODO: Pour le ZIP de gros fichiers, il faudrait télécharger depuis Storage
                # Pour l'instant on skip ou on implémente un fetch
                continue 
            else:
                data = config.get('raw_data', {})

            if not data: continue

            base_name = f"config_{doc.id}"

            if format == "xlsx":
                excel_bytes = generate_excel_bytes(data)
                zip_file.writestr(f"{base_name}.xlsx", excel_bytes.getvalue())
                files_processed += 1
            elif format == "json":
                json_str = json.dumps(data, indent=2, default=str)
                zip_file.writestr(f"{base_name}.json", json_str)
                files_processed += 1

    if files_processed == 0:
        raise HTTPException(status_code=404, detail="Aucun fichier récent compatible trouvé.")

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=batch_export.zip"}
    )
