from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from app.schemas.inrush_schema import InrushRequest, GlobalInrushResponse
from app.calculations import inrush_calculator
from app.core.security import get_current_token
from app.services import session_manager
import json
import traceback

router = APIRouter(prefix="/inrush", tags=["Inrush Calculation"])

# --- HELPER SÉCURISÉ ---
def get_config_from_session_debug(token: str):
    print(f"🔍 DEBUG: Recherche config pour token={token[:5]}...")
    
    files = session_manager.get_files(token)
    if not files:
        print("❌ DEBUG: Session vide (pas de fichiers).")
        raise HTTPException(status_code=400, detail="Session vide. Uploadez un config.json.")
    
    print(f"📂 DEBUG: Fichiers en session : {list(files.keys())}")
    
    target_content = None
    filename_found = ""
    
    if "config.json" in files:
        target_content = files["config.json"]
        filename_found = "config.json"
    else:
        for name, content in files.items():
            if name.lower().endswith(".json"):
                target_content = content
                filename_found = name
                break
    
    if target_content is None:
        print("❌ DEBUG: Aucun JSON trouvé.")
        raise HTTPException(status_code=404, detail="Aucun 'config.json' trouvé en session.")

    print(f"✅ DEBUG: Fichier trouvé : {filename_found} (Type: {type(target_content)})")

    try:
        # Décodage
        if isinstance(target_content, bytes):
            print("⚙️ DEBUG: Décodage bytes -> utf-8...")
            text_content = target_content.decode('utf-8')
        else:
            text_content = target_content
            
        print(f"📄 DEBUG: Contenu (50 premiers cars) : {text_content[:50]}...")
        
        data = json.loads(text_content)
        print("⚙️ DEBUG: JSON loadé avec succès.")
        
        req = InrushRequest(**data)
        print("⚙️ DEBUG: Validation Pydantic OK.")
        return req
        
    except json.JSONDecodeError as e:
        print(f"❌ DEBUG: Erreur JSON : {e}")
        raise HTTPException(status_code=422, detail=f"Fichier {filename_found} invalide (JSON malformé).")
    except Exception as e:
        print(f"❌ DEBUG: Erreur inattendue dans le parsing : {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur parsing: {str(e)}")

# --- ROUTES ---

@router.post("/calculate", response_model=GlobalInrushResponse)
async def calculate_via_session(token: str = Depends(get_current_token)):
    try:
        print("🚀 DEBUG: Démarrage /calculate (Session)...")
        
        # 1. Récupération Config
        request = get_config_from_session_debug(token)
        
        # 2. Vérification Transformers
        if not request.transformers:
            print("❌ DEBUG: Liste transformers vide.")
            raise HTTPException(status_code=400, detail="Liste transformers vide.")

        print(f"⚙️ DEBUG: Lancement du calcul pour {len(request.transformers)} transfos...")
        
        # 3. Calcul
        data = inrush_calculator.process_inrush_request(request.transformers)
        print("✅ DEBUG: Calcul terminé.")
        
        return {
            "status": "success",
            "source": "session_data",
            "summary": data["summary"],
            "details": data["details"]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        print("🔥 CRITICAL ERROR 🔥")
        traceback.print_exc()
        # On renvoie l'erreur en JSON pour que vous puissiez la lire dans le frontend/swagger
        return JSONResponse(
            status_code=500, 
            content={"status": "error", "detail": str(e), "trace": traceback.format_exc()}
        )

@router.post("/calculate-json", response_model=GlobalInrushResponse)
async def calculate_via_json(
    request: InrushRequest, 
    token: str = Depends(get_current_token)
):
    try:
        data = inrush_calculator.process_inrush_request(request.transformers)
        return {
            "status": "success",
            "source": "json_body",
            "summary": data["summary"],
            "details": data["details"]
        }
    except Exception as e:
         return JSONResponse(status_code=500, content={"detail": str(e)})

@router.post("/calculate-config", response_model=GlobalInrushResponse)
async def calculate_via_file_upload(
    file: UploadFile = File(...),
    token: str = Depends(get_current_token)
):
    try:
        content = await file.read()
        text_content = content.decode('utf-8')
        data_json = json.loads(text_content)
        request = InrushRequest(**data_json)
        data = inrush_calculator.process_inrush_request(request.transformers)
        return {
            "status": "success",
            "source": "file_upload",
            "summary": data["summary"],
            "details": data["details"]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
