from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import system, auth, session, ingestion, engine, protection, inrush, extraction, loadflow

app = FastAPI(title="Solufuse Backend V2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTERS ---
app.include_router(system.router)
app.include_router(auth.router)
app.include_router(session.router)
app.include_router(ingestion.router)
app.include_router(engine.router)
app.include_router(protection.router)  # <--- CRITICAL: Now it is connected!
app.include_router(inrush.router)
app.include_router(extraction.router)
app.include_router(loadflow.router)
