
import os
import json
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

# --- CONFIGURATION FIREBASE ---
# Initialisation unique de l'application Firebase Admin
if not firebase_admin._apps:
    firebase_creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if firebase_creds_json:
        try:
            cred = credentials.Certificate(json.loads(firebase_creds_json))
            firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"⚠️ Erreur JSON Firebase: {e}")
            # Fallback (utile si hébergé sur Google Cloud Run par exemple)
            firebase_admin.initialize_app()
    else:
        firebase_admin.initialize_app()

security = HTTPBearer(auto_error=False)

def get_current_token(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security),
    query_token: Optional[str] = Query(None, alias="token")
) -> str:
    """
    Vérifie le token JWT Firebase.
    Renvoie l'UID de l'utilisateur si le token est valide.
    Rejette toute autre tentative.
    """
    token = None
    
    # 1. Extraction du token (Header Bearer OU paramètre URL ?token=...)
    if auth_header:
        token = auth_header.credentials
    elif query_token:
        token = query_token
    
    if not token:
        raise HTTPException(status_code=401, detail="Token d'authentification manquant")
    
    # 2. Vérification stricte via Firebase
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception as e:
        # En production, on évite de renvoyer l'erreur exacte pour ne pas aider l'attaquant
        # print(f"Auth error: {e}") 
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
