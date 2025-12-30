
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
# Import des routeurs (dont le nouveau debug)
from .routers import files, admin, projects, storage_admin, debug 
# Business logic imports...
try:
    from .routers import ingestion, loadflow, protection, inrush, extraction
except ImportError:
    ingestion = loadflow = protection = inrush = extraction = None

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Solufuse API", version="2.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files.router, prefix="/session", tags=["Session"])
app.include_router(admin.router, prefix="/admin", tags=["Global Admin"])
app.include_router(storage_admin.router, prefix="/admin/storage", tags=["Storage"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(debug.router, prefix="/debug", tags=["Debug"]) # <--- NEW

if ingestion: app.include_router(ingestion.router, prefix="/ingestion", tags=["Ingestion"])
if loadflow: app.include_router(loadflow.router, prefix="/loadflow", tags=["Loadflow"])
if protection: app.include_router(protection.router, prefix="/protection", tags=["Protection"])
if inrush: app.include_router(inrush.router, prefix="/inrush", tags=["Inrush"])
if extraction: app.include_router(extraction.router, prefix="/extraction", tags=["Extraction"])

@app.get("/")
def read_root():
    return {"status": "Online", "debug_mode": True}
