from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials
import os
import json

# Imports des routeurs
from routers import ingestion, loadflow, protection

app = FastAPI(
    title="Solufuse Electrical Backend",
    version="4.0.0-restored"
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- FIREBASE INIT ---
def init_firebase():
    if not firebase_admin._apps:
        firebase_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
        if firebase_json:
            try:
                cred = credentials.Certificate(json.loads(firebase_json))
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialized via Env Var")
                return
            except: pass
        try:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized via Default")
        except: pass

init_firebase()

# --- BRANCHEMENT ---
app.include_router(ingestion.router) # Contient le vrai process_and_save
app.include_router(loadflow.router)
app.include_router(protection.router)

@app.get("/")
def health_check():
    return {"status": "Online", "service": "Solufuse Backend Restored"}
