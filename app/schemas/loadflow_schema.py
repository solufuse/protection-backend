from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class LoadflowSettings(BaseModel):
    """
    Configuration settings for the Loadflow Analysis logic.
    """
    target_mw: float = Field(..., description="Target Active Power (MW) value to reach at the Swing Bus (e.g., -80.0).")
    tolerance_mw: float = Field(0.3, description="Acceptable tolerance range (+/- MW) around the target.")
    swing_bus_id: Optional[str] = Field(None, description="Name of the Swing Bus to monitor (e.g., 'Bus RTE 1'). If null, auto-detection is attempted.")
    tap_transformers_ids: List[str] = Field(default_factory=list, description="Deprecated. The script now auto-scans all transformers.")

class SwingBusInfo(BaseModel):
    config: Optional[str] = Field(None, description="The Swing Bus name requested in the configuration.")
    script: Optional[str] = Field(None, description="The Swing Bus name actually found and used in the file.")

class StudyCaseInfo(BaseModel):
    id: Optional[str] = Field(None, description="Study Case ID (e.g., 'LF_198').")
    config: Optional[str] = Field(None, description="Configuration name (e.g., 'Normal').")
    revision: Optional[str] = Field(None, description="Revision name (e.g., 'CH199').")

class TransformerData(BaseModel):
    """
    Electrical data extracted for a specific transformer.
    Aliases are used to match the 'Real Names' in the output JSON.
    """
    tap: Optional[float] = Field(None, alias="Tap", description="Tap position.")
    mw: Optional[float] = Field(None, alias="LFMW", description="Active Power flow (MW).")
    mvar: Optional[float] = Field(None, alias="LFMvar", description="Reactive Power flow (Mvar).")
    amp: Optional[float] = Field(None, alias="LFAmp", description="Current flow (Amp).")
    kv: Optional[float] = Field(None, alias="kV", description="Voltage level (kV).")
    volt_mag: Optional[float] = Field(None, alias="VoltMag", description="Voltage Magnitude (%).")
    pf: Optional[float] = Field(None, alias="LFPF", description="Power Factor (%).")

    class Config:
        # Permet d'utiliser data.tap = ... dans le code python tout en sortant "Tap" en JSON
        populate_by_name = True
        allow_population_by_field_name = True

class LoadflowResultFile(BaseModel):
    filename: str = Field(..., description="Name of the analyzed file.")
    is_valid: bool = Field(False, description="True if the file could be parsed successfully.")
    
    study_case: Optional[StudyCaseInfo] = Field(None, description="Scenario metadata (ID, Config, Revision).")
    
    swing_bus_found: Optional[SwingBusInfo] = Field(None, description="Info regarding the Swing Bus detection.")
    mw_flow: Optional[float] = Field(None, description="Active Power measured at the Swing Bus.")
    mvar_flow: Optional[float] = Field(None, description="Reactive Power measured at the Swing Bus.")
    
    # On utilise Dict[str, Any] pour accepter le dictionnaire déjà converti avec les Alias
    transformers: Dict[str, Any] = Field({}, description="Dictionary of transformers found (Key: Transfo ID).")
    
    delta_target: Optional[float] = Field(None, description="Absolute difference between measured MW and target MW.")
    
    is_winner: bool = Field(False, description="True if this file is the best candidate for its specific Scenario group.")
    victory_reason: Optional[str] = Field(None, description="Explanation of why this file won (e.g., 'Precision', 'Validity').")
    status_color: str = Field("red", description="Visual indicator: 'green' (in tolerance), 'orange' (close), 'red' (far).")

class LoadflowResponse(BaseModel):
    status: str = Field(..., description="Execution status ('success' or 'error').")
    best_file: Optional[str] = Field(None, description="Filename of the overall best file (Legacy field).")
    results: List[LoadflowResultFile] = Field(..., description="List of results for all analyzed files.")
