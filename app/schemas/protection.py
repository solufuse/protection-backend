from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# --- SUB-SCHEMAS ---

class Std51Settings(BaseModel):
    factor_I1: float = 1.2
    factor_I2: float = 0.8
    factor_I3: float = 0.8
    factor_I4: float = 1.15
    # coeff_stab_max is intentionally removed

class TransformerData(BaseModel):
    name: str
    sn_kva: float
    u_kv: float
    ratio_iencl: float
    tau_ms: float

class LinkData(BaseModel):
    id: str
    length_km: float
    impedance_zd: str
    impedance_z0: str

class LoadFlowSettings(BaseModel):
    target_mw: float
    tolerance_mw: float

# --- MAIN SCHEMAS (Required by ansi_51.py) ---

class GlobalSettings(BaseModel):
    std_51: Optional[Std51Settings] = None

class ProtectionPlan(BaseModel):
    id: str
    title: str
    type: str
    ct_primary: Optional[str] = None
    related_source: Optional[str] = None
    active_functions: List[str] = []
    bus_from: Optional[str] = None
    bus_to: Optional[str] = None

class ProjectConfig(BaseModel):
    project_name: Optional[str] = None
    settings: Optional[GlobalSettings] = None
    transformers: List[TransformerData] = []
    plans: List[ProtectionPlan] = []
    loadflow_settings: Optional[LoadFlowSettings] = None
    links_data: List[LinkData] = []
    standard: str = "IEC"
    frequency: float = 50.0

# --- BASE SCHEMAS ---

class ProtectionBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class ProtectionCreate(ProtectionBase):
    pass

class Protection(ProtectionBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
