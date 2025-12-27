from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime
import os
import json
import uuid
import requests
import tempfile
import shutil
import zipfile
import io
import pandas as pd

# Imports Hybrides
try:
    from app.firebase_config import db, bucket
    from app.core.db_converter import DBConverter
    from app.core.memory import SESSIONS
except ImportError:
    from firebase_config import db, bucket
    from core.db_converter import DBConverter
    from core.memory import SESSIONS

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

class IngestionRequest(BaseModel):
    user_id: str
    file_url: str
    file_type: str

ALLOWED_EXTENSIONS = {'.json', '.si2s', '.mdb', '.sqlite', '.lf1s', '.xml'}

# --- HELPERS ---
def json_to_excel_bytes(json_content):
    output = io.BytesIO()
    if "raw_content" in json_content and "tables_data" in json_content["raw_content"]:
        tables = json_content["raw_content"]["tables_data"]
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            if not tables: pd.DataFrame().to_excel(writer, sheet_name="Empty")
            else:
                for table_name, rows in tables.items():
                    try:
                        df = pd.DataFrame(rows)
                        sheet_name = table_name[:31]
                        base_name = sheet_name; count = 1
                        while sheet_name in writer.book.sheetnames:
                            sheet_name = f"{base_name[:28]}_{count}"; count += 1
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                    except: pass
    else:
        df = pd.json_normalize(json_content)
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Data')
    output.seek(0)
    return output

def process_single_file(user_id, file_path, original_filename):
    try:
        # ---------------------------------------------------------
        # ÉTAPE 1 : CONVERSION LOCALE (CPU - ULTRA RAPIDE)
        # ---------------------------------------------------------
        print(f"   ⚡ Start Convert: {original_filename}")
        result_data = DBConverter.convert_to_json(file_path, original_filename)
        _, ext = os.path.splitext(original_filename)

        # On génère les UUIDs tout de suite pour préparer les chemins
        raw_uuid = str(uuid.uuid4())
        result_uuid = str(uuid.uuid4())
        
        raw_storage_path = f"raw_uploads/{user_id}/{raw_uuid}{ext}"
        proc_storage_path = f"processed/{user_id}/{result_uuid}.json"

        # ---------------------------------------------------------
        # ÉTAPE 2 : PRIORITÉ RAM (INSTANTANÉ) 🧠
        # ---------------------------------------------------------
        # On injecte dans la mémoire IMMEDIATEMENT, avant même de parler à Google.
        # Comme ça, ton endpoint /session/details voit le fichier tout de suite.
        
        if user_id not in SESSIONS: SESSIONS[user_id] = []
        
        file_meta = {
            'id': result_uuid, # On utilise l'UUID comme ID temporaire
            'created_at': datetime.utcnow(),
            'source_type': ext.replace('.', ''),
            'original_name': original_filename,
            'processed': True,
            'storage_path': proc_storage_path,   # Chemin "futur" (upload en cours)
            'raw_file_path': raw_storage_path,   # Chemin "futur"
            'preview_available': True,
            'data_preview': result_data          # DONNÉE DISPO DIRECTEMENT !
        }
        
        # On l'insère en haut de la liste
        SESSIONS[user_id].insert(0, file_meta)
        print(f"   🧠 RAM Updated (Instant Access): {original_filename}")

        # ---------------------------------------------------------
        # ÉTAPE 3 : SAUVEGARDE CLOUD (EN ARRIÈRE PLAN) ☁️
        # ---------------------------------------------------------
        # Si ça prend 2 secondes, c'est pas grave, c'est déjà dispo en RAM.
        
        # 3a. Upload Raw File
        bucket.blob(raw_storage_path).upload_from_filename(file_path)

        # 3b. Upload JSON Result
        bucket.blob(proc_storage_path).upload_from_string(json.dumps(result_data, default=str), content_type='application/json')

        # 3c. Update Firestore (Persistance)
        # On utilise le même ID que le nom de fichier JSON pour être cohérent si possible, 
        # ou on laisse Firestore générer un ID (mais pour le lien RAM/Cloud c'est mieux de suivre).
        doc_ref = db.collection('users').document(user_id).collection('configurations').document()
        # On met à jour l'ID Firestore
        final_meta = file_meta.copy()
        del final_meta['data_preview'] # On ne stocke pas le gros JSON dans les métadonnées Firestore
        doc_ref.set(final_meta)
        
        print(f"   ☁️  Cloud Sync Done: {original_filename}")

    except Exception as e:
        print(f"   ❌ Error processing {original_filename}: {e}")

def process_file_task(req: IngestionRequest):
    temp_dir = tempfile.mkdtemp()
    try:
        download_path = os.path.join(temp_dir, "input")
        with requests.get(req.file_url, stream=True) as r:
            with open(download_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        
        if zipfile.is_zipfile(download_path):
            with zipfile.ZipFile(download_path, 'r') as z:
                # On trie pour traiter les petits fichiers d'abord si besoin, 
                # ou alphabétiquement pour que la liste RAM soit stable
                file_list = sorted(z.namelist()) 
                for m in file_list:
                    if not m.startswith('__') and os.path.splitext(m)[1].lower() in ALLOWED_EXTENSIONS:
                        z.extract(m, temp_dir)
                        process_single_file(req.user_id, os.path.join(temp_dir, m), os.path.basename(m))
        else:
            process_single_file(req.user_id, download_path, f"uploaded.{req.file_type}")
    except Exception as e: print(f"Task Error: {e}")
    finally: shutil.rmtree(temp_dir)

@router.post("/process")
async def start(req: IngestionRequest, bt: BackgroundTasks):
    bt.add_task(process_file_task, req)
    return {"status": "started", "mode": "RAM-First (Instant Dev)"}

@router.get("/preview/{doc_id}")
async def preview(doc_id: str, user_id: str):
    # Pour le preview, on regarde d'abord en RAM (plus rapide pour le dev)
    if user_id in SESSIONS:
        for f in SESSIONS[user_id]:
            # On vérifie l'ID ou si c'est un UUID temporaire
            if f.get('id') == doc_id or doc_id in f.get('storage_path', ''):
                if 'data_preview' in f:
                    return f['data_preview']
    
    # Fallback Cloud
    doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
    if not doc.exists: raise HTTPException(404)
    return json.loads(bucket.blob(doc.to_dict()['storage_path']).download_as_string())

@router.get("/download/{doc_id}/{format}")
async def download(doc_id: str, format: str, user_id: str):
    # Idem, on essaie de servir depuis la RAM si possible (sauf pour le raw file qui est sur disque/cloud)
    target_data = None
    original_name = "download"
    
    # 1. Check RAM
    if user_id in SESSIONS:
        for f in SESSIONS[user_id]:
             if f.get('id') == doc_id or doc_id in f.get('storage_path', ''):
                original_name = f.get('original_name', 'download')
                if format != 'raw' and 'data_preview' in f:
                    target_data = f['data_preview']
                break
    
    # 2. Check Cloud (si pas en RAM ou si format raw)
    if not target_data and format != 'raw':
        doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
        if doc.exists:
            meta = doc.to_dict()
            original_name = meta.get('original_name', 'download')
            target_data = json.loads(bucket.blob(meta['storage_path']).download_as_string())

    # 3. Serve
    fname = os.path.splitext(original_name)[0]
    
    if format == 'raw':
        # Raw toujours depuis le cloud (ou disque local temporaire si on voulait complexifier, mais Cloud c'est sûr)
        # Note: Si tu veux le raw instantané, il faudrait le garder en RAM binaire, mais ça prendrait trop de place.
        # Pour le RAW, on attend le cloud.
        doc = db.collection('users').document(user_id).collection('configurations').document(doc_id).get()
        if not doc.exists: raise HTTPException(404, "File not fully uploaded yet")
        meta = doc.to_dict()
        return StreamingResponse(io.BytesIO(bucket.blob(meta['raw_file_path']).download_as_string()), media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename={meta['original_name']}"})

    if format == 'json' and target_data:
        return StreamingResponse(io.BytesIO(json.dumps(target_data, default=str).encode()), media_type="application/json", headers={"Content-Disposition": f"attachment; filename={fname}.json"})
    elif format == 'xlsx' and target_data:
        return StreamingResponse(json_to_excel_bytes(target_data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={fname}.xlsx"})
        
    raise HTTPException(404, "File not found or still processing")

@router.get("/download-all/{format}")
async def download_all(format: str, user_id: str):
    # Version simplifiée Cloud-only pour le ZIP global (plus sûr)
    docs = db.collection('users').document(user_id).collection('configurations').stream()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as z:
        for doc in docs:
            meta = doc.to_dict()
            try:
                name = meta.get('original_name', doc.id)
                clean_name = os.path.splitext(name)[0]
                if format == 'raw' and meta.get('raw_file_path'):
                    z.writestr(name, bucket.blob(meta['raw_file_path']).download_as_string())
                elif meta.get('storage_path'):
                    content = json.loads(bucket.blob(meta['storage_path']).download_as_string())
                    if format == 'json': z.writestr(f"{clean_name}.json", json.dumps(content, default=str))
                    elif format == 'xlsx': z.writestr(f"{clean_name}.xlsx", json_to_excel_bytes(content).getvalue())
            except: pass
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=export_all.zip"})
