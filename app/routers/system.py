from fastapi import APIRouter
router = APIRouter(tags=["System"])
@router.get("/")
def read_root(): return {"status": "Solufuse API v2 Ready", "repo": "protection-backend"}
@router.get("/health")
def health(): return {"status": "ok"}
