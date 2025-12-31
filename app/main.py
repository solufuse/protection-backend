
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import files, admin, projects, storage_admin, debug
from sqlalchemy import text # Nécessaire pour le fix

# [structure:root] : Point d'entrée avec gestion d'erreurs d'import et migration DB.

# --- 1. AUTO-MIGRATION (CRITIQUE POUR EVITER LE CRASH) ---
def run_migrations():
    """
    [!] [CRITICAL] Ajoute les colonnes 'is_active' et 'created_at' si manquantes.
    Permet de mettre à jour la DB sans supprimer les utilisateurs existants.
    """
    try:
        with engine.connect() as connection:
            # Fix: is_active
            try:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                print("✅ [MIGRATION] Colonne 'is_active' ajoutée.")
            except Exception as e:
                if "duplicate column" not in str(e).lower(): print(f"ℹ️ [MIGRATION] Info: {e}")

            # Fix: created_at
            try:
                connection.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
                print("✅ [MIGRATION] Colonne 'created_at' ajoutée.")
            except Exception as e:
                if "duplicate column" not in str(e).lower(): print(f"ℹ️ [MIGRATION] Info: {e}")
                    
            connection.commit()
    except Exception as global_e:
        print(f"⚠️ [MIGRATION ERROR] Erreur lors du patch DB: {global_e}")

# Lancer la réparation AVANT de créer l'app
run_migrations()

# --- 2. IMPORTS ROBUSTES (Ta logique) ---
try:
    from .routers import ingestion, loadflow, protection, inrush, extraction
except ImportError:
    print("⚠️ [WARNING] Certains modules business n'ont pas pu être chargés.")
    ingestion = loadflow = protection = inrush = extraction = None

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Solufuse API", version="2.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. ROUTAGE ---

# Core Routes (Système)
app.include_router(files.router, prefix="/files", tags=["Files (Standard)"])
app.include_router(admin.router, prefix="/admin", tags=["Global Admin"])
app.include_router(storage_admin.router, prefix="/admin/storage", tags=["Storage"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(debug.router, prefix="/debug", tags=["Debug"])

# Business Routes (Calculs)
if ingestion: app.include_router(ingestion.router)
if loadflow: app.include_router(loadflow.router)
if protection: app.include_router(protection.router)
if inrush: app.include_router(inrush.router)
if extraction: app.include_router(extraction.router)

@app.get("/")
def read_root(): return {"status": "Online", "version": "2.6.0"}
