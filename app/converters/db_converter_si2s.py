
from app.schemas.protection import ProjectConfig
from typing import Dict, Any, List

class ProtectionConverter:
    """
    Converter class dedicated to Protection & Short-Circuit (SI2S).
    Extracts protection plans, CT ratios, and relay settings.
    """

    def __init__(self, config: ProjectConfig):
        self.config = config

    def get_protection_plans(self) -> List[Any]:
        """
        Returns the list of protection plans (relays) defined in the project.
        """
        return self.config.plans

    def get_global_settings(self) -> Dict[str, Any]:
        """
        Extracts global protection settings (e.g., ANSI 51 standard factors).
        """
        if not self.config.settings:
            return {}
        
        # Return as dict for easier processing by the engine
        return self.config.settings.model_dump() if hasattr(self.config.settings, 'model_dump') else self.config.settings.dict()

    def convert(self) -> Dict[str, Any]:
        """
        Main entry point to get the full dataset for the Protection engine.
        """
        return {
            "plans": self.get_protection_plans(),
            "global_settings": self.get_global_settings(),
            "transformers": self.config.transformers, # Transformers are needed for SC calculation too
            "project_name": self.config.project_name
        }
