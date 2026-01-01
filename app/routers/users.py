
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import date
from ..database import get_db
from ..models import User
from ..auth import get_current_user

router = APIRouter()

class UserUpdate(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    # birth_date not implemented in frontend yet

@router.get("/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/me")
def update_user_me(data: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 1. Check Username Uniqueness if changed
    if data.username and data.username != user.username:
        existing = db.query(User).filter(User.username == data.username).first()
        if existing:
            raise HTTPException(400, "Username already taken")
        user.username = data.username
    
    # 2. Update other fields
    if data.first_name is not None: user.first_name = data.first_name
    if data.last_name is not None: user.last_name = data.last_name
    if data.bio is not None: user.bio = data.bio
    
    db.commit()
    db.refresh(user)
    return user
