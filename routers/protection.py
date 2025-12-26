from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/protection", tags=["Protection & Coordination"])

@router.post("/coordination")
def check_selectivity():
    # ⚠️ Place ici ton code ou appelle ta fonction restaurée
    return {"status": "Not implemented yet - Paste your code in modules/"}
