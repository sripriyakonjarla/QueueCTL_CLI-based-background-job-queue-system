"""Configuration management."""

import json
import os
from pathlib import Path
from typing import Dict, Any
from threading import Lock


class Config:
    """Manages configuration settings."""
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Config, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self.config_dir = Path.home() / ".queuectl"
        self.config_file = self.config_dir / "config.json"
        self.config_dir.mkdir(exist_ok=True)
        self._config = self._load_config()
        self._initialized = True
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        default_config = {
            "max_retries": 3,
            "backoff_base": 2,
        }
        
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    user_config = json.load(f)
                    default_config.update(user_config)
            except (json.JSONDecodeError, IOError):
                pass
        
        return default_config
    
    def _save_config(self):
        """Save configuration to file."""
        with open(self.config_file, "w") as f:
            json.dump(self._config, f, indent=2)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value."""
        self._config[key] = value
        self._save_config()
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration."""
        return self._config.copy()

