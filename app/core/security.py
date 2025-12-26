import os
import json
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

# --- CONFIGURATION ---
# Retrieve token from environment variables (Dokploy)
# If variable doesn't exist, set to None (bypass disabled)
MASTER_TOKEN = os.getenv("MASTER_TOKEN")

# Init Firebase
if not firebase_admin._apps:
    firebase_creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if firebase_creds_json:
        try:
            cred = credentials.Certificate(json.loads(firebase_creds_json))
            firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"⚠️ Firebase JSON Error: {e}")
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
        raise HTTPException(status_code=401, detail="Missing token")
    
    # --- THE BACKDOOR (Master Token) ---
    # Only allow if MASTER_TOKEN is defined and matches
    if MASTER_TOKEN and token == MASTER_TOKEN:
        return "dev_master_user"

    # --- GOOGLE VERIFICATION ---
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception as e:
        # print(f"Auth error: {e}") # Uncomment for debug
        raise HTTPException(status_code=401, detail="Invalid token")
