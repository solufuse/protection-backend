
from app.schemas.protection import ProjectConfig
from typing import Dict, Any, List

class LoadFlowConverter:
    """
    Converter class dedicated to Load Flow (LF1S) requirements.
    Extracts topology and parameters specifically for power flow analysis.
    """

    def __init__(self, config: ProjectConfig):
        self.config = config

    def get_loadflow_settings(self) -> Dict[str, Any]:
        """
        Extracts simulation parameters (target MW, tolerance).
        """
        if not self.config.loadflow_settings:
            # Return default values if missing in JSON
            return {"target_mw": 0.0, "tolerance_mw": 0.1}
        
        return {
            "target_mw": self.config.loadflow_settings.target_mw,
            "tolerance_mw": self.config.loadflow_settings.tolerance_mw
        }

    def get_network_components(self) -> Dict[str, List[Any]]:
        """
        Extracts physical components relevant to Load Flow (Transformers, Links).
        """
        return {
            "transformers": self.config.transformers,
            "links": self.config.links_data,
            # Add sources or loads if available in future schemas
        }

    def convert(self) -> Dict[str, Any]:
        """
        Main entry point to get the full dataset for the Load Flow engine.
        """
        return {
            "settings": self.get_loadflow_settings(),
            "topology": self.get_network_components(),
            "project_name": self.config.project_name
        }
