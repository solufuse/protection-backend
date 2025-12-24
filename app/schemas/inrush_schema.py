from pydantic import BaseModel, Field
from typing import List, Dict

class TransformerInrushParams(BaseModel):
    name: str
    sn_kva: float = Field(..., description="Puissance nominale en kVA")
    u_kv: float = Field(..., description="Tension nominale en kV")
    ratio_iencl: float = Field(..., description="Ratio I_inrush / I_nominal")
    tau_ms: float = Field(..., description="Constante de temps d'amortissement en ms")

class InrushRequest(BaseModel):
    transformers: List[TransformerInrushParams]

class InrushResult(BaseModel):
    transformer_name: str
    i_nominal: float
    i_peak: float
    decay_curve: Dict[str, float]
