# ========================================
# 文件名: PowerAgent/core/workers.py
# ---------------------------------------
# core/workers.py
# -*- coding: utf-8 -*-

import re
import json
import requests
import time
import os
import subprocess
import platform
import base64
import locale # Import locale to help guess system encoding if needed
import traceback # For logging unexpected errors
# <<< MODIFICATION START: Import datetime and config >>>
import datetime
from core import config # To access global config state (like INCLUDE_TIMESTAMP_IN_PROMPT)
# <<< MODIFICATION END >>>
from PySide6.QtCore import QThread, Signal, QObject # <<< Ensure QObject is imported
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
    URLLIB3_RETRY_AVAILABLE = True
except ImportError:
    print("Warning: Failed to import Retry from urllib3.util.retry. Retries disabled.")
    URLLIB3_RETRY_AVAILABLE = False

def _decode_output(output_bytes: bytes) -> str:
    """
    Attempts to decode bytes, prioritizing UTF-8, then system preferred,
    then 'mbcs' (Windows), finally falling back to latin-1 with replacements.
    """
    if not isinstance(output_bytes, bytes):
        print(f"Warning: _decode_output received non-bytes type: {type(output_bytes)}. Returning as is.")
        if isinstance(output_bytes, str): return output_bytes
        try: return str(output_bytes)
        except: return repr(output_bytes)

    if not output_bytes: return ""

    # 1. 尝试 UTF-8 (最常用)
    try:
        decoded_str = output_bytes.decode('utf-8')
        # print("[Decode] Success with utf-8") # Optional debug print
        return decoded_str
    except UnicodeDecodeError:
        # print("[Decode] Failed utf-8, trying system preferred...") # Optional debug print
        pass # 继续尝试下一个
    except Exception as e:
        print(f"Error decoding with utf-8: {e}, trying system preferred...")
        pass # 继续尝试下一个


    # 2. 尝试系统首选编码 (如 locale 设置)
    system_preferred = locale.getpreferredencoding(False)
    if system_preferred and system_preferred.lower() != 'utf-8': # 避免重复尝试 UTF-8
        try:
            decoded_str = output_bytes.decode(system_preferred, errors='replace') # 使用 replace 避免二次失败
            print(f"[Decode] Success with system preferred: {system_preferred}") # Info print
            return decoded_str
        except UnicodeDecodeError:
             print(f"[Decode] Failed system preferred '{system_preferred}', trying mbcs (Windows) or fallback...")
             pass # 继续尝试下一个
        except Exception as e:
            print(f"Error decoding with system preferred '{system_preferred}': {e}, trying mbcs (Windows) or fallback...")
            pass

    # 3. 尝试 'mbcs' (主要针对 Windows ANSI)
    if platform.system() == 'Windows':
        try:
            decoded_str = output_bytes.decode('mbcs', errors='replace') # 使用 replace 避免二次失败
            print("[Decode] Success with mbcs") # Info print
            return decoded_str
        except UnicodeDecodeError:
             print("[Decode] Failed mbcs, using final fallback latin-1...")
             pass # 继续尝试下一个
        except Exception as e:
            print(f"Error decoding with mbcs: {e}, using final fallback latin-1...")
            pass

    # 4. 最终回退 (Latin-1 通常不会失败，但可能不是预期结果)
    print("[Decode] Using final fallback: latin-1")
    return output_bytes.decode('latin-1', errors='replace')


# --- Worker Threads ---

# For AI Interaction
class ApiWorkerThread(QThread):
    api_result = Signal(str, float)
    cli_output_signal = Signal(bytes) # 发送原始字节
    cli_error_signal = Signal(bytes)  # 发送原始字节
    directory_changed_signal = Signal(str, bool)
    task_finished = Signal()

    # CWD is passed, but other config is read globally when needed
    def __init__(self, api_key, api_url, model_id, history, prompt, cwd):
        super().__init__()
        self._api_key = api_key
        self._api_url = api_url.rstrip('/') if api_url else ""
        self._model_id = model_id
        self._history = list(history)
        self._prompt = prompt
        self._cwd = cwd # CWD is specific to this task instance
        self._is_running = True
        # print(f"ApiWorkerThread initialized with CWD: {self._cwd}") # Debug print

    def stop(self):
        print("API Worker stopping...")
        self._is_running = False

    def run(self):
        try:
            # --- API Call section ---
            if not self._is_running: return
            start_time = time.time()
            raw_model_reply = "Error: API Call did not complete."
            try:
                # _send_message_to_model now reads global config for timestamp inclusion
                raw_model_reply = self._send_message_to_model()
            except Exception as api_err:
                print(f"Unhandled exception during API call: {api_err}")
                traceback.print_exc()
                raw_model_reply = f"Error: Unexpected error during API call: {api_err}"
            finally:
                end_time = time.time(); elapsed_time = end_time - start_time
                print(f"API call took: {elapsed_time:.2f} seconds")

            if not self._is_running: return

            # ================================================================= #
            # <<< MODIFICATION START: Clean reply and parse command AFTER cleaning >>>
            # ================================================================= #
            reply_for_display = raw_model_reply or ""
            reply_for_command_parsing = reply_for_display

            # 1. Remove <think> blocks for display and command parsing
            try:
                # Remove <think>...</think> blocks using a non-greedy regex
                cleaned_reply = re.sub(r"<think>.*?</think>", "", reply_for_display, flags=re.DOTALL | re.IGNORECASE).strip()
                reply_for_display = cleaned_reply
                reply_for_command_parsing = cleaned_reply # Parse command from the cleaned reply
                if raw_model_reply != cleaned_reply:
                    print("[ApiWorker] Removed <think> block from AI reply.")
            except Exception as clean_err:
                print(f"Warning: Error cleaning <think> blocks from reply: {clean_err}")
                # Fallback: Use the original reply if cleaning fails
                reply_for_display = raw_model_reply or ""
                reply_for_command_parsing = reply_for_display

            # 2. Emit the (potentially cleaned) result for display
            if self._is_running:
                 try:
                     self.api_result.emit(reply_for_display, elapsed_time)
                 except RuntimeError as e:
                     print(f"Warning: Could not emit api_result signal: {e}")

            # 3. Parse the cleaned reply for the command to execute
            command_to_run = None
            if reply_for_command_parsing and isinstance(reply_for_command_parsing, str):
                try:
                    # Use the cleaned reply for command extraction
                    command_match = re.search(r"<cmd>\s*(.*?)\s*</cmd>", reply_for_command_parsing, re.DOTALL | re.IGNORECASE)
                    if command_match:
                        command_to_run = command_match.group(1).strip()
                    if command_to_run:
                        print(f"AI Suggested Command Extracted (from cleaned reply): '{command_to_run}'")
                    else:
                        print("No <cmd> tag found or tag was empty in cleaned AI reply.")
                        command_to_run = None
                except Exception as e:
                    print(f"Error parsing command tag from cleaned reply: {e}")
                    if self._is_running:
                        try:
                            self.cli_error_signal.emit(f"Error parsing command tag: {e}".encode('utf-8')) # Encode error message
                        except RuntimeError as sig_e:
                             print(f"Warning: Could not emit command parse error signal: {sig_e}")

            elif reply_for_command_parsing:
                 print(f"Warning: Cleaned AI reply for parsing was not a string: {type(reply_for_command_parsing)}")
            else:
                 print("Cleaned AI reply for parsing was empty or None.")

            # ================================================================= #
            # <<< MODIFICATION END >>>
            # ================================================================= #


            # --- Command Execution (using command_to_run extracted from cleaned reply) ---
            if command_to_run and self._is_running:
                print(f"Executing AI suggested command (from cleaned reply).")
                try: self._execute_command(command_to_run)
                except Exception as exec_err:
                    print(f"Unhandled exception during command execution: {exec_err}")
                    traceback.print_exc()
                    if self._is_running:
                        try:
                             self.cli_error_signal.emit(f"Error: Unexpected error executing command: {exec_err}".encode('utf-8')) # Encode error message
                        except RuntimeError as sig_e:
                             print(f"Warning: Could not emit execution error signal: {sig_e}")
            elif not command_to_run and self._is_running:
                 print("No command to execute (based on cleaned reply). Finishing task.")

        finally:
            if self._is_running:
                print("API Worker emitting task_finished.")
                try: self.task_finished.emit()
                except RuntimeError as e: print(f"Warning: Could not emit task_finished signal: {e}")
            else: print("API Worker stopped before finishing.")

    def _send_message_to_model(self):
        # Reads API Key, URL, Model ID from instance variables
        # Reads INCLUDE_TIMESTAMP_IN_PROMPT from global config
        if not self._api_key or not self._api_url or not self._model_id:
             return "Error: API configuration missing."
        headers = { "Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}" }
        url = f"{self._api_url}/v1/chat/completions"

        os_name = platform.system()
        shell_type = "PowerShell on Windows" if os_name == "Windows" else ("Bash/Zsh on macOS" if os_name == "Darwin" else "Bash/Shell on Linux")

        # <<< MODIFICATION START: Construct timestamp string conditionally >>>
        timestamp_info = ""
        if config.INCLUDE_TIMESTAMP_IN_PROMPT:
            try:
                now = datetime.datetime.now()
                timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
                timestamp_info = f"The current date and time is: {timestamp_str}. "
            except Exception as dt_err:
                print(f"Warning: Could not format timestamp: {dt_err}")
        # <<< MODIFICATION END >>>

        # <<< MODIFICATION START: Include timestamp_info in system_message >>>
        # --- System Message - Instruct AI to potentially use <think> but primarily use <cmd> ---
        # Note: Explicitly telling the AI *not* to use <think> might be counter-productive.
        # Instead, we rely on post-processing to remove it. We keep the instructions for <cmd>.
        system_message = (f"You are an AI assistant designed to help execute commands in a {shell_type} terminal. "
                          f"The user's current working directory is: '{self._cwd}'. "
                          f"{timestamp_info}" # Timestamp info added here
                          f"Your primary task is to provide executable commands based on the user's request. "
                          f"You MUST enclose the *final, complete, and executable* command within <cmd> and </cmd> tags. "
                          # Removed the mention of <think> here, as we handle it via cleaning.
                          f"Example: If the user asks to list files, respond with '<cmd>ls -l</cmd>' (Linux/Mac) or '<cmd>Get-ChildItem -Path .</cmd>' (Windows). "
                          f"Do not add explanations outside the <cmd> tags if the primary goal is just the command. Ensure the command syntax is correct for the target shell ({shell_type}). "
                          f"You may receive additional context labeled '--- 当前 CLI 输出 ---' before the user's final prompt; use this context to inform your command generation.")
        # <<< MODIFICATION END >>>

        messages = [{"role": "system", "content": system_message}]
        for role, message in self._history:
            # Clean model replies from previous <cmd> tags AND <think> tags before sending back
            cleaned_message = message
            if role.lower() != "user": # Keep user messages as is (might include context)
                # Remove <think> blocks first
                cleaned_message = re.sub(r"<think>.*?</think>", "", message, flags=re.DOTALL | re.IGNORECASE).strip()
                # Then remove <cmd> blocks
                cleaned_message = re.sub(r"<cmd>.*?</cmd>", "", cleaned_message, flags=re.DOTALL | re.IGNORECASE).strip()

            # Don't add empty messages (e.g., if model reply only contained tags)
            if not cleaned_message:
                continue

            # Map roles correctly ('system' handled above, others are user/assistant)
            api_role = "user" if role.lower() == "user" else "assistant"
            messages.append({"role": api_role, "content": cleaned_message})

        # print(f"Sending messages to API: {messages}") # Debug print

        session = requests.Session()
        if URLLIB3_RETRY_AVAILABLE:
            try:
                retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["POST"]); adapter = HTTPAdapter(max_retries=retry_strategy); session.mount("https://", adapter); session.mount("http://", adapter)
            except Exception as e: print(f"Warning: Could not configure requests retries: {e}")
        try:
            payload = { "model": self._model_id, "messages": messages, "max_tokens": 1000, "temperature": 0.7 };
            response = session.post(url, headers=headers, json=payload, timeout=90)
            reply_text = "Error: API call failed or did not produce a response."; data = None; api_call_successful = False
            if response is not None:
                if response.ok:
                    try: data = response.json(); api_call_successful = True
                    except json.JSONDecodeError as e: reply_text = f"Error: Could not decode API response (Status: {response.status_code})"
                else:
                    reply_text = f"Error: API request failed with status {response.status_code}."; err_msg = ""
                    try: err_data = response.json(); err_msg = str(err_data.get('error', err_data.get('message', response.text[:200])))
                    except Exception: err_msg = response.text[:200]
                    reply_text += f" Details: {err_msg}"
            if api_call_successful and data:
                reply_text = "Error: Could not parse reply from received data."
                if 'choices' in data and data['choices']:
                    choice = data['choices'][0]; finish_reason = choice.get('finish_reason', 'N/A')
                    if 'message' in choice and 'content' in choice['message']: reply_text = choice['message']['content'].strip()
                    elif 'text' in choice: reply_text = choice['text'].strip()
                    if finish_reason == 'length': reply_text += "\n[Warning: Output may be truncated]"
                elif 'error' in data: reply_text = f"Error from API: {data['error'].get('message', json.dumps(data['error']))}"
            if not isinstance(reply_text, str): reply_text = str(reply_text)
            return reply_text
        except requests.exceptions.Timeout: return "Error: API request timed out."
        except requests.exceptions.SSLError as e: return f"Error: SSL verification failed: {e}."
        except requests.exceptions.RequestException as e: status_code = e.response.status_code if e.response is not None else "N/A"; return f"Error: API request failed ({status_code}): {e}"
        except Exception as e:
            print(f"Unhandled Exception in _send_message_to_model: {e}")
            traceback.print_exc()
            return f"Error during API call ({type(e).__name__}): {e}"

    def _execute_command(self, command):
        """Executes the given command in a subprocess using the appropriate shell, capturing raw bytes."""
        if not self._is_running: print("Command execution skipped: Worker stopped."); return

        os_name = platform.system()
        exec_prefix = "PS>" if os_name == "Windows" else ("% >" if os_name == "Darwin" else "$>")

        status_message = f"Model: {exec_prefix} {command}"
        if self._is_running:
            try: self.cli_output_signal.emit(status_message.encode('utf-8')) # Echo command as utf-8 bytes
            except RuntimeError as e: print(f"Warning: Could not emit AI command echo signal: {e}"); return

        if command.strip().lower().startswith('cd '):
            original_dir = self._cwd
            try:
                path_part = command.strip()[3:].strip()
                if not path_part or path_part == '~': target_dir = os.path.expanduser("~")
                else:
                    if len(path_part) >= 2 and path_part[0] == path_part[-1] and path_part[0] in ('"', "'"): path_part = path_part[1:-1]
                    target_dir = os.path.expanduser(path_part)
                    if not os.path.isabs(target_dir): target_dir = os.path.abspath(os.path.join(self._cwd, target_dir))
                target_dir = os.path.normpath(target_dir)
                if os.path.isdir(target_dir):
                    self._cwd = target_dir
                    if self._is_running:
                        try: self.directory_changed_signal.emit(self._cwd, False) # False for AI command
                        except RuntimeError as e: print(f"Warning: Could not emit directory changed signal: {e}")
                else:
                    error_msg = f"Error: Directory not found: '{target_dir}' (Resolved from '{path_part}')"
                    if self._is_running:
                        try: self.cli_error_signal.emit(error_msg.encode('utf-8')) # Encode error message
                        except RuntimeError as e: print(f"Warning: Could not emit cd error signal: {e}")
            except Exception as e:
                error_msg = f"Error processing 'cd' command: {e}"
                if self._is_running:
                    try: self.cli_error_signal.emit(error_msg.encode('utf-8')) # Encode error message
                    except RuntimeError as e: print(f"Warning: Could not emit cd processing error signal: {e}")
        else:
            try:
                run_args = None; use_shell = False; creationflags = 0
                if os_name == "Windows":
                    try:
                        ps_command_safe_no_progress = f"$ProgressPreference = 'SilentlyContinue'; try {{ {command} }} catch {{ Write-Error $_; exit 1 }}"
                        encoded_bytes = ps_command_safe_no_progress.encode('utf-16le'); encoded_ps_command = base64.b64encode(encoded_bytes).decode('ascii')
                        run_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_ps_command]
                        use_shell = False; creationflags = subprocess.CREATE_NO_WINDOW
                    except Exception as encode_err:
                         if self._is_running:
                             try: self.cli_error_signal.emit(f"Error encoding command for PowerShell: {encode_err}".encode('utf-8'))
                             except RuntimeError as e: print(f"Warning: Could not emit encoding error signal: {e}")
                         return
                else:
                    shell_path = os.environ.get("SHELL", "/bin/sh")
                    run_args = [shell_path, "-c", command]
                    use_shell = False; creationflags = 0
                if run_args is None: return
                print(f"Executing in CWD '{self._cwd}': {run_args}")
                result = subprocess.run( run_args, shell=use_shell, capture_output=True, cwd=self._cwd, timeout=120, check=False, creationflags=creationflags )
                if not self._is_running: print("Command execution finished, but worker was stopped."); return

                # Emit raw bytes directly
                if result.stdout and self._is_running:
                    try: self.cli_output_signal.emit(result.stdout)
                    except RuntimeError as e: print(f"Warning: Could not emit stdout signal: {e}")
                stderr_bytes = result.stderr
                is_clixml = False
                if stderr_bytes and self._is_running:
                    if os_name == "Windows":
                        try:
                            if stderr_bytes.strip().startswith(b"#< CLIXML"): is_clixml = True
                        except Exception: pass
                    if not is_clixml:
                        try: self.cli_error_signal.emit(stderr_bytes)
                        except RuntimeError as e: print(f"Warning: Could not emit stderr signal: {e}")

                print(f"Command '{command}' finished with exit code: {result.returncode}")
                if result.returncode != 0 and self._is_running:
                     emitted_stderr_meaningful = stderr_bytes and not is_clixml
                     # Decode *only* for the check, not for emission
                     stderr_str_for_check = _decode_output(stderr_bytes) if emitted_stderr_meaningful else ""
                     if not emitted_stderr_meaningful or str(result.returncode) not in stderr_str_for_check:
                         exit_msg = f"Command exited with code: {result.returncode}"
                         try: self.cli_error_signal.emit(exit_msg.encode('utf-8')) # Encode exit code message
                         except RuntimeError as e: print(f"Warning: Could not emit exit code signal: {e}")
            except subprocess.TimeoutExpired:
                timeout_msg = f"Error: Command '{command}' timed out after 120 seconds."
                if self._is_running:
                    try: self.cli_error_signal.emit(timeout_msg.encode('utf-8')) # Encode timeout message
                    except RuntimeError as e: print(f"Warning: Could not emit timeout signal: {e}")
            except FileNotFoundError:
                cmd_name = run_args[0] if isinstance(run_args, list) else command.split()[0]
                fnf_msg = f"Error: Command not found: '{cmd_name}'. Check PATH or command spelling."
                if self._is_running:
                    try: self.cli_error_signal.emit(fnf_msg.encode('utf-8')) # Encode FNF message
                    except RuntimeError as e: print(f"Warning: Could not emit FileNotFoundError signal: {e}")
            except Exception as e:
                exec_err_msg = f"Error executing command '{command}': {type(e).__name__} - {e}"
                print(f"Unhandled Exception in _execute_command: {e}")
                traceback.print_exc()
                if self._is_running:
                    try: self.cli_error_signal.emit(exec_err_msg.encode('utf-8')) # Encode error message
                    except RuntimeError as sig_e: print(f"Warning: Could not emit execution error signal: {sig_e}")

# For Manual Command Execution
class ManualCommandThread(QThread):
    cli_output_signal = Signal(bytes) # 发送原始字节
    cli_error_signal = Signal(bytes)  # 发送原始字节
    directory_changed_signal = Signal(str, bool)
    command_finished = Signal()

    def __init__(self, command, cwd):
        super().__init__()
        self._command = command
        self._cwd = cwd
        self._is_running = True
        self._process = None

    def stop(self):
        print("Manual Command Worker stopping...")
        self._is_running = False
        process_to_stop = self._process
        if process_to_stop and process_to_stop.poll() is None:
            print(f"Attempting to terminate manual command process PID: {process_to_stop.pid}...")
            try:
                if platform.system() == "Windows":
                    # Use CREATE_NEW_PROCESS_GROUP in Popen and taskkill /T /F to kill the whole tree
                    subprocess.run(['taskkill', '/PID', str(process_to_stop.pid), '/T', '/F'], check=False, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    import signal
                    os.killpg(os.getpgid(process_to_stop.pid), signal.SIGKILL) # Use SIGKILL directly for faster termination on stop request
                process_to_stop.wait(timeout=0.5)
                print("Process terminated or force killed.")
            except (subprocess.TimeoutExpired, ProcessLookupError):
                 print("Process likely already terminated.")
            except Exception as e: print(f"Error during process termination: {e}")
        else: print("Manual command process not running or already stopped.")
        self._process = None

    def run(self):
        stdout_thread = None; stderr_thread = None; stderr_lines = []
        process_return_code = None
        try:
            if not self._is_running: return
            command = self._command.strip()
            if not command: return

            # Handle 'cd' command directly for manual input
            if command.strip().lower().startswith('cd '):
                original_dir = self._cwd
                try:
                    path_part = command.strip()[3:].strip()
                    if not path_part or path_part == '~': target_dir = os.path.expanduser("~")
                    else:
                        # Remove quotes if present
                        if len(path_part) >= 2 and path_part[0] == path_part[-1] and path_part[0] in ('"', "'"):
                            path_part = path_part[1:-1]
                        target_dir = os.path.expanduser(path_part) # Expand ~
                        # Resolve relative paths
                        if not os.path.isabs(target_dir):
                            target_dir = os.path.abspath(os.path.join(self._cwd, target_dir))
                    target_dir = os.path.normpath(target_dir) # Normalize path separators

                    if os.path.isdir(target_dir):
                        self._cwd = target_dir # Update internal CWD state for the worker
                        if self._is_running:
                            try: self.directory_changed_signal.emit(self._cwd, True) # True for manual command
                            except RuntimeError as e: print(f"Warning: Could not emit directory changed signal: {e}")
                    else:
                        error_msg = f"Error: Directory not found: '{target_dir}' (Resolved from '{path_part}')"
                        if self._is_running:
                             try: self.cli_error_signal.emit(error_msg.encode('utf-8')) # Encode error
                             except RuntimeError as e: print(f"Warning: Could not emit cd error signal: {e}")
                except Exception as e:
                    error_msg = f"Error processing 'cd' command: {e}"
                    if self._is_running:
                        try: self.cli_error_signal.emit(error_msg.encode('utf-8')) # Encode error
                        except RuntimeError as e: print(f"Warning: Could not emit cd processing error signal: {e}")
                # 'cd' command execution finishes here for Manual worker
                return # Important: return after handling cd

            # --- Execute other commands ---
            run_args = None; use_shell = False; creationflags = 0
            stdout_pipe = subprocess.PIPE; stderr_pipe = subprocess.PIPE
            preexec_fn = None; os_name = platform.system()
            if os_name == "Windows":
                try:
                    # Still use encoded command for safety/escaping
                    ps_command_safe_no_progress = f"$ProgressPreference = 'SilentlyContinue'; try {{ {command} }} catch {{ Write-Error $_; exit 1 }}"
                    encoded_bytes = ps_command_safe_no_progress.encode('utf-16le'); encoded_ps_command = base64.b64encode(encoded_bytes).decode('ascii')
                    run_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_ps_command]
                    use_shell = False; creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP # Added CREATE_NEW_PROCESS_GROUP
                except Exception as encode_err:
                    if self._is_running:
                        try: self.cli_error_signal.emit(f"Error encoding command for PowerShell: {encode_err}".encode('utf-8'))
                        except RuntimeError as e: print(f"Warning: Could not emit encoding error signal: {e}")
                    return
            else:
                shell_path = os.environ.get("SHELL", "/bin/sh")
                # For direct execution, pass the command string to the shell's -c option
                run_args = [shell_path, "-c", command]; use_shell = False; creationflags = 0; preexec_fn = os.setsid # Use os.setsid for process group on Unix-like
            if run_args is None: return
            print(f"Executing manually in CWD '{self._cwd}': {run_args}")
            try:
                 # Start the process using Popen for streaming output
                 self._process = subprocess.Popen(run_args, shell=use_shell,
                                                  stdout=stdout_pipe, stderr=stderr_pipe,
                                                  cwd=self._cwd,
                                                  creationflags=creationflags,
                                                  bufsize=0, # Use unbuffered IO for pipes
                                                  preexec_fn=preexec_fn) # setsid for Unix
            except FileNotFoundError:
                 cmd_name = run_args[0] # First element is usually the executable
                 fnf_msg = f"Error: Command not found: '{cmd_name}'. Check PATH or command spelling."
                 if self._is_running:
                     try: self.cli_error_signal.emit(fnf_msg.encode('utf-8')) # Encode error
                     except RuntimeError as e: print(f"Warning: Could not emit FileNotFoundError signal: {e}")
                 return # Stop execution if command not found
            except Exception as popen_err:
                 popen_err_msg = f"Error starting command '{command}': {type(popen_err).__name__} - {popen_err}"
                 print(f"Unhandled Exception during Popen: {popen_err}")
                 traceback.print_exc()
                 if self._is_running:
                     try: self.cli_error_signal.emit(popen_err_msg.encode('utf-8')) # Encode error
                     except RuntimeError as sig_e: print(f"Warning: Could not emit Popen error signal: {sig_e}")
                 return # Stop if Popen fails

            # Stream output if process started successfully
            if self._process:
                # Inner class for stream reading within the thread
                class StreamWorker(QObject):
                     finished = Signal(); output_ready = Signal(bytes)
                     def __init__(self, stream, stop_flag_func, line_list=None, filter_clixml=False):
                         super().__init__(); self.stream = stream; self.stop_flag_func = stop_flag_func; self.line_list = line_list; self.filter_clixml = filter_clixml and platform.system() == "Windows"
                     def run(self):
                         try:
                             while not self.stop_flag_func():
                                 try:
                                     # Use os.read for potentially less blocking behavior on the raw FD
                                     chunk = os.read(self.stream.fileno(), 4096) # Read up to 4KB chunks
                                     if not chunk: break # End of stream
                                     if not self.stop_flag_func(): # Double check stop flag after read
                                         emit_chunk = True
                                         # Append raw bytes to list if needed (for stderr check later)
                                         if self.line_list is not None: self.line_list.append(chunk)
                                         # Filter CLIXML only if requested (basic check)
                                         if self.filter_clixml:
                                             try:
                                                  if chunk.strip().startswith(b"#< CLIXML"): emit_chunk = False
                                             except Exception: pass # Ignore errors during filtering check
                                         # Emit the chunk if not filtered and worker still running
                                         if emit_chunk:
                                              try: self.output_ready.emit(chunk)
                                              except RuntimeError: break # Stop if signal emission fails (e.g., main window closed)
                                 except BlockingIOError: # Expected if no data is ready on non-blocking read
                                     QThread.msleep(10) # Small sleep to yield CPU
                                     continue
                                 except (OSError, ValueError): break # Stream likely closed
                                 except Exception as e: print(f"Unexpected error in StreamWorker loop for FD {self.stream.fileno()}: {e}"); traceback.print_exc(); break
                         finally:
                             try: self.stream.close() # Ensure stream is closed
                             except Exception: pass
                             try: self.finished.emit() # Signal completion
                             except RuntimeError: pass # Ignore if receiver is gone

                # Setup and start threads for stdout/stderr
                if self._process.stdout:
                     stdout_thread = QThread(); stdout_worker = StreamWorker(self._process.stdout, lambda: not self._is_running); stdout_worker.output_ready.connect(self.cli_output_signal.emit); stdout_worker.moveToThread(stdout_thread); stdout_worker.finished.connect(stdout_thread.quit); stdout_worker.finished.connect(stdout_worker.deleteLater); stdout_thread.finished.connect(stdout_thread.deleteLater); stdout_thread.started.connect(stdout_worker.run); stdout_thread.start()
                if self._process.stderr:
                     stderr_thread = QThread(); stderr_worker = StreamWorker(self._process.stderr, lambda: not self._is_running, stderr_lines, filter_clixml=True); stderr_worker.output_ready.connect(self.cli_error_signal.emit); stderr_worker.moveToThread(stderr_thread); stderr_worker.finished.connect(stderr_thread.quit); stderr_worker.finished.connect(stderr_worker.deleteLater); stderr_thread.finished.connect(stderr_thread.deleteLater); stderr_thread.started.connect(stderr_worker.run); stderr_thread.start()

                # Wait for process completion while worker is running
                process_ref = self._process # Local reference for safety
                if process_ref:
                    try:
                         while process_ref.poll() is None and self._is_running: QThread.msleep(50) # Poll periodically
                         if self._is_running: process_return_code = process_ref.poll() # Get final code if worker still running
                         else: process_return_code = process_ref.poll(); print("Process poll after stop signal.")
                    except Exception as wait_err: print(f"Error waiting for process poll: {wait_err}"); process_return_code = -1 if self._is_running else process_return_code

                # Ensure reader threads finish before proceeding
                if stdout_thread: stdout_thread.quit(); stdout_thread.wait(200) # Wait briefly for thread cleanup
                if stderr_thread: stderr_thread.quit(); stderr_thread.wait(200)
                self._process = None # Clear process reference now it has finished

                # Handle non-zero exit code if worker is still running
                if process_return_code is not None:
                     print(f"Manual command '{command}' finished with exit code: {process_return_code}")
                     if process_return_code != 0 and self._is_running:
                          # Check if the exit code was likely already in stderr output
                          stderr_full_output_bytes = b"".join(stderr_lines); emitted_any_stderr = bool(stderr_full_output_bytes)
                          stderr_str_for_check = _decode_output(stderr_full_output_bytes) if emitted_any_stderr else ""
                          if not emitted_any_stderr or str(process_return_code) not in stderr_str_for_check:
                               exit_msg = f"Command exited with code: {process_return_code}"
                               try: self.cli_error_signal.emit(exit_msg.encode('utf-8')) # Encode exit code message
                               except RuntimeError as e: print(f"Warning: Could not emit exit code signal: {e}")
                elif self._is_running: print("Process finished or was stopped without a return code available.")
            else: print("Process reference was None after Popen, cannot proceed.")

        except Exception as run_err:
            print(f"Unhandled error in ManualCommandThread run: {run_err}")
            traceback.print_exc()
            if self._is_running:
                 try: self.cli_error_signal.emit(f"Unexpected thread error: {run_err}".encode('utf-8')) # Encode error
                 except RuntimeError as sig_e: print(f"Warning: Could not emit thread error signal: {sig_e}")
        finally:
            # Final cleanup check in case of unexpected error exit
            if self._process and self._process.poll() is None:
                if self._is_running: print("Forcing stop due to unexpected exit from run loop.");
                self.stop() # Attempt to kill any potentially lingering process
            if stdout_thread and stdout_thread.isRunning(): stdout_thread.quit(); stdout_thread.wait(100)
            if stderr_thread and stderr_thread.isRunning(): stderr_thread.quit(); stderr_thread.wait(100)
            self._process = None # Ensure cleared

            # Emit final signal ONLY if worker wasn't stopped externally
            if self._is_running:
                print("Manual Worker emitting command_finished.")
                try: self.command_finished.emit()
                except RuntimeError as e: print(f"Warning: Could not emit command_finished signal: {e}")
            else: print("Manual command worker stopped before emitting final finished signal.")