from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any

class LoadflowSettings(BaseModel):
    # Cible à atteindre (ex: -80 MW)
    target_mw: float = Field(..., description="Valeur cible en MW (ex: -80.0)")
    tolerance_mw: float = Field(0.3, description="Tolérance acceptée (+/-)")
    
    # Si non fourni, l'API cherchera le Bus Type 'SWNG'
    swing_bus_id: Optional[str] = Field(None, description="Nom du bus Swing (Auto-détecté si vide)")
    
    # Liste des transfos à surveiller pour les Taps (ex: ["TX1-A", "TX1-B"])
    tap_transformers_ids: List[str] = Field(default_factory=list, description="IDs des transfos pour lire les Taps")

class LoadflowResultFile(BaseModel):
    filename: str
    is_valid: bool = False # Est-ce un fichier LF1S valide ?
    
    # Résultats trouvés
    swing_bus_found: Optional[str] = None
    mw_flow: Optional[float] = None
    mvar_flow: Optional[float] = None
    
    # Les Taps lus
    taps: Dict[str, float] = {} # {"TX1-A": 5.0, "TX1-B": 5.0}
    
    # Analyse
    delta_target: Optional[float] = None # Ecart par rapport à la cible
    is_winner: bool = False # Si c'est le meilleur fichier
    status_color: str = "red" # green, orange, red

class LoadflowResponse(BaseModel):
    status: str
    best_file: Optional[str] = None
    results: List[LoadflowResultFile]
