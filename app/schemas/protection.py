from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class Std51Settings(BaseModel):
    # Factors (Seuils courants)
    factor_I1: float = 1.2
    factor_I2: float = 0.8
    factor_I3: float = 0.8
    factor_I4: float = 1.15
    
    # Time Settings (Specific per threshold)
    time_dial_I1: float = 0.5
    time_dial_I2: float = 0.1  # Souvent plus rapide pour le court-circuit
    time_dial_I3: float = 0.1
    time_dial_I4: float = 0.1
    
    # Legacy/Internal defaults
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
