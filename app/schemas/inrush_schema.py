from pydantic import BaseModel, Field, validator
from typing import List, Dict, Optional, Any

class TransformerInrushParams(BaseModel):
    name: str
    
    # On accepte sn_kva, mais aussi 'Sn' ou 'power_kva' via alias
    sn_kva: float = Field(..., alias="Sn", description="Puissance nominale en kVA")
    
    # On accepte u_kv, mais aussi 'Un' ou 'voltage_kv'
    u_kv: float = Field(..., alias="Un", description="Tension nominale en kV")
    
    # --- VALEURS PAR DÉFAUT (Pour éviter le crash si manquant) ---
    ratio_iencl: float = Field(8.0, description="Ratio I_inrush / I_nominal (Défaut: 8.0)")
    tau_ms: float = Field(400.0, description="Constante de temps ms (Défaut: 400.0)")

    # Cette config permet d'utiliser les noms d'alias (Sn/Un) OU les noms réels
    class Config:
        allow_population_by_field_name = True
        extra = "ignore"  # On ignore les champs en trop (ex: ID, type...)

    # Validateur de secours : si sn_kva est manquant mais qu'un autre champ ressemble
    @validator('sn_kva', pre=True, check_fields=False)
    def check_sn(cls, v, values):
        if v is None: return 0.0
        return v

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

class InrushSummary(BaseModel):
    total_curve_rms: Dict[str, float]
    hv_curve_rms: Dict[str, float]
    hv_transformers_list: List[str]

class GlobalInrushResponse(BaseModel):
    status: str
    source: Optional[str] = "unknown"
    count: int
    summary: InrushSummary
    details: List[InrushResult]
