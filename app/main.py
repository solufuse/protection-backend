
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import files, admin, projects, storage_admin, debug
from sqlalchemy import text # Required for the DB fix

# [structure:root] : Application entry point with dynamic imports and DB auto-migration.

# --- 1. AUTO-MIGRATION & DATA REPAIR ---
def run_migrations():
    """
    [!] [CRITICAL] Database Repair Kit.
    1. Adds missing columns (is_active, created_at).
    2. Backfills NULL dates with the current timestamp to ensure cleanup scripts work.
    """
    try:
        with engine.connect() as connection:
            # A. Schema Patches
            try:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
            except Exception: pass # Column likely exists

            try:
                connection.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
            except Exception: pass # Column likely exists
            
            # B. Data Backfill (The Fix for your 'null' issue)
            # Sets 'created_at' to NOW for any user who has it as NULL.
            try:
                connection.execute(text("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
                print("✅ [DATA FIX] Null timestamps updated to current time.")
            except Exception as e:
                print(f"ℹ️ [DATA FIX] Info: {e}")

            # C. Active Status Backfill
            try:
                connection.execute(text("UPDATE users SET is_active = 1 WHERE is_active IS NULL"))
            except Exception: pass
                    
            connection.commit()
    except Exception as global_e:
        print(f"⚠️ [MIGRATION ERROR] Failed to patch Database: {global_e}")

# Run repair BEFORE creating the app
run_migrations()

# --- 2. ROBUST IMPORTS ---
try:
    from .routers import ingestion, loadflow, protection, inrush, extraction
except ImportError:
    print("⚠️ [WARNING] Some business modules could not be loaded.")
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

# Core Routes
app.include_router(files.router, prefix="/files", tags=["Files (Standard)"])
app.include_router(admin.router, prefix="/admin", tags=["Global Admin"])
app.include_router(storage_admin.router, prefix="/admin/storage", tags=["Storage"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(debug.router, prefix="/debug", tags=["Debug"])

# Business Routes
if ingestion: app.include_router(ingestion.router)
if loadflow: app.include_router(loadflow.router)
if protection: app.include_router(protection.router)
if inrush: app.include_router(inrush.router)
if extraction: app.include_router(extraction.router)

@app.get("/")
def read_root(): return {"status": "Online", "version": "2.6.0"}
