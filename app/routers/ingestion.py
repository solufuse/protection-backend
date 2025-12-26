from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime
import os
import json
import uuid
import requests
import tempfile
import shutil

# On importe nos outils Firebase configurés
try:
    from app.firebase_config import db, bucket
except ImportError:
    from firebase_config import db, bucket

router = APIRouter()

class IngestionRequest(BaseModel):
    user_id: str
    file_url: str
    file_type: str

def process_file_task(req: IngestionRequest):
    """
    Tâche en arrière-plan pour ne pas bloquer l'API.
    """
    temp_dir = tempfile.mkdtemp()
    local_path = os.path.join(temp_dir, f"input.{req.file_type}")
    
    try:
        print(f"📥 Downloading file for user {req.user_id}...")
        # 1. Télécharger le fichier depuis l'URL Firebase (signée ou publique)
        with requests.get(req.file_url, stream=True) as r:
            r.raise_for_status()
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # 2. Traitement / Conversion (Simulation pour l'instant)
        # ICI TU METTRAS TA LOGIQUE DE PARSING (MDB, SI2S...)
        print("⚙️ Processing file...")
        
        # Simulation d'un résultat JSON
        result_data = {
            "project_name": "Imported Project",
            "source_file": req.file_url,
            "processed_at": datetime.now().isoformat(),
            "transformers": [{"name": "TX1", "sn_kva": 1000}], # Exemple
            "plans": []
        }
        
        # Si c'est un vrai JSON uploadé, on le lit
        if req.file_type == 'json':
            try:
                with open(local_path, 'r') as f:
                    result_data = json.load(f)
            except: pass

        # 3. Sauvegarder le JSON résultat dans Storage
        result_filename = f"processed/{req.user_id}/{uuid.uuid4()}.json"
        blob = bucket.blob(result_filename)
        blob.upload_from_string(json.dumps(result_data), content_type='application/json')
        print(f"💾 Result uploaded to {result_filename}")

        # 4. Créer la fiche dans Firestore (C'est ÇA qui fait apparaître la ligne sur le site)
        doc_ref = db.collection('users').document(req.user_id).collection('configurations').document()
        doc_ref.set({
            'created_at': firestore.SERVER_TIMESTAMP,
            'source_type': req.file_type,
            'original_name': 'Uploaded File',
            'processed': True,
            'is_large_file': True,
            'storage_path': result_filename, # Lien vers le JSON complet
            'raw_data': None # On ne met pas tout le JSON ici pour ne pas alourdir Firestore
        })
        print("✅ Firestore document created!")

    except Exception as e:
        print(f"❌ Error processing file: {e}")
        # Optionnel : Mettre à jour Firestore avec un statut d'erreur
    finally:
        shutil.rmtree(temp_dir)

@router.post("/process")
async def start_ingestion(req: IngestionRequest, background_tasks: BackgroundTasks):
    """
    Endpoint appelé par le Frontend après l'upload.
    """
    # On lance le traitement en tâche de fond pour répondre tout de suite au Frontend
    background_tasks.add_task(process_file_task, req)
    return {"status": "started", "message": "Processing started in background"}

@router.get("/download-all/{format}")
async def download_all(format: str, user_id: str):
    # TODO: Implémenter la logique ZIP ici
    return {"message": "Not implemented yet, but connected!"}
