from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Optional, Any

class TransformerInrushParams(BaseModel):
    name: str
    
    # Removing 'alias="Sn"' here to make it optional
    sn_kva: float = Field(..., description="Nominal Power in kVA (or Sn)")
    u_kv: float = Field(..., description="Nominal Voltage in kV (or Un)")
    
    # Default values
    ratio_iencl: float = Field(8.0, description="Inrush Ratio (Default 8)")
    tau_ms: float = Field(400.0, description="Tau (Default 400ms)")

    # --- DATA CLEANER ---
    # This validator runs BEFORE Pydantic verifies fields.
    # It normalizes keys (Sn -> sn_kva).
    @model_validator(mode='before')
    @classmethod
    def unify_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Power Handling (Sn -> sn_kva)
            if 'Sn' in data and 'sn_kva' not in data:
                data['sn_kva'] = data['Sn']
            
            # Voltage Handling (Un -> u_kv)
            if 'Un' in data and 'u_kv' not in data:
                data['u_kv'] = data['Un']
                
            # Missing values handling (Extra security)
            if 'ratio_iencl' not in data:
                data['ratio_iencl'] = 8.0
            if 'tau_ms' not in data:
                data['tau_ms'] = 400.0
                
        return data

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
