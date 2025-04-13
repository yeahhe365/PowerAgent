# ========================================
# 文件名: PowerAgent/core/config.py
# (MODIFIED - Added MULTI_STEP_MAX_ITERATIONS config)
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
DEFAULT_MODEL_ID_STRING: str = ""
DEFAULT_CURRENTLY_SELECTED_MODEL_ID: str = ""
DEFAULT_AUTO_STARTUP_ENABLED: bool = False
DEFAULT_APP_THEME: str = "system" # Default theme is system
DEFAULT_INCLUDE_CLI_CONTEXT: bool = True
DEFAULT_INCLUDE_TIMESTAMP: bool = False # Default to NOT include timestamp
DEFAULT_ENABLE_MULTI_STEP: bool = False
# <<< MODIFICATION START: Add default for max iterations >>>
DEFAULT_MULTI_STEP_MAX_ITERATIONS: int = 5 # Default max iterations
# <<< MODIFICATION END >>>


# --- Global Config State (Managed within this module) ---
# Initialize with defaults
API_KEY: str = DEFAULT_API_KEY
API_URL: str = DEFAULT_API_URL
MODEL_ID_STRING: str = DEFAULT_MODEL_ID_STRING
CURRENTLY_SELECTED_MODEL_ID: str = DEFAULT_CURRENTLY_SELECTED_MODEL_ID
AUTO_STARTUP_ENABLED: bool = DEFAULT_AUTO_STARTUP_ENABLED
APP_THEME: str = DEFAULT_APP_THEME
INCLUDE_CLI_CONTEXT: bool = DEFAULT_INCLUDE_CLI_CONTEXT
INCLUDE_TIMESTAMP_IN_PROMPT: bool = DEFAULT_INCLUDE_TIMESTAMP
ENABLE_MULTI_STEP: bool = DEFAULT_ENABLE_MULTI_STEP
# <<< MODIFICATION START: Add global state for max iterations >>>
MULTI_STEP_MAX_ITERATIONS: int = DEFAULT_MULTI_STEP_MAX_ITERATIONS
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
    global API_KEY, API_URL, MODEL_ID_STRING, CURRENTLY_SELECTED_MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT, INCLUDE_TIMESTAMP_IN_PROMPT, ENABLE_MULTI_STEP
    # <<< MODIFICATION START: Add max iterations global >>>
    global MULTI_STEP_MAX_ITERATIONS
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
    MODEL_ID_STRING = settings.value("model_id_string", DEFAULT_MODEL_ID_STRING)
    settings.endGroup()

    # Load General settings
    settings.beginGroup("general")
    AUTO_STARTUP_ENABLED = settings.value("auto_startup", DEFAULT_AUTO_STARTUP_ENABLED, type=bool)
    loaded_theme = settings.value("theme", DEFAULT_APP_THEME, type=str)
    INCLUDE_CLI_CONTEXT = settings.value("include_cli_context", DEFAULT_INCLUDE_CLI_CONTEXT, type=bool)
    CURRENTLY_SELECTED_MODEL_ID = settings.value("selected_model", DEFAULT_CURRENTLY_SELECTED_MODEL_ID)
    INCLUDE_TIMESTAMP_IN_PROMPT = settings.value("include_timestamp", DEFAULT_INCLUDE_TIMESTAMP, type=bool)
    ENABLE_MULTI_STEP = settings.value("enable_multi_step", DEFAULT_ENABLE_MULTI_STEP, type=bool)
    # <<< MODIFICATION START: Load max iterations >>>
    try:
        # Load as int, fallback to default if conversion fails or value is invalid
        loaded_iterations = settings.value("multi_step_max_iterations", DEFAULT_MULTI_STEP_MAX_ITERATIONS)
        MULTI_STEP_MAX_ITERATIONS = int(loaded_iterations)
        if MULTI_STEP_MAX_ITERATIONS < 1: # Ensure at least 1 iteration
            print(f"Warning: Invalid multi_step_max_iterations value ({MULTI_STEP_MAX_ITERATIONS}) loaded. Resetting to default ({DEFAULT_MULTI_STEP_MAX_ITERATIONS}).")
            MULTI_STEP_MAX_ITERATIONS = DEFAULT_MULTI_STEP_MAX_ITERATIONS
    except (ValueError, TypeError):
        print(f"Warning: Could not parse multi_step_max_iterations value ('{loaded_iterations}'). Resetting to default ({DEFAULT_MULTI_STEP_MAX_ITERATIONS}).")
        MULTI_STEP_MAX_ITERATIONS = DEFAULT_MULTI_STEP_MAX_ITERATIONS
    # <<< MODIFICATION END >>>
    settings.endGroup()

    # Validate and set theme
    valid_themes = ["light", "dark", "system"]
    if loaded_theme not in valid_themes:
        print(f"Warning: Invalid theme '{loaded_theme}' found in settings. Defaulting to '{DEFAULT_APP_THEME}'.")
        APP_THEME = DEFAULT_APP_THEME
    else:
        APP_THEME = loaded_theme

    # Validate selected model ID against the list
    available_models = [m.strip() for m in MODEL_ID_STRING.split(',') if m.strip()]
    if CURRENTLY_SELECTED_MODEL_ID and CURRENTLY_SELECTED_MODEL_ID not in available_models:
        print(f"Warning: Saved selected model '{CURRENTLY_SELECTED_MODEL_ID}' is not in the available list {available_models}. Resetting selection.")
        CURRENTLY_SELECTED_MODEL_ID = available_models[0] if available_models else ""
    elif not CURRENTLY_SELECTED_MODEL_ID and available_models:
         print(f"No model previously selected, defaulting to first available: '{available_models[0]}'")
         CURRENTLY_SELECTED_MODEL_ID = available_models[0]

    # <<< MODIFICATION START: Update print message >>>
    print(f"Configuration loaded - Theme: {APP_THEME}, AutoStart: {AUTO_STARTUP_ENABLED}, "
          f"IncludeCLIContext: {INCLUDE_CLI_CONTEXT}, IncludeTimestamp: {INCLUDE_TIMESTAMP_IN_PROMPT}, "
          f"EnableMultiStep: {ENABLE_MULTI_STEP}, MaxIterations: {MULTI_STEP_MAX_ITERATIONS}, " # Added MaxIterations
          f"SelectedModel: {CURRENTLY_SELECTED_MODEL_ID}")
    # <<< MODIFICATION END >>>

    # Check if API configuration is incomplete
    if not API_KEY or not API_URL:
        print("API Key/URL configuration is incomplete in QSettings.")
        return False, "API Key/URL configuration incomplete. Please configure in Settings."
    if not MODEL_ID_STRING:
        print("Model ID list is empty. Please configure in Settings to use AI features.")
        return True, "Configuration loaded, but Model ID list is empty."

    print("Configuration loaded successfully from QSettings.")
    return True, "Configuration loaded successfully."


# <<< MODIFICATION START: Add multi_step_max_iterations to signature >>>
def save_config(api_key: str, api_url: str, model_id_string: str, auto_startup: bool, theme: str,
                include_cli_context: bool, include_timestamp: bool, enable_multi_step: bool,
                multi_step_max_iterations: int, # Added parameter
                selected_model_id: str):
# <<< MODIFICATION END >>>
    """Saves configuration to QSettings (INI format) and updates globals."""
    global API_KEY, API_URL, MODEL_ID_STRING, CURRENTLY_SELECTED_MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT, INCLUDE_TIMESTAMP_IN_PROMPT, ENABLE_MULTI_STEP
    # <<< MODIFICATION START: Add max iterations global >>>
    global MULTI_STEP_MAX_ITERATIONS
    # <<< MODIFICATION END >>>

    print("Saving configuration to QSettings (INI format)...")
    settings = get_settings()

    settings.beginGroup("api")
    settings.setValue("key", api_key)
    settings.setValue("url", api_url)
    settings.setValue("model_id_string", model_id_string)
    settings.endGroup()

    settings.beginGroup("general")
    settings.setValue("auto_startup", auto_startup)
    valid_themes = ["dark", "light", "system"]
    valid_theme = theme if theme in valid_themes else DEFAULT_APP_THEME
    settings.setValue("theme", valid_theme)
    settings.setValue("include_cli_context", include_cli_context)
    settings.setValue("selected_model", selected_model_id)
    settings.setValue("include_timestamp", include_timestamp)
    settings.setValue("enable_multi_step", enable_multi_step)
    # <<< MODIFICATION START: Save max iterations >>>
    # Ensure saved value is at least 1
    save_iterations = max(1, multi_step_max_iterations)
    settings.setValue("multi_step_max_iterations", save_iterations)
    # <<< MODIFICATION END >>>
    settings.endGroup()

    settings.sync()

    if settings.status() != QSettings.Status.NoError:
        print(f"Warning: Error encountered while saving settings: {settings.status()}")
    else:
        print(f"Settings saved successfully to: {settings.fileName()}")

    # Update global variables immediately after saving
    API_KEY, API_URL = api_key, api_url
    MODEL_ID_STRING = model_id_string
    CURRENTLY_SELECTED_MODEL_ID = selected_model_id
    AUTO_STARTUP_ENABLED = auto_startup
    APP_THEME = valid_theme
    INCLUDE_CLI_CONTEXT = include_cli_context
    INCLUDE_TIMESTAMP_IN_PROMPT = include_timestamp
    ENABLE_MULTI_STEP = enable_multi_step
    # <<< MODIFICATION START: Update max iterations global >>>
    MULTI_STEP_MAX_ITERATIONS = save_iterations # Use the validated value
    # <<< MODIFICATION END >>>

    # <<< MODIFICATION START: Update print message >>>
    print(f"Config state updated: AutoStart={AUTO_STARTUP_ENABLED}, Theme={APP_THEME}, "
          f"IncludeCLIContext={INCLUDE_CLI_CONTEXT}, IncludeTimestamp={INCLUDE_TIMESTAMP_IN_PROMPT}, "
          f"EnableMultiStep={ENABLE_MULTI_STEP}, MaxIterations={MULTI_STEP_MAX_ITERATIONS}, " # Added MaxIterations
          f"SelectedModel={CURRENTLY_SELECTED_MODEL_ID}")
    # <<< MODIFICATION END >>>

    # Apply auto-startup change using the saved value
    try: set_auto_startup(AUTO_STARTUP_ENABLED)
    except Exception as e: print(f"Error applying auto-startup setting: {e}")


def reset_to_defaults_and_clear_cache():
    """
    Resets all settings in QSettings to their defaults and clears cached state.
    Also updates the global variables in this module.
    """
    global API_KEY, API_URL, MODEL_ID_STRING, CURRENTLY_SELECTED_MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT, INCLUDE_TIMESTAMP_IN_PROMPT, ENABLE_MULTI_STEP
    # <<< MODIFICATION START: Add max iterations global >>>
    global MULTI_STEP_MAX_ITERATIONS
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
    MODEL_ID_STRING = DEFAULT_MODEL_ID_STRING
    CURRENTLY_SELECTED_MODEL_ID = DEFAULT_CURRENTLY_SELECTED_MODEL_ID
    AUTO_STARTUP_ENABLED = DEFAULT_AUTO_STARTUP_ENABLED
    APP_THEME = DEFAULT_APP_THEME
    INCLUDE_CLI_CONTEXT = DEFAULT_INCLUDE_CLI_CONTEXT
    INCLUDE_TIMESTAMP_IN_PROMPT = DEFAULT_INCLUDE_TIMESTAMP
    ENABLE_MULTI_STEP = DEFAULT_ENABLE_MULTI_STEP
    # <<< MODIFICATION START: Reset max iterations global >>>
    MULTI_STEP_MAX_ITERATIONS = DEFAULT_MULTI_STEP_MAX_ITERATIONS
    # <<< MODIFICATION END >>>

    # <<< MODIFICATION START: Update print message >>>
    print(f"Global config state reset to defaults: AutoStart={AUTO_STARTUP_ENABLED}, Theme={APP_THEME}, "
          f"IncludeCLIContext={INCLUDE_CLI_CONTEXT}, IncludeTimestamp={INCLUDE_TIMESTAMP_IN_PROMPT}, "
          f"EnableMultiStep={ENABLE_MULTI_STEP}, MaxIterations={MULTI_STEP_MAX_ITERATIONS}, " # Added MaxIterations
          f"SelectedModel={CURRENTLY_SELECTED_MODEL_ID}")
    # <<< MODIFICATION END >>>

    # Explicitly disable auto-startup via the platform-specific mechanism
    try:
        print("Disabling platform-specific auto-startup...")
        set_auto_startup(False)
    except Exception as e:
        print(f"Error explicitly disabling auto-startup during reset: {e}")


def get_current_config() -> dict:
    """Returns the current configuration values held in this module."""
    # <<< MODIFICATION START: Add max iterations to returned dict >>>
    return {
        "api_key": API_KEY,
        "api_url": API_URL,
        "model_id_string": MODEL_ID_STRING,
        "currently_selected_model_id": CURRENTLY_SELECTED_MODEL_ID,
        "auto_startup": AUTO_STARTUP_ENABLED,
        "theme": APP_THEME,
        "include_cli_context": INCLUDE_CLI_CONTEXT,
        "include_timestamp_in_prompt": INCLUDE_TIMESTAMP_IN_PROMPT,
        "enable_multi_step": ENABLE_MULTI_STEP,
        "multi_step_max_iterations": MULTI_STEP_MAX_ITERATIONS, # Added field
    }
    # <<< MODIFICATION END >>>