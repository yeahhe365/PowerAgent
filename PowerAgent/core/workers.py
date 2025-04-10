# ========================================
# 文件名: PowerAgent/core/workers.py
# (MODIFIED - Refactored to use helper modules, including keyboard controller)
# ---------------------------------------
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
from PySide6.QtCore import QThread, Signal, QObject
from requests.adapters import HTTPAdapter

# Import global config state
from core import config

# Import modularized components
from .worker_utils import decode_output # Replaces local _decode_output
from .command_executor import execute_command_streamed # Replaces local command execution logic
from .keyboard_controller import KeyboardController, PYNPUT_AVAILABLE # Imports keyboard logic

try:
    from urllib3.util.retry import Retry
    URLLIB3_RETRY_AVAILABLE = True
except ImportError:
    print("Warning: Failed to import Retry from urllib3.util.retry. Retries disabled.")
    URLLIB3_RETRY_AVAILABLE = False


# --- Worker Threads ---

class ApiWorkerThread(QThread):
    """Handles AI interaction, response parsing, and action execution (commands/keyboard)."""
    # Signals remain the same
    api_result = Signal(str, float) # (display_reply, elapsed_time)
    cli_output_signal = Signal(bytes) # Raw stdout bytes from commands
    cli_error_signal = Signal(bytes)  # Raw stderr bytes or error messages
    directory_changed_signal = Signal(str, bool) # (new_directory, is_manual_command=False)
    task_finished = Signal()

    def __init__(self, api_key, api_url, model_id, history, prompt, cwd):
        super().__init__()
        self._api_key = api_key
        self._api_url = api_url.rstrip('/') if api_url else ""
        self._model_id = model_id # The selected model for this specific request
        self._history = list(history) # Copy of history at the time of request
        # Prompt is not directly used in _send_message_to_model anymore, but kept for context if needed
        # self._prompt = prompt
        self._cwd = cwd # CWD for this task instance
        self._is_running = True
        self._keyboard_controller = None # Initialize later if needed and available
        # print(f"ApiWorkerThread initialized with CWD: {self._cwd}") # Debug print

    def stop(self):
        """Signals the thread and its operations (command execution, keyboard) to stop."""
        print("[ApiWorker] Stop signal received. Setting internal flag.")
        self._is_running = False
        # The command executor and keyboard controller checks this flag.
        # No direct process termination needed here, as command_executor handles it.

    def run(self):
        """Main execution logic: API call -> Parse Reply -> Execute Actions."""
        try:
            # --- 1. API Call ---
            if not self._is_running:
                print("[ApiWorker] Run() aborted early: stop signal set before API call.")
                return
            start_time = time.time()
            raw_model_reply = "Error: API Call did not complete."
            try:
                # _send_message_to_model now reads global config for timestamp inclusion
                raw_model_reply = self._send_message_to_model()
            except Exception as api_err:
                print(f"[ApiWorker] Unhandled exception during API call: {api_err}")
                traceback.print_exc()
                raw_model_reply = f"Error: Unexpected error during API call: {api_err}"
            finally:
                end_time = time.time(); elapsed_time = end_time - start_time
                print(f"[ApiWorker] API call took: {elapsed_time:.2f} seconds using model: {self._model_id}")

            if not self._is_running:
                print("[ApiWorker] Run() aborted early: stop signal set after API call.")
                return

            # --- 2. Reply Processing & Parsing ---
            reply_for_display = raw_model_reply or ""
            reply_for_parsing = reply_for_display
            command_to_run = None
            keyboard_actions = [] # Store parsed keyboard actions {"call": "name", "args": {...}}

            # Remove <think> blocks for both display and parsing
            try:
                # Use a temporary variable to avoid modifying the original if cleaning fails
                temp_cleaned_reply = re.sub(r"<think>.*?</think>", "", reply_for_parsing, flags=re.DOTALL | re.IGNORECASE).strip()
                if raw_model_reply != temp_cleaned_reply:
                    print("[ApiWorker] Removed <think> block from AI reply.")
                reply_for_display = temp_cleaned_reply
                reply_for_parsing = temp_cleaned_reply # Use cleaned reply for parsing actions
            except Exception as clean_err:
                print(f"[ApiWorker] Warning: Error cleaning <think> blocks: {clean_err}. Using original reply.")
                # Use original reply if cleaning fails
                reply_for_display = raw_model_reply or ""
                reply_for_parsing = raw_model_reply or ""

            # Emit the user-facing part of the reply (without action tags) FIRST
            if self._is_running:
                 try:
                     # Further clean for display: remove cmd tags and replace function tags
                     display_text = re.sub(r"<cmd>.*?</cmd>", "", reply_for_display, flags=re.DOTALL | re.IGNORECASE).strip()
                     display_text = re.sub(r"<function\s+call=[\"']keyboard_.*?[\"'].*?</function>", "[Keyboard Action]", display_text, flags=re.DOTALL | re.IGNORECASE).strip()
                     self.api_result.emit(display_text, elapsed_time)
                 except RuntimeError as e:
                     # This happens if the main window was closed while the worker was running
                     print(f"[ApiWorker] Warning: Could not emit api_result signal (likely main window closed): {e}")
                 except Exception as e:
                     print(f"[ApiWorker] Error emitting api_result signal: {e}")

            if not self._is_running:
                print("[ApiWorker] Run() aborted early: stop signal set after emitting result.")
                return

            # Parse the cleaned reply for <cmd> AND <function call="keyboard_..."> tags
            if reply_for_parsing and isinstance(reply_for_parsing, str):
                print(f"[ApiWorker] Parsing reply for actions: '{reply_for_parsing[:100]}{'...' if len(reply_for_parsing)>100 else ''}'")
                try:
                    # Parse <cmd> tag (expects only one)
                    command_match = re.search(r"<cmd>\s*(.*?)\s*</cmd>", reply_for_parsing, re.DOTALL | re.IGNORECASE)
                    if command_match:
                        command_to_run = command_match.group(1).strip()
                        if command_to_run:
                            print(f"[ApiWorker] AI Suggested Command Extracted: '{command_to_run}'")
                        else:
                            print("[ApiWorker] AI suggested <cmd> tag was empty.")
                            command_to_run = None # Ensure it's None if tag was empty

                    # Parse <function call="keyboard_..."> tags (multiple possible)
                    func_pattern = re.compile(
                        # Use VERBOSE flag for comments and readability
                        r"""<function\s+                   # Opening tag <function with space
                            call=[\"'](keyboard_\w+)[\"'] # Capture 'keyboard_xxx' in group 1 (function name)
                            \s+                         # Required space after call attribute
                            args=[\"'](.*?)[\"']        # Capture args JSON string in group 2 (non-greedy)
                            \s*                         # Optional whitespace before closing >
                            /?                          # Optional self-closing slash (though unlikely needed here)
                            >                           # Closing >
                            (?:</function>)?            # Optional non-capturing closing tag </function> (for robustness)
                         """, re.VERBOSE | re.DOTALL | re.IGNORECASE
                    )
                    for match in func_pattern.finditer(reply_for_parsing):
                        func_name = match.group(1)
                        # Basic HTML entity decode for quotes/ampersands within JSON string
                        # It's crucial this happens *before* JSON parsing
                        args_json_str = match.group(2).replace('&apos;', "'").replace('&quot;', '"').replace('&amp;', '&')
                        try:
                            args_dict = json.loads(args_json_str)
                            keyboard_actions.append({"call": func_name, "args": args_dict})
                            print(f"[ApiWorker] AI Suggested Keyboard Action Parsed: {func_name}, Args: {args_dict}")
                        except json.JSONDecodeError as json_err:
                            err_msg = f"Error parsing JSON args for keyboard function '{func_name}': {json_err}. Args string after decode: '{args_json_str}'"
                            print(err_msg)
                            if self._is_running: self._emit_cli_error(err_msg)
                        except Exception as parse_err:
                            err_msg = f"Error processing keyboard function tag '{func_name}': {parse_err}."
                            print(err_msg)
                            if self._is_running: self._emit_cli_error(err_msg)

                except Exception as e:
                    err_msg = f"Error parsing command/function tags from reply: {e}"
                    print(err_msg)
                    traceback.print_exc()
                    if self._is_running: self._emit_cli_error(err_msg)

            elif not isinstance(reply_for_parsing, str):
                 print(f"[ApiWorker] Warning: Cleaned AI reply for parsing was not a string: {type(reply_for_parsing)}")
            elif self._is_running:
                 print("[ApiWorker] Cleaned AI reply for parsing was empty or None. No actions to parse.")


            # --- 3. Action Execution ---
            # Order: Execute shell command first, then keyboard actions

            # Execute Shell Command (if found and thread is still running)
            if command_to_run and self._is_running:
                print(f"[ApiWorker] Executing AI suggested command: '{command_to_run}'...")
                # --- Echo Command with CWD before execution ---
                status_message = f"Model {self._cwd}: {command_to_run}"
                self._emit_cli_output_bytes(status_message.encode('utf-8'), is_stderr=False)
                print(f"[ApiWorker] Echoed command: {status_message}")

                try:
                    # Call the dedicated command executor function
                    # Pass the lambda to check self._is_running
                    new_cwd, exit_code = execute_command_streamed(
                        command=command_to_run,
                        cwd=self._cwd,
                        stop_flag_func=lambda: not self._is_running,
                        output_signal=self.cli_output_signal,
                        error_signal=self.cli_error_signal,
                        directory_changed_signal=self.directory_changed_signal,
                        is_manual_command=False # AI command source
                    )
                    # Update worker's CWD state if changed by the executor (e.g., 'cd' command)
                    self._cwd = new_cwd
                    print(f"[ApiWorker] Command execution finished. ExitCode: {exit_code}, New CWD for worker instance: {self._cwd}")
                    # Add a small delay after a command executes, before potential keyboard actions
                    if self._is_running:
                        time.sleep(0.5) # 500ms delay, adjust as needed

                except Exception as exec_err:
                    err_msg = f"Error calling command executor: {exec_err}"
                    print(f"[ApiWorker] {err_msg}")
                    traceback.print_exc()
                    if self._is_running: self._emit_cli_error(err_msg)
            elif not command_to_run and self._is_running:
                 print("[ApiWorker] No <cmd> command found in reply to execute.")

            # Execute Keyboard Actions (if found and thread is still running)
            if keyboard_actions and self._is_running:
                print(f"[ApiWorker] Executing {len(keyboard_actions)} AI suggested keyboard action(s)...")
                if not PYNPUT_AVAILABLE:
                    err_msg = "Cannot execute keyboard actions: pynput library is not available or failed to import."
                    print(err_msg)
                    self._emit_cli_error(err_msg)
                else:
                    # Initialize KeyboardController on demand
                    if self._keyboard_controller is None:
                        print("[ApiWorker] Initializing KeyboardController...")
                        self._keyboard_controller = KeyboardController()
                        # Connect its error signal to our error emitter
                        self._keyboard_controller.error_signal.connect(self._emit_cli_error)

                    if not self._keyboard_controller.is_available():
                         # Error should have been emitted by KeyboardController init via the signal
                         err_msg = "Keyboard controller failed to initialize or is unavailable. Cannot execute actions."
                         print(err_msg)
                         # Optionally emit again, though signal should have covered it.
                         # self._emit_cli_error(err_msg)
                    else:
                        # Execute actions sequentially
                        for action in keyboard_actions:
                            if not self._is_running:
                                print("[ApiWorker] Stop signal received during keyboard action loop.")
                                break # Check flag before each action

                            call = action.get("call")
                            args = action.get("args", {})
                            print(f"[ApiWorker] Processing keyboard action: {call} with args: {args}")

                            try:
                                # Check if call is a known keyboard function
                                if call == "keyboard_type":
                                    text = args.get("text")
                                    if text is not None and isinstance(text, str): # Check type
                                         self._keyboard_controller.type_text(text)
                                    else: self._emit_cli_error(f"Invalid or missing 'text' (string) argument for keyboard_type: {args.get('text')}")
                                elif call == "keyboard_press":
                                    key = args.get("key")
                                    if key and isinstance(key, str): # Check type
                                        self._keyboard_controller.press_key(key)
                                    else: self._emit_cli_error(f"Invalid or missing 'key' (string) argument for keyboard_press: {args.get('key')}")
                                elif call == "keyboard_hotkey":
                                    keys = args.get("keys")
                                    if keys and isinstance(keys, list) and all(isinstance(k, str) for k in keys): # Check type
                                        self._keyboard_controller.press_hotkey(keys)
                                    else: self._emit_cli_error(f"Invalid or missing 'keys' (list of strings) argument for keyboard_hotkey: {args.get('keys')}")
                                else:
                                    err_msg = f"Unknown keyboard function requested by AI: {call}"
                                    print(f"[ApiWorker] Skipping: {err_msg}")
                                    self._emit_cli_error(err_msg)

                                # Add a small delay between keyboard actions if executing multiple
                                if self._is_running and len(keyboard_actions) > 1:
                                    time.sleep(0.3) # 300ms delay

                            except Exception as key_exec_err:
                                # Catch errors during the *call* to the controller methods
                                # (Internal errors in controller methods emit their own signals)
                                err_msg = f"Error executing keyboard action '{call}': {key_exec_err}"
                                print(f"[ApiWorker] {err_msg}")
                                traceback.print_exc()
                                if self._is_running: self._emit_cli_error(err_msg)
                                # Continue with next action? Yes.

            elif not keyboard_actions and self._is_running:
                 print("[ApiWorker] No keyboard actions found in reply to execute.")

        except Exception as main_run_err:
            # Catch errors in the main run logic (API call, parsing, action triggering)
            err_msg = f"Unexpected error in ApiWorkerThread run loop: {main_run_err}"
            print(f"[ApiWorker] {err_msg}")
            traceback.print_exc()
            # Emit error only if thread wasn't stopped externally
            if self._is_running: self._emit_cli_error(err_msg)

        finally:
            # Ensure task_finished is emitted *once* at the very end,
            # regardless of errors or whether actions were performed,
            # unless the thread was explicitly stopped early.
            if self._is_running:
                print("[ApiWorker] Run() sequence completed, emitting task_finished.")
                try:
                    self.task_finished.emit()
                except RuntimeError as e:
                    # Can happen if main window closed just before emit
                    print(f"[ApiWorker] Warning: Could not emit task_finished signal (likely main window closed): {e}")
                except Exception as e:
                    print(f"[ApiWorker] Error emitting task_finished signal: {e}")

            else:
                print("[ApiWorker] Run() sequence ended because stop signal was set.")

            # Clean up keyboard controller if it was created
            if self._keyboard_controller:
                print("[ApiWorker] Scheduling KeyboardController for deletion.")
                self._keyboard_controller.deleteLater() # Schedule for deletion on event loop

    # --- Helper methods for safe signal emission ---
    # (These remain useful for emitting errors generated within this thread's logic)
    def _emit_cli_error(self, message: str):
        """Helper to safely emit string errors to the CLI error signal."""
        if self._is_running: # Check running flag before emitting
            try:
                # Ensure message is string before encoding
                if not isinstance(message, str): message = str(message)
                self.cli_error_signal.emit(f"Error: {message}".encode('utf-8'))
            except RuntimeError as e:
                print(f"[ApiWorker] Warning: Could not emit CLI error signal (likely main window closed): {e}")
            except Exception as e:
                 print(f"[ApiWorker] Unexpected error emitting CLI error signal: {e}")

    def _emit_cli_output_bytes(self, message_bytes: bytes, is_stderr: bool = False):
        """Helper to safely emit raw bytes output via the correct signal."""
        if self._is_running: # Check running flag before emitting
            target_signal = self.cli_error_signal if is_stderr else self.cli_output_signal
            try:
                target_signal.emit(message_bytes)
            except RuntimeError as e:
                 print(f"[ApiWorker] Warning: Could not emit CLI signal ({'stderr' if is_stderr else 'stdout'}) (likely main window closed): {e}")
            except Exception as e:
                 print(f"[ApiWorker] Unexpected error emitting CLI signal ({'stderr' if is_stderr else 'stdout'}): {e}")

    # --- API Call Logic (Kept within ApiWorkerThread for now) ---
    def _send_message_to_model(self):
        """Sends history and prompt to the configured AI model API."""
        if not self._api_key or not self._api_url or not self._model_id:
             return f"Error: API configuration missing or no model selected (Using: {self._model_id})."
        headers = { "Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}" }
        # Construct API endpoint URL
        url = f"{self._api_url.rstrip('/')}/v1/chat/completions" # Standard OpenAI-compatible path

        # --- System Prompt Construction ---
        os_name = platform.system()
        shell_type = "PowerShell on Windows" if os_name == "Windows" else ("Bash/Zsh on macOS" if os_name == "Darwin" else "Bash/Shell on Linux")
        timestamp_info = ""
        if config.INCLUDE_TIMESTAMP_IN_PROMPT: # Check global config
            try:
                now = datetime.datetime.now()
                timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
                timestamp_info = f"The current date and time is: {timestamp_str}. "
            except Exception as dt_err:
                print(f"[ApiWorker] Warning: Could not format timestamp: {dt_err}")

        # Updated System Prompt explaining commands AND keyboard functions
        system_message = (f"You are an AI assistant designed to help users interact with their computer ({os_name}). "
                          f"You can execute terminal commands OR perform keyboard actions. "
                          f"The user's current working directory (for commands) is: '{self._cwd}'. "
                          f"{timestamp_info}"
                          f"To execute a shell command in {shell_type}, enclose the *complete, executable* command within <cmd> and </cmd> tags. Example: <cmd>ls -l</cmd> or <cmd>Get-ChildItem</cmd>. Only one <cmd> tag per response. " # Added clarification
                          f"To perform keyboard actions, use the <function> tag with specific calls:\n"
                          f"  - Type text: `<function call='keyboard_type' args='{{\"text\": \"hello world\"}}'>` (Use valid JSON escaped within the string)\n"
                          f"  - Press special key: `<function call='keyboard_press' args='{{\"key\": \"enter\"}}'>` (Common keys: enter, tab, esc, space, backspace, delete, up, down, left, right, home, end, pgup, pgdn, insert, f1-f20, ctrl, alt, shift, cmd/win)\n"
                          f"  - Press hotkey: `<function call='keyboard_hotkey' args='{{\"keys\": [\"ctrl\", \"c\"]}}'>` (List of keys, last is main key)\n"
                          f"You can provide *either* a <cmd> tag *or* one or more <function> tags in your response, or just text if no action is needed. "
                          f"If providing actions, keep explanatory text minimal or within <think>...</think> blocks (which will be ignored by the execution logic). "
                          f"Ensure JSON in 'args' is valid (double quotes for keys and string values). Be cautious with destructive commands or keyboard actions.")
        # --- End System Prompt ---

        # Prepare messages list for API
        messages = [{"role": "system", "content": system_message}]
        for role, message in self._history:
            # Clean previous assistant messages before sending them back as history
            # Remove think blocks and action tags to avoid confusing the model
            cleaned_message = message
            # Only clean non-user messages
            if role.lower() not in ["user", "system", "help", "prompt", "error"]: # Keep user/system messages as is
                cleaned_message = re.sub(r"<think>.*?</think>", "", message, flags=re.DOTALL | re.IGNORECASE).strip()
                cleaned_message = re.sub(r"<cmd>.*?</cmd>", "", cleaned_message, flags=re.DOTALL | re.IGNORECASE).strip()
                cleaned_message = re.sub(r"<function\s+call=[\"']keyboard_.*?[\"'].*?</function>", "", cleaned_message, flags=re.DOTALL | re.IGNORECASE).strip()
                # Also remove potential timing info added by the UI
                cleaned_message = re.sub(r"\s*\([\u0041-\uFFFF]+:\s*[\d.]+\s*[\u0041-\uFFFF]+\)$", "", cleaned_message).strip()


            # Skip adding empty messages after cleaning
            if not cleaned_message:
                continue

            # Determine the role for the API call ('user' or 'assistant')
            # Map internal roles ('Model', 'User', 'System', etc.) to API roles
            api_role = "user" if role.lower() == "user" else "assistant" # Treat 'Model' and others as 'assistant' in history context
            messages.append({"role": api_role, "content": cleaned_message})

        # --- Setup requests Session with Retries ---
        session = requests.Session()
        if URLLIB3_RETRY_AVAILABLE:
            try:
                # Configure retries for common transient errors
                retry_strategy = Retry(
                    total=3, # Total number of retries
                    backoff_factor=1, # Exponential backoff factor (e.g., 1s, 2s, 4s)
                    status_forcelist=[429, 500, 502, 503, 504], # HTTP status codes to retry on
                    allowed_methods=["POST"] # Only retry POST requests
                )
                adapter = HTTPAdapter(max_retries=retry_strategy)
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                print("[ApiWorker] Requests session configured with retries.")
            except Exception as e:
                print(f"[ApiWorker] Warning: Could not configure requests retries: {e}")
        # --- End Session Setup ---

        try:
            # API Payload
            payload = {
                "model": self._model_id,
                "messages": messages,
                "max_tokens": 1200, # Increased slightly for function calls
                "temperature": 0.6 # Slightly lower temperature for more deterministic actions
                # "stream": False # Not using streaming responses for now
            }
            print(f"[ApiWorker] Sending API request to {url} with model {self._model_id}...") # Debug: Confirm model
            # DEBUG: Uncomment to log the exact messages being sent
            # try:
            #     print(f"[ApiWorker] Payload messages:\n{json.dumps(messages, indent=2)}")
            # except Exception as dump_err:
            #     print(f"[ApiWorker] Error dumping messages for logging: {dump_err}")


            response = session.post(url, headers=headers, json=payload, timeout=90) # 90 second timeout

            reply_text = "Error: API call failed or did not produce a response." # Default error
            data = None
            api_call_successful = False

            if response is not None:
                if response.ok: # Status code 2xx
                    try:
                        data = response.json()
                        api_call_successful = True
                    except json.JSONDecodeError as e:
                        reply_text = f"Error: Could not decode API response JSON (Status: {response.status_code})"
                        print(f"[ApiWorker] {reply_text}. Response Text: {response.text[:500]}")
                else:
                    # Handle API errors (4xx, 5xx)
                    reply_text = f"Error: API request failed with status {response.status_code}."
                    err_details = ""
                    try: # Attempt to get error details from JSON response
                        err_data = response.json()
                        # Look for common error message structures
                        error_obj = err_data.get('error', err_data) # Handle cases where error is top-level or nested
                        err_details = str(error_obj.get('message', error_obj)) # Get message if available
                    except Exception:
                        err_details = response.text[:200] # Fallback to raw text
                    reply_text += f" Details: {err_details}"
                    print(f"[ApiWorker] {reply_text}") # Log the detailed error

            # Process successful response data
            if api_call_successful and data:
                try:
                    if 'choices' in data and data['choices']:
                        choice = data['choices'][0]
                        finish_reason = choice.get('finish_reason', 'N/A')
                        if 'message' in choice and 'content' in choice['message']:
                             reply_text = choice['message']['content'] # Get content, strip later
                             if reply_text is None: reply_text = "" # Handle null content
                        elif 'text' in choice: # Fallback for older API formats
                             reply_text = choice['text']
                             if reply_text is None: reply_text = ""
                        else:
                             reply_text = "Error: Could not find 'content' or 'text' in API choice."

                        # Append warning if output was truncated
                        if finish_reason == 'length':
                            reply_text += "\n[Warning: AI output may have been truncated due to token limits.]"
                    elif 'error' in data: # Handle cases where API returns 200 OK but includes an error object
                         error_obj = data.get('error', data)
                         reply_text = f"Error from API: {error_obj.get('message', json.dumps(error_obj))}"
                    else: # Response OK, JSON parsed, but no choices/error?
                         reply_text = "Error: Unexpected API response structure."
                         print(f"[ApiWorker] Unexpected API response data: {json.dumps(data)}")
                except Exception as parse_err:
                    reply_text = f"Error parsing successful API response: {parse_err}"
                    print(f"[ApiWorker] {reply_text}. Data: {data}")

            # Ensure reply_text is always a string and strip whitespace
            if not isinstance(reply_text, str):
                reply_text = str(reply_text)
            reply_text = reply_text.strip()

            return reply_text

        except requests.exceptions.Timeout:
            print("[ApiWorker] API request timed out.")
            return "Error: API request timed out after 90 seconds."
        except requests.exceptions.SSLError as e:
            print(f"[ApiWorker] SSL Error: {e}")
            return f"Error: SSL verification failed. Check system certificates or network proxy settings: {e}."
        except requests.exceptions.RequestException as e:
            status_code = e.response.status_code if e.response is not None else "N/A"
            print(f"[ApiWorker] Network/Connection Error (Status: {status_code}): {e}")
            return f"Error: API request failed (Network/Connection Error, Status: {status_code}): {e}"
        except Exception as e:
            print(f"[ApiWorker] Unhandled Exception in _send_message_to_model: {e}")
            traceback.print_exc()
            return f"Error: An unexpected error occurred during the API call ({type(e).__name__}): {e}"

# --- End ApiWorkerThread ---


# For Manual Command Execution
class ManualCommandThread(QThread):
    """Handles manually entered shell commands."""
    # Signals remain the same
    cli_output_signal = Signal(bytes) # Raw stdout bytes
    cli_error_signal = Signal(bytes)  # Raw stderr bytes or error messages
    directory_changed_signal = Signal(str, bool) # (new_directory, is_manual_command=True)
    command_finished = Signal() # Renamed from task_finished for clarity

    def __init__(self, command, cwd):
        super().__init__()
        self._command = command
        self._cwd = cwd
        self._is_running = True
        # No process handle needed here directly, executor manages it.

    def stop(self):
        """Signals the thread and the command executor to stop."""
        print("[ManualWorker] Stop signal received. Setting internal flag.")
        self._is_running = False
        # The command executor checks this flag.

    def run(self):
        """Executes the manual command using the command executor."""
        exit_code = None
        try:
            if not self._is_running:
                print("[ManualWorker] Run() aborted early: stop signal set before execution.")
                return
            command_to_run = self._command.strip()
            if not command_to_run:
                 print("[ManualWorker] Empty command received, doing nothing.")
                 return # Don't execute empty command

            print(f"[ManualWorker] Executing manual command: '{command_to_run}' in CWD: {self._cwd}")
            # Call the dedicated command executor function
            new_cwd, exit_code = execute_command_streamed(
                command=command_to_run,
                cwd=self._cwd,
                stop_flag_func=lambda: not self._is_running, # Pass stop check
                output_signal=self.cli_output_signal,
                error_signal=self.cli_error_signal,
                directory_changed_signal=self.directory_changed_signal,
                is_manual_command=True # Manual command source
            )
            # Update internal CWD state if changed by executor (e.g., via 'cd')
            # This worker's CWD state isn't directly used elsewhere after it finishes,
            # but updating it reflects the outcome accurately.
            self._cwd = new_cwd
            print(f"[ManualWorker] Command execution finished. ExitCode: {exit_code}, Final CWD for worker instance: {self._cwd}")

        except Exception as run_err:
            # Catch errors during the call to the executor or if executor raises unexpected error
            print(f"[ManualWorker] Unhandled error in run loop: {run_err}")
            traceback.print_exc()
            # Emit error only if thread wasn't stopped externally
            if self._is_running: self._emit_cli_error(f"Unexpected thread error: {run_err}")

        finally:
            # Emit finished signal if the thread wasn't stopped externally
            if self._is_running:
                print(f"[ManualWorker] Run() sequence completed, emitting command_finished.")
                try:
                    self.command_finished.emit()
                except RuntimeError as e:
                    print(f"[ManualWorker] Warning: Could not emit command_finished signal (likely main window closed): {e}")
                except Exception as e:
                    print(f"[ManualWorker] Error emitting command_finished signal: {e}")

            else:
                 print("[ManualWorker] Run() sequence ended because stop signal was set.")

    # --- Helper methods for safe signal emission ---
    def _emit_cli_error(self, message: str):
        """Helper to safely emit string errors via the error signal."""
        if self._is_running: # Check running flag before emitting
            try:
                # Ensure message is string before encoding
                if not isinstance(message, str): message = str(message)
                self.cli_error_signal.emit(f"Error: {message}".encode('utf-8'))
            except RuntimeError as e:
                print(f"[ManualWorker] Warning: Could not emit CLI error signal (likely main window closed): {e}")
            except Exception as e:
                 print(f"[ManualWorker] Unexpected error emitting CLI error signal: {e}")

    # Note: _emit_cli_output_bytes is not needed here as output comes directly from executor's signals

# --- End ManualCommandThread ---