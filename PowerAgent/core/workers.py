# core/workers.py
# -*- coding: utf-8 -*-

import re
import json
import requests
import time
import os
import platform
import traceback
import datetime
import html
import logging # Import logging
# --- Typing Import ---
from typing import Optional, Dict, Any, List, Tuple
# --- End Typing Import ---
from PySide6.QtCore import QThread, Signal, QObject
from requests.adapters import HTTPAdapter

# --- Get Logger ---
logger = logging.getLogger(__name__)

# --- uiautomation Import (Logging added) ---
UIAUTOMATION_AVAILABLE_FOR_KEYBOARD = False
UIAUTOMATION_AVAILABLE_FOR_GUI = False # Separate flag for GUI parts
UIAUTOMATION_IMPORT_ERROR = ""
if platform.system() == "Windows":
    try:
        logger.debug("Attempting to import 'uiautomation' library...")
        import uiautomation as auto
        try:
            logger.debug("Verifying 'uiautomation' basic functionality...")
            auto.GetRootControl()
            UIAUTOMATION_AVAILABLE_FOR_KEYBOARD = True # Keyboard depends only on import
            UIAUTOMATION_AVAILABLE_FOR_GUI = True      # GUI depends on import and basic function
            logger.info("'uiautomation' imported and verified successfully for keyboard/GUI.")
        except Exception as verify_err:
            UIAUTOMATION_AVAILABLE_FOR_KEYBOARD = True # Import succeeded, keyboard might still work
            UIAUTOMATION_AVAILABLE_FOR_GUI = False     # Basic function failed, GUI likely won't work
            UIAUTOMATION_IMPORT_ERROR = f"Failed to verify 'uiautomation' functionality: {verify_err}. GUI control likely disabled."
            logger.error(UIAUTOMATION_IMPORT_ERROR, exc_info=False) # Log as error, no need for full traceback here
    except ImportError:
        UIAUTOMATION_IMPORT_ERROR = "Failed to import 'uiautomation'. Please install it (`pip install uiautomation`). Keyboard and GUI control disabled."
        logger.warning(UIAUTOMATION_IMPORT_ERROR)
        auto = None # type: ignore
    except Exception as import_err:
        UIAUTOMATION_IMPORT_ERROR = f"An unexpected error occurred importing 'uiautomation': {import_err}. Keyboard and GUI control disabled."
        logger.error(UIAUTOMATION_IMPORT_ERROR, exc_info=True)
        auto = None # type: ignore
else:
    UIAUTOMATION_IMPORT_ERROR = "Keyboard and GUI Automation are only supported on Windows."
    logger.info(UIAUTOMATION_IMPORT_ERROR)
    auto = None # type: ignore
# --- End uiautomation Import ---


# Import global config state using relative import
try:
    from . import config
except ImportError:
    logger.critical("Failed to import '.config'. Ensure core/__init__.py exists and check relative paths.", exc_info=True)
    # Define fallback class with all necessary attributes
    class DummyConfig:
        ENABLE_MULTI_STEP = False
        MULTI_STEP_MAX_ITERATIONS = 5
        INCLUDE_TIMESTAMP_IN_PROMPT = False
        API_KEY = None
        API_URL = None
        MODEL_ID_STRING = None
        AUTO_INCLUDE_UI_INFO = False # Add the new config attribute
        INCLUDE_CLI_CONTEXT = True # Assume default if needed by other parts
    config = DummyConfig()


# Import modularized components using relative imports
try:
    from .worker_utils import decode_output
except ImportError:
    logger.error("Failed to import '.worker_utils'", exc_info=True)
    def decode_output(b): return repr(b)

try:
    from .command_executor import execute_command_streamed
except ImportError:
    logger.error("Failed to import '.command_executor'", exc_info=True)
    def execute_command_streamed(*args, **kwargs):
        logger.error("execute_command_streamed is unavailable due to import error.")
        return kwargs.get('cwd', '.'), -1

try:
    # --- Use the GUI specific flag now ---
    if UIAUTOMATION_AVAILABLE_FOR_GUI:
        logger.debug("GUI is available, importing GuiController and get_active_window_ui_text.")
        from .gui_controller import GuiController, get_active_window_ui_text # Import the new function
    else:
        # Define fallbacks if GUI is not available
        logger.info(f"GUI Controller features disabled ({UIAUTOMATION_IMPORT_ERROR}). Defining fallbacks.")
        GuiController = None # type: ignore
        def get_active_window_ui_text(*args, **kwargs) -> str:
            logger.warning("get_active_window_ui_text called but GUI is unavailable.")
            return "错误: GUI 分析功能在此平台或配置下不可用。"
except ImportError as e:
    logger.warning(f"Optional module '.gui_controller' not found or failed to import: {e}. GUI functionality disabled.", exc_info=False)
    GuiController = None # type: ignore
    UIAUTOMATION_AVAILABLE_FOR_GUI = False # Ensure flag is False on import error
    UIAUTOMATION_IMPORT_ERROR = f"Import failed: {e}"
    def get_active_window_ui_text(*args, **kwargs) -> str:
         logger.warning(f"get_active_window_ui_text called but GUI controller import failed ({UIAUTOMATION_IMPORT_ERROR}).")
         return f"错误: GUI 分析功能不可用 ({UIAUTOMATION_IMPORT_ERROR})."
# --- End Relative Imports ---


try:
    from urllib3.util.retry import Retry
    URLLIB3_RETRY_AVAILABLE = True
    logger.debug("urllib3 Retry strategy available.")
except ImportError:
    logger.warning("Failed to import Retry from urllib3.util.retry. Request retries disabled.")
    URLLIB3_RETRY_AVAILABLE = False

# --- Key Mapping (Lowercase key names to auto.Keys constants) ---
KEY_MAPPING = {}
if UIAUTOMATION_AVAILABLE_FOR_KEYBOARD and auto: # Check keyboard flag
    logger.debug("Mapping key names to uiautomation constants.")
    KEY_MAPPING = {
        'win': auto.Keys.VK_LWIN, 'windows': auto.Keys.VK_LWIN,
        'ctrl': auto.Keys.VK_CONTROL, 'control': auto.Keys.VK_CONTROL,
        'alt': auto.Keys.VK_MENU, 'menu': auto.Keys.VK_MENU,
        'shift': auto.Keys.VK_SHIFT,
        'enter': auto.Keys.VK_RETURN, 'return': auto.Keys.VK_RETURN,
        'esc': auto.Keys.VK_ESCAPE, 'escape': auto.Keys.VK_ESCAPE,
        'tab': auto.Keys.VK_TAB,
        'space': auto.Keys.VK_SPACE, 'spacebar': auto.Keys.VK_SPACE,
        'backspace': auto.Keys.VK_BACK,
        'delete': auto.Keys.VK_DELETE, 'del': auto.Keys.VK_DELETE,
        'insert': auto.Keys.VK_INSERT, 'ins': auto.Keys.VK_INSERT,
        'home': auto.Keys.VK_HOME,
        'end': auto.Keys.VK_END,
        'pageup': auto.Keys.VK_PRIOR, 'pgup': auto.Keys.VK_PRIOR,
        'pagedown': auto.Keys.VK_NEXT, 'pgdn': auto.Keys.VK_NEXT,
        'up': auto.Keys.VK_UP, 'uparrow': auto.Keys.VK_UP,
        'down': auto.Keys.VK_DOWN, 'downarrow': auto.Keys.VK_DOWN,
        'left': auto.Keys.VK_LEFT, 'leftarrow': auto.Keys.VK_LEFT,
        'right': auto.Keys.VK_RIGHT, 'rightarrow': auto.Keys.VK_RIGHT,
        'f1': auto.Keys.VK_F1, 'f2': auto.Keys.VK_F2, 'f3': auto.Keys.VK_F3,
        'f4': auto.Keys.VK_F4, 'f5': auto.Keys.VK_F5, 'f6': auto.Keys.VK_F6,
        'f7': auto.Keys.VK_F7, 'f8': auto.Keys.VK_F8, 'f9': auto.Keys.VK_F9,
        'f10': auto.Keys.VK_F10, 'f11': auto.Keys.VK_F11, 'f12': auto.Keys.VK_F12,
        'capslock': auto.Keys.VK_CAPITAL,
        'numlock': auto.Keys.VK_NUMLOCK,
        'scrolllock': auto.Keys.VK_SCROLL,
        'printscreen': auto.Keys.VK_SNAPSHOT, 'prtsc': auto.Keys.VK_SNAPSHOT,
        # Add more mappings as needed
    }
else:
     logger.debug("Keyboard automation not available, skipping key mapping.")

# --- Worker Threads ---

class ApiWorkerThread(QThread):
    """Handles AI interaction, response parsing, and action execution (commands/keyboard/GUI)."""
    # (Signals remain the same)
    api_result = Signal(str, float) # (reply_for_display, elapsed_time)
    cli_output_signal = Signal(bytes)
    cli_error_signal = Signal(bytes)
    directory_changed_signal = Signal(str, bool) # (new_dir, is_manual)
    task_finished = Signal()
    ai_command_echo_signal = Signal(str) # Emits the command string to be echoed in chat

    def __init__(self, api_key: str, api_url: str, model_id: str, history: List[List[str]], prompt: str, cwd: str):
        super().__init__()
        logger.info("Initializing ApiWorkerThread...")
        self._api_key = api_key # Keep API key internal, do not log directly
        self._api_url = api_url.rstrip('/') if api_url else ""
        self._model_id = model_id
        self._history = [list(item) if isinstance(item, (list, tuple)) and len(item) == 2 else ["unknown", str(item)] for item in history]
        self._cwd = cwd
        self._is_running = True
        self._gui_controller: Optional['GuiController'] = None
        self._action_outcome_message: str = ""
        self._keyboard_available = UIAUTOMATION_AVAILABLE_FOR_KEYBOARD
        self._gui_available = UIAUTOMATION_AVAILABLE_FOR_GUI

        # Log initialization parameters (mask sensitive data)
        logger.debug("ApiWorkerThread Init Params:")
        logger.debug("  API Key Provided: %s", bool(self._api_key)) # Log presence, not value
        logger.debug("  API URL: %s", self._api_url if self._api_url else "<Not Set>")
        logger.debug("  Model ID: %s", self._model_id if self._model_id else "<Not Set>")
        logger.debug("  Initial History Length: %d", len(self._history))
        # Optionally log prompt if not sensitive, or its length
        logger.debug("  Initial Prompt Length: %d", len(prompt) if prompt else 0)
        # logger.debug("  Initial Prompt: %s", prompt[:100] + "..." if prompt else "<empty>") # Be careful with prompt content
        logger.debug("  Initial CWD: %s", self._cwd)
        logger.debug("  Keyboard Available: %s", self._keyboard_available)
        logger.debug("  GUI Available: %s", self._gui_available)
        logger.info("ApiWorkerThread initialized.")


    def stop(self):
        logger.info("ApiWorkerThread stop() called. Setting internal flag.")
        self._is_running = False

    def _update_history_with_outcome(self, ai_reply_cleaned: str):
        """Adds AI reply (if new) and action outcome to history."""
        # Add AI reply if it's non-empty and different from the last assistant message
        if ai_reply_cleaned:
            last_msg_role = self._history[-1][0].lower() if self._history else None
            last_msg_content = self._history[-1][1] if self._history else None
            if last_msg_role != 'assistant' or last_msg_content != ai_reply_cleaned:
                 logger.debug("Adding AI reply (cleaned) to history.")
                 self._history.append(["assistant", ai_reply_cleaned])
            else:
                 logger.debug("Skipping duplicate AI reply in history.")

        # Add action outcome if it exists
        if self._action_outcome_message:
            logger.info(f"Adding action outcome to history: {self._action_outcome_message[:100]}...")
            last_msg_role = self._history[-1][0].lower() if self._history else None
            last_msg_content = self._history[-1][1] if self._history else None
            if last_msg_role != 'system' or last_msg_content != self._action_outcome_message:
                logger.debug("Appending system message with action outcome to history.")
                self._history.append(["system", self._action_outcome_message])
            else:
                 logger.debug("Skipping duplicate system outcome message in history.")
            self._action_outcome_message = "" # Clear after adding

    def _try_delete_gui_controller(self):
        """Safely attempt to schedule GuiController deletion."""
        if self._gui_controller:
            controller_instance = self._gui_controller
            logger.info("Attempting to schedule GuiController for deletion.")
            self._gui_controller = None # Clear internal reference first
            try:
                # Disconnect signals robustly
                if hasattr(controller_instance, 'error_signal') and callable(getattr(controller_instance.error_signal, 'disconnect', None)):
                    try:
                        controller_instance.error_signal.disconnect()
                        logger.debug("Disconnected signals from GuiController instance.")
                    except (TypeError, RuntimeError) as disconn_err:
                        logger.warning(f"Error disconnecting signal from GuiController: {disconn_err}")
            except Exception as e:
                 logger.warning(f"Unexpected error during GuiController disconnect logic: {e}")

            try:
                controller_instance.deleteLater() # Schedule deletion
                logger.info("GuiController scheduled for deletion via deleteLater().")
            except Exception as del_err:
                 logger.error(f"Error scheduling GuiController deletion: {del_err}")
        else:
             logger.debug("No GuiController instance to delete.")

    def run(self):
        """Main execution logic: Initializes GUI controller, then branches based on config.ENABLE_MULTI_STEP."""
        logger.info("ApiWorkerThread run() started.")
        # Initialize GUI Controller only if GUI is available
        if self._gui_available and GuiController:
            logger.info("GUI Automation available. Initializing GuiController instance...")
            try:
                self._gui_controller = GuiController()
                if self._gui_controller:
                    # Connect error signal from controller to our handler
                    self._gui_controller.error_signal.connect(self._try_emit_cli_error)
                    logger.debug("Connected GuiController error_signal.")
                    # Verify if the instance is actually available after init
                    if not self._gui_controller.is_available():
                        logger.warning("GuiController instance failed is_available() check after init. Disabling GUI features.")
                        self._gui_controller = None # Set to None if not truly available
                    else:
                        logger.info("GuiController initialized successfully.")
                else:
                    logger.error("Failed to instantiate GuiController.")
            except Exception as gui_init_err:
                logger.error("Error initializing GuiController.", exc_info=True)
                self._gui_controller = None # Ensure it's None on error
                self._try_emit_cli_error(f"Failed GUI Controller init: {gui_init_err}")
        else:
             logger.info("GUI Automation not available. GUI controller will not be initialized.")
             self._gui_controller = None

        try:
            # Determine execution mode based on global config
            is_multi_step = getattr(config, 'ENABLE_MULTI_STEP', False)
            logger.info(f"Multi-step mode enabled: {is_multi_step}")

            if is_multi_step:
                self._run_iterative_multi_step()
            else:
                self._run_single_step()
        except Exception as main_run_err:
             # Catch any unhandled exceptions within the run logic
             logger.critical("CRITICAL UNHANDLED ERROR in ApiWorkerThread run method.", exc_info=True)
             # Try to emit error to UI if possible
             self._try_emit_cli_error(f"CRITICAL THREAD ERROR: {main_run_err}")
        finally:
             # This block runs whether the try block succeeded or failed
             logger.info(f"ApiWorkerThread run() sequence finished (is_running={self._is_running}).")
             # Ensure controller cleanup happens AFTER the run logic finishes
             self._try_delete_gui_controller()
             # Emit the task_finished signal reliably
             try:
                 logger.debug("Emitting task_finished signal.")
                 self.task_finished.emit()
             except RuntimeError as e:
                 logger.warning(f"Could not emit task_finished signal (RuntimeError - likely target deleted): {e}")
             except Exception as e:
                  logger.error("Error emitting task_finished signal.", exc_info=True)
             logger.info("ApiWorkerThread run() finished.")

    def _run_single_step(self):
        """Handles a single API call and subsequent action execution."""
        logger.info("Running in single-step mode.")
        elapsed_time = 0.0
        raw_model_reply = "错误: API 调用未完成。"
        try:
            if not self._is_running:
                logger.warning("Single-step execution cancelled before API call (stop signal received).")
                raw_model_reply = "错误: API 调用已取消。"
            else:
                logger.info("Sending single-step API request...")
                start_time = time.time()
                raw_model_reply = self._send_message_to_model(is_multi_step_flow=False)
                end_time = time.time()
                elapsed_time = end_time - start_time
                logger.info(f"Single-step API call finished in {elapsed_time:.2f}s.")
                logger.debug(f"Raw model reply (single-step): {raw_model_reply[:200]}...") # Log truncated reply

            # Check stop signal again after API call
            if not self._is_running and raw_model_reply != "错误: API 调用已取消。":
                logger.warning("Stop signal received after API call completed. Overriding reply.")
                raw_model_reply = "错误: API 调用已取消。"

            reply_for_display, reply_for_parsing = raw_model_reply or "", raw_model_reply or ""
            try:
                logger.debug("Cleaning <think> tags from reply...")
                temp_cleaned_reply = re.sub(r"<think>.*?</think>", "", reply_for_parsing, flags=re.DOTALL | re.IGNORECASE).strip()
                reply_for_display, reply_for_parsing = temp_cleaned_reply, temp_cleaned_reply
                logger.debug(f"Reply after <think> cleaning: {reply_for_display[:200]}...")
            except Exception as clean_err:
                logger.warning("Error cleaning <think> tags.", exc_info=True)

            # --- Emit Result ---
            if self._is_running:
                 logger.debug("Cleaning action tags for UI display...")
                 display_text_for_emit = reply_for_display # Start with think-cleaned version
                 actions_to_clean = [r"<cmd>.*?</cmd>", r"<gui_action\s+call=.*?/>", r"<keyboard\s+call=.*?/>", r"<get_ui_info\s*.*?/>", r"<continue />"]
                 for pattern in actions_to_clean:
                     try: display_text_for_emit = re.sub(pattern, "", display_text_for_emit, flags=re.DOTALL | re.IGNORECASE).strip()
                     except Exception as action_clean_err: logger.warning(f"Error cleaning pattern '{pattern}': {action_clean_err}")
                 # Ensure we emit something, even if it's the raw reply or error
                 display_text_to_emit = display_text_for_emit if display_text_for_emit else raw_model_reply
                 if "错误:" in raw_model_reply and "错误:" not in display_text_to_emit: display_text_to_emit = raw_model_reply # Prioritize showing errors
                 logger.debug(f"Text to emit to UI: {display_text_to_emit[:200]}...")
                 self._try_emit_api_result(display_text_to_emit, elapsed_time)
            else:
                 logger.info("Stop signal set, skipping api_result emission.")

            # --- Parse and Execute Action ---
            if not self._is_running: logger.info("Stop signal set, skipping action parsing and execution."); return

            command_to_run, keyboard_action_to_run, gui_action_to_run, get_ui_request = None, None, None, None
            action_parsed = False
            if reply_for_parsing and isinstance(reply_for_parsing, str) and "错误:" not in raw_model_reply:
                logger.info("Parsing reply for actions...")
                try:
                    # --- Action Parsing Logic (Same as before, just added logging) ---
                    command_match = re.search(r"<cmd>\s*(.*?)\s*</cmd>", reply_for_parsing, re.DOTALL | re.IGNORECASE)
                    keyboard_match = re.search(r"""<keyboard\s+call=['"]([^'"]+)['"]\s+(?:key=['"]([^'"]+)['"]|text=['"](.*?)['"]|keys=['"]([^'"]+)['"])\s*/>""", reply_for_parsing, re.VERBOSE | re.DOTALL | re.IGNORECASE)
                    gui_match = re.search(r"""<gui_action\s+call=['"]([^'"]+)['"]\s+args=['"](.*?)['"]\s*/>""", reply_for_parsing, re.VERBOSE | re.DOTALL | re.IGNORECASE)
                    get_ui_info_match = re.search(r"<get_ui_info\s*(.*?)\s*/>", reply_for_parsing, re.IGNORECASE)

                    if command_match:
                        command_to_run = command_match.group(1).strip() or None
                        if command_to_run: logger.info(f"Command action parsed: '{command_to_run}'"); action_parsed = True
                    elif keyboard_match:
                        kb_call = keyboard_match.group(1).strip().lower(); kb_key = keyboard_match.group(2); kb_text = keyboard_match.group(3); kb_keys = keyboard_match.group(4)
                        keyboard_action_to_run = {"call": kb_call}
                        if kb_key is not None: keyboard_action_to_run["key"] = kb_key.strip()
                        if kb_text is not None: keyboard_action_to_run["text"] = html.unescape(kb_text) # Unescape here
                        if kb_keys is not None: keyboard_action_to_run["keys"] = kb_keys.strip()
                        logger.info(f"Keyboard action parsed: {keyboard_action_to_run}"); action_parsed = True
                    elif gui_match:
                        try:
                            gui_call, gui_args_json_html = gui_match.groups(); gui_args_json = html.unescape(gui_args_json_html.strip()); gui_args_dict = json.loads(gui_args_json)
                            gui_action_to_run = {"call": gui_call.strip(), "args": gui_args_dict}; logger.info(f"GUI action parsed: {gui_action_to_run['call']}"); action_parsed = True
                        except Exception as gui_parse_err: logger.error(f"Error parsing GUI action JSON arguments: {gui_parse_err}"); self._try_emit_cli_error(f"Error parsing GUI action args: {gui_parse_err}")
                    elif get_ui_info_match:
                         params_str = get_ui_info_match.group(1)
                         get_ui_request = {"params": params_str}
                         logger.info(f"Get UI Info action parsed. Params: '{params_str}'"); action_parsed = True
                    else:
                        logger.info("No executable action tag found in reply.")

                except Exception as e:
                    logger.error("Error parsing action tags from reply.", exc_info=True)
                    self._try_emit_cli_error(f"Error parsing reply: {e}")
            elif "错误:" in raw_model_reply:
                 logger.info("Skipping action parsing due to error in model reply.")
            else:
                 logger.info("No reply content to parse for actions.")

            # --- Execute Action ---
            if not self._is_running: logger.info("Stop signal set, skipping action execution."); return

            if command_to_run:
                logger.info(f"Executing command: '{command_to_run}'...")
                self._try_emit_ai_command_echo(command_to_run) # Echo command to chat
                status_message = f"Model {self._cwd}> {command_to_run}"; self._try_emit_cli_output_bytes(status_message.encode('utf-8')) # Echo to CLI
                try:
                    original_cwd = self._cwd
                    # Updated to receive four values
                    new_cwd, exit_code, stdout_summary, stderr_summary = execute_command_streamed(
                        command=command_to_run,
                        cwd=self._cwd,
                        stop_flag_func=lambda: not self._is_running,
                        output_signal=self.cli_output_signal, # Still used for live streaming to GUI
                        error_signal=self.cli_error_signal,   # Still used for live streaming to GUI
                        directory_changed_signal=self.directory_changed_signal,
                        is_manual_command=False
                    )
                    self._cwd = new_cwd
                    logger.info(f"Single-step command execution finished. ExitCode: {exit_code}, New CWD: {self._cwd}, STDOUT len: {len(stdout_summary)}, STDERR len: {len(stderr_summary)}")

                    # Construct and emit outcome message for single step, similar to multi-step for consistency in logging/display if desired
                    # This might be useful if we want to display the summary in the CLI output area after execution.
                    outcome_parts = [f"Command: '{command_to_run}'", f"Exit Code: {exit_code if exit_code is not None else 'N/A'}"]
                    if original_cwd != self._cwd:
                        outcome_parts.append(f"CWD: '{self._cwd}'")
                    
                    # Emit STDOUT summary if present
                    if stdout_summary:
                        stdout_msg = f"\n--- STDOUT (Summary) ---\n{stdout_summary}\n--- END STDOUT ---"
                        logger.debug(f"Emitting single-step STDOUT summary: {stdout_msg[:200]}...")
                        self._try_emit_cli_output_bytes(stdout_msg.encode('utf-8'), is_stderr=False)
                    
                    # Emit STDERR summary if present
                    if stderr_summary:
                        stderr_msg = f"\n--- STDERR (Summary) ---\n{stderr_summary}\n--- END STDERR ---"
                        logger.debug(f"Emitting single-step STDERR summary: {stderr_msg[:200]}...")
                        self._try_emit_cli_output_bytes(stderr_msg.encode('utf-8'), is_stderr=True) # Emit to error signal

                    # Note: _action_outcome_message is not typically used for history in single-step mode,
                    # but we could set it if there's a desire to log it or use it elsewhere.
                    # For now, direct emission of summaries to GUI is the primary goal here.

                except Exception as exec_err:
                    logger.error("Error during single-step command execution.", exc_info=True)
                    self._try_emit_cli_error(f"Command execution error: {exec_err}")
            elif keyboard_action_to_run:
                logger.info(f"Executing keyboard action: {keyboard_action_to_run}...")
                success, outcome_msg = self._execute_keyboard_action(keyboard_action_to_run)
                if not success: self._try_emit_cli_error(outcome_msg) # Report failure
                logger.info(f"Keyboard action finished. Success: {success}, Message: {outcome_msg}")
            elif gui_action_to_run:
                logger.info(f"Executing GUI action: {gui_action_to_run['call']}...")
                if self._gui_available and self._gui_controller:
                    logger.debug("Waiting 1.0s before GUI action...")
                    time.sleep(1.0)
                    if not self._is_running: logger.info("Aborted after delay, before GUI action execution."); return
                    if self._gui_controller and self._gui_controller.is_available(): # Re-check
                        try:
                            call_name = gui_action_to_run.get('call', 'Unknown'); args = gui_action_to_run.get('args', {}); timeout = args.get('wait_timeout', 5)
                            success, result_value = False, None
                            gui_method = getattr(self._gui_controller, call_name, None)
                            if callable(gui_method):
                                 logger.debug(f"Calling GuiController method '{call_name}' with timeout {timeout}s.")
                                 if call_name in ['click_control', 'set_text', 'select_item', 'toggle_checkbox']: success = gui_method(args, timeout)
                                 elif call_name in ['get_text', 'get_control_state']: result_value = gui_method(args, timeout); success = result_value is not None
                                 else: self._try_emit_cli_error(f"Unsupported GUI action call: '{call_name}'"); logger.error(f"Unsupported GUI action call: '{call_name}'")
                            else:
                                self._try_emit_cli_error(f"Unknown GUI action call in GuiController: '{call_name}'"); logger.error(f"Unknown GUI action call in GuiController: '{call_name}'")
                            # Log results/failures
                            if success: logger.info(f"GUI action '{call_name}' succeeded.")
                            else: logger.warning(f"GUI action '{call_name}' failed.")
                            if result_value is not None: logger.info(f"GUI get action result: '{str(result_value)[:100]}...'"); self._try_emit_cli_output_bytes(f"GUI get action result: {str(result_value)}".encode('utf-8'))
                        except Exception as gui_exec_err: logger.error(f"Error executing GUI action '{gui_action_to_run.get('call')}'", exc_info=True); self._try_emit_cli_error(f"GUI action execution error: {gui_exec_err}")
                    else: logger.error("Cannot execute GUI action: Controller became unavailable."); self._try_emit_cli_error("Cannot execute GUI action: Controller became unavailable.")
                else: logger.error("Cannot execute GUI action: GUI Automation not available."); self._try_emit_cli_error("Cannot execute GUI action: GUI Automation not available.")
            elif get_ui_request:
                 # Get UI Info is typically only useful in multi-step, but handle it here too if requested
                 logger.info("Executing Get UI Info action (Single Step)...")
                 params_str = get_ui_request.get("params", ""); format_type = "text"; max_depth = 3
                 try:
                     fmt_match = re.search(r"format=['\"]([^'\"]+)['\"]", params_str, re.IGNORECASE); dep_match = re.search(r"max_depth=['\"](\d+)['\"]", params_str, re.IGNORECASE)
                     if fmt_match: format_type = fmt_match.group(1).lower()
                     if dep_match: max_depth = int(dep_match.group(1))
                 except Exception as param_parse_err: logger.warning(f"Could not parse get_ui_info params '{params_str}': {param_parse_err}")
                 logger.info(f"Getting UI info (Format: {format_type}, Depth: {max_depth})")
                 ui_text_info = get_active_window_ui_text(format_type, max_depth)
                 if ui_text_info:
                     logger.info(f"Get UI Info result (first 100 chars): {ui_text_info[:100]}...")
                     # Optionally emit this info to the user or just log it
                     self._try_emit_cli_output_bytes(f"--- UI Info Retrieved ---\n{ui_text_info}\n--- End UI Info ---".encode('utf-8'))
                 else: logger.warning("Get UI Info action returned no information.")
            else:
                 logger.info("No action executed in this step.")

        except Exception as single_step_err:
             logger.error("Unexpected error in _run_single_step logic.", exc_info=True)
             self._try_emit_cli_error(f"内部错误: {single_step_err}")
             self._try_emit_api_result(f"错误: 执行期间发生内部错误。", elapsed_time)
        finally:
            logger.info("Single-step execution finished.")

    def _run_iterative_multi_step(self):
        """Handles the application-driven multi-step flow including keyboard/GUI actions."""
        logger.info("Running in iterative multi-step mode.")
        max_iterations = getattr(config, 'MULTI_STEP_MAX_ITERATIONS', 5)
        current_iteration = 0
        last_emitted_reply_content = None
        logger.info(f"Max iterations set to: {max_iterations}")

        while self._is_running and current_iteration < max_iterations:
            current_iteration += 1
            logger.info(f"--- Multi-Step Iteration {current_iteration}/{max_iterations} Start ---")
            self._action_outcome_message = "" # Clear outcome message for this iteration
            action_found_this_iteration = False
            elapsed_time = 0.0

            # --- API Call ---
            if not self._is_running: logger.warning(f"Iteration {current_iteration} aborted: stop signal before API call."); break
            logger.info(f"Iteration {current_iteration}: Sending API request...")
            start_time = time.time()
            raw_model_reply = "错误: API 调用未完成。"
            try: raw_model_reply = self._send_message_to_model(is_multi_step_flow=True)
            except Exception as api_err: logger.error(f"Iteration {current_iteration}: API call exception.", exc_info=True); raw_model_reply = f"错误: API 调用期间发生意外错误: {api_err}"
            finally: end_time = time.time(); elapsed_time = end_time - start_time; logger.info(f"Iteration {current_iteration}: API call finished in {elapsed_time:.2f}s.")
            logger.debug(f"Iteration {current_iteration}: Raw model reply: {raw_model_reply[:200]}...")

            if not self._is_running: logger.warning(f"Iteration {current_iteration}: Stop signal received after API call."); break

            # --- Process Reply ---
            reply_for_display, reply_for_parsing = raw_model_reply or "", raw_model_reply or ""
            try:
                logger.debug(f"Iteration {current_iteration}: Cleaning <think> tags...")
                temp_cleaned_reply = re.sub(r"<think>.*?</think>", "", reply_for_parsing, flags=re.DOTALL | re.IGNORECASE).strip()
                reply_for_display, reply_for_parsing = temp_cleaned_reply, temp_cleaned_reply
                # Also clean <continue /> tag
                reply_for_display = reply_for_display.replace("<continue />", "").strip()
                reply_for_parsing = reply_for_parsing.replace("<continue />", "").strip()
                logger.debug(f"Iteration {current_iteration}: Reply after <think>/<continue> cleaning: {reply_for_display[:200]}...")
            except Exception as clean_err: logger.warning(f"Iteration {current_iteration}: Error cleaning tags.", exc_info=True)

            # --- Emit Text Result to UI (if changed or error) ---
            logger.debug(f"Iteration {current_iteration}: Cleaning action tags for UI display...")
            display_text_for_emit = reply_for_display
            actions_to_clean = [r"<cmd>.*?</cmd>", r"<gui_action\s+call=.*?/>", r"<keyboard\s+call=.*?/>", r"<get_ui_info\s*.*?/>"]
            for pattern in actions_to_clean:
                try: display_text_for_emit = re.sub(pattern, "", display_text_for_emit, flags=re.DOTALL | re.IGNORECASE).strip()
                except Exception as action_clean_err: logger.warning(f"Iteration {current_iteration}: Error cleaning pattern '{pattern}': {action_clean_err}")
            display_text_to_emit = display_text_for_emit if display_text_for_emit else raw_model_reply
            if "错误:" in raw_model_reply and "错误:" not in display_text_to_emit: display_text_to_emit = raw_model_reply
            logger.debug(f"Iteration {current_iteration}: Text to emit to UI: {display_text_to_emit[:200]}...")
            if display_text_to_emit and (display_text_to_emit != last_emitted_reply_content or "错误:" in display_text_to_emit):
                self._try_emit_api_result(display_text_to_emit, elapsed_time)
                last_emitted_reply_content = display_text_to_emit
                logger.info(f"Iteration {current_iteration}: Emitted api_result to UI.")
            else: logger.debug(f"Iteration {current_iteration}: Skipping api_result emission (no new content or error).")

            if not self._is_running: logger.warning(f"Iteration {current_iteration}: Stop signal set after processing reply."); break

            # --- Parse and Execute Action ---
            command_to_run, keyboard_action_to_run, gui_action_to_run, get_ui_request = None, None, None, None
            exit_code = None # Store command exit code

            if reply_for_parsing and isinstance(reply_for_parsing, str) and "错误:" not in raw_model_reply:
                logger.info(f"Iteration {current_iteration}: Parsing reply for actions...")
                try:
                    # --- Action Parsing Logic (Same as single step) ---
                    command_match = re.search(r"<cmd>\s*(.*?)\s*</cmd>", reply_for_parsing, re.DOTALL | re.IGNORECASE)
                    keyboard_match = re.search(r"""<keyboard\s+call=['"]([^'"]+)['"]\s+(?:key=['"]([^'"]+)['"]|text=['"](.*?)['"]|keys=['"]([^'"]+)['"])\s*/>""", reply_for_parsing, re.VERBOSE | re.DOTALL | re.IGNORECASE)
                    gui_match = re.search(r"""<gui_action\s+call=['"]([^'"]+)['"]\s+args=['"](.*?)['"]\s*/>""", reply_for_parsing, re.VERBOSE | re.DOTALL | re.IGNORECASE)
                    get_ui_info_match = re.search(r"<get_ui_info\s*(.*?)\s*/>", reply_for_parsing, re.IGNORECASE)

                    if command_match:
                        command_to_run = command_match.group(1).strip() or None
                        if command_to_run: logger.info(f"Iteration {current_iteration}: Command action parsed: '{command_to_run}'"); action_found_this_iteration = True
                    elif keyboard_match:
                        kb_call = keyboard_match.group(1).strip().lower(); kb_key = keyboard_match.group(2); kb_text = keyboard_match.group(3); kb_keys = keyboard_match.group(4)
                        keyboard_action_to_run = {"call": kb_call}
                        if kb_key is not None: keyboard_action_to_run["key"] = kb_key.strip()
                        if kb_text is not None: keyboard_action_to_run["text"] = html.unescape(kb_text)
                        if kb_keys is not None: keyboard_action_to_run["keys"] = kb_keys.strip()
                        logger.info(f"Iteration {current_iteration}: Keyboard action parsed: {keyboard_action_to_run}"); action_found_this_iteration = True
                    elif gui_match:
                        try:
                            gui_call, gui_args_json_html = gui_match.groups(); gui_args_json = html.unescape(gui_args_json_html.strip()); gui_args_dict = json.loads(gui_args_json)
                            gui_action_to_run = {"call": gui_call.strip(), "args": gui_args_dict}; logger.info(f"Iteration {current_iteration}: GUI action parsed: {gui_action_to_run['call']}"); action_found_this_iteration = True
                        except Exception as gui_parse_err: logger.error(f"Iteration {current_iteration}: Error parsing GUI action JSON arguments: {gui_parse_err}"); self._try_emit_cli_error(f"Error parsing GUI action args: {gui_parse_err}")
                    elif get_ui_info_match:
                         params_str = get_ui_info_match.group(1)
                         get_ui_request = {"params": params_str}
                         logger.info(f"Iteration {current_iteration}: Get UI Info action parsed. Params: '{params_str}'"); action_found_this_iteration = True
                    else: logger.info(f"Iteration {current_iteration}: No executable action tag found in reply.")

                except Exception as e: logger.error(f"Iteration {current_iteration}: Error parsing action tags from reply.", exc_info=True); self._try_emit_cli_error(f"Error parsing reply: {e}")
            elif "错误:" in raw_model_reply: logger.info(f"Iteration {current_iteration}: Skipping action parsing due to error in model reply.")
            else: logger.info(f"Iteration {current_iteration}: No reply content to parse for actions.")

            # --- Action Execution Logic (with outcome message generation) ---
            if not self._is_running: logger.warning(f"Iteration {current_iteration}: Stop signal set, skipping action execution."); break

            action_executed = False # Flag to track if any action ran this iteration
            if command_to_run:
                action_executed = True
                logger.info(f"Iteration {current_iteration}: Executing command: '{command_to_run}'...")
                self._try_emit_ai_command_echo(command_to_run)
                status_message = f"Model {self._cwd}> {command_to_run}"; self._try_emit_cli_output_bytes(status_message.encode('utf-8'))
                try:
                    original_cwd = self._cwd
                    # Updated to receive four values
                    new_cwd, exit_code, stdout_summary, stderr_summary = execute_command_streamed(
                        command=command_to_run,
                        cwd=self._cwd,
                        stop_flag_func=lambda: not self._is_running,
                        output_signal=self.cli_output_signal,
                        error_signal=self.cli_error_signal,
                        directory_changed_signal=self.directory_changed_signal,
                        is_manual_command=False
                    )
                    self._cwd = new_cwd
                    logger.info(f"Iteration {current_iteration}: Command finished. ExitCode: {exit_code}, New CWD: {self._cwd}, STDOUT len: {len(stdout_summary)}, STDERR len: {len(stderr_summary)}")

                    outcome_parts = [f"Command: '{command_to_run}'"]
                    outcome_parts.append(f"Exit Code: {exit_code if exit_code is not None else 'N/A (e.g., cd)'}")

                    if original_cwd != self._cwd:
                        outcome_parts.append(f"CWD: '{self._cwd}'")

                    outcome_parts.append("STDOUT:\n---")
                    outcome_parts.append(stdout_summary if stdout_summary else "[EMPTY]")
                    outcome_parts.append("---")

                    outcome_parts.append("STDERR:\n---")
                    outcome_parts.append(stderr_summary if stderr_summary else "[EMPTY]")
                    outcome_parts.append("---")

                    self._action_outcome_message = "\n".join(outcome_parts)
                    if exit_code == -999: # Stopped by user
                        self._is_running = False # Ensure loop breaks
                    
                    time.sleep(0.5 if self._is_running else 0)
                except Exception as exec_err:
                    logger.error(f"Iteration {current_iteration}: Error executing command or processing its outcome.", exc_info=True)
                    self._action_outcome_message = f"System Error: Failed command '{command_to_run[:50]}...': {exec_err}"
                    self._try_emit_cli_error(self._action_outcome_message)
                if not self._is_running: break # Break if stopped by user

            elif keyboard_action_to_run:
                action_executed = True
                logger.info(f"Iteration {current_iteration}: Executing keyboard action: {keyboard_action_to_run}...")
                success, outcome_msg = self._execute_keyboard_action(keyboard_action_to_run)
                self._action_outcome_message = outcome_msg
                if not success: self._try_emit_cli_error(outcome_msg)
                logger.info(f"Iteration {current_iteration}: Keyboard action finished. Success: {success}, Message: {outcome_msg}")
                time.sleep(0.5 if self._is_running else 0)

            elif gui_action_to_run:
                action_executed = True
                logger.info(f"Iteration {current_iteration}: Executing GUI action: {gui_action_to_run['call']}...")
                action_success, action_error_message, action_result_value = False, "", None
                if self._gui_available and self._gui_controller:
                    logger.debug(f"Iteration {current_iteration}: Waiting 1.0s before GUI action...")
                    time.sleep(1.0)
                    if not self._is_running: logger.info(f"Iteration {current_iteration}: Aborted after delay, before GUI action execution."); break
                    if self._gui_controller and self._gui_controller.is_available():
                        try:
                            call_name = gui_action_to_run.get('call', 'Unknown'); args = gui_action_to_run.get('args', {}); timeout = args.get('wait_timeout', 5)
                            locators = {k: args.get(k) for k in ['name', 'automation_id', 'control_type', 'class_name', 'parent_name', 'parent_automation_id', 'parent_control_type']}
                            gui_method = getattr(self._gui_controller, call_name, None)
                            if callable(gui_method):
                                logger.debug(f"Iteration {current_iteration}: Calling GuiController method '{call_name}' with timeout {timeout}s.")
                                if call_name in ['click_control', 'set_text', 'select_item', 'toggle_checkbox']: action_success = gui_method(args, timeout)
                                elif call_name in ['get_text', 'get_control_state']: action_result_value = gui_method(args, timeout); action_success = action_result_value is not None
                                else: action_error_message = f"Unsupported GUI action call: '{call_name}'"; self._try_emit_cli_error(action_error_message); logger.error(f"Unsupported GUI action call: '{call_name}'")
                            else: action_error_message = f"Unknown GUI action call in GuiController: '{call_name}'"; self._try_emit_cli_error(action_error_message); logger.error(f"Unknown GUI action call in GuiController: '{call_name}'")
                            if not action_success and not action_error_message: action_error_message = f"GUI Action '{call_name}' failed (no specific error reported)."
                        except Exception as gui_exec_err: logger.error(f"Iteration {current_iteration}: Error executing GUI action '{gui_action_to_run.get('call')}'", exc_info=True); action_error_message = f"GUI action execution error: {gui_exec_err}"; self._try_emit_cli_error(action_error_message); action_success = False
                    else: action_error_message = "Cannot execute GUI action: Controller became unavailable."; logger.error(action_error_message); self._try_emit_cli_error(action_error_message); action_success = False
                else: action_error_message = "Cannot execute GUI action: GUI Automation not available."; logger.error(action_error_message); self._try_emit_cli_error(action_error_message); action_success = False
                # Generate Outcome Message
                gui_call_summary = gui_action_to_run.get('call', 'Unknown GUI Action'); locators_summary = str({k: v for k, v in locators.items() if v})
                if action_success: outcome = f"GUI Action '{gui_call_summary}' on control matching {locators_summary} executed successfully."; res_str = str(action_result_value); outcome += f" Result: '{res_str[:100]}{'...' if len(res_str) > 100 else ''}'" if action_result_value is not None else ""
                else: outcome = f"GUI Action '{gui_call_summary}' on control matching {locators_summary} failed."; outcome += f" Reason: {action_error_message}" if action_error_message else ""
                self._action_outcome_message = outcome
                logger.info(f"Iteration {current_iteration}: GUI action finished. Success: {action_success}. Outcome: {outcome}")
                time.sleep(0.5 if self._is_running else 0)

            elif get_ui_request:
                action_executed = True
                logger.info(f"Iteration {current_iteration}: Executing Get UI Info action...")
                params_str = get_ui_request.get("params", ""); format_type = "text"; max_depth = 3
                try:
                     fmt_match = re.search(r"format=['\"]([^'\"]+)['\"]", params_str, re.IGNORECASE); dep_match = re.search(r"max_depth=['\"](\d+)['\"]", params_str, re.IGNORECASE)
                     if fmt_match: format_type = fmt_match.group(1).lower()
                     if dep_match: max_depth = int(dep_match.group(1))
                except Exception as param_parse_err: logger.warning(f"Could not parse get_ui_info params '{params_str}': {param_parse_err}")
                logger.info(f"Iteration {current_iteration}: Getting UI info (Format: {format_type}, Depth: {max_depth})")
                ui_text_info = get_active_window_ui_text(format_type, max_depth)
                if ui_text_info:
                    max_len = 4000; info_to_store = ui_text_info[:max_len] + (f"\n... [UI 信息已截断, 超过 {max_len} 字符]" if len(ui_text_info) > max_len else "")
                    self._action_outcome_message = f"当前活动窗口 UI 信息 ({format_type}, 深度 {max_depth}):\n{info_to_store}"
                    logger.info(f"Iteration {current_iteration}: Get UI Info succeeded. Stored outcome length: {len(self._action_outcome_message)}")
                else: self._action_outcome_message = "系统: 无法获取当前活动窗口的 UI 信息。"; logger.warning(f"Iteration {current_iteration}: Get UI Info failed.")
                time.sleep(0.2)

            # --- Update History and Check Loop Conditions ---
            if not action_executed:
                 logger.info(f"Iteration {current_iteration}: No action found or executed. Breaking loop.")
                 # Optionally add the final text response to history if needed
                 # self._update_history_with_outcome(reply_for_display)
                 break # Exit loop if no action was taken

            if self._is_running:
                logger.debug(f"Iteration {current_iteration}: Updating history before next iteration or finish.")
                self._update_history_with_outcome(reply_for_parsing) # Include action tags in history context
                logger.info(f"Iteration {current_iteration}: History updated. New size: {len(self._history)}")

            # Check loop exit conditions
            if not self._is_running: logger.info(f"Iteration {current_iteration}: Loop breaking: stop signal set."); break
            if current_iteration >= max_iterations:
                logger.warning(f"Loop breaking: Reached max iterations ({max_iterations}).")
                self._try_emit_cli_error(f"已达到最大连续操作次数 ({max_iterations})。")
                break
            # Small pause before next iteration
            logger.debug(f"Iteration {current_iteration}: Pausing briefly before next iteration.")
            time.sleep(0.2)
            logger.info(f"--- Multi-Step Iteration {current_iteration}/{max_iterations} End ---")


        logger.info(f"Multi-step iterative loop finished after {current_iteration} iteration(s).")

    def _execute_keyboard_action(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """Executes a keyboard action using uiautomation, with added checks and logging."""
        call = action.get("call", "unknown")
        logger.info(f"Attempting keyboard action: '{call}'")
        logger.debug(f"Action details: {action}")

        if not self._keyboard_available or not auto:
            msg = "Keyboard action failed: uiautomation library not available or not on Windows."
            logger.error(msg)
            return False, msg

        success = False
        outcome_message = f"Keyboard action '{call}'"

        try:
            if call == "press":
                key_name = action.get("key", "").lower(); outcome_message += f" (Key: {key_name})"
                if not key_name: raise ValueError("Missing 'key' parameter for 'press'")
                key_code = KEY_MAPPING.get(key_name)
                if key_code is None: raise ValueError(f"Unknown key name: '{key_name}'")
                logger.debug(f"Pressing key: {key_name} (Code: {key_code})")
                auto.PressKey(key_code); time.sleep(0.05); auto.ReleaseKey(key_code); time.sleep(0.05) # Add delay after release too
                success = True; outcome_message += " executed successfully."
            elif call == "type":
                text_to_type = action.get("text") # Get original text
                outcome_message += f" (Text: {repr(text_to_type)[:30]}{'...' if len(repr(text_to_type))>30 else ''})"
                if text_to_type is None: raise ValueError("Missing 'text' parameter for 'type'")
                if not isinstance(text_to_type, str):
                     logger.warning(f"Keyboard type action received non-string text '{repr(text_to_type)}' (Type: {type(text_to_type)}). Attempting conversion.")
                     try: text_to_type = str(text_to_type)
                     except Exception as str_conv_err: raise ValueError(f"Could not convert text parameter to string for 'type': {str_conv_err}") from str_conv_err
                logger.debug(f"Typing text: '{text_to_type[:50]}...'")
                auto.SendKeys(text_to_type, interval=0.01) # interval can be adjusted
                success = True; outcome_message += " executed successfully."
            elif call == "hotkey":
                keys_str = action.get("keys", "").lower(); outcome_message += f" (Keys: {keys_str})"
                if not keys_str: raise ValueError("Missing 'keys' parameter for 'hotkey'")
                keys = [k.strip() for k in keys_str.split('+') if k.strip()];
                if not keys: raise ValueError("No valid keys specified for hotkey")
                logger.debug(f"Executing hotkey: {keys_str}")
                modifiers_to_press = []; main_key_code = None
                for key_name in keys:
                    key_code = KEY_MAPPING.get(key_name)
                    if key_code is None: raise ValueError(f"Unknown key name in hotkey: '{key_name}'")
                    if key_name in ['ctrl', 'control', 'alt', 'menu', 'shift', 'win', 'windows']: modifiers_to_press.append(key_code)
                    elif main_key_code is None: main_key_code = key_code
                    else: raise ValueError(f"Hotkey can only have one non-modifier key. Found multiple: '{keys_str}'")
                if main_key_code is None: raise ValueError(f"No non-modifier key found in hotkey: '{keys_str}'")
                logger.debug(f"Pressing modifiers: {modifiers_to_press}, Main key: {main_key_code}")
                for mod_code in modifiers_to_press: auto.PressKey(mod_code)
                time.sleep(0.05); auto.PressKey(main_key_code); auto.ReleaseKey(main_key_code); time.sleep(0.05)
                for mod_code in reversed(modifiers_to_press): auto.ReleaseKey(mod_code)
                success = True; outcome_message += " executed successfully."
            else:
                raise ValueError(f"Unsupported keyboard action call: '{call}'")

            time.sleep(0.2) # General pause after keyboard action

        except ValueError as ve: logger.error(f"Invalid keyboard action {action}: {ve}"); outcome_message = f"Keyboard Error: {ve}"; success = False
        except Exception as e: logger.error(f"Failed to execute keyboard action {action}", exc_info=True); outcome_message = f"Keyboard Error: {e}"; success = False

        return success, outcome_message

    # --- Signal Emission Helpers (Added Logging) ---
    def _try_emit_api_result(self, message: str, elapsed_time: float):
        """Safely emit the api_result signal."""
        if self._is_running:
            logger.debug(f"Emitting api_result signal (Time: {elapsed_time:.2f}s, Msg: {message[:100]}...)")
            try: self.api_result.emit(message, elapsed_time)
            except RuntimeError: logger.warning("Cannot emit api_result signal, target likely deleted.")
            except Exception as e: logger.error("Error emitting api_result signal.", exc_info=True)
        else: logger.debug("Skipping api_result signal emission (worker stopped).")

    def _try_emit_ai_command_echo(self, command: str):
        """Safely emit the ai_command_echo signal."""
        if self._is_running:
             logger.debug(f"Emitting ai_command_echo signal: {command}")
             try: self.ai_command_echo_signal.emit(command)
             except RuntimeError: logger.warning("Cannot emit ai_command_echo signal, target likely deleted.")
             except Exception as e: logger.error("Error emitting ai_command_echo signal.", exc_info=True)
        else: logger.debug("Skipping ai_command_echo signal emission (worker stopped).")

    def _try_emit_cli_error(self, message: str):
        """Safely emit an error message to the CLI error signal."""
        # Reuse _emit_cli_error for consistency
        if self._is_running: self._emit_cli_error(message)
        else: logger.debug("Skipping CLI error signal emission (worker stopped).")

    def _try_emit_cli_output_bytes(self, message_bytes: bytes, is_stderr: bool = False):
        """Safely emit bytes to the correct CLI signal."""
        # Reuse _emit_cli_output_bytes for consistency
        if self._is_running: self._emit_cli_output_bytes(message_bytes, is_stderr)
        else: logger.debug("Skipping CLI output signal emission (worker stopped).")

    def _emit_cli_error(self, message: str):
        """Helper to format and emit error messages."""
        try:
            if not isinstance(message, str): message = str(message)
            error_prefix = "[Error] "
            msg_lower = message.lower()
            if "keyboard" in msg_lower or "key name" in msg_lower or "hotkey" in msg_lower: error_prefix = "[Keyboard Error] "
            elif "gui" in msg_lower or "uiautomation" in msg_lower or "control" in msg_lower: error_prefix = "[GUI Ctrl Error] "
            elif "command" in msg_lower or "shell" in msg_lower or "exit code" in msg_lower: error_prefix = "[Shell Error] "
            elif "api" in msg_lower or "request" in msg_lower or "model" in msg_lower: error_prefix = "[API Error] "
            full_message = f"{error_prefix}{message}"
            logger.debug(f"Emitting cli_error signal: {full_message}")
            self.cli_error_signal.emit(full_message.encode('utf-8'))
        except RuntimeError: logger.warning("Cannot emit cli_error signal, target likely deleted.")
        except Exception as e: logger.error("Unexpected error emitting CLI error signal.", exc_info=True)

    def _emit_cli_output_bytes(self, message_bytes: bytes, is_stderr: bool = False):
        """Helper to emit raw bytes to the correct signal."""
        target_signal = self.cli_error_signal if is_stderr else self.cli_output_signal
        signal_name = "cli_error_signal" if is_stderr else "cli_output_signal"
        try:
             logger.debug(f"Emitting {signal_name} with {len(message_bytes)} bytes.")
             target_signal.emit(message_bytes)
        except RuntimeError: logger.warning(f"Cannot emit {signal_name}, target likely deleted.")
        except Exception as e: logger.error(f"Unexpected error emitting {signal_name}.", exc_info=True)


    def _send_message_to_model(self, is_multi_step_flow: bool):
        """Sends history and prompt to the configured AI model API, potentially including UI info. Logs the process."""
        logger.info("Preparing to send message to model...")
        if not self._is_running: logger.warning("Send message cancelled: Stop signal received."); return "错误: API 调用已取消。"

        # Get current config values safely
        api_key = getattr(config, 'API_KEY', None)
        api_url = getattr(config, 'API_URL', None)
        include_timestamp = getattr(config, 'INCLUDE_TIMESTAMP_IN_PROMPT', False)
        max_iterations = getattr(config, 'MULTI_STEP_MAX_ITERATIONS', 5)
        auto_include_ui = getattr(config, 'AUTO_INCLUDE_UI_INFO', False)

        if not api_key or not api_url or not self._model_id:
            err_msg = f"API configuration missing or model not selected (URL:{bool(api_url)}, Key:{bool(api_key)}, Model:{self._model_id})."
            logger.error(err_msg)
            return f"错误: {err_msg}"

        headers = { "Content-Type": "application/json", "Authorization": f"Bearer {api_key}" }
        url = f"{api_url.rstrip('/')}/v1/chat/completions" # Assume OpenAI compatible API endpoint
        logger.debug(f"Target API URL: {url}")

        os_name = platform.system(); shell_type = "PowerShell" if os_name == "Windows" else "Default Shell"
        shell_info = f"You are operating within {shell_type} on {os_name}."
        timestamp_info = f"Current date and time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. " if include_timestamp else ""

        # --- Construct System Prompt ---
        base_instructions = (
            f"You are an AI assistant interacting with a user's computer ({os_name}). "
            f"{shell_info} Your goal is to fulfill user requests by executing actions. "
            f"Prioritize actions in this order: 1. `<cmd>` (Shell Command), 2. `<keyboard>` (Keyboard Simulation - Windows ONLY), 3. `<gui_action>` (GUI Control - Windows ONLY).\n"
            f"Current Working Directory (CWD): '{self._cwd}'\n"
            f"{timestamp_info}"
            f"**ACTION RULES:**\n"
            f"- **`<cmd>your_command_here</cmd>`**: Executes a shell command. The command runs in the CWD. Output (stdout/stderr) will be returned to you.\n"
            f"    **Important Guidelines for `<cmd>`:**\n"
            f"    - **Quoting Paths:** If file or directory paths contain spaces, ensure they are enclosed in double quotes. Example: `<cmd>ls \"my documents/reports\"</cmd>`.\n"
            f"    - **Preference for Non-Interactive Commands:** Generate commands that are non-interactive and do not require further user input unless explicitly requested by the user.\n"
            f"    - **Common Command Examples:**\n"
            f"        - Listing files: To list files, use `<cmd>ls</cmd>` (or `<cmd>dir</cmd>` on Windows). To list with details: `<cmd>ls -l</cmd>`.\n"
            f"        - Directory creation: To create a directory: `<cmd>mkdir new_folder_name</cmd>`.\n"
            f"        - Reading file contents (first few lines for brevity): To see the first few lines of a text file (e.g., `notes.txt`): `<cmd>head -n 5 notes.txt</cmd>` (Linux/macOS) or `<cmd>type notes.txt | select -first 5</cmd>` (Windows PowerShell).\n"
            f"    - **`cd` Command Guidance:** To change the current working directory, use `<cmd>cd path/to/directory</cmd>`. You will be informed of the success and the new CWD, or failure. Do not assume CWD changes without confirmation.\n"
            f"    - **Simplicity and Directness:** Commands should be direct and achieve a specific part of the user's request. If a task is complex, break it down into multiple, simpler commands in subsequent steps if multi-step mode is active.\n"
            f"    - Example: `<cmd>ls -l</cmd>`.\n"
            f"- **`<keyboard call=\"press|type|hotkey\" key=\"key_name\" text=\"text_to_type\" keys=\"ctrl+alt+del\" />`**: Simulates keyboard actions (Windows ONLY). Use 'press' for single key presses (e.g., 'enter', 'esc', 'a', 'b', '1', 'F1'). Use 'type' to send a string of characters. Use 'hotkey' for key combinations (e.g., 'ctrl+c', 'win+r'). Ensure `uiautomation` library is available. Key names are case-insensitive (e.g., 'enter', 'CTRL', 'Shift', 'ALT', 'WIN', 'F1'-'F12', 'a', 'b', '1', '2', 'space', 'backspace', 'delete', 'home', 'end', 'pageup', 'pagedown', 'up', 'left', etc.). Text for 'type' will be typed as is. For 'hotkey', combine keys with '+'.\n"
            f"- **`<gui_action call=\"method_name\" args='{{\"key1\": \"value1\", ...}}' />`**: Performs a GUI action using `uiautomation` (Windows ONLY). `call` is the method name (e.g., `click_control`, `set_text`, `get_text`, `get_control_state`). `args` is a JSON string of arguments for the method, often including locators like `name`, `automation_id`, `control_type`. Example: `<gui_action call=\"click_control\" args='{{\"name\": \"Save Button\"}}' />`. Ensure `uiautomation` library is available and the target application is active.\n"
            f"- **`<get_ui_info format=\"text|json\" max_depth=\"3\" />`**: (Windows ONLY) Retrieves UI element information from the currently active window. `format` can be 'text' (human-readable) or 'json'. `max_depth` (optional, default 3) controls how deep the UI tree is inspected. This action helps you understand the UI before attempting a `<gui_action>`. The result will be provided in a system message.\n"
            f"- **`<continue />`**: (Multi-Step Mode ONLY) If a command or action is part of a sequence and you need to continue to the next step based on the outcome (which will be in history), use this tag. It tells the system to wait for your next instruction. Do not use this if the task is complete or if you need user input.\n"
            f"- **Output/Results:** Command output, keyboard/GUI action success/failure, or UI info will be returned in a system message. Use this information to decide the next step or to formulate your final response.\n"
            f"- **Error Handling:** If a command or action fails, the error message will be provided. Analyze it and try to correct your action or inform the user.\n"
            f"- **Clarity:** Be explicit. Don't assume context beyond what's in the history or current CWD.\n"
            f"- **No nested tags.** Only one action tag per response.\n"
            f"- **Text Response:** If no action is needed, or if the task is complete, provide a direct textual response in Chinese without any action tags.\n"
            f"**UI 信息 (Windows ONLY, 可选):**\n"
            f"If the user provides UI information via a screenshot or describes a UI, it might be included below. Use this to inform `<gui_action>` calls if appropriate.\n"
            f"**General Instructions:**\n"
            f"- Think step-by-step. "
            f"- If a request is complex, break it down. In multi-step mode, you can issue a sequence of actions. "
            f"- Prefer simpler, more direct commands/actions. "
            f"- If you need more information (e.g., a filename), ask the user. "
            f"- Strive to be helpful and accurate. "
            f"- Respond in Chinese when providing a textual answer to the user.\n"
        )
        flow_instructions = ""
        if is_multi_step_flow:
            flow_instructions = f"""

**Iterative Operation Mode:**
- You are in a multi-step process. Your previous action's outcome (or UI info) is in the history (System message).
- Max consecutive actions: {max_iterations}.
- **Your Task:** Analyze history/outcome/UI info. Determine the **single next action** (`<cmd>`, `<keyboard>`, `<gui_action>`, or `<get_ui_info>`).
- If task complete, provide final **textual confirmation/summary** (in Chinese) with NO action tags.
- If error occurred, try to correct or inform user.
- **Remember:** Only provide the *next single step* or the *final textual response*.
**请根据上一步操作的结果/UI信息决定下一步操作 (`<cmd>`, `<keyboard>`, `<gui_action>`, `<get_ui_info>`) 或提供最终的中文文本回复。**
"""
        else:
             flow_instructions = """

**Single Operation Mode:**
- Analyze user request and potentially provided UI info. Provide the single best action (`<cmd>`, `<keyboard>`, `<gui_action>`, `<get_ui_info>`) OR a textual response.
- No follow-up API call after action execution.
"""
        system_message = base_instructions + flow_instructions
        messages = [{"role": "system", "content": system_message}]
        logger.debug(f"System prompt constructed (Length: {len(system_message)}). Multi-step flow: {is_multi_step_flow}")

        # --- Process history for API payload ---
        logger.debug(f"Processing history (Size: {len(self._history)}) for API payload...")
        history_msg_count = 0
        for role, message in self._history:
            cleaned_message = message if isinstance(message, str) else str(message)
            cleaned_message = re.sub(r"<think>.*?</think>", "", cleaned_message, flags=re.DOTALL | re.IGNORECASE).strip()
            if not cleaned_message: logger.debug("Skipping empty message in history."); continue
            api_role = "user" if role.lower() == "user" else "assistant" if role.lower() == "assistant" else "system"
            messages.append({"role": api_role, "content": cleaned_message})
            history_msg_count += 1
        logger.debug(f"Added {history_msg_count} messages from history.")

        # --- Add UI Info if configured and available ---
        if auto_include_ui and self._gui_available:
            logger.info("Auto-include UI info is enabled. Getting current UI structure...")
            try:
                # Use text format and limited depth for automatic inclusion
                ui_info_text = get_active_window_ui_text(format_type="text", max_depth=2)
                if ui_info_text:
                     max_len = 2500; ui_info_to_add = ui_info_text[:max_len] + (f"\n... [UI 信息已截断, 超过 {max_len} 字符]" if len(ui_info_text) > max_len else "")
                     ui_message = {"role": "system", "content": f"当前活动窗口 UI 结构 (参考):\n{ui_info_to_add}"}
                     messages.append(ui_message) # Append UI info near the end
                     logger.info(f"Added automatically retrieved UI info (length {len(ui_info_to_add)}) to messages.")
                else: logger.warning("get_active_window_ui_text returned no information for automatic inclusion.")
            except Exception as ui_get_err:
                 logger.error("Error getting UI info for automatic inclusion.", exc_info=True)
                 # Optionally add an error message to the context
                 messages.append({"role": "system", "content": f"系统错误: 自动获取 UI 信息失败: {ui_get_err}"})
        elif auto_include_ui and not self._gui_available:
             logger.warning("Auto-include UI info is enabled, but GUI is not available.")

        # --- Prepare API Call ---
        session = requests.Session()
        if URLLIB3_RETRY_AVAILABLE:
            try:
                retry_strategy = Retry( total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["POST"])
                adapter = HTTPAdapter(max_retries=retry_strategy)
                session.mount("https://", adapter); session.mount("http://", adapter)
                logger.debug("Requests session configured with retry strategy.")
            except Exception as e: logger.warning(f"Could not configure requests retries: {e}")
        else: logger.debug("Requests retries not available or disabled.")

        # --- Make API call ---
        reply_text = "错误: API 调用失败或未产生响应。" # Default error
        try:
            payload = { "model": self._model_id, "messages": messages, "max_tokens": 1500, "temperature": 0.5 }
            payload_size = 0
            try: payload_size = len(json.dumps(payload)) # Estimate size
            except: pass
            logger.info(f"Sending API request to {url} (Model: {self._model_id}, Msgs: {len(messages)}, Approx Size: {payload_size} bytes)")
            # logger.debug(f"API Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}") # Log full payload only if needed for deep debug

            timeout_seconds = 90 # Increased timeout
            response = session.post(url, headers=headers, json=payload, timeout=timeout_seconds)
            logger.info(f"API Response Status Code: {response.status_code}")

            response.encoding = 'utf-8'
            if response.ok:
                try:
                    data = response.json()
                    logger.debug(f"API Response JSON (Top Level Keys): {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    # (Response parsing logic remains the same)
                    if 'choices' in data and data['choices']:
                         choice = data['choices'][0]; finish_reason = choice.get('finish_reason', 'N/A')
                         content = ""; msg_data = choice.get('message')
                         if msg_data and isinstance(msg_data, dict) and 'content' in msg_data: content = msg_data['content']
                         elif 'text' in choice: content = choice['text'] # Fallback
                         reply_text = content if content is not None else ""
                         logger.info(f"API call successful. Finish reason: {finish_reason}")
                         if finish_reason == 'length': reply_text += "\n[警告: AI 输出可能因达到最大长度而被截断。]"; logger.warning("AI output may be truncated due to max length.")
                    elif 'error' in data: error_obj = data.get('error', data); reply_text = f"来自 API 的错误: {error_obj.get('message', json.dumps(error_obj))}"; logger.error(f"API returned error: {reply_text}")
                    else: reply_text = "错误: 意外的 API 响应结构。"; logger.error(f"Unexpected API response structure: {data}")
                except json.JSONDecodeError as json_err: reply_text = f"错误: 无法解码 API 响应 JSON (状态码 {response.status_code})"; logger.error(f"API JSON Decode Error: {json_err}", exc_info=True)
                except Exception as parse_err: reply_text = f"错误: 解析成功的 API 响应时出错: {parse_err}"; logger.error("Error parsing successful API response.", exc_info=True)
            else:
                err_details = ""
                try: err_data = response.json(); error_obj = err_data.get('error', err_data); err_details = str(error_obj.get('message', error_obj));
                except: err_details = response.text[:200]
                reply_text = f"错误: API 请求失败 (状态码 {response.status_code}) 详情: {err_details}"
                logger.error(f"API request failed: {reply_text}")

            if not isinstance(reply_text, str): reply_text = str(reply_text)
            return reply_text.strip()

        except requests.exceptions.Timeout:
            logger.error(f"API request timed out after {timeout_seconds} seconds.")
            return f"错误: AI 服务请求超时 ({timeout_seconds} 秒)。请检查您的网络连接或稍后再试。"
        except requests.exceptions.ConnectionError as e:
            logger.error(f"API request Connection Error: {e}", exc_info=False)
            return "错误: 网络连接错误。请检查您的互联网连接并重试。"
        except requests.exceptions.TooManyRedirects as e:
            logger.error(f"API request Too Many Redirects: {e}", exc_info=False)
            return "错误: API 请求因重定向过多而失败。请联系技术支持。"
        except requests.exceptions.SSLError as e: # Specific SSL error
            logger.error(f"API request SSL Error: {e}", exc_info=False)
            return f"错误: SSL 验证失败。无法建立到 AI 服务的安全连接: {e}"
        except requests.exceptions.RequestException as e: # General requests error
            status_code_str = "N/A"
            if e.response is not None:
                status_code = e.response.status_code
                status_code_str = str(status_code)
                logger.error(f"API request failed with HTTP status {status_code}: {e}", exc_info=False)
                if status_code == 500:
                    return "错误: AI 服务遇到内部错误 (HTTP 500)。请稍后再试。"
                elif status_code == 502:
                    return "错误: AI 服务暂时不可用 (Bad Gateway - HTTP 502)。请稍后再试。"
                elif status_code == 503:
                    return "错误: AI 服务暂时过载或正在维护 (Service Unavailable - HTTP 503)。请稍后再试。"
                elif status_code == 504:
                    return "错误: AI 服务网关超时 (Gateway Timeout - HTTP 504)。请稍后再试。"
                elif status_code == 400:
                    return f"错误: API 请求无效 (Bad Request - HTTP 400)。详情: {e.response.text[:100]}"
                elif status_code == 401:
                    return "错误: API 密钥无效或未授权 (Unauthorized - HTTP 401)。请检查您的 API 密钥配置。"
                elif status_code == 403:
                    return "错误: API 访问被拒绝 (Forbidden - HTTP 403)。请检查您的 API 密钥权限。"
                elif status_code == 429:
                    return "错误: API 请求频率过高 (Too Many Requests - HTTP 429)。请稍后重试。"
                else:
                    return f"错误: API 请求失败 (HTTP {status_code_str})。详情: {e.response.text[:100]}"
            else:
                logger.error(f"API request failed (No response/other RequestException): {e}", exc_info=False)
                return f"错误: API 请求失败 (网络/连接问题)。请检查您的网络连接或 API URL 配置。"
        except Exception as e:
            logger.critical("Unhandled Exception in _send_message_to_model", exc_info=True)
            return f"错误: API 调用期间发生未处理的意外错误 ({type(e).__name__})。"
        finally:
            session.close() # Ensure session is closed
            logger.debug("Requests session closed.")

# --- ManualCommandThread ---
class ManualCommandThread(QThread):
    # (Signals remain the same)
    cli_output_signal = Signal(bytes)
    cli_error_signal = Signal(bytes)
    directory_changed_signal = Signal(str, bool)
    command_finished = Signal()

    def __init__(self, command, cwd):
        super().__init__()
        self._command = command
        self._cwd = cwd
        self._is_running = True
        logger.info("Initializing ManualCommandThread...")
        logger.debug(f"  Command: '{self._command}'")
        logger.debug(f"  CWD: {self._cwd}")

    def stop(self):
        logger.info("ManualCommandThread stop() called. Setting internal flag.")
        self._is_running = False

    def run(self):
        logger.info("ManualCommandThread run() started.")
        exit_code = None
        try:
            if not self._is_running: logger.warning("Manual command run aborted early (stop signal received)."); return

            command_to_run = self._command.strip()
            if not command_to_run: logger.info("Manual command is empty, nothing to execute."); return

            logger.info(f"Executing manual command: '{command_to_run}' in CWD: {self._cwd}")
            # execute_command_streamed should handle its own internal logging
            new_cwd, exit_code = execute_command_streamed(
                command=command_to_run,
                cwd=self._cwd,
                stop_flag_func=lambda: not self._is_running, # Pass the check function
                output_signal=self.cli_output_signal,
                error_signal=self.cli_error_signal,
                directory_changed_signal=self.directory_changed_signal,
                is_manual_command=True
            )

            # Update CWD only if the thread wasn't stopped during execution
            if self._is_running:
                self._cwd = new_cwd
            else:
                 logger.info("Manual command execution was stopped. Not updating CWD.")

            logger.info(f"Manual command finished execution. ExitCode: {exit_code}, Final CWD (internal): {self._cwd}")

        except Exception as run_err:
            logger.error("Unhandled error in ManualCommandThread run method.", exc_info=True)
            # Only emit error if the thread wasn't stopped externally
            if self._is_running:
                self._emit_cli_error(f"线程错误: {run_err}") # Use simplified error message for UI
        finally:
            logger.info(f"ManualCommandThread run() sequence finished (is_running={self._is_running}).")
            try:
                 logger.debug("Emitting command_finished signal.")
                 self.command_finished.emit()
            except RuntimeError as e:
                 logger.warning(f"Could not emit command_finished signal (RuntimeError - likely target deleted): {e}")
            except Exception as e:
                 logger.error("Error emitting command_finished signal.", exc_info=True)
            logger.info("ManualCommandThread run() finished.")

    def _emit_cli_error(self, message: str):
        """Safely emit an error message to the CLI error signal."""
        # Ensure thread is still considered running before emitting error
        if self._is_running:
            try:
                if not isinstance(message, str): message = str(message)
                full_message = f"错误: {message}"
                logger.debug(f"Emitting cli_error signal (manual): {full_message}")
                self.cli_error_signal.emit(full_message.encode('utf-8'))
            except RuntimeError: logger.warning("Cannot emit cli_error signal (manual), target likely deleted.")
            except Exception as e: logger.error("Error emitting CLI error signal (manual).", exc_info=True)
        else: logger.debug("Skipping CLI error signal emission (manual worker stopped).")