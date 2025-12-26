from firebase_admin import firestore, storage
import json
import uuid

db = firestore.client()

def save_smartly(user_id: str, data: dict, file_type: str) -> str:
    """
    Service: Decides whether to save data to Firestore (if small) or Storage (if large).
    """
    json_str = json.dumps(data)
    size_in_bytes = len(json_str.encode('utf-8'))
    
    # Threshold: 900KB
    LIMIT_BYTES = 900 * 1024 
    
    collection_ref = db.collection("users").document(user_id).collection("configurations")
    
    doc_data = {
        "processed": True,
        "source_type": file_type,
        "created_at": firestore.SERVER_TIMESTAMP,
        "is_large_file": False,
        "storage_path": None,
        "raw_data": None
    }

    if size_in_bytes < LIMIT_BYTES:
        print(f"✅ [Service] Saving small file ({size_in_bytes} bytes) to Firestore.")
        doc_data["raw_data"] = data
        doc_ref = collection_ref.document()
        doc_ref.set(doc_data)
    else:
        print(f"⚠️ [Service] Offloading large file ({size_in_bytes} bytes) to Storage.")
        file_uuid = str(uuid.uuid4())
        blob_path = f"users/{user_id}/processed_results/{file_uuid}.json"
        
        bucket = storage.bucket()
        blob = bucket.blob(blob_path)
        blob.upload_from_string(json_str, content_type='application/json')
        
        doc_data["is_large_file"] = True
        doc_data["storage_path"] = blob_path
        doc_ref = collection_ref.document()
        doc_ref.set(doc_data)
        
    return doc_ref.id

def log_error(user_id: str, error_msg: str, file_url: str):
    """Service: Logs errors to Firestore."""
    error_ref = db.collection("users").document(user_id).collection("errors").document()
    error_ref.set({
        "error": error_msg, 
        "file_url": file_url,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
