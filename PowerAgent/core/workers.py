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
from PySide6.QtCore import QThread, Signal
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
    URLLIB3_RETRY_AVAILABLE = True
except ImportError:
    print("Warning: Failed to import Retry from urllib3.util.retry. Retries disabled.")
    URLLIB3_RETRY_AVAILABLE = False

# Helper function to decode subprocess output bytes
def _decode_output(output_bytes: bytes) -> str:
    """
    Attempts to decode bytes using the system's default ANSI code page
    ('mbcs' on Windows) first, falling back to UTF-8 if mbcs fails.
    """
    if not isinstance(output_bytes, bytes): # <<< ADDED type check for safety
        print(f"Warning: _decode_output received non-bytes type: {type(output_bytes)}. Returning as is.")
        # Attempt to convert common types or return repr
        if isinstance(output_bytes, str):
            return output_bytes # Already a string
        try:
            return str(output_bytes)
        except:
            return repr(output_bytes)

    if not output_bytes:
        return ""

    primary_encoding = 'mbcs' if platform.system() == 'Windows' else locale.getpreferredencoding(False)
    if not primary_encoding: primary_encoding = 'utf-8'
    fallback_encoding = 'utf-8' if primary_encoding != 'utf-8' else 'iso-8859-1'

    try:
        decoded_str = output_bytes.decode(primary_encoding)
        return decoded_str # Return stripped version later if needed
    except UnicodeDecodeError:
        # print(f"Decoding with '{primary_encoding}' failed, trying fallback '{fallback_encoding}'...") # Reduce noise
        try:
            decoded_str = output_bytes.decode(fallback_encoding, errors='replace')
            return decoded_str
        except Exception as e:
            print(f"Fallback decoding also failed: {e}")
            return output_bytes.decode('latin-1', errors='replace') # Keep all bytes
    except Exception as e:
        print(f"Error decoding with '{primary_encoding}': {e}, trying fallback '{fallback_encoding}'...")
        try:
            decoded_str = output_bytes.decode(fallback_encoding, errors='replace')
            return decoded_str
        except Exception as e2:
            print(f"Fallback decoding also failed: {e2}")
            return output_bytes.decode('latin-1', errors='replace')

# --- Worker Threads ---

# For AI Interaction
class ApiWorkerThread(QThread):
    # <<< MODIFIED: Signals emit bytes >>>
    api_result = Signal(str, float)
    cli_output_signal = Signal(bytes)
    cli_error_signal = Signal(bytes)
    directory_changed_signal = Signal(str, bool)
    task_finished = Signal()
    # <<< END MODIFIED >>>

    def __init__(self, api_key, api_url, model_id, history, prompt, mode, cwd):
        super().__init__()
        self._api_key = api_key
        self._api_url = api_url.rstrip('/') if api_url else ""
        self._model_id = model_id
        self._history = list(history)
        self._prompt = prompt
        self._mode = mode
        self._cwd = cwd
        self._is_running = True

    def stop(self):
        print("API Worker stopping...")
        self._is_running = False

    def run(self):
        # --- API Call section ---
        if not self._is_running: return
        start_time = time.time()
        raw_model_reply = self._send_message_to_model(self._prompt)
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"API call took: {elapsed_time:.2f} seconds")

        if not self._is_running: return
        if self._is_running: self.api_result.emit(raw_model_reply, elapsed_time) # This signal remains str

        # --- Command Parsing section ---
        command_to_run = None
        if raw_model_reply:
            try:
                command_match = re.search(r"<cmd>\s*(.*?)\s*</cmd>", raw_model_reply, re.DOTALL | re.IGNORECASE)
                if command_match: command_to_run = command_match.group(1).strip()
                if command_to_run: print(f"AI Suggested Command Extracted: '{command_to_run}'")
                else: print("No <cmd> tag found or tag was empty in AI reply."); command_to_run = None
            except Exception as e:
                print(f"Error parsing command tag: {e}")
                # <<< MODIFIED: Emit encoded error string >>>
                if self._is_running: self.cli_error_signal.emit(f"Error parsing command tag: {e}".encode('utf-8'))
        else: print("AI reply was empty.")


        if command_to_run and self._is_running:
            self._execute_command(command_to_run)
        elif not command_to_run and self._is_running:
            print("No command to execute. Finishing task.")

        if self._is_running: self.task_finished.emit()
        else: print("API Worker stopped before finishing.")

    def _send_message_to_model(self, user_prompt):
        # --- This function remains unchanged ---
        if not self._api_key or not self._api_url or not self._model_id: return "Error: API configuration missing."
        headers = { "Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}" }
        url = f"{self._api_url}/v1/chat/completions"
        system_message = (f"You are an AI assistant designed to help execute commands in a PowerShell terminal on a Windows system. The user's current working directory is: '{self._cwd}'. Your primary task is to provide executable PowerShell commands based on the user's request. You MUST enclose the *complete* and *executable* PowerShell command within <cmd> and </cmd> tags. Example: If the user asks to list files, you might respond with '<cmd>Get-ChildItem -Path .'</cmd>. Do not add explanations outside the tags if the primary goal is just the command. Ensure the command syntax is correct for PowerShell on Windows.")
        messages = [{"role": "system", "content": system_message}]
        for role, message in self._history:
            cleaned_message = message
            if role.lower() != "user": cleaned_message = re.sub(r"<cmd>.*?</cmd>", "", message, flags=re.DOTALL | re.IGNORECASE).strip()
            if not cleaned_message: continue
            api_role = "user" if role.lower() == "user" else "assistant"
            messages.append({"role": api_role, "content": cleaned_message})
        messages.append({"role": "user", "content": user_prompt})
        session = requests.Session()
        if URLLIB3_RETRY_AVAILABLE:
            try:
                retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["POST"]); adapter = HTTPAdapter(max_retries=retry_strategy); session.mount("https://", adapter); session.mount("http://", adapter)
            except Exception as e: print(f"Warning: Could not configure requests retries: {e}")
        try:
            payload = { "model": self._model_id, "messages": messages, "max_tokens": 1000, "temperature": 0.7 }; response = session.post(url, headers=headers, json=payload, timeout=90)
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
        except Exception as e: import traceback; traceback.print_exc(); return f"Error during API call ({type(e).__name__}): {e}"
        # --- End of unchanged _send_message_to_model ---


    def _execute_command(self, command):
        """Executes the given command in a subprocess using PowerShell on Windows, capturing raw bytes."""
        if not self._is_running: print("Command execution skipped: Worker stopped."); return

        exec_prefix = "PS>"
        # <<< MODIFIED: Emit encoded status message >>>
        if self._is_running: self.cli_output_signal.emit(f"AI Executing: {exec_prefix} {command}".encode('utf-8'))

        if command.strip().lower().startswith('cd '):
            # --- cd command handling ---
            original_dir = self._cwd
            try:
                path_part = command.strip()[3:].strip()
                if not path_part or path_part == '~': target_dir = os.path.expanduser("~")
                else:
                    if (path_part.startswith('"') and path_part.endswith('"')) or \
                       (path_part.startswith("'") and path_part.endswith("'")): path_part = path_part[1:-1]
                    target_dir = os.path.expanduser(path_part)
                    if not os.path.isabs(target_dir): target_dir = os.path.abspath(os.path.join(self._cwd, target_dir))
                if os.path.isdir(target_dir):
                    self._cwd = target_dir
                    if self._is_running: self.directory_changed_signal.emit(self._cwd, False) # This signal is str
                else:
                    # <<< MODIFIED: Emit encoded error message >>>
                    error_msg = f"Error: Directory not found: '{target_dir}' (Resolved from '{path_part}')"
                    if self._is_running: self.cli_error_signal.emit(error_msg.encode('utf-8'))
            except Exception as e:
                 # <<< MODIFIED: Emit encoded error message >>>
                error_msg = f"Error processing 'cd' command: {e}"
                if self._is_running: self.cli_error_signal.emit(error_msg.encode('utf-8'))
                self._cwd = original_dir # Should revert CWD on error? Probably not needed as it wasn't changed.
            # --- End of cd handling ---
        else:
            # --- Subprocess execution ---
            try:
                run_args = None; use_shell = False; creationflags = 0
                ps_command_safe = f"try {{ {command} }} catch {{ Write-Error $_; exit 1 }}"
                try:
                    encoded_bytes = ps_command_safe.encode('utf-16le'); encoded_ps_command = base64.b64encode(encoded_bytes).decode('ascii')
                    run_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_ps_command]
                    use_shell = False; creationflags = subprocess.CREATE_NO_WINDOW
                except Exception as encode_err:
                     # <<< MODIFIED: Emit encoded error message >>>
                    if self._is_running: self.cli_error_signal.emit(f"Error encoding command for PowerShell: {encode_err}".encode('utf-8'))
                    return

                if run_args is None: return
                print(f"Executing in CWD '{self._cwd}': {run_args}")
                result = subprocess.run( run_args, shell=use_shell, capture_output=True, cwd=self._cwd, timeout=120, check=False, creationflags=creationflags )

                if not self._is_running: print("Command execution finished, but worker was stopped."); return

                # <<< MODIFIED: Emit raw stdout bytes >>>
                if result.stdout and self._is_running:
                    self.cli_output_signal.emit(result.stdout)

                 # <<< MODIFIED: Emit raw stderr bytes (after potential filtering) >>>
                stderr_bytes = result.stderr
                if stderr_bytes and self._is_running:
                    # Basic CLIXML check on bytes before emitting
                    try:
                        # Quick check if it *starts* like CLIXML (might not be perfect)
                        if not stderr_bytes.strip().startswith(b"#< CLIXML"):
                             self.cli_error_signal.emit(stderr_bytes)
                        else:
                             print("Filtered potential CLIXML progress message from stderr bytes.")
                    except Exception: # If decoding for check fails, emit raw anyway
                         self.cli_error_signal.emit(stderr_bytes)


                print(f"Command '{command}' finished with exit code: {result.returncode}")
                if result.returncode != 0 and self._is_running:
                     # <<< MODIFIED: Emit encoded error message >>>
                     # Check if stderr likely contained the error already by decoding for comparison
                     stderr_str_for_check = _decode_output(stderr_bytes) if stderr_bytes else ""
                     if not stderr_str_for_check or str(result.returncode) not in stderr_str_for_check:
                         self.cli_error_signal.emit(f"Command exited with code: {result.returncode}".encode('utf-8'))

            except subprocess.TimeoutExpired:
                 # <<< MODIFIED: Emit encoded error message >>>
                if self._is_running: self.cli_error_signal.emit(f"Error: Command '{command}' timed out after 120 seconds.".encode('utf-8'))
            except FileNotFoundError:
                 # <<< MODIFIED: Emit encoded error message >>>
                if self._is_running:
                    cmd_name = run_args[0] if isinstance(run_args, list) else command.split()[0]
                    self.cli_error_signal.emit(f"Error: Command not found: '{cmd_name}'. Check PATH or command spelling.".encode('utf-8'))
            except Exception as e:
                 # <<< MODIFIED: Emit encoded error message >>>
                if self._is_running:
                    import traceback; traceback.print_exc()
                    self.cli_error_signal.emit(f"Error executing command '{command}': {type(e).__name__} - {e}".encode('utf-8'))
            # --- End Subprocess execution ---


# For Manual Command Execution
class ManualCommandThread(QThread):
    # <<< MODIFIED: Signals emit bytes >>>
    cli_output_signal = Signal(bytes)
    cli_error_signal = Signal(bytes)
    directory_changed_signal = Signal(str, bool)
    command_finished = Signal()
    # <<< END MODIFIED >>>

    def __init__(self, command, cwd):
        super().__init__()
        self._command = command
        self._cwd = cwd
        self._is_running = True
        self._process = None

    def stop(self):
        # --- Unchanged stop logic ---
        print("Manual Command Worker stopping...")
        self._is_running = False
        if self._process and self._process.poll() is None:
            print("Attempting to terminate manual command process...")
            try:
                self._process.terminate(); self._process.wait(timeout=1); print("Process terminated.")
            except subprocess.TimeoutExpired: print("Process kill..."); self._process.kill(); print("Process killed.")
            except ProcessLookupError: print("Process already terminated.")
            except Exception as e: print(f"Error terminating process: {e}")
        self._process = None

    def run(self):
        if not self._is_running: return
        command = self._command.strip()
        if not command:
            if self._is_running: self.command_finished.emit()
            return

        if command.strip().lower().startswith('cd '):
             # --- cd command handling ---
            original_dir = self._cwd
            try:
                path_part = command.strip()[3:].strip()
                if not path_part or path_part == '~': target_dir = os.path.expanduser("~")
                else:
                    if (path_part.startswith('"') and path_part.endswith('"')) or \
                       (path_part.startswith("'") and path_part.endswith("'")): path_part = path_part[1:-1]
                    target_dir = os.path.expanduser(path_part)
                    if not os.path.isabs(target_dir): target_dir = os.path.abspath(os.path.join(self._cwd, target_dir))
                if os.path.isdir(target_dir):
                    self._cwd = target_dir
                    if self._is_running: self.directory_changed_signal.emit(self._cwd, True) # This signal is str
                else:
                    # <<< MODIFIED: Emit encoded error message >>>
                    error_msg = f"Error: Directory not found: '{target_dir}' (Resolved from '{path_part}')"
                    if self._is_running: self.cli_error_signal.emit(error_msg.encode('utf-8'))
            except Exception as e:
                # <<< MODIFIED: Emit encoded error message >>>
                error_msg = f"Error processing 'cd' command: {e}"
                if self._is_running: self.cli_error_signal.emit(error_msg.encode('utf-8'))
             # --- End of cd handling ---
        else:
            # --- Subprocess execution ---
            try:
                run_args = None; use_shell = False; creationflags = 0
                ps_command_safe = f"try {{ {command} }} catch {{ Write-Error $_; exit 1 }}"
                try:
                    encoded_bytes = ps_command_safe.encode('utf-16le'); encoded_ps_command = base64.b64encode(encoded_bytes).decode('ascii')
                    run_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_ps_command]
                    use_shell = False; creationflags = subprocess.CREATE_NO_WINDOW
                except Exception as encode_err:
                    # <<< MODIFIED: Emit encoded error message >>>
                    if self._is_running: self.cli_error_signal.emit(f"Error encoding command for PowerShell: {encode_err}".encode('utf-8'))
                    if self._is_running: self.command_finished.emit()
                    return

                if run_args is None: return
                print(f"Executing manually in CWD '{self._cwd}': {run_args}")
                # Use Popen for streaming
                self._process = subprocess.Popen( run_args, shell=use_shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self._cwd, creationflags=creationflags, bufsize=1 ) # bufsize=1 might cause warning but helps streaming

                # Stream and emit stdout bytes
                if self._process.stdout:
                    for line_bytes in iter(self._process.stdout.readline, b''):
                        if not self._is_running: break
                        # <<< MODIFIED: Emit raw line_bytes >>>
                        if line_bytes and self._is_running:
                             self.cli_output_signal.emit(line_bytes)
                    if self._process and self._process.stdout: self._process.stdout.close()

                # Stream and accumulate stderr bytes
                stderr_full_output = b""
                if self._process and self._process.stderr:
                    for line_bytes in iter(self._process.stderr.readline, b''):
                        if not self._is_running: break
                        stderr_full_output += line_bytes
                    if self._process and self._process.stderr: self._process.stderr.close()

                # Emit accumulated stderr bytes (after potential filtering)
                if stderr_full_output and self._is_running:
                     # <<< MODIFIED: Emit raw stderr_full_output bytes (after potential filtering) >>>
                    try:
                        # Basic CLIXML check on bytes before emitting
                        if not stderr_full_output.strip().startswith(b"#< CLIXML"):
                             self.cli_error_signal.emit(stderr_full_output)
                        else:
                             print("Filtered potential CLIXML progress message from stderr bytes (manual command).")
                    except Exception:
                         self.cli_error_signal.emit(stderr_full_output)


                if not self._is_running: print("Manual command worker stopped before wait()."); self.stop(); return

                if self._process:
                    return_code = self._process.wait()
                    self._process = None # Clear process reference
                    print(f"Manual command '{command}' finished with exit code: {return_code}")
                    if return_code != 0 and self._is_running:
                         # <<< MODIFIED: Emit encoded error message >>>
                         # Check if stderr likely contained the error already
                         stderr_str_for_check = _decode_output(stderr_full_output) if stderr_full_output else ""
                         if not stderr_str_for_check or str(return_code) not in stderr_str_for_check:
                            self.cli_error_signal.emit(f"Command exited with code: {return_code}".encode('utf-8'))
                else: print("Process reference was None before reporting exit code.")

            except FileNotFoundError:
                 # <<< MODIFIED: Emit encoded error message >>>
                if self._is_running:
                    cmd_name = run_args[0] if isinstance(run_args, list) else command.split()[0]
                    self.cli_error_signal.emit(f"Error: Command not found: '{cmd_name}'. Check PATH or command spelling.".encode('utf-8'))
            except Exception as e:
                 # <<< MODIFIED: Emit encoded error message >>>
                if self._is_running:
                    import traceback; traceback.print_exc()
                    self.cli_error_signal.emit(f"Error executing command '{command}': {type(e).__name__} - {e}".encode('utf-8'))
            finally:
                if self._process: # Ensure cleanup if Popen started but error occurred before wait
                    try:
                        if self._process.stdout: self._process.stdout.close()
                        if self._process.stderr: self._process.stderr.close()
                        if self._process.poll() is None: self.stop() # Try to stop if still running
                    except Exception as close_err: print(f"Error closing streams/stopping process during finally block: {close_err}")
                    self._process = None
            # --- End Subprocess execution ---

        if self._is_running: self.command_finished.emit()
        else: print("Manual command worker stopped before emitting final finished signal.")