# gui/main_window_state.py
# -*- coding: utf-8 -*-

import os
import json
import traceback
import logging # Import logging
from collections import deque
from typing import TYPE_CHECKING

# Import necessary components from the project
from core import config

# Type hinting for MainWindow without causing circular import at runtime
if TYPE_CHECKING:
    from .main_window import MainWindow

# --- Get Logger ---
logger = logging.getLogger(__name__)

class StateMixin:
    """Mixin containing state saving/loading logic for MainWindow."""

    def save_state(self: 'MainWindow'):
        """Saves chat history, CLI history, current directory, splitter state, and selected model."""
        if self._closing:
            logger.info("Skipping save_state during close sequence.")
            return

        logger.info("Attempting to save application state...")
        try:
            settings = config.get_settings() # Get QSettings instance

            # --- Prepare Data ---
            # Make copies to avoid issues if original deques are modified during save
            history_list = list(self.conversation_history)
            cli_history_list = list(self.cli_command_history)
            current_directory_to_save = self.current_directory
            current_selected_model_to_save = config.CURRENTLY_SELECTED_MODEL_ID # Get from config module

            logger.debug("State to save:")
            logger.debug(f"  Chat History Items: {len(history_list)}")
            logger.debug(f"  CLI History Items: {len(cli_history_list)}")
            logger.debug(f"  Current Directory: {current_directory_to_save}")
            logger.debug(f"  Selected Model: {current_selected_model_to_save if current_selected_model_to_save else '<none>'}")

            # --- Save UI/History State to QSettings ---
            logger.debug("Saving state group...")
            settings.beginGroup("state")
            settings.setValue("conversation_history", json.dumps(history_list))
            settings.setValue("current_directory", current_directory_to_save)
            settings.setValue("cli_history", json.dumps(cli_history_list))
            settings.endGroup()
            logger.debug("State group saved.")

            # --- Save UI Geometry/Splitter State ---
            if self.splitter:
                logger.debug("Saving UI group (splitter state)...")
                settings.beginGroup("ui")
                splitter_state = self.splitter.saveState()
                settings.setValue("splitter_state", splitter_state)
                settings.endGroup()
                logger.debug(f"Splitter state saved (Size: {len(splitter_state) if splitter_state else 0} bytes).")
            else:
                logger.warning("Splitter not found, cannot save its state.")

            # --- Save currently selected model via config.save_config ---
            # This might seem redundant, but ensures the selected model is stored
            # alongside other config settings managed by save_config.
            logger.debug("Updating config module with current selected model...")
            # Retrieve the rest of the config values to pass them back to save_config
            current_config_vals = config.get_current_config()
            try:
                config.save_config(
                    api_key=current_config_vals["api_key"],
                    api_url=current_config_vals["api_url"],
                    model_id_string=current_config_vals["model_id_string"],
                    auto_startup=current_config_vals["auto_startup"],
                    theme=current_config_vals["theme"],
                    include_cli_context=current_config_vals["include_cli_context"],
                    include_timestamp=current_config_vals.get("include_timestamp_in_prompt", config.DEFAULT_INCLUDE_TIMESTAMP),
                    enable_multi_step=current_config_vals["enable_multi_step"],
                    multi_step_max_iterations=current_config_vals["multi_step_max_iterations"],
                    auto_include_ui_info=current_config_vals["auto_include_ui_info"],
                    selected_model_id=current_selected_model_to_save # Pass the specific value to be saved
                )
                logger.debug("Selected model ID (%s) passed to config.save_config.", current_selected_model_to_save)
            except Exception as config_save_err:
                 # Log error from config save, but don't let it stop state saving
                 logger.error("Error occurred while calling config.save_config during state save.", exc_info=True)


            logger.info("Application state saved successfully.")

        except Exception as e:
            # Log the exception with traceback
            logger.error("Error saving application state.", exc_info=True)
            # Optionally display an error message to the user if critical

    def load_state(self: 'MainWindow'):
        """
        Loads state on startup (CWD, chat history, CLI history). Logs the process.
        Sets self.current_directory based on saved state or falls back to self.initial_directory.
        The actual process CWD change happens later in __init__ using _sync_process_cwd.
        """
        if self._closing:
            logger.info("Skipping load_state during close sequence.")
            return

        logger.info("Loading application state...")
        # --- Ensure default directories exist before loading ---
        if not hasattr(self, 'initial_directory') or not self.initial_directory:
             logger.error("CRITICAL: initial_directory not set before load_state. Cannot determine default CWD.")
             # Handle this critical error, maybe set a hardcoded default or raise exception
             # For now, set a placeholder to avoid crashing later code, but log the error.
             self.initial_directory = "." # Placeholder CWD

        if not hasattr(self, 'application_base_dir') or not self.application_base_dir:
            logger.warning("application_base_dir not set before load_state.")
            # This might be less critical than initial_directory

        try:
            settings = config.get_settings()
            # Default to the initial directory ('Space') if nothing valid is loaded
            restored_cwd = self.initial_directory
            logger.debug(f"Default CWD set to initial directory: {restored_cwd}")

            # --- Load State Group ---
            logger.debug("Loading state group...")
            settings.beginGroup("state")
            saved_cwd = settings.value("current_directory") # Load raw value first
            history_json = settings.value("conversation_history", "[]")
            cli_history_json = settings.value("cli_history", "[]")
            settings.endGroup()
            logger.debug("State group loaded.")

            # --- Load and Validate CWD ---
            logger.debug("Processing saved CWD...")
            if saved_cwd and isinstance(saved_cwd, str) and saved_cwd.strip():
                normalized_saved_cwd = os.path.normpath(saved_cwd)
                logger.info(f"Found saved directory in settings: {normalized_saved_cwd}")
                if os.path.isdir(normalized_saved_cwd): # Check if saved directory exists and is a directory
                    restored_cwd = normalized_saved_cwd
                    logger.info(f"Saved directory is valid. Using: {restored_cwd}")
                else:
                    logger.warning(f"Saved directory '{normalized_saved_cwd}' not found or invalid. Falling back to default '{self.initial_directory}'.")
                    # restored_cwd remains self.initial_directory
            else:
                logger.info(f"No valid saved directory found in settings. Using default directory '{self.initial_directory}'.")
                # restored_cwd remains self.initial_directory

            # Set the internal current directory state based on loading result
            self.current_directory = restored_cwd
            logger.info(f"Internal CWD state set to: {self.current_directory} (OS chdir will be attempted later in __init__)")

            # --- Load Chat History ---
            logger.debug("Processing saved conversation history...")
            loaded_history = []
            try:
                 # Ensure json data is string before loading
                 if not isinstance(history_json, str): history_json = str(history_json)
                 history_list = json.loads(history_json)
                 # Basic validation of history format
                 if isinstance(history_list, list) and \
                    all(isinstance(item, (list, tuple)) and len(item) == 2 and
                        isinstance(item[0], str) and isinstance(item[1], str) for item in history_list):
                     loaded_history = history_list
                     logger.info(f"Loaded {len(loaded_history)} conversation history items.")
                 elif history_json and history_json != "[]": # Log only if non-empty but invalid
                     logger.warning(f"Saved conversation history format invalid. JSON was: {history_json[:100]}...")
                 else:
                      logger.info("No conversation history found or history was empty.")
            except json.JSONDecodeError as json_err:
                 logger.warning(f"Error decoding conversation history JSON: {json_err}. History will be empty.")
            except Exception as e:
                logger.error("Unexpected error processing saved conversation history.", exc_info=True)

            # Initialize conversation_history if it doesn't exist yet (defensive)
            if not hasattr(self, 'conversation_history') or not isinstance(self.conversation_history, deque):
                logger.warning("conversation_history deque not initialized before load_state. Creating new.")
                self.conversation_history = deque(maxlen=50) # Use constant or config value for maxlen ideally
            self.conversation_history.clear(); self.conversation_history.extend(loaded_history)
            logger.debug("conversation_history deque updated.")

            # --- Load CLI History ---
            logger.debug("Processing saved CLI history...")
            loaded_cli_history = []
            try:
                if not isinstance(cli_history_json, str): cli_history_json = str(cli_history_json)
                cli_history_list = json.loads(cli_history_json)
                if isinstance(cli_history_list, list) and all(isinstance(item, str) for item in cli_history_list):
                    loaded_cli_history = cli_history_list
                    logger.info(f"Loaded {len(loaded_cli_history)} CLI history items.")
                elif cli_history_json and cli_history_json != "[]": # Log only if non-empty but invalid
                    logger.warning(f"Saved CLI history format invalid. JSON was: {cli_history_json[:100]}...")
                else:
                     logger.info("No CLI history found or history was empty.")
            except json.JSONDecodeError as json_err:
                logger.warning(f"Error decoding CLI history JSON: {json_err}. History will be empty.")
            except Exception as e:
                 logger.error("Unexpected error processing saved CLI history.", exc_info=True)

            # Initialize cli_command_history if it doesn't exist yet (defensive)
            if not hasattr(self, 'cli_command_history') or not isinstance(self.cli_command_history, deque):
                logger.warning("cli_command_history deque not initialized before load_state. Creating new.")
                self.cli_command_history = deque(maxlen=100) # Use constant/config for maxlen
            self.cli_command_history.clear(); self.cli_command_history.extend(loaded_cli_history)
            self.cli_history_index = -1 # Reset navigation index
            logger.debug("cli_command_history deque updated and index reset.")

            logger.info("Application state loading process finished.")

        except Exception as e:
            # Log the critical error with traceback
            logger.critical("CRITICAL Error during application state loading.", exc_info=True)
            logger.warning("Resetting state variables to defaults due to loading error.")
            # Ensure deques exist before clearing (Defensive)
            if not hasattr(self, 'conversation_history') or not isinstance(self.conversation_history, deque): self.conversation_history = deque(maxlen=50)
            if not hasattr(self, 'cli_command_history') or not isinstance(self.cli_command_history, deque): self.cli_command_history = deque(maxlen=100)
            self.conversation_history.clear(); self.cli_command_history.clear(); self.cli_history_index = -1
            # Ensure CWD defaults to the 'Space' directory even after error
            self.current_directory = self.initial_directory
            logger.info(f"Internal CWD state reset to default due to error: {self.current_directory}")