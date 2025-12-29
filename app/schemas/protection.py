from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class Std51Settings(BaseModel):
    factor_I1: float = 1.2
    factor_I2: float = 0.8
    factor_I3: float = 0.8
    factor_I4: float = 1.15
    # coeff_stab_max has been removed as requested

class ProjectConfig(BaseModel):
    project_name: Optional[str] = None
    settings: Optional[Any] = None
    transformers: List[Any] = []
    plans: List[Any] = []
    loadflow_settings: Optional[Any] = None
    links_data: List[Any] = []
