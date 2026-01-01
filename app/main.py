
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
# [!] [INFO] Add messages router import
from .routers import files, admin, projects, storage_admin, debug, users, messages
from sqlalchemy import text 

# --- AUTO-MIGRATION ---
def run_migrations():
    try:
        with engine.connect() as connection:
            # Columns Checks (Users)
            try: connection.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
            except: pass 
            try: connection.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
            except: pass 
            try: connection.execute(text("ALTER TABLE users ADD COLUMN ban_reason VARCHAR"))
            except: pass
            try: connection.execute(text("ALTER TABLE users ADD COLUMN admin_notes TEXT"))
            except: pass
            # Profile
            try: connection.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR"))
            except: pass
            try: connection.execute(text("ALTER TABLE users ADD COLUMN first_name VARCHAR"))
            except: pass
            try: connection.execute(text("ALTER TABLE users ADD COLUMN last_name VARCHAR"))
            except: pass
            try: connection.execute(text("ALTER TABLE users ADD COLUMN bio VARCHAR"))
            except: pass
            try: connection.execute(text("ALTER TABLE users ADD COLUMN birth_date DATE"))
            except: pass
            # Projects
            try: connection.execute(text("ALTER TABLE projects ADD COLUMN owner_id VARCHAR"))
            except: pass
            # Cleanup
            try: connection.execute(text("UPDATE users SET is_active = 1 WHERE is_active IS NULL"))
            except: pass
            connection.commit()
            print("✅ Database Schema Synced")
    except Exception as e:
        print(f"Migration Log: {e}")

run_migrations()

# --- IMPORTS ---
try:
    from .routers import ingestion, loadflow, protection, inrush, extraction
except ImportError:
    ingestion = loadflow = protection = inrush = extraction = None

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Solufuse API", version="2.9.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files.router, prefix="/files", tags=["Files"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(users.router, prefix="/users", tags=["Users (Profile)"])
# [+] [INFO] New Forum Router
app.include_router(messages.router, prefix="/messages", tags=["Forum Messages"])
app.include_router(admin.router, prefix="/admin", tags=["Global Admin"])
app.include_router(storage_admin.router, prefix="/admin/storage", tags=["Storage"])
app.include_router(debug.router, prefix="/debug", tags=["Debug"])

if ingestion: app.include_router(ingestion.router)
if loadflow: app.include_router(loadflow.router)
if protection: app.include_router(protection.router)
if inrush: app.include_router(inrush.router)
if extraction: app.include_router(extraction.router)

@app.get("/")
def read_root(): return {"status": "Online", "version": "2.9.3"}

@app.get("/health")
def health_check(): return {"status": "ok"}
