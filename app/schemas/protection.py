from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# New sub-model for Time Dial details
class TimeDialConfig(BaseModel):
    value: float = Field(0.5, description="The numerical Time Multiplier Setting (TMS).")
    curve: str = Field("IEC-S", description="Curve type: VIT, SIT, EIT, DT (Definite Time), etc.")
    comment: Optional[str] = Field(None, description="User comments for documentation.")

class Std51Settings(BaseModel):
    # Factors (Seuils courants)
    factor_I1: float = 1.2
    factor_I2: float = 0.8
    factor_I3: float = 0.8
    factor_I4: float = 1.15
    
    # Time Settings (Rich Objects)
    time_dial_I1: TimeDialConfig = TimeDialConfig(value=0.5, curve="VIT")
    time_dial_I2: TimeDialConfig = TimeDialConfig(value=0.1, curve="DT")
    time_dial_I3: TimeDialConfig = TimeDialConfig(value=0.1, curve="DT")
    time_dial_I4: TimeDialConfig = TimeDialConfig(value=0.1, curve="DT")
    
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
