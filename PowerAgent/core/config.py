# ========================================
# 文件名: PowerAgent/core/config.py
# (MODIFIED)
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
# <<< MODIFIED: Default for comma-separated string >>>
DEFAULT_MODEL_ID_STRING: str = ""
DEFAULT_CURRENTLY_SELECTED_MODEL_ID: str = ""
# <<< END MODIFICATION >>>
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
# <<< MODIFIED: Global state variables >>>
MODEL_ID_STRING: str = DEFAULT_MODEL_ID_STRING
CURRENTLY_SELECTED_MODEL_ID: str = DEFAULT_CURRENTLY_SELECTED_MODEL_ID
# <<< END MODIFICATION >>>
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
    # <<< MODIFIED: Global variable list >>>
    global API_KEY, API_URL, MODEL_ID_STRING, CURRENTLY_SELECTED_MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT, INCLUDE_TIMESTAMP_IN_PROMPT
    # <<< END MODIFICATION >>>

    print("Loading configuration from QSettings (INI format)...")
    settings = get_settings()
    settings_path = settings.fileName()
    if os.path.exists(settings_path): print(f"Settings file found: {settings_path}")
    else: print(f"Settings file does not exist yet: {settings_path}")

    # Load API settings
    settings.beginGroup("api")
    API_KEY = settings.value("key", DEFAULT_API_KEY)
    API_URL = settings.value("url", DEFAULT_API_URL)
    # <<< MODIFIED: Load model_id_string >>>
    MODEL_ID_STRING = settings.value("model_id_string", DEFAULT_MODEL_ID_STRING) # Changed key name
    # <<< END MODIFICATION >>>
    settings.endGroup()

    # Load General settings
    settings.beginGroup("general")
    AUTO_STARTUP_ENABLED = settings.value("auto_startup", DEFAULT_AUTO_STARTUP_ENABLED, type=bool)
    loaded_theme = settings.value("theme", DEFAULT_APP_THEME, type=str)
    INCLUDE_CLI_CONTEXT = settings.value("include_cli_context", DEFAULT_INCLUDE_CLI_CONTEXT, type=bool)
    # <<< MODIFIED: Load selected model >>>
    CURRENTLY_SELECTED_MODEL_ID = settings.value("selected_model", DEFAULT_CURRENTLY_SELECTED_MODEL_ID) # New key
    # <<< END MODIFICATION >>>
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

    # <<< MODIFIED: Validate selected model ID against the list >>>
    # Ensure the loaded selected model is actually in the list of available models
    available_models = [m.strip() for m in MODEL_ID_STRING.split(',') if m.strip()]
    if CURRENTLY_SELECTED_MODEL_ID and CURRENTLY_SELECTED_MODEL_ID not in available_models:
        print(f"Warning: Saved selected model '{CURRENTLY_SELECTED_MODEL_ID}' is not in the available list {available_models}. Resetting selection.")
        CURRENTLY_SELECTED_MODEL_ID = available_models[0] if available_models else ""
        # Optionally save this correction back immediately, though update_model_selector in main_window will handle it too.
        # settings.beginGroup("general")
        # settings.setValue("selected_model", CURRENTLY_SELECTED_MODEL_ID)
        # settings.endGroup()
        # settings.sync()
    elif not CURRENTLY_SELECTED_MODEL_ID and available_models:
         # If no model was selected but models are available, select the first one
         print(f"No model previously selected, defaulting to first available: '{available_models[0]}'")
         CURRENTLY_SELECTED_MODEL_ID = available_models[0]
         # Optionally save this default back
         # settings.beginGroup("general")
         # settings.setValue("selected_model", CURRENTLY_SELECTED_MODEL_ID)
         # settings.endGroup()
         # settings.sync()

    # <<< MODIFICATION START: Update print message >>>
    print(f"Configuration loaded - Theme: {APP_THEME}, AutoStart: {AUTO_STARTUP_ENABLED}, IncludeCLIContext: {INCLUDE_CLI_CONTEXT} (Full context), IncludeTimestamp: {INCLUDE_TIMESTAMP_IN_PROMPT}, SelectedModel: {CURRENTLY_SELECTED_MODEL_ID}")
    # <<< MODIFICATION END >>>

    # Check if API configuration is incomplete (API Key/URL still needed)
    if not API_KEY or not API_URL: # Removed MODEL_ID check here, as list might be empty intentionally initially
        print("API Key/URL configuration is incomplete in QSettings.")
        return False, "API Key/URL configuration incomplete. Please configure in Settings."
    if not MODEL_ID_STRING:
        print("Model ID list is empty. Please configure in Settings to use AI features.")
        # Return True, but message indicates models needed
        return True, "Configuration loaded, but Model ID list is empty."

    print("Configuration loaded successfully from QSettings.")
    return True, "Configuration loaded successfully."


# <<< MODIFIED: Signature changed to accept model_id_string and selected_model_id >>>
def save_config(api_key: str, api_url: str, model_id_string: str, auto_startup: bool, theme: str,
                include_cli_context: bool, include_timestamp: bool, selected_model_id: str):
# <<< END MODIFICATION >>>
    """Saves configuration to QSettings (INI format) and updates globals."""
    # <<< MODIFIED: Global variable list >>>
    global API_KEY, API_URL, MODEL_ID_STRING, CURRENTLY_SELECTED_MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT, INCLUDE_TIMESTAMP_IN_PROMPT
    # <<< END MODIFICATION >>>

    print("Saving configuration to QSettings (INI format)...")
    settings = get_settings()

    settings.beginGroup("api")
    settings.setValue("key", api_key)
    settings.setValue("url", api_url)
    # <<< MODIFIED: Save model_id_string >>>
    settings.setValue("model_id_string", model_id_string) # Changed key name
    # <<< END MODIFICATION >>>
    settings.endGroup()

    settings.beginGroup("general")
    settings.setValue("auto_startup", auto_startup)
    valid_themes = ["dark", "light", "system"]
    valid_theme = theme if theme in valid_themes else DEFAULT_APP_THEME
    settings.setValue("theme", valid_theme)
    settings.setValue("include_cli_context", include_cli_context)
    # <<< MODIFIED: Save selected model >>>
    settings.setValue("selected_model", selected_model_id) # New key
    # <<< END MODIFICATION >>>
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
    API_KEY, API_URL = api_key, api_url
    # <<< MODIFIED: Update globals >>>
    MODEL_ID_STRING = model_id_string
    CURRENTLY_SELECTED_MODEL_ID = selected_model_id
    # <<< END MODIFICATION >>>
    AUTO_STARTUP_ENABLED = auto_startup
    APP_THEME = valid_theme
    INCLUDE_CLI_CONTEXT = include_cli_context
    # <<< MODIFICATION START: Update timestamp global >>>
    INCLUDE_TIMESTAMP_IN_PROMPT = include_timestamp
    # <<< MODIFICATION END >>>

    # <<< MODIFICATION START: Update print message >>>
    print(f"Config state updated: AutoStart={AUTO_STARTUP_ENABLED}, Theme={APP_THEME}, IncludeCLIContext={INCLUDE_CLI_CONTEXT} (Full context), IncludeTimestamp={INCLUDE_TIMESTAMP_IN_PROMPT}, SelectedModel={CURRENTLY_SELECTED_MODEL_ID}")
    # <<< MODIFICATION END >>>

    # Apply auto-startup change using the saved value
    try: set_auto_startup(AUTO_STARTUP_ENABLED)
    except Exception as e: print(f"Error applying auto-startup setting: {e}")


def reset_to_defaults_and_clear_cache():
    """
    Resets all settings in QSettings to their defaults and clears cached state.
    Also updates the global variables in this module.
    """
    # <<< MODIFIED: Global variable list >>>
    global API_KEY, API_URL, MODEL_ID_STRING, CURRENTLY_SELECTED_MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT, INCLUDE_TIMESTAMP_IN_PROMPT
    # <<< END MODIFICATION >>>

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
    # <<< MODIFIED: Reset globals >>>
    MODEL_ID_STRING = DEFAULT_MODEL_ID_STRING
    CURRENTLY_SELECTED_MODEL_ID = DEFAULT_CURRENTLY_SELECTED_MODEL_ID
    # <<< END MODIFICATION >>>
    AUTO_STARTUP_ENABLED = DEFAULT_AUTO_STARTUP_ENABLED
    APP_THEME = DEFAULT_APP_THEME
    INCLUDE_CLI_CONTEXT = DEFAULT_INCLUDE_CLI_CONTEXT
    # <<< MODIFICATION START: Reset timestamp global >>>
    INCLUDE_TIMESTAMP_IN_PROMPT = DEFAULT_INCLUDE_TIMESTAMP
    # <<< MODIFICATION END >>>

    # <<< MODIFICATION START: Update print message >>>
    print(f"Global config state reset to defaults: AutoStart={AUTO_STARTUP_ENABLED}, Theme={APP_THEME}, IncludeCLIContext={INCLUDE_CLI_CONTEXT} (Full context), IncludeTimestamp={INCLUDE_TIMESTAMP_IN_PROMPT}, SelectedModel={CURRENTLY_SELECTED_MODEL_ID}")
    # <<< MODIFICATION END >>>

    # Explicitly disable auto-startup via the platform-specific mechanism
    try:
        print("Disabling platform-specific auto-startup...")
        set_auto_startup(False)
    except Exception as e:
        print(f"Error explicitly disabling auto-startup during reset: {e}")


def get_current_config() -> dict:
    """Returns the current configuration values held in this module."""
    # <<< MODIFIED: Return new structure >>>
    return {
        "api_key": API_KEY,
        "api_url": API_URL,
        "model_id_string": MODEL_ID_STRING, # Renamed key
        "currently_selected_model_id": CURRENTLY_SELECTED_MODEL_ID, # Added key
        "auto_startup": AUTO_STARTUP_ENABLED,
        "theme": APP_THEME,
        "include_cli_context": INCLUDE_CLI_CONTEXT,
        "include_timestamp_in_prompt": INCLUDE_TIMESTAMP_IN_PROMPT, # Timestamp key
    }
    # <<< END MODIFICATION >>>