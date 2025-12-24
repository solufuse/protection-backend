from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

SECRET_KEY = "SOLUFUSE_SUPER_SECRET_KEY_PHASE1"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 
MASTER_TOKEN = "solufuse-dev-token"

# On met auto_error=False pour gérer nous-mêmes l'absence de header
security = HTTPBearer(auto_error=False)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_token(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security),
    query_token: Optional[str] = Query(None, alias="token", description="Token d'accès (alternative au Header)")
):
    """
    Récupère le token depuis le Header Authorization OU depuis l'URL (?token=...)
    """
    token = None
    
    # 1. Priorité au Header
    if auth_header:
        token = auth_header.credentials
    # 2. Sinon, on regarde l'URL
    elif query_token:
        token = query_token
    
    if not token:
        raise HTTPException(status_code=401, detail="Token manquant (Header ou URL)")
    
    # 3. Validation
    if token == MASTER_TOKEN:
        return token
        
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return token
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
