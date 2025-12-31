
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import files, admin, projects, storage_admin, debug 

# Business logic imports
try:
    from .routers import ingestion, loadflow, protection, inrush, extraction
except ImportError:
    ingestion = loadflow = protection = inrush = extraction = None

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Solufuse API", version="2.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SYSTEM ROUTERS (Ceux que j'ai créés sans préfixe interne) ---
# Eux, ils ont BESOIN du préfixe ici
app.include_router(files.router, prefix="/session", tags=["Session (Legacy)"])
app.include_router(files.router, prefix="/files", tags=["Files (Standard)"])
app.include_router(admin.router, prefix="/admin", tags=["Global Admin"])
app.include_router(storage_admin.router, prefix="/admin/storage", tags=["Storage"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(debug.router, prefix="/debug", tags=["Debug"])

# --- BUSINESS ROUTERS (Ceux qui ont déjà leur préfixe interne) ---
# [FIX] On enlève 'prefix=...' car ils l'ont déjà dans leur fichier respectif
if ingestion: app.include_router(ingestion.router) 
if loadflow: app.include_router(loadflow.router)
if protection: app.include_router(protection.router)
if inrush: app.include_router(inrush.router)
if extraction: app.include_router(extraction.router)

@app.get("/")
def read_root():
    return {"status": "Online", "routing_fix": "Applied"}
