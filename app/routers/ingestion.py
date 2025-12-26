from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime
import os
import json
import uuid
import requests
import tempfile
import shutil
import zipfile  # Nécessaire pour le dézippage

# Import sécurisé de la config Firebase
try:
    from app.firebase_config import db, bucket
except ImportError:
    from firebase_config import db, bucket

router = APIRouter(
    prefix="/ingestion",
    tags=["ingestion"]
)

class IngestionRequest(BaseModel):
    user_id: str
    file_url: str
    file_type: str

# Extensions que l'on accepte d'extraire du ZIP
ALLOWED_EXTENSIONS = {'.json', '.si2s', '.mdb', '.sqlite', '.lf1s', '.xml'}

def process_single_file(user_id, file_path, original_filename):
    """
    Fonction auxiliaire pour traiter UN fichier (qu'il vienne d'un upload direct ou d'un zip).
    Enregistre le résultat dans Storage et crée la fiche dans Firestore.
    """
    try:
        file_ext = os.path.splitext(original_filename)[1].lower()
        
        # 1. Traitement Simulé (ou lecture réelle si JSON)
        print(f"   ⚙️ Processing: {original_filename}")
        
        result_data = {
            "project_name": os.path.splitext(original_filename)[0],
            "source_file": original_filename,
            "processed_at": datetime.utcnow().isoformat(),
            "transformers": [], 
            "plans": []
        }

        # Si c'est un fichier de config JSON, on essaie de le lire
        if file_ext == '.json':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    # On fusionne avec les métadonnées de base
                    if isinstance(content, dict):
                        result_data.update(content)
            except Exception as e:
                print(f"   ⚠️ Warning reading JSON {original_filename}: {e}")

        # 2. Upload du résultat JSON dans Firebase Storage (Dossier 'processed')
        # C'est ce fichier que le Frontend téléchargera pour l'ouvrir
        result_uuid = str(uuid.uuid4())
        result_filename = f"processed/{user_id}/{result_uuid}.json"
        
        blob = bucket.blob(result_filename)
        blob.upload_from_string(
            json.dumps(result_data, default=str), # default=str gère les dates
            content_type='application/json'
        )

        # 3. Création de la fiche dans Firestore
        # Cela permet au fichier d'apparaître dans la liste du Frontend
        doc_ref = db.collection('users').document(user_id).collection('configurations').document()
        doc_ref.set({
            'created_at': datetime.utcnow(),
            'source_type': file_ext.replace('.', ''), # ex: 'json', 'si2s'
            'original_name': original_filename,
            'processed': True,
            'is_large_file': True,
            'storage_path': result_filename,
            'raw_data': None # On garde Firestore léger
        })
        print(f"   ✅ Saved to Firestore: {original_filename}")

    except Exception as e:
        print(f"   ❌ Error processing single file {original_filename}: {e}")

def process_file_task(req: IngestionRequest):
    if not db or not bucket:
        print("❌ ABORT: Firebase non initialisé.")
        return

    temp_dir = tempfile.mkdtemp()
    download_path = os.path.join(temp_dir, f"input_download")
    
    try:
        print(f"📥 Downloading source file for user {req.user_id}...")
        # 1. Téléchargement du fichier source (le ZIP ou le fichier unique)
        with requests.get(req.file_url, stream=True) as r:
            r.raise_for_status()
            with open(download_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # 2. Vérification : Est-ce un ZIP ?
        if zipfile.is_zipfile(download_path):
            print("📦 ZIP detected! Extracting...")
            with zipfile.ZipFile(download_path, 'r') as zip_ref:
                # On parcourt chaque fichier contenu dans le ZIP
                for member in zip_ref.namelist():
                    # On ignore les dossiers cachés MacOS (__MACOSX) et les dossiers
                    if member.startswith('__MACOSX') or member.endswith('/'):
                        continue
                    
                    # On vérifie l'extension
                    _, ext = os.path.splitext(member)
                    if ext.lower() in ALLOWED_EXTENSIONS:
                        # On extrait ce fichier spécifique
                        zip_ref.extract(member, temp_dir)
                        extracted_path = os.path.join(temp_dir, member)
                        
                        # On traite ce fichier extrait comme un nouveau fichier
                        process_single_file(req.user_id, extracted_path, os.path.basename(member))
        else:
            # Ce n'est pas un ZIP, on traite le fichier tel quel
            # On utilise le nom d'origine s'il est dispo dans l'URL, sinon un nom générique
            original_name = "uploaded_file." + req.file_type
            process_single_file(req.user_id, download_path, original_name)

    except Exception as e:
        print(f"❌ Global Error in process task: {e}")
    finally:
        # Nettoyage propre du dossier temporaire
        shutil.rmtree(temp_dir)

@router.post("/process")
async def start_ingestion(req: IngestionRequest, background_tasks: BackgroundTasks):
    if not db:
        raise HTTPException(status_code=500, detail="Firebase Database not connected.")
    
    # On lance le travail en arrière-plan
    background_tasks.add_task(process_file_task, req)
    return {"status": "started", "message": "Extraction and processing started"}

@router.get("/download-all/{format}")
async def download_all(format: str, user_id: str):
    return {"message": "Endpoint not implemented yet"}
