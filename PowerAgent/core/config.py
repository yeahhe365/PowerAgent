# ========================================
# 文件名: PowerAgent/core/config.py
# ---------------------------------------
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
DEFAULT_INCLUDE_CLI_CONTEXT: bool = True
# <<< MODIFICATION START: Add default for timestamp inclusion >>>
DEFAULT_INCLUDE_TIMESTAMP: bool = False # Default to NOT include timestamp
# <<< MODIFICATION END >>>


# --- Global Config State (Managed within this module) ---
# Initialize with defaults
API_KEY: str = DEFAULT_API_KEY
API_URL: str = DEFAULT_API_URL
MODEL_ID: str = DEFAULT_MODEL_ID
AUTO_STARTUP_ENABLED: bool = DEFAULT_AUTO_STARTUP_ENABLED
APP_THEME: str = DEFAULT_APP_THEME
INCLUDE_CLI_CONTEXT: bool = DEFAULT_INCLUDE_CLI_CONTEXT
# <<< MODIFICATION START: Add global state for timestamp >>>
INCLUDE_TIMESTAMP_IN_PROMPT: bool = DEFAULT_INCLUDE_TIMESTAMP
# <<< MODIFICATION END >>>


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
    global INCLUDE_CLI_CONTEXT
    # <<< MODIFICATION START: Add timestamp global >>>
    global INCLUDE_TIMESTAMP_IN_PROMPT
    # <<< MODIFICATION END >>>

    print("Loading configuration from QSettings (INI format)...")
    settings = get_settings()
    settings_path = settings.fileName()
    if os.path.exists(settings_path): print(f"Settings file found: {settings_path}")
    else: print(f"Settings file does not exist yet: {settings_path}")

    # Load API settings
    settings.beginGroup("api")
    API_KEY = settings.value("key", DEFAULT_API_KEY)
    API_URL = settings.value("url", DEFAULT_API_URL)
    MODEL_ID = settings.value("model_id", DEFAULT_MODEL_ID)
    settings.endGroup()

    # Load General settings
    settings.beginGroup("general")
    AUTO_STARTUP_ENABLED = settings.value("auto_startup", DEFAULT_AUTO_STARTUP_ENABLED, type=bool)
    loaded_theme = settings.value("theme", DEFAULT_APP_THEME, type=str)
    INCLUDE_CLI_CONTEXT = settings.value("include_cli_context", DEFAULT_INCLUDE_CLI_CONTEXT, type=bool)
    # <<< MODIFICATION START: Load timestamp setting >>>
    INCLUDE_TIMESTAMP_IN_PROMPT = settings.value("include_timestamp", DEFAULT_INCLUDE_TIMESTAMP, type=bool)
    # <<< MODIFICATION END >>>
    settings.endGroup()

    # Validate and set theme
    valid_themes = ["light", "dark", "system"]
    if loaded_theme not in valid_themes:
        print(f"Warning: Invalid theme '{loaded_theme}' found in settings. Defaulting to '{DEFAULT_APP_THEME}'.")
        APP_THEME = DEFAULT_APP_THEME
    else:
        APP_THEME = loaded_theme

    # <<< MODIFICATION START: Update print message >>>
    print(f"Configuration loaded - Theme: {APP_THEME}, AutoStart: {AUTO_STARTUP_ENABLED}, IncludeCLIContext: {INCLUDE_CLI_CONTEXT} (Full context), IncludeTimestamp: {INCLUDE_TIMESTAMP_IN_PROMPT}")
    # <<< MODIFICATION END >>>

    # Check if API configuration is incomplete
    if not API_KEY or not API_URL or not MODEL_ID:
        print("API configuration is incomplete in QSettings.")
        return False, "API configuration incomplete. Please configure in Settings."

    print("Configuration loaded successfully from QSettings.")
    return True, "Configuration loaded successfully."


# <<< MODIFICATION START: Add include_timestamp parameter >>>
def save_config(api_key: str, api_url: str, model_id: str, auto_startup: bool, theme: str,
                include_cli_context: bool, include_timestamp: bool):
# <<< MODIFICATION END >>>
    """Saves configuration to QSettings (INI format) and updates globals."""
    global API_KEY, API_URL, MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT
    # <<< MODIFICATION START: Add timestamp global >>>
    global INCLUDE_TIMESTAMP_IN_PROMPT
    # <<< MODIFICATION END >>>

    print("Saving configuration to QSettings (INI format)...")
    settings = get_settings()

    settings.beginGroup("api")
    settings.setValue("key", api_key)
    settings.setValue("url", api_url)
    settings.setValue("model_id", model_id)
    settings.endGroup()

    settings.beginGroup("general")
    settings.setValue("auto_startup", auto_startup)
    valid_themes = ["dark", "light", "system"]
    valid_theme = theme if theme in valid_themes else DEFAULT_APP_THEME
    settings.setValue("theme", valid_theme)
    settings.setValue("include_cli_context", include_cli_context)
    # <<< MODIFICATION START: Save timestamp setting >>>
    settings.setValue("include_timestamp", include_timestamp)
    # <<< MODIFICATION END >>>
    settings.endGroup()

    settings.sync()

    if settings.status() != QSettings.Status.NoError:
        print(f"Warning: Error encountered while saving settings: {settings.status()}")
    else:
        print(f"Settings saved successfully to: {settings.fileName()}")

    # Update global variables immediately after saving
    API_KEY, API_URL, MODEL_ID = api_key, api_url, model_id
    AUTO_STARTUP_ENABLED = auto_startup
    APP_THEME = valid_theme
    INCLUDE_CLI_CONTEXT = include_cli_context
    # <<< MODIFICATION START: Update timestamp global >>>
    INCLUDE_TIMESTAMP_IN_PROMPT = include_timestamp
    # <<< MODIFICATION END >>>

    # <<< MODIFICATION START: Update print message >>>
    print(f"Config state updated: AutoStart={AUTO_STARTUP_ENABLED}, Theme={APP_THEME}, IncludeCLIContext={INCLUDE_CLI_CONTEXT} (Full context), IncludeTimestamp={INCLUDE_TIMESTAMP_IN_PROMPT}")
    # <<< MODIFICATION END >>>

    # Apply auto-startup change using the saved value
    try: set_auto_startup(AUTO_STARTUP_ENABLED)
    except Exception as e: print(f"Error applying auto-startup setting: {e}")


def reset_to_defaults_and_clear_cache():
    """
    Resets all settings in QSettings to their defaults and clears cached state.
    Also updates the global variables in this module.
    """
    global API_KEY, API_URL, MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT
    # <<< MODIFICATION START: Add timestamp global >>>
    global INCLUDE_TIMESTAMP_IN_PROMPT
    # <<< MODIFICATION END >>>

    print("Resetting all settings and clearing cache...")
    settings = get_settings()

    # Clear ALL settings managed by QSettings
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
    INCLUDE_CLI_CONTEXT = DEFAULT_INCLUDE_CLI_CONTEXT
    # <<< MODIFICATION START: Reset timestamp global >>>
    INCLUDE_TIMESTAMP_IN_PROMPT = DEFAULT_INCLUDE_TIMESTAMP
    # <<< MODIFICATION END >>>

    # <<< MODIFICATION START: Update print message >>>
    print(f"Global config state reset to defaults: AutoStart={AUTO_STARTUP_ENABLED}, Theme={APP_THEME}, IncludeCLIContext={INCLUDE_CLI_CONTEXT} (Full context), IncludeTimestamp={INCLUDE_TIMESTAMP_IN_PROMPT}")
    # <<< MODIFICATION END >>>

    # Explicitly disable auto-startup via the platform-specific mechanism
    try:
        print("Disabling platform-specific auto-startup...")
        set_auto_startup(False)
    except Exception as e:
        print(f"Error explicitly disabling auto-startup during reset: {e}")


def get_current_config() -> dict:
    """Returns the current configuration values held in this module."""
    # <<< MODIFICATION START: Add timestamp to returned dict >>>
    return {
        "api_key": API_KEY,
        "api_url": API_URL,
        "model_id": MODEL_ID,
        "auto_startup": AUTO_STARTUP_ENABLED,
        "theme": APP_THEME,
        "include_cli_context": INCLUDE_CLI_CONTEXT,
        "include_timestamp_in_prompt": INCLUDE_TIMESTAMP_IN_PROMPT, # New key
    }
    # <<< MODIFICATION END >>>