
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# --- GLOBAL SETTINGS (ANSI STD) ---
class Std51Settings(BaseModel):
    coeff_stab_max: float = 1.2
    coeff_backup_min: float = 0.8
    coeff_sensibilite: float = 0.8
    coeff_inrush_margin: float = 1.15
    selectivity_adder: float = 0.3
    backup_strategy: str = "REMOTE_FLOOR"

class GlobalSettings(BaseModel):
    std_51: Std51Settings = Std51Settings()

# --- COMPONENTS ---
class TransformerConfig(BaseModel):
    name: str
    desc: Optional[str] = None
    ratio_iencl: float = 8.0
    tau_ms: float = 100.0

class LinkData(BaseModel):
    id: str
    length_km: float = 0.0
    impedance_zd: str = "0+j0"
    impedance_z0: str = "0+j0"

# --- PLAN ---
class ProtectionPlan(BaseModel):
    id: str
    type: str  # TRANSFORMER, INCOMER, FEEDER...
    bus_from: str
    bus_to: Optional[str] = None
    ct_primary: str = "CT 100/1 A"
    related_source: Optional[str] = None  # Sert à lier un Transfo (TX1) ou un Link (Liaison_RTE)
    active_functions: List[str] = []

# --- ROOT CONFIG ---
class ProjectConfig(BaseModel):
    settings: GlobalSettings = GlobalSettings()
    transformers: List[TransformerConfig] = []
    links_data: List[LinkData] = []  # <--- C'EST CETTE LIGNE QUI MANQUAIT OU N'ETAIT PAS PRISE EN COMPTE
    plans: List[ProtectionPlan] = []
