from pydantic import BaseModel

class LoadflowSettings(BaseModel):
    target_mw: float = 0.0
    tolerance_mw: float = 0.1

# Alias pour supporter les deux casses (LoadFlow / Loadflow)
LoadFlowSettings = LoadflowSettings
