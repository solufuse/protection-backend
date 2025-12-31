
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import files, admin, projects, storage_admin, debug
from sqlalchemy import text # Required for the DB fix

# [structure:root] : Application entry point with dynamic imports and DB auto-migration.

# --- 1. AUTO-MIGRATION (CRITICAL FIX) ---
def run_migrations():
    """
    [!] [CRITICAL] Adds 'is_active' and 'created_at' columns if they are missing.
    This allows updating the DB schema without deleting existing users or the database file.
    """
    try:
        with engine.connect() as connection:
            # Fix: is_active
            try:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                print("✅ [MIGRATION] Column 'is_active' successfully added.")
            except Exception as e:
                # If error contains "duplicate column", it means it's already there.
                if "duplicate column" not in str(e).lower(): print(f"ℹ️ [MIGRATION] Info: {e}")

            # Fix: created_at
            try:
                connection.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
                print("✅ [MIGRATION] Column 'created_at' successfully added.")
            except Exception as e:
                if "duplicate column" not in str(e).lower(): print(f"ℹ️ [MIGRATION] Info: {e}")
                    
            connection.commit()
    except Exception as global_e:
        print(f"⚠️ [MIGRATION ERROR] Failed to patch Database: {global_e}")

# Run repair BEFORE creating the app
run_migrations()

# --- 2. ROBUST IMPORTS (Business Logic) ---
try:
    from .routers import ingestion, loadflow, protection, inrush, extraction
except ImportError:
    print("⚠️ [WARNING] Some business modules could not be loaded (missing files?).")
    ingestion = loadflow = protection = inrush = extraction = None

# Ensure standard tables exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Solufuse API", version="2.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. ROUTING ---

# Core Routes (System & Admin)
app.include_router(files.router, prefix="/files", tags=["Files (Standard)"])
app.include_router(admin.router, prefix="/admin", tags=["Global Admin"])
app.include_router(storage_admin.router, prefix="/admin/storage", tags=["Storage"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(debug.router, prefix="/debug", tags=["Debug"])

# Business Routes (Calculation Engines)
if ingestion: app.include_router(ingestion.router)
if loadflow: app.include_router(loadflow.router)
if protection: app.include_router(protection.router)
if inrush: app.include_router(inrush.router)
if extraction: app.include_router(extraction.router)

@app.get("/")
def read_root(): return {"status": "Online", "version": "2.6.0"}
