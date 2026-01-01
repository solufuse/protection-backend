
import html
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

from ..database import get_db
from ..models import User, Project, ProjectMember, Message
from ..auth import get_current_user, GLOBAL_LEVELS, PROJECT_LEVELS

router = APIRouter()

# --- SCHEMAS ---
class MessageCreate(BaseModel):
    content: str

class MessageView(BaseModel):
    id: int
    content: str
    created_at: datetime
    author_uid: str
    author_username: Optional[str] = None
    author_email: Optional[str] = None 
    author_role: str 
    
    class Config:
        from_attributes = True

# --- SETTINGS ---
COOLDOWN_SECONDS = {"user": 5, "nitro": 1, "moderator": 0, "admin": 0, "super_admin": 0}
CHAR_LIMITS = {"guest": 0, "user": 1000, "nitro": 2000, "moderator": 5000, "admin": 10000, "super_admin": 20000} 

# --- ROUTES ---

@router.get("/{project_id}", response_model=List[MessageView])
def list_messages(project_id: str, limit: int = 50, skip: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not project_id.startswith("PUBLIC_"):
        if GLOBAL_LEVELS.get(user.global_role, 0) < 60: 
            mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
            if not mem: raise HTTPException(403, "Access denied")

    msgs = db.query(Message).filter(Message.project_id == project_id).order_by(desc(Message.created_at)).offset(skip).limit(limit).all()
        
    results = []
    for m in msgs:
        results.append(MessageView(
            id=m.id,
            content=m.content,
            created_at=m.created_at,
            author_uid=m.author.firebase_uid,
            author_username=m.author.username,
            author_email=m.author.email,
            author_role=m.author.global_role
        ))
    return results

@router.post("/{project_id}")
def post_message(project_id: str, msg: MessageCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_role = user.global_role
    if GLOBAL_LEVELS.get(user_role, 0) < 20: raise HTTPException(403, "Guests cannot post.")

    if not project_id.startswith("PUBLIC_"):
        if GLOBAL_LEVELS.get(user_role, 0) < 60:
            if not db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first():
                raise HTTPException(403, "Access denied")
    
    delay = COOLDOWN_SECONDS.get(user_role, 5)
    if delay > 0:
        last_msg = db.query(Message).filter(Message.user_id == user.id).order_by(desc(Message.created_at)).first()
        if last_msg and (datetime.utcnow() - last_msg.created_at).total_seconds() < delay:
            raise HTTPException(429, "Slow down!")

    max_chars = CHAR_LIMITS.get(user_role, 1000) 
    if len(msg.content) > max_chars: raise HTTPException(400, f"Limit: {max_chars} chars.")
    if len(msg.content.strip()) == 0: raise HTTPException(400, "Empty message.")

    new_msg = Message(content=html.escape(msg.content), user_id=user.id, project_id=project_id, created_at=datetime.utcnow())
    db.add(new_msg); db.commit(); db.refresh(new_msg)
    return {"status": "sent", "id": new_msg.id}

@router.delete("/{message_id}")
def delete_message(message_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 1. Find Message
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg: raise HTTPException(404, "Message not found")
    
    # 2. Permissions Check
    
    # A. Author (Always allowed to delete own message)
    if msg.user_id == user.id:
        db.delete(msg); db.commit()
        return {"status": "deleted"}

    # B. Global Staff (Super Admin / Admin)
    if GLOBAL_LEVELS.get(user.global_role, 0) >= 80:
        db.delete(msg); db.commit()
        return {"status": "deleted"}

    # C. Project Staff (Owner / Admin / Moderator of THIS project)
    # Note: Does not apply to PUBLIC_ channels unless user is global staff (handled above)
    if not msg.project_id.startswith("PUBLIC_"):
        # Check membership role
        member = db.query(ProjectMember).filter(
            ProjectMember.project_id == msg.project_id, 
            ProjectMember.user_id == user.id
        ).first()
        
        if member:
            # Allowed roles: owner, admin, moderator
            if member.project_role in ['owner', 'admin', 'moderator']:
                db.delete(msg); db.commit()
                return {"status": "deleted"}

    raise HTTPException(403, "Insufficient permissions to delete this message.")
