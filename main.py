from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials
import os
import json

# Import the new router
from routers import processor

# --- CONFIGURATION & INIT ---

app = FastAPI(title="Solufuse Backend API", version="1.4.0")

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
        # Dokploy Env Var Strategy
        firebase_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
        if firebase_json:
            try:
                print("🔑 Attempting to load credentials from env var...")
                cred_dict = json.loads(firebase_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialized via FIREBASE_CREDENTIALS_JSON")
                return
            except Exception as e:
                print(f"❌ Error loading Firebase JSON from env: {e}")
        
        # Cloud Run / Default Strategy
        try:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized via ApplicationDefault")
        except Exception as e:
            print(f"❌ Failed to init Firebase: {e}")
            raise RuntimeError("Could not initialize Firebase Credentials.")

init_firebase()

# --- ROUTERS INCLUSION ---
# This is where you plug in your modules.
# The processor routes will be available at /files/process
app.include_router(processor.router)

@app.get("/")
def health_check():
    return {"status": "ok", "service": "Solufuse Backend", "router_mode": "active"}
