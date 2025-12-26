from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials
import os
import json
import importlib
import pkgutil
import sys

# --- CONFIG ---
app = FastAPI(title="Solufuse Backend API", version="5.0.0-hybrid")

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
                return
            except: pass
        try:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred)
        except: pass

init_firebase()

# --- DYNAMIC ROUTER LOADER ---
# C'est ici la magie : on charge tout ce qui est dans app/routers
def include_routers_automatically():
    from app import routers # On importe le package
    package_path = routers.__path__
    prefix = routers.__name__ + "."

    print(f"🔍 Scanning routers in {package_path}...")

    for _, name, _ in pkgutil.iter_modules(package_path):
        try:
            # On importe le module (ex: app.routers.loadflow)
            module = importlib.import_module(prefix + name)
            
            # On cherche s'il y a un objet 'router' dedans
            if hasattr(module, "router"):
                print(f"✅ Loading router: {name}")
                app.include_router(module.router)
            else:
                print(f"⚠️  Skipping {name}: No 'router' object found.")
        except Exception as e:
            print(f"❌ Error loading module {name}: {e}")

# Lancement du scan
include_routers_automatically()

@app.get("/")
def health_check():
    return {"status": "Online", "mode": "Dynamic Router Loading"}
