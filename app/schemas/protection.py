
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class Std51Settings(BaseModel):
    coeff_stab_max: float = 1.2
    coeff_backup_min: float = 0.8
    coeff_sensibilite: float = 0.8
    coeff_inrush_margin: float = 1.15
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
    
    # Champs internes connus
    topology_origin: Optional[str] = None
    debug_info: Optional[str] = None

    # LA SOLUTION MAGIQUE : On autorise n'importe quel autre champ !
    class Config:
        extra = "allow" 

class ProjectConfig(BaseModel):
    settings: GlobalSettings = GlobalSettings()
    transformers: List[TransformerConfig] = []
    links_data: List[LinkData] = []
    plans: List[ProtectionPlan] = []
