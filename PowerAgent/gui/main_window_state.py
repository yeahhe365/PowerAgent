# ========================================
# 文件名: PowerAgent/gui/main_window_state.py
# (MODIFIED - Updated CWD loading logic to fallback to initial_directory)
# ----------------------------------------
# gui/main_window_state.py
# -*- coding: utf-8 -*-

import os
import json
import traceback
from collections import deque
from typing import TYPE_CHECKING

# Import necessary components from the project
from core import config

# Type hinting for MainWindow without causing circular import at runtime
if TYPE_CHECKING:
    from .main_window import MainWindow


class StateMixin:
    """Mixin containing state saving/loading logic for MainWindow."""

    def save_state(self: 'MainWindow'):
        """Saves chat history, CLI history, current directory, splitter state, and selected model."""
        if self._closing: print("Skipping save_state during close sequence."); return
        try:
            settings = config.get_settings()
            history_list = list(self.conversation_history)

            # --- Save UI/History State to QSettings ---
            settings.beginGroup("state")
            settings.setValue("conversation_history", json.dumps(history_list))
            # Always save the *current* directory, whatever it is
            settings.setValue("current_directory", self.current_directory)
            settings.setValue("cli_history", json.dumps(list(self.cli_command_history)))
            settings.endGroup()

            # --- Save UI Geometry/Splitter State ---
            if self.splitter:
                settings.beginGroup("ui")
                settings.setValue("splitter_state", self.splitter.saveState())
                settings.endGroup()

            # --- Save currently selected model via config.save_config ---
            current_config_vals = config.get_current_config()
            current_selected_model = config.CURRENTLY_SELECTED_MODEL_ID

            config.save_config(
                api_key=current_config_vals["api_key"],
                api_url=current_config_vals["api_url"],
                model_id_string=current_config_vals["model_id_string"],
                auto_startup=current_config_vals["auto_startup"],
                theme=current_config_vals["theme"],
                include_cli_context=current_config_vals["include_cli_context"],
                include_timestamp=current_config_vals.get("include_timestamp_in_prompt", config.DEFAULT_INCLUDE_TIMESTAMP),
                selected_model_id=current_selected_model # Ensure this is saved
            )

            print(f"State saved: Chat History({len(history_list)}), CWD({self.current_directory}), CLI History({len(self.cli_command_history)}), SelectedModel({current_selected_model})")

        except Exception as e:
            print(f"Error saving state: {e}")
            traceback.print_exc()

    def load_state(self: 'MainWindow'):
        """
        Loads state on startup (CWD, chat history, CLI history).
        Sets self.current_directory based on saved state or falls back to self.initial_directory.
        The actual process CWD change happens later in __init__ using _sync_process_cwd.
        """
        if self._closing: return
        print("Loading state (CWD, Chat History, CLI History)...")
        try:
            settings = config.get_settings()
            # Default to the initial directory ('Space') if nothing valid is loaded
            restored_cwd = self.initial_directory

            # --- Load State Group ---
            settings.beginGroup("state")
            saved_cwd = settings.value("current_directory")
            history_json = settings.value("conversation_history", "[]")
            cli_history_json = settings.value("cli_history", "[]")
            settings.endGroup()

            # --- Load and Validate CWD ---
            if saved_cwd and isinstance(saved_cwd, str) and saved_cwd.strip():
                normalized_saved_cwd = os.path.normpath(saved_cwd)
                if os.path.isdir(normalized_saved_cwd): # Check if saved directory exists and is a directory
                    restored_cwd = normalized_saved_cwd
                    print(f"Found valid saved directory: {restored_cwd}")
                else:
                    print(f"Warning: Saved directory '{normalized_saved_cwd}' not found or invalid. Using default directory '{self.initial_directory}'.")
                    # restored_cwd remains self.initial_directory
            else:
                print(f"No valid saved directory found in settings. Using default directory '{self.initial_directory}'.")
                # restored_cwd remains self.initial_directory

            # Set the internal current directory state based on loading result
            self.current_directory = restored_cwd
            print(f"Internal CWD state set to: {self.current_directory} (will attempt chdir later)")

            # --- Load Chat History ---
            loaded_history = []
            try:
                 if not isinstance(history_json, str): history_json = str(history_json)
                 history_list = json.loads(history_json)
                 if isinstance(history_list, list) and \
                    all(isinstance(item, (list, tuple)) and len(item) == 2 and
                        isinstance(item[0], str) and isinstance(item[1], str) for item in history_list):
                     loaded_history = history_list
                     print(f"Loaded {len(loaded_history)} conversation history items.")
                 elif history_json != "[]":
                     print(f"Warning: Saved conversation history format invalid.")
            except Exception as e: print(f"Error processing saved conversation history: {e}.")
            # Initialize conversation_history if it doesn't exist yet
            if not hasattr(self, 'conversation_history') or not isinstance(self.conversation_history, deque):
                self.conversation_history = deque(maxlen=50)
            self.conversation_history.clear(); self.conversation_history.extend(loaded_history)

            # --- Load CLI History ---
            loaded_cli_history = []
            try:
                if not isinstance(cli_history_json, str): cli_history_json = str(cli_history_json)
                cli_history_list = json.loads(cli_history_json)
                if isinstance(cli_history_list, list) and all(isinstance(item, str) for item in cli_history_list):
                    loaded_cli_history = cli_history_list
                    print(f"Loaded {len(loaded_cli_history)} CLI history items.")
                elif cli_history_json != "[]": print(f"Warning: Saved CLI history format invalid.")
            except Exception as e: print(f"Error processing saved CLI history: {e}.")
            # Initialize cli_command_history if it doesn't exist yet
            if not hasattr(self, 'cli_command_history') or not isinstance(self.cli_command_history, deque):
                self.cli_command_history = deque(maxlen=100)
            self.cli_command_history.clear(); self.cli_command_history.extend(loaded_cli_history)
            self.cli_history_index = -1 # Reset navigation index

        except Exception as e:
            print(f"CRITICAL Error loading state: {e}. Resetting state variables.")
            traceback.print_exc()
            # Ensure deques exist before clearing
            if not hasattr(self, 'conversation_history') or not isinstance(self.conversation_history, deque): self.conversation_history = deque(maxlen=50)
            if not hasattr(self, 'cli_command_history') or not isinstance(self.cli_command_history, deque): self.cli_command_history = deque(maxlen=100)
            self.conversation_history.clear(); self.cli_command_history.clear(); self.cli_history_index = -1
            # Ensure CWD defaults to the 'Space' directory even after error
            self.current_directory = self.initial_directory
            print(f"Internal CWD state reset to default due to error: {self.current_directory}")