from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class TransformerData(BaseModel):
    name: str
    sn_kva: float
    u_kv: float
    ratio_iencl: float
    tau_ms: float

class SwingBusInfo(BaseModel):
    bus_id: str
    voltage_pu: float = 1.0
    angle_deg: float = 0.0
    script: Optional[str] = None

class StudyCaseInfo(BaseModel):
    id: str
    config: Optional[str] = None
    revision: Optional[str] = None

class LoadflowSettings(BaseModel):
    target_mw: float = 0.0
    tolerance_mw: float = 0.1

# Compatibility Aliases
LoadFlowSettings = LoadflowSettings
