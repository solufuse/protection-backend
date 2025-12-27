from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_token
from app.core.memory import SESSIONS

router = APIRouter(prefix="/session", tags=["Session Connectivity"])

@router.get("/details")
async def get_details(token: str = Depends(get_current_token)):
    return {"files": SESSIONS.get(token, [])}

@router.delete("/file/{file_id}")
async def delete_specific_file(file_id: str, token: str = Depends(get_current_token)):
    """ Supprime un fichier précis de la RAM """
    if token in SESSIONS:
        initial_count = len(SESSIONS[token])
        SESSIONS[token] = [f for f in SESSIONS[token] if f['id'] != file_id]
        if len(SESSIONS[token]) < initial_count:
            return {"status": "deleted", "id": file_id}
    raise HTTPException(status_code=404, detail="Fichier non trouvé en RAM")

@router.delete("/clear")
async def clear_session(token: str = Depends(get_current_token)):
    """ Vide TOUTE la RAM de l'utilisateur """
    SESSIONS[token] = []
    return {"status": "cleared", "user_id": token}
