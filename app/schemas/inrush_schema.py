from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Optional, Any

class TransformerInrushParams(BaseModel):
    name: str
    
    # On enlève 'alias="Sn"' ici pour ne pas le rendre obligatoire
    sn_kva: float = Field(..., description="Puissance nominale en kVA (ou Sn)")
    u_kv: float = Field(..., description="Tension nominale en kV (ou Un)")
    
    # Valeurs par défaut
    ratio_iencl: float = Field(8.0, description="Ratio Inrush (Défaut 8)")
    tau_ms: float = Field(400.0, description="Tau (Défaut 400ms)")

    # --- LE NETTOYEUR DE DONNÉES ---
    # Ce validateur s'exécute AVANT que Pydantic ne vérifie les champs.
    # Il normalise les clés (Sn -> sn_kva).
    @model_validator(mode='before')
    @classmethod
    def unify_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Gestion de la Puissance (Sn -> sn_kva)
            if 'Sn' in data and 'sn_kva' not in data:
                data['sn_kva'] = data['Sn']
            
            # Gestion de la Tension (Un -> u_kv)
            if 'Un' in data and 'u_kv' not in data:
                data['u_kv'] = data['Un']
                
            # Gestion des valeurs manquantes (Sécurité supplémentaire)
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
