"""TUI settings state management with persistent storage."""

import json
import os
import copy
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("TUI")


class TUISettings:
    """Manages TUI settings with persistence to disk."""

    DEFAULT_SETTINGS = {
        "display": {
            "theme": "textual-dark",
            "show_line_numbers": True,
            "results_per_page": 20,
            "source_file_display": "auto",  # auto, always, never
        },
        "search": {
            "mode": "fuzzy",  # fuzzy, prefix, exact
            "case_sensitive": False,
            "max_results": 50,
        },
        "config": {
            "last_vendor": "asa",
            "last_path": "",
            "auto_reload": False,
        },
        "advanced": {
            "enable_logging": True,
            "log_level": "INFO",  # DEBUG, INFO, WARNING, ERROR
            "cache_enabled": True,
            "results_per_page": 50,
        },
    }

    def __init__(self, config_path: Optional[str] = None):
        """Initialize settings manager.

        Args:
            config_path: Optional path to settings file. If None, uses default.
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            # Use XDG_CONFIG_HOME or fallback to ~/.config
            config_home = os.environ.get("XDG_CONFIG_HOME")
            if config_home:
                base_dir = Path(config_home)
            else:
                base_dir = Path.home() / ".config"

            self.config_dir = base_dir / "acl-inspector"
            self.config_path = self.config_dir / "tui-settings.json"

        self.settings: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load settings from disk, creating defaults if not found."""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    loaded = json.load(f)
                # Merge with defaults (in case new settings were added)
                self.settings = self._merge_settings(copy.deepcopy(self.DEFAULT_SETTINGS), loaded)
                logger.info(f"Loaded settings from {self.config_path}")
            else:
                # Use defaults
                self.settings = copy.deepcopy(self.DEFAULT_SETTINGS)
                logger.info("Using default settings (no config file found)")
        except Exception as e:
            logger.error(f"Error loading settings: {e}, using defaults")
            self.settings = copy.deepcopy(self.DEFAULT_SETTINGS)

    def save(self) -> bool:
        """Save settings to disk.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create config directory if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_path, 'w') as f:
                json.dump(self.settings, f, indent=2)

            logger.info(f"Saved settings to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return False

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """Get a setting value.

        Args:
            category: Settings category (display, search, config, advanced)
            key: Setting key within category
            default: Default value if not found

        Returns:
            Setting value or default
        """
        return self.settings.get(category, {}).get(key, default)

    def set(self, category: str, key: str, value: Any) -> None:
        """Set a setting value.

        Args:
            category: Settings category
            key: Setting key
            value: New value
        """
        if category not in self.settings:
            self.settings[category] = {}
        self.settings[category][key] = value

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self.settings = copy.deepcopy(self.DEFAULT_SETTINGS)
        logger.info("Reset settings to defaults")

    def reset_category(self, category: str) -> None:
        """Reset a specific category to defaults.

        Args:
            category: Category to reset
        """
        if category in self.DEFAULT_SETTINGS:
            self.settings[category] = copy.deepcopy(self.DEFAULT_SETTINGS[category])
            logger.info(f"Reset {category} settings to defaults")

    def get_all(self) -> Dict[str, Any]:
        """Get all settings.

        Returns:
            Complete settings dictionary
        """
        return self.settings.copy()

    def _merge_settings(self, defaults: Dict, loaded: Dict) -> Dict:
        """Merge loaded settings with defaults (recursively).

        Args:
            defaults: Default settings structure
            loaded: Loaded settings from file

        Returns:
            Merged settings
        """
        result = defaults.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursive merge for nested dicts
                result[key] = self._merge_settings(result[key], value)
            else:
                # Direct assignment
                result[key] = value
        return result

    def export_to_file(self, path: str) -> bool:
        """Export settings to a file.

        Args:
            path: Export file path

        Returns:
            True if successful
        """
        try:
            with open(path, 'w') as f:
                json.dump(self.settings, f, indent=2)
            logger.info(f"Exported settings to {path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting settings: {e}")
            return False

    def import_from_file(self, path: str) -> bool:
        """Import settings from a file.

        Args:
            path: Import file path

        Returns:
            True if successful
        """
        try:
            with open(path, 'r') as f:
                loaded = json.load(f)
            self.settings = self._merge_settings(copy.deepcopy(self.DEFAULT_SETTINGS), loaded)
            logger.info(f"Imported settings from {path}")
            return True
        except Exception as e:
            logger.error(f"Error importing settings: {e}")
            return False
