from fastapi import APIRouter
from app.core import security
router = APIRouter(prefix="/auth", tags=["Auth"])
@router.post("/login")
def login():
    token = security.create_access_token(data={"sub": "guest"})
    return {"access_token": token, "token_type": "bearer"}
