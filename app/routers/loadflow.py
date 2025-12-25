from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app.core.security import get_current_token
from app.core.session_manager import session_store
import os
import zipfile
import io

router = APIRouter(prefix="/loadflow", tags=["Loadflow"])

# --- HELPER: Fonction pour créer un ZIP depuis la RAM ---
def create_zip_from_session(user_id: str, prefix: str = ""):
    if user_id not in session_store or not session_store[user_id]:
        raise HTTPException(status_code=400, detail="Session vide. Uploadez des fichiers d'abord.")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in session_store[user_id].items():
            # On peut filtrer ici si besoin selon la route
            zip_file.writestr(f"{prefix}{filename}", content)
            
    zip_buffer.seek(0)
    
    # Sauvegarde temporaire pour envoi
    temp_path = f"/tmp/export_{user_id}_{prefix}.zip"
    with open(temp_path, "wb") as f:
        f.write(zip_buffer.read())
        
    return temp_path

# ==========================================
# 1. RUN COMMANDS
# ==========================================

@router.post("/run")
async def run_loadflow_session(user_id: str = Depends(get_current_token)):
    """ 1. Run Loadflow Session (Calcul complet) """
    if user_id not in session_store:
        raise HTTPException(status_code=400, detail="Session vide.")
    
    files = session_store[user_id]
    # TODO: Intégrer ici votre logique Python/Pandapower
    
    return {
        "status": "success", 
        "message": "Calcul Loadflow complet terminé.", 
        "files_count": len(files)
    }

@router.post("/run-win")
async def run_loadflow_winners(user_id: str = Depends(get_current_token)):
    """ 2. Run Loadflow Winners Only (Optimisation) """
    if user_id not in session_store:
        raise HTTPException(status_code=400, detail="Session vide.")
        
    # TODO: Logique spécifique Winners
    return {
        "status": "success", 
        "mode": "winners_only", 
        "message": "Calcul Winners terminé."
    }

# ==========================================
# 2. EXPORT COMMANDS
# ==========================================

@router.get("/export")
async def export_all_files(user_id: str = Depends(get_current_token)):
    """ 3. Export All Files (Tout télécharger) """
    path = create_zip_from_session(user_id, prefix="ALL_")
    return FileResponse(path, media_type="application/zip", filename="full_export.zip")

@router.get("/export-win")
async def export_winners_flat(user_id: str = Depends(get_current_token)):
    """ 4. Export Winners Flat (Résultats à plat) """
    # Pour l'instant, on renvoie tout (simulation), plus tard on filtrera
    path = create_zip_from_session(user_id, prefix="WIN_FLAT_")
    return FileResponse(path, media_type="application/zip", filename="winners_flat.zip")

@router.get("/export-l1fs")
async def export_winners_l1fs(user_id: str = Depends(get_current_token)):
    """ 5. Export Winners L1Fs (Format L1F spécifique) """
    path = create_zip_from_session(user_id, prefix="L1FS_")
    return FileResponse(path, media_type="application/zip", filename="winners_l1fs.zip")
