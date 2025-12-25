from pydantic import BaseModel, Field
from typing import List, Dict, Optional

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
    sn_kva: float
    u_kv: float
    ratio_iencl: float
    tau_ms: float
    i_nominal: float
    i_peak: float
    decay_curve_rms: Dict[str, float]

# --- NOUVEAUX MODÈLES POUR LE TOTAL ---
class InrushSummary(BaseModel):
    total_curve_rms: Dict[str, float] = Field(..., description="Somme de TOUS les transfos")
    hv_curve_rms: Dict[str, float] = Field(..., description="Somme des transfos > 50kV")
    hv_transformers_list: List[str] = Field(..., description="Liste des transfos considérés comme HV")

class GlobalInrushResponse(BaseModel):
    status: str
    count: int
    summary: InrushSummary  # <--- Le résumé global
    details: List[InrushResult] # <--- Les détails par transfo
