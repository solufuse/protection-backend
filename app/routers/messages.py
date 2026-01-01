
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
    author_role: str 
    
    class Config:
        from_attributes = True

# --- SETTINGS (LIMITS) ---

# 1. Anti-Spam (Time between messages)
COOLDOWN_SECONDS = {
    "user": 5,      
    "nitro": 1,     
    "moderator": 0, 
    "admin": 0,
    "super_admin": 0
}

# 2. Character Limits (Length of message)
CHAR_LIMITS = {
    "guest": 0,      # Cannot post anyway
    "user": 200,     # Standard limit
    "nitro": 500,    # Paid perk
    "moderator": 2000,
    "admin": 4000,
    "super_admin": 5000
}

# --- ROUTES ---

@router.get("/{project_id}", response_model=List[MessageView])
def list_messages(
    project_id: str, 
    limit: int = 50, 
    skip: int = 0,
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Read messages safely.
    """
    # Access Control
    if not project_id.startswith("PUBLIC_"):
        if GLOBAL_LEVELS.get(user.global_role, 0) < 60: 
            mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
            if not mem:
                raise HTTPException(403, "You do not have access to this private channel.")

    # Fetch
    msgs = db.query(Message).filter(Message.project_id == project_id)\
        .order_by(desc(Message.created_at))\
        .offset(skip).limit(limit).all()
        
    results = []
    for m in msgs:
        results.append(MessageView(
            id=m.id,
            content=m.content,
            created_at=m.created_at,
            author_uid=m.author.firebase_uid,
            author_username=m.author.username,
            author_role=m.author.global_role
        ))
    
    return results

@router.post("/{project_id}")
def post_message(
    project_id: str, 
    msg: MessageCreate, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    [+] [INFO] Post message with strict validation.
    [security]
    1. Check Guest (Ban)
    2. Check Membership (Access)
    3. Check Rate Limit (Spam)
    4. Check Char Limit (Length)
    5. Sanitize HTML (XSS Protection)
    """
    
    user_role = user.global_role
    user_level = GLOBAL_LEVELS.get(user_role, 0)

    # 1. GUEST BLOCK
    if user_level < 20: 
        raise HTTPException(403, "Guests cannot post messages.")

    # 2. MEMBERSHIP CHECK
    if not project_id.startswith("PUBLIC_"):
        if user_level < 60:
            mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
            if not mem:
                raise HTTPException(403, "You are not a member of this private channel.")
    
    # 3. ANTI-SPAM (Time)
    delay = COOLDOWN_SECONDS.get(user_role, 5)
    if delay > 0:
        last_msg = db.query(Message).filter(Message.user_id == user.id)\
            .order_by(desc(Message.created_at)).first()
        if last_msg:
            diff = (datetime.utcnow() - last_msg.created_at).total_seconds()
            if diff < delay:
                raise HTTPException(429, f"Slow down! Wait {int(delay - diff)}s.")

    # 4. [+] [SECURITY] CHARACTER LIMIT CHECK
    max_chars = CHAR_LIMITS.get(user_role, 200) # Default to 200 if role unknown
    if len(msg.content) > max_chars:
        raise HTTPException(400, f"Message too long. Your limit is {max_chars} characters.")

    if len(msg.content.strip()) == 0:
        raise HTTPException(400, "Message cannot be empty.")

    # 5. [+] [SECURITY] XSS SANITIZATION
    # Converts <script> to &lt;script&gt; so it displays as text but doesn't run.
    # SQLAlchemy (db.add) automatically handles SQL Injection protection.
    safe_content = html.escape(msg.content)

    # 6. SAVE
    new_msg = Message(
        content=safe_content,
        user_id=user.id,
        project_id=project_id,
        created_at=datetime.utcnow()
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    
    return {"status": "sent", "id": new_msg.id}

@router.delete("/{message_id}")
def delete_message(
    message_id: int, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg: raise HTTPException(404, "Message not found")
    
    is_author = (msg.user_id == user.id)
    is_staff = GLOBAL_LEVELS.get(user.global_role, 0) >= 60
    
    if not (is_author or is_staff):
        raise HTTPException(403, "Cannot delete this message")
        
    db.delete(msg)
    db.commit()
    return {"status": "deleted"}
