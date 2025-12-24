from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import protection

app = FastAPI(title="Solufuse API V2.1 (Architectured)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(protection.router)

@app.get("/")
def read_root():
    return {"status": "Online", "architecture": "Core + Managers + Services"}
