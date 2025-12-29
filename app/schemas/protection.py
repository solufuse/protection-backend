from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class Std51Settings(BaseModel):
    # [decision:logic] Updated to match config.json keys (factor_I1..I4)
    factor_I1: float = 1.2
    factor_I2: float = 0.8
    factor_I3: float = 0.8
    factor_I4: float = 1.15
    
    # Legacy/Internal defaults (kept for compatibility logic if needed later)
    selectivity_adder: float = 0.3
    backup_strategy: str = "REMOTE_FLOOR"

class GlobalSettings(BaseModel):
    std_51: Std51Settings = Std51Settings()

class TransformerConfig(BaseModel):
    name: str
    desc: Optional[str] = None
    ratio_iencl: float = 8.0
    tau_ms: float = 100.0

class LinkData(BaseModel):
    id: str
    length_km: float = 0.0
    impedance_zd: str = "0+j0"
    impedance_z0: str = "0+j0"

class ProtectionPlan(BaseModel):
    id: str
    type: str
    
    bus_from: Optional[str] = None 
    bus_to: Optional[str] = None
    
    ct_primary: str = "CT 100/1 A"
    related_source: Optional[str] = None
    active_functions: List[str] = []
    
    # Champs internes
    topology_origin: Optional[str] = None
    debug_info: Optional[str] = None
    meta_data: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow" 

class ProjectConfig(BaseModel):
    settings: GlobalSettings = GlobalSettings()
    transformers: List[TransformerConfig] = []
    links_data: List[LinkData] = []
    plans: List[ProtectionPlan] = []
