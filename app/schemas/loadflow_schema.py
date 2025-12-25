from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any

class LoadflowSettings(BaseModel):
    target_mw: float = Field(..., description="Valeur cible en MW")
    tolerance_mw: float = Field(0.3, description="Tolérance (+/-)")
    swing_bus_id: Optional[str] = Field(None, description="Bus Swing")
    tap_transformers_ids: List[str] = Field(default_factory=list)

# NOUVEAU : Objet détaillé pour chaque transfo
class TransformerData(BaseModel):
    tap: Optional[float] = None
    mw: Optional[float] = None
    mvar: Optional[float] = None
    amp: Optional[float] = None
    kv: Optional[float] = None
    volt_mag: Optional[float] = None
    pf: Optional[float] = None

class LoadflowResultFile(BaseModel):
    filename: str
    is_valid: bool = False
    
    swing_bus_found: Optional[str] = None
    mw_flow: Optional[float] = None
    mvar_flow: Optional[float] = None
    
    # NOUVEAU : Dictionnaire complet
    transformers: Dict[str, TransformerData] = {} 
    
    delta_target: Optional[float] = None
    is_winner: bool = False
    status_color: str = "red"

class LoadflowResponse(BaseModel):
    status: str
    best_file: Optional[str] = None
    results: List[LoadflowResultFile]
