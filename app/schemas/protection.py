from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

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
