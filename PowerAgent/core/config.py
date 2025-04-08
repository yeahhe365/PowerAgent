# ========================================
# 文件名: PowerAgent/core/config.py
# -----------------------------------------------------------------------
# core/config.py
# -*- coding: utf-8 -*-

import os
import sys
import configparser
from PySide6.QtCore import QSettings, QCoreApplication

# Import constants and potentially other core modules if needed later
from constants import ORG_NAME, SETTINGS_APP_NAME
# Import autostart function because save_config calls it
from .autostart import set_auto_startup

# --- Default Values ---
DEFAULT_API_KEY: str = ""
DEFAULT_API_URL: str = ""
DEFAULT_MODEL_ID: str = ""
DEFAULT_AUTO_STARTUP_ENABLED: bool = False
DEFAULT_APP_THEME: str = "system" # Default theme is system

# --- Global Config State (Managed within this module) ---
# Initialize with defaults
API_KEY: str = DEFAULT_API_KEY
API_URL: str = DEFAULT_API_URL
MODEL_ID: str = DEFAULT_MODEL_ID
AUTO_STARTUP_ENABLED: bool = DEFAULT_AUTO_STARTUP_ENABLED
APP_THEME: str = DEFAULT_APP_THEME

# --- Configuration Handling (Using QSettings primarily) ---
def get_settings() -> QSettings:
    """Get a QSettings object, ensuring Org/App names are set."""
    if not QCoreApplication.organizationName():
        QCoreApplication.setOrganizationName(ORG_NAME)
    if not QCoreApplication.applicationName():
        QCoreApplication.setApplicationName(SETTINGS_APP_NAME)
    # Use INI format for better readability if opened manually
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, ORG_NAME, SETTINGS_APP_NAME)

def load_config() -> tuple[bool, str]:
    """
    Loads configuration from QSettings (INI format).
    Updates the global variables in this module.
    Returns:
        tuple: (bool: success, str: message)
    """
    global API_KEY, API_URL, MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    print("Loading configuration from QSettings (INI format)...")
    settings = get_settings()
    settings_path = settings.fileName()
    if os.path.exists(settings_path): print(f"Settings file found: {settings_path}")
    else: print(f"Settings file does not exist yet: {settings_path}")

    # Load settings, providing defaults from constants
    settings.beginGroup("api")
    API_KEY = settings.value("key", DEFAULT_API_KEY)
    API_URL = settings.value("url", DEFAULT_API_URL)
    MODEL_ID = settings.value("model_id", DEFAULT_MODEL_ID)
    settings.endGroup()

    settings.beginGroup("general")
    AUTO_STARTUP_ENABLED = settings.value("auto_startup", DEFAULT_AUTO_STARTUP_ENABLED, type=bool)
    loaded_theme = settings.value("theme", DEFAULT_APP_THEME, type=str)
    settings.endGroup()

    valid_themes = ["light", "dark", "system"]
    if loaded_theme not in valid_themes:
        print(f"Warning: Invalid theme '{loaded_theme}' found in settings. Defaulting to '{DEFAULT_APP_THEME}'.")
        APP_THEME = DEFAULT_APP_THEME
        # Optionally update the setting if invalid
        # settings.beginGroup("general"); settings.setValue("theme", APP_THEME); settings.endGroup(); settings.sync()
    else:
        APP_THEME = loaded_theme
    print(f"Configuration loaded - Theme: {APP_THEME}, AutoStart: {AUTO_STARTUP_ENABLED}")

    # Check if API configuration is incomplete AFTER loading (still relevant)
    if not API_KEY or not API_URL or not MODEL_ID:
        print("API configuration is incomplete in QSettings.")
        return False, "API configuration incomplete. Please configure in Settings."

    print("Configuration loaded successfully from QSettings.")
    return True, "Configuration loaded successfully."


def save_config(api_key: str, api_url: str, model_id: str, auto_startup: bool, theme: str):
    """Saves configuration to QSettings (INI format) and updates globals."""
    global API_KEY, API_URL, MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    print("Saving configuration to QSettings (INI format)...")
    settings = get_settings()

    settings.beginGroup("api"); settings.setValue("key", api_key); settings.setValue("url", api_url); settings.setValue("model_id", model_id); settings.endGroup()
    settings.beginGroup("general"); settings.setValue("auto_startup", auto_startup)
    valid_themes = ["dark", "light", "system"]; valid_theme = theme if theme in valid_themes else DEFAULT_APP_THEME
    settings.setValue("theme", valid_theme); settings.endGroup()
    settings.sync()

    if settings.status() != QSettings.Status.NoError: print(f"Warning: Error encountered while saving settings: {settings.status()}")
    else: print(f"Settings saved successfully to: {settings.fileName()}")

    # Update global variables immediately after saving
    API_KEY, API_URL, MODEL_ID = api_key, api_url, model_id
    AUTO_STARTUP_ENABLED = auto_startup
    APP_THEME = valid_theme
    print(f"Config state updated: AutoStart={AUTO_STARTUP_ENABLED}, Theme={APP_THEME}")

    # Apply auto-startup change using the saved value
    try: set_auto_startup(AUTO_STARTUP_ENABLED)
    except Exception as e: print(f"Error applying auto-startup setting: {e}")

# <<< ADDED Reset Function >>>
def reset_to_defaults_and_clear_cache():
    """
    Resets all settings in QSettings to their defaults and clears cached state.
    Also updates the global variables in this module.
    """
    global API_KEY, API_URL, MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    print("Resetting all settings and clearing cache...")
    settings = get_settings()

    # Clear ALL settings managed by QSettings
    # This includes 'api/*', 'general/*', 'state/*', 'ui/*' etc.
    settings.clear()
    settings.sync() # Ensure the file is cleared

    if settings.status() != QSettings.Status.NoError:
        print(f"Warning: Error encountered while clearing settings: {settings.status()}")
    else:
        print(f"All settings cleared successfully in: {settings.fileName()}")

    # Reset global variables to defaults
    API_KEY = DEFAULT_API_KEY
    API_URL = DEFAULT_API_URL
    MODEL_ID = DEFAULT_MODEL_ID
    AUTO_STARTUP_ENABLED = DEFAULT_AUTO_STARTUP_ENABLED
    APP_THEME = DEFAULT_APP_THEME

    print(f"Global config state reset to defaults: AutoStart={AUTO_STARTUP_ENABLED}, Theme={APP_THEME}")

    # Explicitly disable auto-startup via the platform-specific mechanism
    try:
        print("Disabling platform-specific auto-startup...")
        set_auto_startup(False)
    except Exception as e:
        print(f"Error explicitly disabling auto-startup during reset: {e}")


# Helper function to get current config values
def get_current_config() -> dict:
    """Returns the current configuration values held in this module."""
    return {
        "api_key": API_KEY,
        "api_url": API_URL,
        "model_id": MODEL_ID,
        "auto_startup": AUTO_STARTUP_ENABLED,
        "theme": APP_THEME,
    }