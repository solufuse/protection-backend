import os
import json
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

# --- CONFIGURATION ---
# On récupère le token depuis les variables d'environnement (Dokploy)
# Si la variable n'existe pas, on met None (le bypass sera désactivé)
MASTER_TOKEN = os.getenv("MASTER_TOKEN")

# Init Firebase
if not firebase_admin._apps:
    firebase_creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if firebase_creds_json:
        try:
            cred = credentials.Certificate(json.loads(firebase_creds_json))
            firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"⚠️ Erreur JSON Firebase: {e}")
            firebase_admin.initialize_app()
    else:
        firebase_admin.initialize_app()

security = HTTPBearer(auto_error=False)

def get_current_token(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security),
    query_token: Optional[str] = Query(None, alias="token")
) -> str:
    token = None
    
    if auth_header:
        token = auth_header.credentials
    elif query_token:
        token = query_token
    
    if not token:
        raise HTTPException(status_code=401, detail="Token manquant")
    
    # --- LA PORTE DÉROBÉE (Master Token) ---
    # On ne laisse passer que si MASTER_TOKEN est défini et correspond
    if MASTER_TOKEN and token == MASTER_TOKEN:
        return "dev_master_user"

    # --- VÉRIFICATION GOOGLE ---
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception as e:
        # print(f"Auth error: {e}") # Décommenter pour debug
        raise HTTPException(status_code=401, detail="Token invalide")
