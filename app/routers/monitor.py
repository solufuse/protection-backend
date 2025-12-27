from fastapi import APIRouter, HTTPException
from app.firebase_config import db

router = APIRouter(prefix="/monitor", tags=["monitor"])

@router.get("/status/{user_id}")
async def get_monitor_status(user_id: str):
    """
    PROD ENDPOINT: Reads from Firestore.
    Persistent data source.
    """
    try:
        docs = db.collection('users').document(user_id).collection('configurations')\
                 .order_by('created_at', direction='DESCENDING').stream()
        files = []
        for d in docs:
            data = d.to_dict()
            files.append({
                "id": d.id,
                "name": data.get('original_name'),
                "status": "Processed" if data.get('processed') else "Pending"
            })
        return {
            "user_id": user_id,
            "source": "Firestore (Persistent)",
            "count": len(files),
            "files": files
        }
    except Exception as e: raise HTTPException(500, str(e))
