import os
import json
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

# --- CONFIGURATION ---
# Ta clé secrète pour le développement (Bypass Google)
MASTER_TOKEN = "sk_dev_9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b"

# Init Firebase (si pas déjà fait)
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
    
    # 1. On cherche le token dans le Header ou l'URL
    if auth_header:
        token = auth_header.credentials
    elif query_token:
        token = query_token
    
    if not token:
        raise HTTPException(status_code=401, detail="Token manquant")
    
    # --- 2. LA PORTE DÉROBÉE (Master Token) ---
    # Si le token correspond à ta clé dev, on laisse passer !
    if token == MASTER_TOKEN:
        return "dev_master_user" # On renvoie un faux ID utilisateur

    # --- 3. SINON, VÉRIFICATION GOOGLE ---
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Token invalide")
