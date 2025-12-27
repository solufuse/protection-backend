# Router for Engine Logic
from fastapi import APIRouter

router = APIRouter(
    prefix="/engine",
    tags=["Engine"]
)

@router.get("/")
def read_engine_status():
    return {"status": "Engine module is active"}
