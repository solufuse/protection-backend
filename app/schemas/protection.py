from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

# --- SUB-SCHEMAS (Helpers based on config.json) ---

class Std51Settings(BaseModel):
    # Settings specific to ANSI 51 calculation
    factor_I1: float = 1.2
    factor_I2: float = 0.8
    factor_I3: float = 0.8
    factor_I4: float = 1.15

class TransformerData(BaseModel):
    # Transformer characteristics
    name: str
    sn_kva: float
    u_kv: float
    ratio_iencl: float
    tau_ms: float

class LinkData(BaseModel):
    # Network link characteristics (cables, lines)
    id: str
    length_km: float
    impedance_zd: str
    impedance_z0: str

class LoadFlowSettings(BaseModel):
    # Settings for load flow calculation
    target_mw: float
    tolerance_mw: float

# --- MAIN SCHEMAS (Required by Imports) ---

class GlobalSettings(BaseModel):
    # Maps to the "settings" key in config.json
    std_51: Optional[Std51Settings] = None

class ProtectionPlan(BaseModel):
    # Maps to items in the "plans" list in config.json
    id: str
    title: str
    type: str  # e.g., TRANSFORMER, COUPLING, INCOMER
    ct_primary: Optional[str] = None
    related_source: Optional[str] = None
    active_functions: List[str] = []
    bus_from: Optional[str] = None
    bus_to: Optional[str] = None

# --- ROOT CONFIGURATION SCHEMA ---

class ProjectConfig(BaseModel):
    # Represents the entire config.json structure
    project_name: Optional[str] = None
    settings: Optional[GlobalSettings] = None
    transformers: List[TransformerData] = []
    plans: List[ProtectionPlan] = []
    loadflow_settings: Optional[LoadFlowSettings] = None
    links_data: List[LinkData] = []
    
    # Generic fields kept for backward compatibility if needed
    standard: str = "IEC"
    frequency: float = 50.0
    description: Optional[str] = None

# --- DB / API INTERFACE SCHEMAS ---
# Kept to avoid breaking database related routes

class ProtectionBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class ProtectionCreate(ProtectionBase):
    pass

class ProtectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class Protection(ProtectionBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
