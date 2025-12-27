from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import ingestion, session, monitor

app = FastAPI(title="Solufuse Backend Hybride", version="3.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion.router)
app.include_router(session.router)
app.include_router(monitor.router)

# --- FIX ICI : On autorise HEAD pour les health-checks ---
@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {"status": "online", "mode": "Hybrid (Cloud + RAM)"}
