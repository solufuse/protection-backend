from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class TimeDialConfig(BaseModel):
    value: float = Field(0.5, description="TMS Value")
    curve: str = Field("IEC-S", description="Curve Type")
    comment: Optional[str] = None

class Std51Settings(BaseModel):
    factor_I1: float = 1.2
    factor_I2: float = 0.8
    factor_I3: float = 0.8
    factor_I4: float = 6.0  # Default High Set

    time_dial_I1: TimeDialConfig = TimeDialConfig(value=0.5, curve="VIT")
    time_dial_I2: TimeDialConfig = TimeDialConfig(value=0.1, curve="DT")
    time_dial_I3: TimeDialConfig = TimeDialConfig(value=0.1, curve="DT")
    time_dial_I4: TimeDialConfig = TimeDialConfig(value=0.05, curve="DT")

# New container for typed settings
class Ansi51Category(BaseModel):
    transformer: Std51Settings = Std51Settings()
    incomer: Std51Settings = Std51Settings(factor_I1=1.0) # Default sensible for Incomer
    coupling: Std51Settings = Std51Settings(factor_I1=1.0) # Default sensible for Coupling

class GlobalSettings(BaseModel):
    # Replaced single 'std_51' with categorised 'ansi_51'
    ansi_51: Ansi51Category = Ansi51Category()

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
