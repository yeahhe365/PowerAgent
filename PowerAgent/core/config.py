# core/config.py
# -*- coding: utf-8 -*-

import os
import sys
import configparser
import logging # Import logging
from PySide6.QtCore import QSettings, QCoreApplication

# Import constants and potentially other core modules if needed later
from constants import ORG_NAME, SETTINGS_APP_NAME
# Import autostart function because save_config calls it
from .autostart import set_auto_startup

# --- Get Logger ---
# Get the logger for this specific module
logger = logging.getLogger(__name__)

# --- Default Values ---
# (Defaults remain the same)
DEFAULT_API_KEY: str = ""
DEFAULT_API_URL: str = ""
DEFAULT_MODEL_ID_STRING: str = ""
DEFAULT_CURRENTLY_SELECTED_MODEL_ID: str = ""
DEFAULT_AUTO_STARTUP_ENABLED: bool = False
DEFAULT_APP_THEME: str = "system" # Default theme is system
DEFAULT_INCLUDE_CLI_CONTEXT: bool = True
DEFAULT_INCLUDE_TIMESTAMP: bool = False # Default to NOT include timestamp
DEFAULT_ENABLE_MULTI_STEP: bool = False
DEFAULT_MULTI_STEP_MAX_ITERATIONS: int = 5 # Default max iterations
DEFAULT_AUTO_INCLUDE_UI_INFO: bool = False # Default to NOT automatically include UI info

# --- Global Config State (Managed within this module) ---
# (Global state variables remain the same)
API_KEY: str = DEFAULT_API_KEY
API_URL: str = DEFAULT_API_URL
MODEL_ID_STRING: str = DEFAULT_MODEL_ID_STRING
CURRENTLY_SELECTED_MODEL_ID: str = DEFAULT_CURRENTLY_SELECTED_MODEL_ID
AUTO_STARTUP_ENABLED: bool = DEFAULT_AUTO_STARTUP_ENABLED
APP_THEME: str = DEFAULT_APP_THEME
INCLUDE_CLI_CONTEXT: bool = DEFAULT_INCLUDE_CLI_CONTEXT
INCLUDE_TIMESTAMP_IN_PROMPT: bool = DEFAULT_INCLUDE_TIMESTAMP
ENABLE_MULTI_STEP: bool = DEFAULT_ENABLE_MULTI_STEP
MULTI_STEP_MAX_ITERATIONS: int = DEFAULT_MULTI_STEP_MAX_ITERATIONS
AUTO_INCLUDE_UI_INFO: bool = DEFAULT_AUTO_INCLUDE_UI_INFO

# --- Configuration Handling (Using QSettings primarily) ---
def get_settings() -> QSettings:
    """Get a QSettings object, ensuring Org/App names are set."""
    # Log the attempt to get settings
    logger.debug("Attempting to get QSettings instance.")
    try:
        # Ensure Org/App names are set before creating QSettings
        if not QCoreApplication.organizationName():
            logger.debug("Organization name not set, setting to default: %s", ORG_NAME)
            QCoreApplication.setOrganizationName(ORG_NAME)
        if not QCoreApplication.applicationName():
            logger.debug("Application name not set, setting to default: %s", SETTINGS_APP_NAME)
            QCoreApplication.setApplicationName(SETTINGS_APP_NAME)

        # Use INI format for better readability if opened manually
        settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, ORG_NAME, SETTINGS_APP_NAME)
        settings_path = settings.fileName()
        logger.info(f"Using settings file: {settings_path}") # Log path even if it doesn't exist yet
        return settings
    except Exception as e:
        logger.error("Failed to create QSettings instance.", exc_info=True)
        # Propagate the exception or return a dummy object, depending on desired robustness
        raise # Re-raise the exception for now

def load_config() -> tuple[bool, str]:
    """
    Loads configuration from QSettings (INI format).
    Updates the global variables in this module. Logs the process.
    Returns:
        tuple: (bool: success, str: message)
    """
    global API_KEY, API_URL, MODEL_ID_STRING, CURRENTLY_SELECTED_MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT, INCLUDE_TIMESTAMP_IN_PROMPT, ENABLE_MULTI_STEP, MULTI_STEP_MAX_ITERATIONS
    global AUTO_INCLUDE_UI_INFO

    logger.info("Loading configuration from QSettings...")
    try:
        settings = get_settings() # Will log the settings file path
        settings_path = settings.fileName() # Get path again for logging existence check
        if os.path.exists(settings_path):
            logger.info(f"Settings file exists: {settings_path}")
        else:
            logger.info(f"Settings file does not exist yet (will use defaults): {settings_path}")

        # --- Load API settings ---
        logger.debug("Loading [api] settings group...")
        settings.beginGroup("api")
        API_KEY = settings.value("key", DEFAULT_API_KEY, type=str)
        # Log API Key presence, not the key itself
        logger.debug("Loaded API Key: %s", "Present" if API_KEY else "Absent")
        API_URL = settings.value("url", DEFAULT_API_URL, type=str)
        logger.debug("Loaded API URL: %s", API_URL if API_URL else "<empty>")
        MODEL_ID_STRING = settings.value("model_id_string", DEFAULT_MODEL_ID_STRING, type=str)
        logger.debug("Loaded Model ID String: %s", MODEL_ID_STRING if MODEL_ID_STRING else "<empty>")
        settings.endGroup()

        # --- Load General settings ---
        logger.debug("Loading [general] settings group...")
        settings.beginGroup("general")
        AUTO_STARTUP_ENABLED = settings.value("auto_startup", DEFAULT_AUTO_STARTUP_ENABLED, type=bool)
        logger.debug("Loaded Auto Startup Enabled: %s", AUTO_STARTUP_ENABLED)
        loaded_theme = settings.value("theme", DEFAULT_APP_THEME, type=str)
        logger.debug("Loaded Theme (raw): %s", loaded_theme)
        INCLUDE_CLI_CONTEXT = settings.value("include_cli_context", DEFAULT_INCLUDE_CLI_CONTEXT, type=bool)
        logger.debug("Loaded Include CLI Context: %s", INCLUDE_CLI_CONTEXT)
        CURRENTLY_SELECTED_MODEL_ID = settings.value("selected_model", DEFAULT_CURRENTLY_SELECTED_MODEL_ID, type=str)
        logger.debug("Loaded Selected Model ID (raw): %s", CURRENTLY_SELECTED_MODEL_ID if CURRENTLY_SELECTED_MODEL_ID else "<empty>")
        INCLUDE_TIMESTAMP_IN_PROMPT = settings.value("include_timestamp", DEFAULT_INCLUDE_TIMESTAMP, type=bool)
        logger.debug("Loaded Include Timestamp: %s", INCLUDE_TIMESTAMP_IN_PROMPT)
        ENABLE_MULTI_STEP = settings.value("enable_multi_step", DEFAULT_ENABLE_MULTI_STEP, type=bool)
        logger.debug("Loaded Enable Multi-Step: %s", ENABLE_MULTI_STEP)

        # Load max iterations with error handling
        loaded_iterations_raw = settings.value("multi_step_max_iterations", DEFAULT_MULTI_STEP_MAX_ITERATIONS)
        try:
            MULTI_STEP_MAX_ITERATIONS = int(loaded_iterations_raw)
            if MULTI_STEP_MAX_ITERATIONS < 1:
                logger.warning(f"Invalid multi_step_max_iterations value ({MULTI_STEP_MAX_ITERATIONS}) loaded. Resetting to default ({DEFAULT_MULTI_STEP_MAX_ITERATIONS}).")
                MULTI_STEP_MAX_ITERATIONS = DEFAULT_MULTI_STEP_MAX_ITERATIONS
            logger.debug("Loaded Multi-Step Max Iterations: %d", MULTI_STEP_MAX_ITERATIONS)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse multi_step_max_iterations value ('{loaded_iterations_raw}'). Resetting to default ({DEFAULT_MULTI_STEP_MAX_ITERATIONS}).")
            MULTI_STEP_MAX_ITERATIONS = DEFAULT_MULTI_STEP_MAX_ITERATIONS

        # Load Auto Include UI Info setting
        AUTO_INCLUDE_UI_INFO = settings.value("auto_include_ui_info", DEFAULT_AUTO_INCLUDE_UI_INFO, type=bool)
        logger.debug("Loaded Auto Include UI Info: %s", AUTO_INCLUDE_UI_INFO)
        settings.endGroup()

        # --- Validate and set theme ---
        valid_themes = ["light", "dark", "system"]
        if loaded_theme not in valid_themes:
            logger.warning(f"Invalid theme '{loaded_theme}' found in settings. Defaulting to '{DEFAULT_APP_THEME}'.")
            APP_THEME = DEFAULT_APP_THEME
        else:
            APP_THEME = loaded_theme
        logger.debug("Validated Theme: %s", APP_THEME)

        # --- Validate selected model ID against the list ---
        available_models = [m.strip() for m in MODEL_ID_STRING.split(',') if m.strip()]
        logger.debug("Available models based on Model ID String: %s", available_models)
        if CURRENTLY_SELECTED_MODEL_ID and CURRENTLY_SELECTED_MODEL_ID not in available_models:
            logger.warning(f"Saved selected model '{CURRENTLY_SELECTED_MODEL_ID}' is not in the available list. Resetting selection.")
            CURRENTLY_SELECTED_MODEL_ID = available_models[0] if available_models else ""
        elif not CURRENTLY_SELECTED_MODEL_ID and available_models:
            logger.info(f"No model previously selected, defaulting to first available: '{available_models[0]}'")
            CURRENTLY_SELECTED_MODEL_ID = available_models[0]
        elif not available_models:
             # If no models are available, ensure selected ID is also empty
             CURRENTLY_SELECTED_MODEL_ID = ""
        logger.debug("Validated Selected Model ID: %s", CURRENTLY_SELECTED_MODEL_ID if CURRENTLY_SELECTED_MODEL_ID else "<none>")

        # Log final loaded state
        logger.info(f"Configuration loaded - Theme: {APP_THEME}, AutoStart: {AUTO_STARTUP_ENABLED}, "
                    f"IncludeCLIContext: {INCLUDE_CLI_CONTEXT}, IncludeTimestamp: {INCLUDE_TIMESTAMP_IN_PROMPT}, "
                    f"EnableMultiStep: {ENABLE_MULTI_STEP}, MaxIterations: {MULTI_STEP_MAX_ITERATIONS}, "
                    f"AutoIncludeUI: {AUTO_INCLUDE_UI_INFO}, SelectedModel: {CURRENTLY_SELECTED_MODEL_ID}")

        # --- Check if API configuration is incomplete ---
        config_complete = True
        message = "Configuration loaded successfully."
        if not API_KEY or not API_URL:
            logger.warning("API Key or API URL configuration is incomplete in QSettings.")
            config_complete = False
            message = "API Key/URL configuration incomplete. Please configure in Settings."
        if not MODEL_ID_STRING:
            logger.info("Model ID list is empty. AI features require configuration in Settings.")
            if config_complete:
                message = "Configuration loaded, but Model ID list is empty."

        logger.info(f"Final config load check: Success={config_complete}, Message='{message}'")
        return config_complete, message

    except Exception as e:
        logger.error("CRITICAL error during configuration loading.", exc_info=True)
        return False, f"Failed to load configuration due to an error: {e}"


def save_config(api_key: str, api_url: str, model_id_string: str, auto_startup: bool, theme: str,
                include_cli_context: bool, include_timestamp: bool, enable_multi_step: bool,
                multi_step_max_iterations: int, auto_include_ui_info: bool,
                selected_model_id: str):
    """Saves configuration to QSettings (INI format) and updates globals. Logs the process."""
    global API_KEY, API_URL, MODEL_ID_STRING, CURRENTLY_SELECTED_MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT, INCLUDE_TIMESTAMP_IN_PROMPT, ENABLE_MULTI_STEP, MULTI_STEP_MAX_ITERATIONS
    global AUTO_INCLUDE_UI_INFO

    logger.info("Saving configuration to QSettings...")
    try:
        settings = get_settings()

        # --- Log values being saved (DEBUG level, mask API key) ---
        logger.debug("Saving values:")
        logger.debug("  API Key: %s", "****" if api_key else "<empty>") # Mask API Key
        logger.debug("  API URL: %s", api_url if api_url else "<empty>")
        logger.debug("  Model ID String: %s", model_id_string if model_id_string else "<empty>")
        logger.debug("  Selected Model ID: %s", selected_model_id if selected_model_id else "<empty>")
        logger.debug("  Auto Startup: %s", auto_startup)
        logger.debug("  Theme: %s", theme)
        logger.debug("  Include CLI Context: %s", include_cli_context)
        logger.debug("  Include Timestamp: %s", include_timestamp)
        logger.debug("  Enable Multi-Step: %s", enable_multi_step)
        logger.debug("  Multi-Step Max Iterations: %d", multi_step_max_iterations)
        logger.debug("  Auto Include UI Info: %s", auto_include_ui_info)

        # --- Save API Settings ---
        settings.beginGroup("api")
        settings.setValue("key", api_key)
        settings.setValue("url", api_url)
        settings.setValue("model_id_string", model_id_string)
        settings.endGroup()

        # --- Save General Settings ---
        settings.beginGroup("general")
        settings.setValue("auto_startup", auto_startup)
        valid_themes = ["dark", "light", "system"]
        valid_theme = theme if theme in valid_themes else DEFAULT_APP_THEME
        if theme != valid_theme:
             logger.warning(f"Attempted to save invalid theme '{theme}', saving default '{valid_theme}' instead.")
        settings.setValue("theme", valid_theme)
        settings.setValue("include_cli_context", include_cli_context)
        settings.setValue("selected_model", selected_model_id)
        settings.setValue("include_timestamp", include_timestamp)
        settings.setValue("enable_multi_step", enable_multi_step)
        # Ensure saved iteration value is at least 1
        save_iterations = max(1, multi_step_max_iterations)
        if save_iterations != multi_step_max_iterations:
            logger.warning(f"Adjusted multi_step_max_iterations from {multi_step_max_iterations} to {save_iterations} before saving.")
        settings.setValue("multi_step_max_iterations", save_iterations)
        settings.setValue("auto_include_ui_info", auto_include_ui_info)
        settings.endGroup()

        # --- Sync settings to file ---
        logger.debug("Syncing settings to file...")
        settings.sync()

        # --- Check for save errors ---
        save_status = settings.status()
        if save_status != QSettings.Status.NoError:
            # Log error but continue updating globals and applying auto-startup
            logger.error(f"Error encountered while syncing settings to file: Status Code {save_status}")
        else:
            logger.info(f"Settings saved successfully to: {settings.fileName()}")

        # --- Update global variables immediately after attempting save ---
        API_KEY, API_URL = api_key, api_url
        MODEL_ID_STRING = model_id_string
        CURRENTLY_SELECTED_MODEL_ID = selected_model_id
        AUTO_STARTUP_ENABLED = auto_startup
        APP_THEME = valid_theme
        INCLUDE_CLI_CONTEXT = include_cli_context
        INCLUDE_TIMESTAMP_IN_PROMPT = include_timestamp
        ENABLE_MULTI_STEP = enable_multi_step
        MULTI_STEP_MAX_ITERATIONS = save_iterations # Use the validated value
        AUTO_INCLUDE_UI_INFO = auto_include_ui_info
        logger.info("Global config variables updated with saved values.")
        logger.debug(f"Updated globals - AutoStart={AUTO_STARTUP_ENABLED}, Theme={APP_THEME}, SelectedModel={CURRENTLY_SELECTED_MODEL_ID}")

        # --- Apply auto-startup change using the saved value ---
        logger.info(f"Applying auto-startup setting ({AUTO_STARTUP_ENABLED})...")
        try:
            set_auto_startup(AUTO_STARTUP_ENABLED) # set_auto_startup should contain its own logging
        except Exception as e:
            # Log the error from applying auto-startup
            logger.error("Error applying auto-startup setting.", exc_info=True)

    except Exception as e:
        logger.error("Unhandled error during configuration saving process.", exc_info=True)

def reset_to_defaults_and_clear_cache():
    """
    Resets all settings in QSettings to their defaults and clears cached state.
    Also updates the global variables in this module. Logs the process.
    """
    global API_KEY, API_URL, MODEL_ID_STRING, CURRENTLY_SELECTED_MODEL_ID, AUTO_STARTUP_ENABLED, APP_THEME
    global INCLUDE_CLI_CONTEXT, INCLUDE_TIMESTAMP_IN_PROMPT, ENABLE_MULTI_STEP, MULTI_STEP_MAX_ITERATIONS
    global AUTO_INCLUDE_UI_INFO

    logger.warning("--- Resetting all settings to defaults and clearing cache ---")
    try:
        settings = get_settings()

        # Clear ALL settings managed by QSettings for this application
        logger.info(f"Clearing all settings in {settings.fileName()}...")
        settings.clear()
        logger.debug("Syncing cleared settings...")
        settings.sync()

        if settings.status() != QSettings.Status.NoError:
            logger.error(f"Error encountered while clearing/syncing settings: Status {settings.status()}")
        else:
            logger.info("All settings cleared successfully.")

        # --- Reset global variables to defaults ---
        logger.info("Resetting global config variables to defaults...")
        API_KEY = DEFAULT_API_KEY
        API_URL = DEFAULT_API_URL
        MODEL_ID_STRING = DEFAULT_MODEL_ID_STRING
        CURRENTLY_SELECTED_MODEL_ID = DEFAULT_CURRENTLY_SELECTED_MODEL_ID
        AUTO_STARTUP_ENABLED = DEFAULT_AUTO_STARTUP_ENABLED
        APP_THEME = DEFAULT_APP_THEME
        INCLUDE_CLI_CONTEXT = DEFAULT_INCLUDE_CLI_CONTEXT
        INCLUDE_TIMESTAMP_IN_PROMPT = DEFAULT_INCLUDE_TIMESTAMP
        ENABLE_MULTI_STEP = DEFAULT_ENABLE_MULTI_STEP
        MULTI_STEP_MAX_ITERATIONS = DEFAULT_MULTI_STEP_MAX_ITERATIONS
        AUTO_INCLUDE_UI_INFO = DEFAULT_AUTO_INCLUDE_UI_INFO
        logger.info("Global config variables reset.")
        logger.debug(f"Defaults applied - AutoStart={AUTO_STARTUP_ENABLED}, Theme={APP_THEME}, SelectedModel={CURRENTLY_SELECTED_MODEL_ID}")

        # --- Explicitly disable auto-startup ---
        # Important because simply clearing settings might not remove the OS-level entry
        logger.info("Disabling platform-specific auto-startup explicitly after reset...")
        try:
            set_auto_startup(False)
        except Exception as e:
            logger.error("Error explicitly disabling auto-startup during reset.", exc_info=True)

        logger.warning("--- Settings reset complete ---")

    except Exception as e:
        logger.error("Unhandled error during settings reset process.", exc_info=True)


def get_current_config() -> dict:
    """Returns the current configuration values held in this module's global state."""
    # Log at DEBUG level as this might be called frequently
    logger.debug("get_current_config() called.")
    # <<< MODIFICATION START: Add auto UI info to returned dict >>>
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
        "multi_step_max_iterations": MULTI_STEP_MAX_ITERATIONS,
        "auto_include_ui_info": AUTO_INCLUDE_UI_INFO, # Added field
    }
    # <<< MODIFICATION END >>>