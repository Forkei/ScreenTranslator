import os
import logging
import yaml

from src.models.app_settings import AppSettings

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config.yaml"


class ConfigManager:
    """Loads and saves AppSettings to a YAML config file."""

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path

    def load(self) -> AppSettings:
        """Load settings from YAML file. Returns defaults if file doesn't exist."""
        if not os.path.exists(self.config_path):
            logger.info("No config file found, using defaults")
            return AppSettings()
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data is None:
                return AppSettings()
            return AppSettings.from_dict(data)
        except Exception as e:
            logger.error("Failed to load config: %s", e)
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        """Save settings to YAML file."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(settings.to_dict(), f, default_flow_style=False, allow_unicode=True)
            logger.info("Config saved to %s", self.config_path)
        except Exception as e:
            logger.error("Failed to save config: %s", e)
