from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# --- CONFIGURATION SCHEMAS ---

# Schema for project-wide protection configuration
# This satisfies the 'from app.schemas.protection import ProjectConfig' requirement
class ProjectConfig(BaseModel):
    project_id: Optional[str] = None
    standard: str = "IEC"  # Default to IEC, could be ANSI
    frequency: float = 50.0
    settings: Optional[Dict[str, Any]] = {}
    description: Optional[str] = None

# --- PROTECTION OBJECT SCHEMAS ---

# Base schema with shared attributes
class ProtectionBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True
    # Add other fields relevant to protection logic here

# Schema for creating a protection (client input)
class ProtectionCreate(ProtectionBase):
    pass

# Schema for updating a protection (all fields optional)
class ProtectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

# Schema for reading a protection (includes DB ID and timestamps)
class Protection(ProtectionBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
