
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base

# --- IMPORTS DES ROUTEURS ---
# 1. Administration & Système
from .routers import files, admin, projects, storage_admin
# 2. Cœur de Métier (Business Logic)
# Note: On utilise try/except pour éviter que le build plante si un fichier manque encore
try:
    from .routers import ingestion, loadflow, protection, inrush, extraction
except ImportError as e:
    print(f"WARNING: Business router missing: {e}")
    ingestion = loadflow = protection = inrush = extraction = None

# Initialisation DB
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Solufuse Backend V2", version="2.2.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CABLAGE DES ROUTES (ROUTING) ---

# 1. Gestion de Session & Fichiers (Remplace l'ancien 'session')
app.include_router(files.router, prefix="/session", tags=["Session (Guest)"])

# 2. Administration RBAC & Stockage (Nouveau)
app.include_router(admin.router, prefix="/admin", tags=["Global Admin"])
app.include_router(storage_admin.router, prefix="/admin/storage", tags=["Storage Admin"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])

# 3. Moteurs de Calcul (Ancien Core)
if ingestion: app.include_router(ingestion.router, prefix="/ingestion", tags=["Ingestion"])
if loadflow: app.include_router(loadflow.router, prefix="/loadflow", tags=["Loadflow"])
if protection: app.include_router(protection.router, prefix="/protection", tags=["Protection"])
if inrush: app.include_router(inrush.router, prefix="/inrush", tags=["Inrush"])
if extraction: app.include_router(extraction.router, prefix="/extraction", tags=["Extraction"])

@app.get("/")
def read_root():
    return {
        "status": "Solufuse Backend Operational", 
        "version": "2.2.0",
        "modules_active": [
            "Session", "Admin", "Storage", "Projects",
            "Ingestion", "Loadflow", "Protection", "Inrush"
        ]
    }
