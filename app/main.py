from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import ingestion, session, monitor

app = FastAPI(title="Solufuse Backend Hybrid", version="3.1")

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

@app.get("/")
def read_root():
    return {"status": "online", "mode": "Hybrid (Cloud + RAM)"}
