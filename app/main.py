
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import files, admin, projects, storage_admin, debug 

try:
    from .routers import ingestion, loadflow, protection, inrush, extraction
except ImportError:
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

# Core Routes
app.include_router(files.router, prefix="/session", tags=["Session (Legacy)"])
app.include_router(files.router, prefix="/files", tags=["Files (Standard)"])
app.include_router(admin.router, prefix="/admin", tags=["Global Admin"])
app.include_router(storage_admin.router, prefix="/admin/storage", tags=["Storage"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(debug.router, prefix="/debug", tags=["Debug"])

# Business Routes (No extra prefix if they have one internally)
if ingestion: app.include_router(ingestion.router)
if loadflow: app.include_router(loadflow.router)
if protection: app.include_router(protection.router)
if inrush: app.include_router(inrush.router)
if extraction: app.include_router(extraction.router)

@app.get("/")
def read_root(): return {"status": "Online", "version": "2.6.0"}
