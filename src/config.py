import os
import json
from typing import Dict, Any

class ConfigManager:
    """
    Manages application settings, API keys, and model preferences.
    Loads from 'config.json' or Environment Variables.
    """
    
    DEFAULT_CONFIG = {
        "ai_provider": "openai",
        "ai_model": "gpt-4-turbo",
        "api_key": "", # User must provide
        "api_base_url": "https://api.openai.com/v1", # Change for OpenRouter/LocalAI
        "analysis": {
            "critical_float_threshold": 0,
            "slippage_threshold_days": 5
        }
    }
    
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load JSON or fallback to defaults."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return {**self.DEFAULT_CONFIG, **json.load(f)}
            except Exception:
                return self.DEFAULT_CONFIG
        return self.DEFAULT_CONFIG

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def save(self, new_config: Dict[str, Any]):
        """Update and save config to disk."""
        self.config.update(new_config)
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

# Singleton instance
config = ConfigManager()
