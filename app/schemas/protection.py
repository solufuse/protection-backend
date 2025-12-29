from pydantic import BaseModel
from typing import Optional, List, Any

class Std51Settings(BaseModel):
    # Alignement exact sur ton config.json
    factor_I1: float = 1.2
    factor_I2: float = 0.8
    factor_I3: float = 0.8
    factor_I4: float = 1.15

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
    transformers: List[Any] = []
    plans: List[ProtectionPlan] = []
    loadflow_settings: Optional[Any] = None
    links_data: List[Any] = []
