
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
    author_role: str # To show colors in UI (Admin/Nitro)
    
    class Config:
        from_attributes = True

# --- SETTINGS ---
COOLDOWN_SECONDS = {
    "user": 5,      # Anti-spam standard
    "nitro": 1,     # Fast chat
    "moderator": 0, # No limit
    "admin": 0,
    "super_admin": 0
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
    [+] [INFO] Read messages.
    [decision:logic]
    - PUBLIC_ projects: Readable by everyone (even Guests).
    - Private projects: Readable only by members.
    """
    # 1. Access Control
    if not project_id.startswith("PUBLIC_"):
        # Strict check for private projects
        if GLOBAL_LEVELS.get(user.global_role, 0) < 60: # Staff bypass
            mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
            if not mem:
                raise HTTPException(403, "You do not have access to this private channel.")

    # 2. Fetch Messages (Newest first usually for chat apps, but API often sends oldest first or pagination)
    # Let's return newest first for easy UI handling
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
    [+] [INFO] Post a message.
    [!] [CRITICAL] 
    - Guests blocked.
    - Rate Limit applied based on Role.
    """
    
    # 1. GUEST BLOCK
    user_level = GLOBAL_LEVELS.get(user.global_role, 0)
    if user_level < 20: # 20 is 'user'
        raise HTTPException(403, "Guests cannot post messages. Please register.")

    # 2. MEMBERSHIP CHECK
    if not project_id.startswith("PUBLIC_"):
        if user_level < 60:
            mem = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id).first()
            if not mem:
                raise HTTPException(403, "You are not a member of this private channel.")
    
    # 3. ANTI-SPAM (Rate Limit)
    delay = COOLDOWN_SECONDS.get(user.global_role, 5) # Default 5s
    if delay > 0:
        last_msg = db.query(Message).filter(Message.user_id == user.id)\
            .order_by(desc(Message.created_at)).first()
        
        if last_msg:
            # Calculate time passed
            # Note: created_at is naive or timezone aware depending on config. Assuming UTC.
            now = datetime.utcnow()
            # Safety for TZ issues: if last_msg is 'future' (clock drift), we block just in case or ignore
            diff = (now - last_msg.created_at).total_seconds()
            
            if diff < delay:
                raise HTTPException(429, f"Slow down! Wait {int(delay - diff)}s before posting.")

    # 4. SAVE
    new_msg = Message(
        content=msg.content,
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
    """
    [+] [INFO] Delete message.
    Logic: You can delete your OWN message, or be a Moderator+.
    """
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg: raise HTTPException(404, "Message not found")
    
    is_author = (msg.user_id == user.id)
    is_staff = GLOBAL_LEVELS.get(user.global_role, 0) >= 60
    
    if not (is_author or is_staff):
        raise HTTPException(403, "Cannot delete this message")
        
    db.delete(msg)
    db.commit()
    return {"status": "deleted"}
