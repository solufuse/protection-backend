from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any

class Std51Settings(BaseModel):
    coeff_stab_max: float = Field(1.2)
    coeff_backup_min: float = Field(0.8)
    coeff_sensibilite: float = Field(0.8)
    coeff_inrush_margin: float = Field(1.15)
    selectivity_adder: float = Field(0.0)
    backup_strategy: str = "REMOTE_FLOOR"

class SelectivitySettings(BaseModel):
    margin_amperemetric: float = Field(300.0)
    coeff_amperemetric: float = Field(1.20)

class GlobalSettings(BaseModel):
    std_51: Std51Settings = Std51Settings()
    selectivity: SelectivitySettings = SelectivitySettings()

class TransformerConfig(BaseModel):
    name: str
    sn_kva: float
    u_kv: float
    ratio_iencl: float
    tau_ms: float

class ProtectionPlan(BaseModel):
    id: str
    title: Optional[str] = None
    type: Literal['INCOMER', 'TRANSFORMER', 'COUPLING', 'FEEDER']
    ct_primary: str
    relay_model: str = "TBD"
    related_source: Optional[str] = None 
    active_functions: List[str] = ["51"]
    bus_from: Optional[str] = None
    bus_to: Optional[str] = None
    
    # TRACEABILITY
    topology_origin: str = Field("unknown", description="config_user or script_topo")
    debug_info: Optional[str] = None
    meta_data: Optional[Dict[str, Any]] = None

class ProjectConfig(BaseModel):
    project_name: str = "Projet Solufuse"
    settings: GlobalSettings = GlobalSettings()
    transformers: List[TransformerConfig] = []
    plans: List[ProtectionPlan] = []
