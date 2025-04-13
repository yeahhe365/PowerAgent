# ========================================
# 文件名: PowerAgent/core/workers.py
# (MODIFIED - Use config.MULTI_STEP_MAX_ITERATIONS in multi-step loop)
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
import html
from PySide6.QtCore import QThread, Signal, QObject
from requests.adapters import HTTPAdapter

# Import global config state
from core import config # Import the whole module to access config values

# Import modularized components
from .worker_utils import decode_output
from .command_executor import execute_command_streamed
from .keyboard_controller import KeyboardController, PYNPUT_AVAILABLE, PYPERCLIP_AVAILABLE


try:
    from urllib3.util.retry import Retry
    URLLIB3_RETRY_AVAILABLE = True
except ImportError:
    print("Warning: Failed to import Retry from urllib3.util.retry. Retries disabled.")
    URLLIB3_RETRY_AVAILABLE = False


# --- Worker Threads ---

class ApiWorkerThread(QThread):
    """Handles AI interaction, response parsing, and action execution (commands/keyboard). Includes NEW multi-step logic."""
    api_result = Signal(str, float) # (reply_for_display, elapsed_time)
    cli_output_signal = Signal(bytes)
    cli_error_signal = Signal(bytes)
    directory_changed_signal = Signal(str, bool) # (new_dir, is_manual)
    task_finished = Signal()
    ai_command_echo_signal = Signal(str) # Emits the command string to be echoed in chat

    def __init__(self, api_key, api_url, model_id, history, prompt, cwd):
        super().__init__()
        self._api_key = api_key
        self._api_url = api_url.rstrip('/') if api_url else ""
        self._model_id = model_id
        # IMPORTANT: Use a deep copy of the history list to avoid modifying the original deque in MainWindow directly
        self._history = [list(item) if isinstance(item, tuple) else item for item in history]
        self._cwd = cwd
        self._is_running = True
        self._keyboard_controller = None
        self._action_outcome_message = "" # Store outcome message for adding to history in multi-step loop

    def stop(self):
        """Signals the thread and its operations to stop."""
        print("[ApiWorker] Stop signal received. Setting internal flag.")
        self._is_running = False

    def _update_history_with_outcome(self, ai_reply_cleaned: str):
        """Appends AI reply and action outcome to the internal history list."""
        # Add AI's response (cleaned of think tags etc.)
        if ai_reply_cleaned:
            # Avoid adding duplicate identical responses
            if not self._history or self._history[-1] != ["assistant", ai_reply_cleaned]:
                self._history.append(["assistant", ai_reply_cleaned])

        # Add the action outcome message if available
        if self._action_outcome_message:
            print(f"[ApiWorker] Adding outcome to history: {self._action_outcome_message}")
            # Ensure outcome message is added even if it's the same as the previous one (e.g., repeated errors)
            self._history.append(["system", self._action_outcome_message])
            self._action_outcome_message = "" # Reset for next iteration

    def run(self):
        """Main execution logic: Branches based on config.ENABLE_MULTI_STEP."""
        try:
            if config.ENABLE_MULTI_STEP:
                # Use the NEW application-driven multi-step logic
                self._run_iterative_multi_step()
            else:
                # Use the original single-step logic
                self._run_single_step()
        except Exception as main_run_err:
             err_msg = f"CRITICAL UNHANDLED ERROR in ApiWorkerThread run: {main_run_err}"
             print(err_msg)
             traceback.print_exc()
             self._try_emit_cli_error(err_msg) # Try to report error
        finally:
             # Ensure task_finished is always emitted, regardless of path
             print(f"[ApiWorker] Run sequence finished (running={self._is_running}). Emitting task_finished.")
             try:
                 self.task_finished.emit()
             except RuntimeError as e:
                 print(f"[ApiWorker] Warning: Could not emit task_finished signal (RuntimeError): {e}")
             except Exception as e:
                 print(f"[ApiWorker] Error emitting task_finished signal: {e}")
             # Ensure controller cleanup happens after either run path
             if self._keyboard_controller:
                 print("[ApiWorker] Scheduling KeyboardController for deletion post-run.")
                 self._try_delete_controller()


    def _run_single_step(self):
        """Original logic for handling a single API call and action."""
        print("[ApiWorker] Running in original single-step mode.")
        elapsed_time = 0.0
        raw_model_reply = "错误: API 调用未完成。"
        try:
            # --- 1. API Call ---
            if not self._is_running:
                print("[ApiWorker SingleStep] Run() aborted early: stop signal.")
                raw_model_reply = "错误: API 调用已取消。"
            else:
                start_time = time.time()
                try:
                    # Call API without multi-step context
                    raw_model_reply = self._send_message_to_model(is_multi_step_flow=False)
                except Exception as api_err:
                    print(f"[ApiWorker SingleStep] API call exception: {api_err}")
                    raw_model_reply = f"错误: API 调用期间发生意外错误: {api_err}"
                finally:
                    end_time = time.time(); elapsed_time = end_time - start_time
                    print(f"[ApiWorker SingleStep] API call took: {elapsed_time:.2f}s")

            if not self._is_running and raw_model_reply != "错误: API 调用已取消。":
                print("[ApiWorker SingleStep] Run() aborted: stop signal after API call.")
                raw_model_reply = "错误: API 调用已取消。"

            # --- 2. Reply Processing & Parsing ---
            reply_for_display = raw_model_reply or ""
            reply_for_parsing = reply_for_display

            # Clean <think> blocks
            try:
                temp_cleaned_reply = re.sub(r"<think>.*?</think>", "", reply_for_parsing, flags=re.DOTALL | re.IGNORECASE).strip()
                if raw_model_reply != temp_cleaned_reply: print("[ApiWorker SingleStep] Removed <think> block.")
                reply_for_display = temp_cleaned_reply
                reply_for_parsing = temp_cleaned_reply
            except Exception as clean_err: print(f"[ApiWorker SingleStep] Warning: Error cleaning <think>: {clean_err}.")

            # Emit result to UI
            if self._is_running:
                 try:
                     # Extract text part for display, excluding actions
                     display_text_for_emit = re.sub(r"<cmd>.*?</cmd>", "", reply_for_display, flags=re.DOTALL | re.IGNORECASE).strip()
                     display_text_for_emit = re.sub(r"<function\s+call=.*?/?>.*?</function>", "", display_text_for_emit, flags=re.DOTALL | re.IGNORECASE).strip()
                     display_text_for_emit = re.sub(r"<function\s+call=.*?/>", "", display_text_for_emit, flags=re.DOTALL | re.IGNORECASE).strip()
                     # Remove old <continue /> tag if present (shouldn't be, but defensive)
                     display_text_for_emit = display_text_for_emit.replace("<continue />", "").strip()
                     display_text_to_emit = display_text_for_emit if display_text_for_emit else raw_model_reply # Fallback
                     if raw_model_reply == "错误: API 调用已取消。": display_text_to_emit = raw_model_reply

                     self.api_result.emit(display_text_to_emit, elapsed_time)
                     print("[ApiWorker SingleStep] Emitted api_result.")
                 except RuntimeError as e: print(f"[ApiWorker SingleStep] Warning: Could not emit api_result signal: {e}")
                 except Exception as e: print(f"[ApiWorker SingleStep] Error emitting api_result signal: {e}")
            else: print("[ApiWorker SingleStep] Stop signal set, skipping api_result emission.")

            if not self._is_running: return # Exit if stopped

            # --- 3. Parse Actions ---
            command_to_run = None
            keyboard_actions = []
            if reply_for_parsing and isinstance(reply_for_parsing, str):
                print(f"[ApiWorker SingleStep] Parsing reply for actions: '{reply_for_parsing[:100]}...'")
                try:
                    command_match = re.search(r"<cmd>\s*(.*?)\s*</cmd>", reply_for_parsing, re.DOTALL | re.IGNORECASE)
                    if command_match:
                         command_to_run = command_match.group(1).strip()
                         if command_to_run: print(f"[ApiWorker SingleStep] Command Extracted: '{command_to_run}'")
                         else: command_to_run = None

                    func_pattern = re.compile(r"""<function\s+call=['"]([\w_]+)['"]\s+args=['"](.*?)['"]\s*/?>(?:</function>)?""", re.VERBOSE | re.DOTALL | re.IGNORECASE)
                    for match in func_pattern.finditer(reply_for_parsing):
                        func_name = match.group(1); args_json_str_html = match.group(2)
                        try: args_json_str = html.unescape(args_json_str_html)
                        except Exception: args_json_str = args_json_str_html
                        try:
                            args_dict = json.loads(args_json_str)
                            if func_name in ["clipboard_paste", "keyboard_press", "keyboard_hotkey"]: keyboard_actions.append({"call": func_name, "args": args_dict}); print(f"[ApiWorker SingleStep] Keyboard Action Parsed: {func_name}")
                            else: print(f"[ApiWorker SingleStep] Warning: Ignoring unsupported function '{func_name}'.")
                        except Exception as parse_err: print(f"[ApiWorker SingleStep] Error parsing args for '{func_name}': {parse_err}"); self._try_emit_cli_error(f"Error parsing function args: {parse_err}")
                except Exception as e: print(f"[ApiWorker SingleStep] Error parsing action tags: {e}"); self._try_emit_cli_error(f"Error parsing reply: {e}")

            # --- 4. Action Execution ---
            if command_to_run and self._is_running:
                print(f"[ApiWorker SingleStep] Executing command: '{command_to_run}'...")
                try: self.ai_command_echo_signal.emit(command_to_run)
                except RuntimeError: pass
                status_message = f"Model {self._cwd}> {command_to_run}"; self._try_emit_cli_output_bytes(status_message.encode('utf-8')) # Use > prompt symbol
                try:
                    new_cwd, exit_code = execute_command_streamed( command=command_to_run, cwd=self._cwd, stop_flag_func=lambda: not self._is_running, output_signal=self.cli_output_signal, error_signal=self.cli_error_signal, directory_changed_signal=self.directory_changed_signal, is_manual_command=False)
                    self._cwd = new_cwd; print(f"[ApiWorker SingleStep] Command finished. ExitCode: {exit_code}, New CWD: {self._cwd}")
                except Exception as exec_err: print(f"[ApiWorker SingleStep] Error executing command: {exec_err}"); self._try_emit_cli_error(f"Command execution error: {exec_err}")
            elif keyboard_actions and self._is_running and not command_to_run: # Only run KB if NO <cmd>
                print(f"[ApiWorker SingleStep] Executing {len(keyboard_actions)} keyboard action(s)...")
                if self._keyboard_controller is None and self._is_running: self._keyboard_controller = KeyboardController(); self._keyboard_controller.error_signal.connect(self._try_emit_cli_error)
                if not self._is_running or not self._keyboard_controller or not self._keyboard_controller.is_pynput_available():
                     err_msg = "Cannot execute keyboard actions: pynput not available/initialized."
                     print(err_msg); self._try_emit_cli_error(err_msg)
                else:
                     for action in keyboard_actions:
                         if not self._is_running: break
                         call = action.get("call"); args = action.get("args", {})
                         try: self._execute_keyboard_action(call, args) # Use helper
                         except Exception as key_exec_err: print(f"[ApiWorker SingleStep] Error executing KB action '{call}': {key_exec_err}"); self._try_emit_cli_error(f"Keyboard action error: {key_exec_err}")
                         if self._is_running and len(keyboard_actions) > 1: time.sleep(0.3) # Delay between actions
            elif command_to_run and keyboard_actions:
                print("[ApiWorker SingleStep] Skipping keyboard actions because <cmd> was present.")
        except Exception as single_step_err:
            # Catch any unexpected error within the single-step logic
            err_msg = f"Unexpected error in _run_single_step: {single_step_err}"
            print(f"[ApiWorker SingleStep] {err_msg}")
            traceback.print_exc()
            self._try_emit_cli_error(err_msg) # Report the error
            # Optionally emit an error result to the main display as well
            self._try_emit_api_result(f"错误: 执行期间发生内部错误。", elapsed_time)

    def _run_iterative_multi_step(self):
        """NEW logic: Application-driven multi-step flow."""
        print("[ApiWorker] Running in NEW iterative multi-step mode.")
        # <<< MODIFICATION START: Use config value for max iterations >>>
        max_iterations = config.MULTI_STEP_MAX_ITERATIONS
        # <<< MODIFICATION END >>>
        current_iteration = 0
        last_emitted_reply_content = None # Track last emitted reply to avoid duplicates

        print(f"[ApiWorker Iterative] Max iterations set to: {max_iterations}") # Log the limit being used

        while self._is_running and current_iteration < max_iterations:
            current_iteration += 1
            print(f"[ApiWorker Iterative] Starting iteration {current_iteration}/{max_iterations}")
            self._action_outcome_message = "" # Reset outcome message for this iteration
            action_found_this_iteration = False # Reset flag for this iteration

            # --- 1. API Call ---
            if not self._is_running: print(f"[ApiWorker Iterative Iter {current_iteration}] Aborted: stop signal."); break
            start_time = time.time()
            raw_model_reply = "错误: API 调用未完成。"
            elapsed_time = 0.0
            try:
                # Pass the current internal history (includes previous outcomes)
                # Indicate this is part of the multi-step flow for prompt generation
                raw_model_reply = self._send_message_to_model(is_multi_step_flow=True)
            except Exception as api_err:
                print(f"[ApiWorker Iterative Iter {current_iteration}] API call exception: {api_err}"); traceback.print_exc()
                raw_model_reply = f"错误: API 调用期间发生意外错误: {api_err}";
            finally:
                end_time = time.time(); elapsed_time = end_time - start_time
                print(f"[ApiWorker Iterative Iter {current_iteration}] API call took: {elapsed_time:.2f}s")

            if not self._is_running:
                print(f"[ApiWorker Iterative Iter {current_iteration}] Aborted: stop signal after API call.")
                # Emit cancellation error only if it hasn't been emitted before for this request chain
                if last_emitted_reply_content != "错误: API 调用已取消.":
                    self._try_emit_api_result("错误: API 调用已取消。", elapsed_time)
                break

            # --- 2. Reply Processing & Parsing ---
            reply_for_display = raw_model_reply or ""
            reply_for_parsing = reply_for_display

            # Clean <think> blocks
            try:
                temp_cleaned_reply = re.sub(r"<think>.*?</think>", "", reply_for_parsing, flags=re.DOTALL | re.IGNORECASE).strip()
                if raw_model_reply != temp_cleaned_reply: print(f"[ApiWorker Iterative Iter {current_iteration}] Removed <think> block.")
                reply_for_display = temp_cleaned_reply
                reply_for_parsing = temp_cleaned_reply
            except Exception as clean_err: print(f"[ApiWorker Iterative Iter {current_iteration}] Warning: Error cleaning <think>: {clean_err}.")

            # Remove old <continue /> tag if present (it's ignored anyway)
            reply_for_display = reply_for_display.replace("<continue />", "").strip()
            reply_for_parsing = reply_for_parsing.replace("<continue />", "").strip()

            # --- Emit the processed reply for THIS iteration ---
            # Extract text part excluding actions for display
            display_text_for_emit = re.sub(r"<cmd>.*?</cmd>", "", reply_for_display, flags=re.DOTALL | re.IGNORECASE).strip()
            display_text_for_emit = re.sub(r"<function\s+call=.*?/?>.*?</function>", "", display_text_for_emit, flags=re.DOTALL | re.IGNORECASE).strip()
            display_text_for_emit = re.sub(r"<function\s+call=.*?/>", "", display_text_for_emit, flags=re.DOTALL | re.IGNORECASE).strip()
            display_text_to_emit = display_text_for_emit if display_text_for_emit else raw_model_reply # Fallback

            # Special case: Ensure cancellation message is emitted correctly
            if raw_model_reply == "错误: API 调用已取消." and "错误:" not in display_text_to_emit :
                 display_text_to_emit = raw_model_reply

            # Avoid emitting empty/duplicate results unless it's an error
            if display_text_to_emit and (display_text_to_emit != last_emitted_reply_content or "错误:" in display_text_to_emit):
                self._try_emit_api_result(display_text_to_emit, elapsed_time)
                last_emitted_reply_content = display_text_to_emit # Track what was emitted
                print(f"[ApiWorker Iterative Iter {current_iteration}] Emitted api_result.")
            elif not display_text_to_emit:
                 print(f"[ApiWorker Iterative Iter {current_iteration}] Skipping empty api_result emission.")


            if not self._is_running: print(f"[ApiWorker Iterative Iter {current_iteration}] Stop signal set after processing reply."); break

            # --- 3. Parse Actions ---
            command_to_run = None
            keyboard_actions = []
            exit_code = None # Reset exit code for this iteration's action
            if reply_for_parsing and isinstance(reply_for_parsing, str) and "错误:" not in raw_model_reply: # Don't parse if API call failed
                print(f"[ApiWorker Iterative Iter {current_iteration}] Parsing reply for actions: '{reply_for_parsing[:100]}...'")
                try:
                    command_match = re.search(r"<cmd>\s*(.*?)\s*</cmd>", reply_for_parsing, re.DOTALL | re.IGNORECASE)
                    if command_match:
                         command_to_run = command_match.group(1).strip()
                         if command_to_run:
                             print(f"[ApiWorker Iterative Iter {current_iteration}] Command Extracted: '{command_to_run}'")
                             action_found_this_iteration = True
                         else: command_to_run = None

                    func_pattern = re.compile(r"""<function\s+call=['"]([\w_]+)['"]\s+args=['"](.*?)['"]\s*/?>(?:</function>)?""", re.VERBOSE | re.DOTALL | re.IGNORECASE)
                    for match in func_pattern.finditer(reply_for_parsing):
                        func_name = match.group(1); args_json_str_html = match.group(2)
                        try: args_json_str = html.unescape(args_json_str_html)
                        except Exception: args_json_str = args_json_str_html
                        try:
                            args_dict = json.loads(args_json_str)
                            if func_name in ["clipboard_paste", "keyboard_press", "keyboard_hotkey"]:
                                keyboard_actions.append({"call": func_name, "args": args_dict})
                                print(f"[ApiWorker Iterative Iter {current_iteration}] Keyboard Action Parsed: {func_name}")
                                if not command_to_run: # KB action counts only if no command
                                     action_found_this_iteration = True
                            else: print(f"[ApiWorker Iterative Iter {current_iteration}] Warning: Ignoring unsupported function '{func_name}'.")
                        except Exception as parse_err:
                             print(f"[ApiWorker Iterative Iter {current_iteration}] Error parsing args for '{func_name}': {parse_err}")
                             self._try_emit_cli_error(f"Error parsing function args: {parse_err}")
                             # Don't stop the loop, just report error and maybe AI can fix next time
                except Exception as e:
                    print(f"[ApiWorker Iterative Iter {current_iteration}] Error parsing action tags: {e}"); traceback.print_exc()
                    self._try_emit_cli_error(f"Error parsing reply: {e}")
                    # Don't stop the loop here either, let history update

            # --- 4. Action Execution ---
            if command_to_run and self._is_running:
                print(f"[ApiWorker Iterative Iter {current_iteration}] Executing command: '{command_to_run}'...")
                try: self.ai_command_echo_signal.emit(command_to_run)
                except RuntimeError: pass
                status_message = f"Model {self._cwd}> {command_to_run}"; self._try_emit_cli_output_bytes(status_message.encode('utf-8'))

                try:
                    original_cwd = self._cwd
                    new_cwd, exit_code = execute_command_streamed( command=command_to_run, cwd=self._cwd, stop_flag_func=lambda: not self._is_running, output_signal=self.cli_output_signal, error_signal=self.cli_error_signal, directory_changed_signal=self.directory_changed_signal, is_manual_command=False )
                    self._cwd = new_cwd; print(f"[ApiWorker Iterative Iter {current_iteration}] Command finished. ExitCode: {exit_code}, New CWD: {self._cwd}")
                    # Prepare outcome message
                    cmd_summary = f"'{command_to_run[:50]}{'...' if len(command_to_run)>50 else ''}'"
                    outcome = f"Command {cmd_summary} executed."
                    if exit_code == 0: outcome += f" Success (Exit Code: 0)."
                    elif exit_code is None: outcome += f" Likely finished/handled (e.g., 'cd')."
                    elif exit_code == -999: outcome += f" Stopped by user."
                    else: outcome += f" Failed (Exit Code: {exit_code})."
                    if original_cwd != self._cwd: outcome += f" CWD changed to '{self._cwd}'."
                    self._action_outcome_message = outcome
                    if self._is_running: time.sleep(0.5)
                except Exception as exec_err:
                    print(f"[ApiWorker Iterative Iter {current_iteration}] Error executing command: {exec_err}"); traceback.print_exc()
                    self._action_outcome_message = f"System Error: Failed command {cmd_summary}: {exec_err}"
                    self._try_emit_cli_error(self._action_outcome_message);
                if exit_code == -999: self._is_running = False # Ensure loop stops if user stopped command

            elif keyboard_actions and self._is_running and not command_to_run: # Only run KB if NO <cmd>
                print(f"[ApiWorker Iterative Iter {current_iteration}] Executing {len(keyboard_actions)} keyboard action(s)...")
                if self._keyboard_controller is None and self._is_running: self._keyboard_controller = KeyboardController(); self._keyboard_controller.error_signal.connect(self._try_emit_cli_error)

                if not self._is_running or not self._keyboard_controller or not self._keyboard_controller.is_pynput_available():
                     err_msg = "Cannot execute keyboard actions: pynput not available/initialized."
                     print(err_msg); self._try_emit_cli_error(err_msg)
                     self._action_outcome_message = f"System Error: {err_msg}"
                else:
                    actions_successful = True; action_details = []
                    for action in keyboard_actions:
                        if not self._is_running: print("Stop signal during KB loop."); actions_successful = False; break
                        call = action.get("call"); args = action.get("args", {})
                        action_details.append(f"{call}({str(args)[:30]}...)")
                        try: self._execute_keyboard_action(call, args) # Use helper
                        except Exception as key_exec_err:
                            err_msg = f"Error executing KB action '{call}': {key_exec_err}"; print(err_msg); traceback.print_exc()
                            self._action_outcome_message = f"System Error: Failed KB action '{call}': {key_exec_err}"
                            self._try_emit_cli_error(self._action_outcome_message); actions_successful = False; break # Stop KB actions on error
                        if self._is_running and len(keyboard_actions) > 1: time.sleep(0.3) # Delay
                    if actions_successful and self._is_running:
                        self._action_outcome_message = f"Keyboard action(s) executed: {', '.join(action_details)}."

            # --- 5. Update History for Next Iteration ---
            # Update history with the AI's reply (cleaned) and the action outcome message
            # This happens regardless of whether an action was found, so AI knows its text was received.
            if self._is_running:
                self._update_history_with_outcome(reply_for_parsing) # Pass the cleaned reply
                print(f"[ApiWorker Iterative Iter {current_iteration}] History updated. Size: {len(self._history)}")

            # --- 6. Loop termination checks ---
            if not self._is_running: print(f"[ApiWorker Iterative Iter {current_iteration}] Loop breaking: stop signal."); break
            if not action_found_this_iteration: print(f"[ApiWorker Iterative Iter {current_iteration}] Loop breaking: No action found in AI response."); break
            # <<< MODIFICATION START: Use configured max_iterations in check >>>
            if current_iteration >= max_iterations:
                print(f"[ApiWorker Iterative] Loop breaking: Reached max iterations ({max_iterations}).")
                self._try_emit_cli_error(f"已达到最大连续操作次数 ({max_iterations})。") # Use variable in error message
                break
            # <<< MODIFICATION END >>>

            # Small delay before next API call if an action was executed
            if action_found_this_iteration:
                time.sleep(0.2)

        # --- End of Loop ---
        print(f"[ApiWorker Iterative] Loop finished after {current_iteration} iteration(s).")
        # task_finished is emitted by the main run() method's finally block


    def _execute_keyboard_action(self, call: str, args: dict):
        """Helper to execute a single keyboard action."""
        if not self._keyboard_controller: raise RuntimeError("Keyboard controller not initialized.")

        print(f"[ApiWorker] Executing KB Action: {call} with args: {args}")
        if call == "clipboard_paste":
            if not self._keyboard_controller.is_paste_available(): raise RuntimeError("Paste prerequisites not met.")
            text = args.get("text");
            if text is not None and isinstance(text, str): self._keyboard_controller.paste_text(text)
            else: raise ValueError(f"Invalid 'text' arg for paste: {args.get('text')}")
        elif call == "keyboard_press":
            key = args.get("key");
            if key and isinstance(key, str): self._keyboard_controller.press_key(key)
            else: raise ValueError(f"Invalid 'key' arg for press: {args.get('key')}")
        elif call == "keyboard_hotkey":
            keys = args.get("keys");
            if keys and isinstance(keys, list) and all(isinstance(k, str) for k in keys): self._keyboard_controller.press_hotkey(keys)
            else: raise ValueError(f"Invalid 'keys' arg for hotkey: {args.get('keys')}")
        else:
            raise ValueError(f"Unknown keyboard function requested: {call}")

    def _try_emit_api_result(self, message: str, elapsed_time: float):
        """Safely emit api_result signal if still running."""
        if self._is_running:
            try:
                self.api_result.emit(message, elapsed_time)
            except RuntimeError: pass # Ignore if receiver is gone
            except Exception as e: print(f"[ApiWorker] Error emitting api_result: {e}")

    def _try_delete_controller(self):
        """Safely attempts to delete the keyboard controller."""
        if self._keyboard_controller:
            try:
                self._keyboard_controller.deleteLater()
                self._keyboard_controller = None # Clear reference
            except Exception as del_err: print(f"[ApiWorker] Error scheduling KB controller deletion: {del_err}")

    def _try_emit_cli_error(self, message: str):
        """Helper method to emit CLI error signal if still running."""
        if self._is_running:
            self._emit_cli_error(message)

    def _try_emit_cli_output_bytes(self, message_bytes: bytes, is_stderr: bool = False):
        """Helper method to emit CLI output signal if still running."""
        if self._is_running:
            self._emit_cli_output_bytes(message_bytes, is_stderr)

    def _emit_cli_error(self, message: str):
        try:
            if not isinstance(message, str): message = str(message)
            self.cli_error_signal.emit(f"错误: {message}".encode('utf-8'))
        except RuntimeError as e: print(f"[ApiWorker] Warning: Could not emit CLI error signal: {e}")
        except Exception as e: print(f"[ApiWorker] Unexpected error emitting CLI error signal: {e}")

    def _emit_cli_output_bytes(self, message_bytes: bytes, is_stderr: bool = False):
        target_signal = self.cli_error_signal if is_stderr else self.cli_output_signal
        try: target_signal.emit(message_bytes)
        except RuntimeError as e: print(f"[ApiWorker] Warning: Could not emit CLI signal ({'stderr' if is_stderr else 'stdout'}): {e}")
        except Exception as e: print(f"[ApiWorker] Unexpected error emitting CLI signal ({'stderr' if is_stderr else 'stdout'}): {e}")

    def _send_message_to_model(self, is_multi_step_flow: bool):
        """
        Sends history and prompt to the configured AI model API.
        The system prompt is adjusted based on whether this is part of the new multi-step flow.
        """
        if not self._is_running: return "错误: API 调用已取消。"
        if not self._api_key or not self._api_url or not self._model_id: return f"错误: API 配置缺失或未选择模型 (当前: {self._model_id})。"

        headers = { "Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}" }
        url = f"{self._api_url.rstrip('/')}/v1/chat/completions"
        os_name = platform.system(); shell_type = "PowerShell" if os_name == "Windows" else "Default Shell"
        shell_info = f"You are operating within {shell_type} on {os_name}."
        timestamp_info = ""
        if config.INCLUDE_TIMESTAMP_IN_PROMPT:
            try: timestamp_info = f"Current date and time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. "
            except Exception: pass

        # --- Base Instructions (Common to both modes) ---
        base_instructions = (
            f"You are an AI assistant interacting with a user's computer ({os_name}). "
            f"{shell_info} Your primary goal is to fulfill user requests using **command-line operations (`<cmd>`)** within this shell. "
            f"Only use keyboard operations (`<function>`) as a last resort if a task **cannot** be achieved via a standard command-line command in the current shell.\n"
            f"Current Working Directory (CWD): '{self._cwd}'\n"
            f"{timestamp_info}"

            f"**RULE 1: PRIORITIZE `<cmd>`**\n"
            f"   - **Goal:** Solve the user's request directly via the command line.\n"
            f"   - **Format:** `<cmd>Full Shell Command Here</cmd>`.\n"
            f"   - **Web/Search (CRITICAL):** MUST use `<cmd>` with shell's URL opening command (Windows: `Start-Process \"URL\"` or `start \"URL\"` [NO `start \"\" \"URL\"`], macOS: `open 'URL'`, Linux: `xdg-open 'URL'`). Quote URL properly.\n"
            f"   - **Limit:** Only ONE `<cmd>` tag per response.\n\n"

            f"**RULE 2: USE `<function>` ONLY IF `<cmd>` IS IMPOSSIBLE**\n"
            f"   - **When:** For actions *not achievable* with a single standard command (e.g., simulating specific hotkeys like Ctrl+C, pasting into *already open* GUI).\n"
            f"   - **Format:** Paste: `<function call='clipboard_paste' args='{{\"text\": \"Content\"}}'>`, Key Press: `<function call='keyboard_press' args='{{\"key\": \"key_name\"}}'>`, Hotkey: `<function call='keyboard_hotkey' args='{{\"keys\": [\"key1\", ... ]}}'>`.\n"
            f"   - **Avoid:** File operations, opening URLs, starting most apps – use `<cmd>`.\n\n"

             f"**Language Instruction:** Please provide all your textual explanations and conversational replies in **Chinese**. (请用中文进行回复。)\n\n" # Keep Chinese instruction

            f"**OUTPUT FORMAT:**\n"
            f"1.  If `<cmd>` works: Respond *only* with `<cmd>...</cmd>`. Put thoughts in `<think>...</think>`.\n"
            f"2.  If `<cmd>` impossible, `<function>` works: Respond *only* with one or more `<function...>` tags. Put thoughts in `<think>...</think>`.\n"
            f"3.  If neither works or info only: Respond with plain text (in Chinese).\n"
            f"**DO NOT** include both `<cmd>` and `<function>` in the same response. Ensure JSON `args` valid (double quotes). Use `&quot;` for quotes within JSON strings if needed."
            # Removed the old multi-step instruction about <continue /> here.
        )

        # --- Specific Instructions based on Flow ---
        flow_instructions = ""
        if is_multi_step_flow:
            flow_instructions = (
                f"\n\n**Iterative Operation Mode:**\n"
                f"- You are in a multi-step process. Your previous action (if any) was executed, and the outcome is provided in the history (as a System message).\n"
                # <<< MODIFICATION START: Mention configured max iterations >>>
                f"- You can perform a maximum of {config.MULTI_STEP_MAX_ITERATIONS} consecutive actions.\n"
                # <<< MODIFICATION END >>>
                f"- **Your Task:** Analyze the history, the outcome of the last step, and the original user request. Determine the **single next action** needed.\n"
                f"- If another `<cmd>` or `<function>` is required, provide it using the standard format.\n"
                f"- If the task is now complete based on the last outcome, provide a final **textual confirmation or summary** in Chinese, **without** any `<cmd>` or `<function>` tags.\n"
                f"- If an error occurred in the previous step, try to correct it or inform the user if you cannot proceed.\n"
                f"- **Remember:** Only provide the *next single step* or the *final textual response*."
                f"**请根据上一步操作的结果（在历史记录中以 System 消息提供）决定下一步操作（`<cmd>`或`<function>`）或提供最终的中文文本回复。**"
            )
        else: # Single-step mode
             flow_instructions = (
                f"\n\n**Single Operation Mode:**\n"
                f"- Analyze the user request and provide a single `<cmd>` or sequence of `<function>` tags to achieve it in one go, OR provide a textual response if no action is possible/needed.\n"
                f"- There will be no follow-up API call after your action is executed."
             )


        # --- Combine System Message ---
        system_message = base_instructions + flow_instructions

        messages = [{"role": "system", "content": system_message}]
        # Use the current internal history list (which includes outcomes from multi-step)
        for role, message in self._history:
            cleaned_message = message
            # Minimal cleaning for history before sending
            if role.lower() in ["system", "error", "help", "prompt", "ai command"]:
                if message.startswith("System Error:") or message.startswith("Command ") or message.startswith("Keyboard action"): # Keep outcome messages mostly as is
                    pass # Perhaps truncate very long error messages later if needed
                else: # Clean other system-like roles more aggressively if needed
                    cleaned_message = re.sub(r"<think>.*?</think>", "", message, flags=re.DOTALL | re.IGNORECASE).strip()
                    cleaned_message = re.sub(r"<cmd>.*?</cmd>", "", cleaned_message, flags=re.DOTALL | re.IGNORECASE).strip()
                    cleaned_message = re.sub(r"<function.*?>.*?</function>", "", cleaned_message, flags=re.DOTALL | re.IGNORECASE).strip()
                    cleaned_message = re.sub(r"<function.*?/>", "", cleaned_message, flags=re.DOTALL | re.IGNORECASE).strip()
                    # Remove our own time marker if present
                    cleaned_message = re.sub(r"\s*\([\u0041-\uFFFF]+:\s*[\d.]+\s*[\u0041-\uFFFF]+\)$", "", cleaned_message).strip()

            if not cleaned_message: continue

            # Map roles for the API
            if role.lower() == "user": api_role = "user"
            elif role.lower() == "system": api_role = "system" # Send action outcomes as system role
            else: api_role = "assistant" # Model, AI Command, Help, Error etc. map to assistant

            messages.append({"role": api_role, "content": cleaned_message})

        session = requests.Session()
        if URLLIB3_RETRY_AVAILABLE:
            try:
                retry_strategy = Retry( total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["POST"])
                adapter = HTTPAdapter(max_retries=retry_strategy); session.mount("https://", adapter); session.mount("http://", adapter)
            except Exception as e: print(f"[ApiWorker] Warning: Could not configure requests retries: {e}")


        try:
            payload = { "model": self._model_id, "messages": messages, "max_tokens": 1500, "temperature": 0.5 }
            print(f"[ApiWorker] Sending API request to {url} (IterativeMode={is_multi_step_flow}). History size: {len(messages)}")
            # print(f"[ApiWorker DEBUG] Sending Payload Messages: {json.dumps(messages, ensure_ascii=False, indent=2)}") # Careful with large history
            timeout_seconds = 90
            response = session.post(url, headers=headers, json=payload, timeout=timeout_seconds)

            reply_text = "错误: API 调用失败或未产生响应。"
            data = None; api_call_successful = False
            if response is not None:
                response.encoding = 'utf-8' # Force UTF-8 decoding
                if response.ok:
                    try: data = response.json(); api_call_successful = True
                    except json.JSONDecodeError: reply_text = f"错误: 无法解码 API 响应 JSON (状态码 {response.status_code})"
                    except Exception as e: reply_text = f"错误: 处理 API 响应时出错 (状态码 {response.status_code}): {e}"
                else:
                    reply_text = f"错误: API 请求失败 (状态码 {response.status_code})"; err_details = ""
                    try: err_data = response.json(); error_obj = err_data.get('error', err_data); err_details = str(error_obj.get('message', error_obj))
                    except Exception: err_details = response.text[:200]
                    reply_text += f" 详情: {err_details}"

            if api_call_successful and data:
                 try:
                     if 'choices' in data and data['choices']:
                         choice = data['choices'][0]; finish_reason = choice.get('finish_reason', 'N/A')
                         if 'message' in choice and 'content' in choice['message']: reply_text = choice['message']['content'] or ""
                         elif 'text' in choice: reply_text = choice['text'] or "" # Fallback for older APIs?
                         else: reply_text = "错误: 未能在 API 选项中找到 'content' 或 'text'。"
                         if finish_reason == 'length': reply_text += "\n[警告: AI 输出可能因达到最大长度而被截断。]"
                     elif 'error' in data: error_obj = data.get('error', data); reply_text = f"来自 API 的错误: {error_obj.get('message', json.dumps(error_obj))}"
                     else: reply_text = "错误: 意外的 API 响应结构。"
                 except Exception as parse_err: reply_text = f"错误: 解析成功的 API 响应时出错: {parse_err}"

            if not isinstance(reply_text, str): reply_text = str(reply_text)
            return reply_text.strip()

        except requests.exceptions.Timeout: print("[ApiWorker] API request timed out."); return f"错误: API 请求超时 ({timeout_seconds} 秒)。"
        except requests.exceptions.SSLError as e: print(f"[ApiWorker] SSL Error: {e}"); return f"错误: SSL 验证失败 ({e})。"
        except requests.exceptions.RequestException as e: status_code = e.response.status_code if e.response is not None else "N/A"; print(f"[ApiWorker] Network/Connection Error (Status: {status_code}): {e}"); return f"错误: API 请求失败 (网络/连接错误, 状态码: {status_code})"
        except Exception as e: print(f"[ApiWorker] Unhandled Exception in _send_message_to_model: {e}"); traceback.print_exc(); return f"错误: API 调用期间发生意外错误 ({type(e).__name__})"

# --- End ApiWorkerThread ---


# --- ManualCommandThread (Remains Unchanged) ---
class ManualCommandThread(QThread):
    cli_output_signal = Signal(bytes)
    cli_error_signal = Signal(bytes)
    directory_changed_signal = Signal(str, bool)
    command_finished = Signal()

    def __init__(self, command, cwd):
        super().__init__()
        self._command = command
        self._cwd = cwd
        self._is_running = True

    def stop(self):
        print("[ManualWorker] Stop signal received. Setting internal flag.")
        self._is_running = False

    def run(self):
        exit_code = None
        try:
            if not self._is_running: print("[ManualWorker] Run aborted early."); return
            command_to_run = self._command.strip();
            if not command_to_run: print("[ManualWorker] Empty command."); return

            print(f"[ManualWorker] Executing manual command: '{command_to_run}' in CWD: {self._cwd}")
            new_cwd, exit_code = execute_command_streamed( command=command_to_run, cwd=self._cwd, stop_flag_func=lambda: not self._is_running, output_signal=self.cli_output_signal, error_signal=self.cli_error_signal, directory_changed_signal=self.directory_changed_signal, is_manual_command=True)
            self._cwd = new_cwd; print(f"[ManualWorker] Command finished. ExitCode: {exit_code}, Final CWD: {self._cwd}")
        except Exception as run_err:
            print(f"[ManualWorker] Unhandled error: {run_err}"); traceback.print_exc()
            if self._is_running: self._emit_cli_error(f"意外的线程错误: {run_err}")
        finally:
            print(f"[ManualWorker] Run sequence finished (running={self._is_running}). Emitting command_finished.")
            try: self.command_finished.emit()
            except RuntimeError as e: print(f"[ManualWorker] Warning: Could not emit finished signal: {e}")
            except Exception as e: print(f"[ManualWorker] Error emitting finished signal: {e}")

    def _emit_cli_error(self, message: str):
        if self._is_running:
            try:
                if not isinstance(message, str): message = str(message)
                self.cli_error_signal.emit(f"错误: {message}".encode('utf-8'))
            except RuntimeError: pass
            except Exception as e: print(f"[ManualWorker] Error emitting CLI error signal: {e}")
# --- End ManualCommandThread ---