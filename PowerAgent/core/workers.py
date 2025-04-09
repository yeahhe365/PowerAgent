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
# <<< MODIFICATION START: Added QObject to the import >>>
from PySide6.QtCore import QThread, Signal, QObject
# <<< MODIFICATION END >>>
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
    api_result = Signal(str, float)
    cli_output_signal = Signal(bytes)
    cli_error_signal = Signal(bytes)
    directory_changed_signal = Signal(str, bool)
    task_finished = Signal()

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

        # Determine shell prefix based on OS for display
        exec_prefix = "PS>" if platform.system() == "Windows" else "$>"
        # <<< MODIFICATION: Changed "AI Executing" to "Model" >>>
        status_message = f"Model: {exec_prefix} {command}"
        if self._is_running:
            self.cli_output_signal.emit(status_message.encode('utf-8'))

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
                    error_msg = f"Error: Directory not found: '{target_dir}' (Resolved from '{path_part}')"
                    if self._is_running: self.cli_error_signal.emit(error_msg.encode('utf-8'))
            except Exception as e:
                error_msg = f"Error processing 'cd' command: {e}"
                if self._is_running: self.cli_error_signal.emit(error_msg.encode('utf-8'))
                self._cwd = original_dir # Should revert CWD on error? Probably not needed as it wasn't changed.
            # --- End of cd handling ---
        else:
            # --- Subprocess execution ---
            try:
                run_args = None; use_shell = False; creationflags = 0
                # Prepare command based on OS
                if platform.system() == "Windows":
                    # Use PowerShell with Base64 encoding for safety
                    ps_command_safe = f"try {{ {command} }} catch {{ Write-Error $_; exit 1 }}"
                    try:
                        # <<< CHANGE START: Redirect PowerShell progress stream to null >>>
                        # $ProgressPreference = 'SilentlyContinue' affects the current scope
                        ps_command_safe_no_progress = f"$ProgressPreference = 'SilentlyContinue'; try {{ {command} }} catch {{ Write-Error $_; exit 1 }}"
                        encoded_bytes = ps_command_safe_no_progress.encode('utf-16le'); encoded_ps_command = base64.b64encode(encoded_bytes).decode('ascii')
                        # <<< CHANGE END >>>
                        run_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_ps_command]
                        use_shell = False; creationflags = subprocess.CREATE_NO_WINDOW
                    except Exception as encode_err:
                         if self._is_running: self.cli_error_signal.emit(f"Error encoding command for PowerShell: {encode_err}".encode('utf-8'))
                         return
                else: # Linux/macOS - use default shell
                    run_args = command # Pass command string directly to shell
                    use_shell = True
                    creationflags = 0 # Not applicable

                if run_args is None: return
                print(f"Executing in CWD '{self._cwd}': {run_args}")
                result = subprocess.run( run_args, shell=use_shell, capture_output=True, cwd=self._cwd, timeout=120, check=False, creationflags=creationflags )

                if not self._is_running: print("Command execution finished, but worker was stopped."); return

                if result.stdout and self._is_running:
                    self.cli_output_signal.emit(result.stdout)

                # <<< CHANGE START: Filter stderr bytes for CLIXML before emitting >>>
                stderr_bytes = result.stderr
                if stderr_bytes and self._is_running:
                    is_clixml = False
                    if platform.system() == "Windows":
                        try:
                            # Basic check on bytes before emitting
                            if stderr_bytes.strip().startswith(b"#< CLIXML"):
                                is_clixml = True
                                print("Filtered CLIXML progress message from stderr bytes (API Worker).")
                        except Exception: pass # Ignore decoding errors for this check

                    if not is_clixml:
                        self.cli_error_signal.emit(stderr_bytes)
                # <<< CHANGE END >>>

                print(f"Command '{command}' finished with exit code: {result.returncode}")
                # Append exit code message only if non-zero AND stderr wasn't already emitted (or was filtered)
                if result.returncode != 0 and self._is_running:
                     # Check if we emitted *any* non-clixml stderr
                     emitted_stderr = stderr_bytes and not is_clixml
                     # Decode emitted stderr to check if return code is already present
                     stderr_str_for_check = _decode_output(stderr_bytes) if emitted_stderr else ""
                     if not emitted_stderr or str(result.returncode) not in stderr_str_for_check:
                         self.cli_error_signal.emit(f"Command exited with code: {result.returncode}".encode('utf-8'))


            except subprocess.TimeoutExpired:
                if self._is_running: self.cli_error_signal.emit(f"Error: Command '{command}' timed out after 120 seconds.".encode('utf-8'))
            except FileNotFoundError:
                if self._is_running:
                    cmd_name = run_args[0] if isinstance(run_args, list) and platform.system() == "Windows" else command.split()[0]
                    self.cli_error_signal.emit(f"Error: Command not found: '{cmd_name}'. Check PATH or command spelling.".encode('utf-8'))
            except Exception as e:
                if self._is_running:
                    import traceback; traceback.print_exc()
                    self.cli_error_signal.emit(f"Error executing command '{command}': {type(e).__name__} - {e}".encode('utf-8'))
            # --- End Subprocess execution ---


# For Manual Command Execution
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
        self._process = None

    def stop(self):
        # --- Unchanged stop logic ---
        print("Manual Command Worker stopping...")
        self._is_running = False
        if self._process and self._process.poll() is None:
            print("Attempting to terminate manual command process...")
            try:
                if platform.system() == "Windows":
                    # Graceful termination first
                    subprocess.run(['taskkill', '/PID', str(self._process.pid), '/T'], check=False, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    self._process.terminate() # Fallback
                else:
                    import signal
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM) # Send TERM to process group
                    self._process.terminate() # Fallback for main process
                self._process.wait(timeout=1) # Wait briefly for termination
                print("Process terminated.")
            except subprocess.TimeoutExpired:
                print("Process termination timed out, attempting kill...")
                try:
                    if platform.system() == "Windows":
                         subprocess.run(['taskkill', '/PID', str(self._process.pid), '/T', '/F'], check=False, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                         self._process.kill() # Fallback
                    else:
                        import signal
                        os.killpg(os.getpgid(self._process.pid), signal.SIGKILL) # Send KILL to process group
                        self._process.kill() # Fallback for main process
                    self._process.wait(timeout=1) # Wait after kill
                    print("Process killed.")
                except Exception as kill_err:
                    print(f"Error during process kill: {kill_err}")
            except ProcessLookupError:
                print("Process already terminated.")
            except Exception as e:
                print(f"Error terminating/killing process: {e}")
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
                    # Remove outer quotes if present (handle both ' and ")
                    if len(path_part) >= 2 and path_part[0] == path_part[-1] and path_part[0] in ('"', "'"):
                        path_part = path_part[1:-1]
                    target_dir = os.path.expanduser(path_part) # Handles ~ within paths too
                    # Resolve relative paths based on current worker directory
                    if not os.path.isabs(target_dir):
                        target_dir = os.path.abspath(os.path.join(self._cwd, target_dir))

                # Normalize the path for comparison and storage
                target_dir = os.path.normpath(target_dir)

                if os.path.isdir(target_dir):
                    self._cwd = target_dir # Update worker's CWD
                    if self._is_running: self.directory_changed_signal.emit(self._cwd, True) # Emit signal with True for manual
                else:
                    error_msg = f"Error: Directory not found: '{target_dir}' (Resolved from '{path_part}')"
                    if self._is_running: self.cli_error_signal.emit(error_msg.encode('utf-8'))
            except Exception as e:
                error_msg = f"Error processing 'cd' command: {e}"
                if self._is_running: self.cli_error_signal.emit(error_msg.encode('utf-8'))
             # --- End of cd handling ---
        else:
            # --- Subprocess execution ---
            stdout_thread = None # Define outside try block
            stderr_thread = None # Define outside try block
            stderr_lines = [] # Accumulate all stderr bytes for final check
            try:
                run_args = None; use_shell = False; creationflags = 0
                stdout_pipe = subprocess.PIPE; stderr_pipe = subprocess.PIPE
                preexec_fn = None # For setting process group on Unix

                if platform.system() == "Windows":
                    # <<< CHANGE START: Redirect PowerShell progress stream to null >>>
                    ps_command_safe_no_progress = f"$ProgressPreference = 'SilentlyContinue'; try {{ {command} }} catch {{ Write-Error $_; exit 1 }}"
                    try:
                        encoded_bytes = ps_command_safe_no_progress.encode('utf-16le'); encoded_ps_command = base64.b64encode(encoded_bytes).decode('ascii')
                        run_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_ps_command]
                        use_shell = False; creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                    except Exception as encode_err:
                        if self._is_running: self.cli_error_signal.emit(f"Error encoding command for PowerShell: {encode_err}".encode('utf-8'))
                        if self._is_running: self.command_finished.emit()
                        return
                    # <<< CHANGE END >>>
                else: # Linux/macOS
                    shell_path = os.environ.get("SHELL", "/bin/sh")
                    run_args = [shell_path, "-c", command] # Execute command within the shell
                    use_shell = False # We are explicitly calling the shell
                    creationflags = 0
                    preexec_fn = os.setsid # Create new session and process group

                if run_args is None:
                    if self._is_running: self.command_finished.emit()
                    return

                print(f"Executing manually in CWD '{self._cwd}': {run_args}")
                # Use Popen for streaming
                self._process = subprocess.Popen(
                    run_args,
                    shell=use_shell,
                    stdout=stdout_pipe,
                    stderr=stderr_pipe,
                    cwd=self._cwd,
                    creationflags=creationflags,
                    bufsize=0, # Use 0 for unbuffered binary IO with os.read
                    preexec_fn=preexec_fn # Set process group on Unix
                )

                # --- Stream Output ---
                if self._process:
                    # Define functions to read streams and emit signals
                    def read_stream(stream, signal_emitter):
                         try:
                              # Use os.read for potentially better responsiveness than readline
                              while self._is_running:
                                  try:
                                      # Read a chunk (adjust size as needed)
                                      chunk = os.read(stream.fileno(), 1024)
                                      if not chunk: break # End of stream
                                      if self._is_running:
                                          signal_emitter(chunk)
                                  except OSError as e: # Handle potential errors like closed pipe
                                       # print(f"Read error on stream {stream.fileno()}: {e}") # Reduce noise
                                       break
                                  except ValueError as e: # Handle "negative file descriptor" after close
                                       # print(f"Stream {stream.fileno()} likely closed: {e}") # Reduce noise
                                       break
                         except Exception as e: # Catch other potential errors
                              print(f"Error in read_stream loop for {stream.fileno()}: {e}")
                         finally:
                              try:
                                   stream.close()
                              except Exception: pass

                    # Need a worker object for the thread
                    class StreamWorker(QObject): # QObject used here
                         def __init__(self, func, *args): super().__init__(); self.func=func; self.args=args
                         finished = Signal() # Define signal for clean thread exit coordination
                         def run(self):
                             try:
                                 self.func(*self.args)
                             finally:
                                 try:
                                      self.finished.emit() # Signal completion
                                 except RuntimeError: # Handle case where thread is already quitting
                                      pass

                    # Start threads to read stdout and stderr concurrently
                    if self._process.stdout:
                         stdout_thread = QThread()
                         stdout_worker = StreamWorker(read_stream, self._process.stdout, self.cli_output_signal.emit)
                         stdout_worker.moveToThread(stdout_thread)
                         stdout_worker.finished.connect(stdout_thread.quit)
                         stdout_worker.finished.connect(stdout_worker.deleteLater) # Cleanup worker
                         stdout_thread.finished.connect(stdout_thread.deleteLater) # Cleanup thread
                         stdout_thread.started.connect(stdout_worker.run)
                         stdout_thread.start()

                    # <<< CHANGE START: Modify read_stderr to filter CLIXML before emitting >>>
                    def read_stderr(stream, signal_emitter, line_list):
                         try:
                            while self._is_running:
                                try:
                                    chunk = os.read(stream.fileno(), 1024)
                                    if not chunk: break
                                    if self._is_running:
                                        # Always append the raw chunk for later analysis
                                        line_list.append(chunk)

                                        # Filter CLIXML before emitting the signal
                                        is_clixml = False
                                        if platform.system() == "Windows":
                                            try:
                                                # Check if the chunk contains the CLIXML marker
                                                if b"#< CLIXML" in chunk.strip():
                                                    is_clixml = True
                                                    # print("Filtered potential CLIXML chunk signal emission (Manual Worker).") # Reduce noise
                                            except Exception: pass # Ignore errors during check

                                        if not is_clixml:
                                            signal_emitter(chunk) # Emit only non-CLIXML chunks

                                except OSError as e:
                                     # print(f"Read error on stderr stream {stream.fileno()}: {e}") # Reduce noise
                                     break
                                except ValueError as e:
                                     # print(f"Stderr stream {stream.fileno()} likely closed: {e}") # Reduce noise
                                     break
                         except Exception as e:
                             print(f"Error in read_stderr loop for {stream.fileno()}: {e}")
                         finally:
                              try:
                                   stream.close()
                              except Exception: pass
                    # <<< CHANGE END >>>

                    if self._process.stderr:
                         stderr_thread = QThread()
                         stderr_worker = StreamWorker(read_stderr, self._process.stderr, self.cli_error_signal.emit, stderr_lines)
                         stderr_worker.moveToThread(stderr_thread)
                         stderr_worker.finished.connect(stderr_thread.quit)
                         stderr_worker.finished.connect(stderr_worker.deleteLater)
                         stderr_thread.finished.connect(stderr_thread.deleteLater)
                         stderr_thread.started.connect(stderr_worker.run)
                         stderr_thread.start()

                    # Wait for process and stream threads to finish
                    process_return_code = None
                    if self._process:
                        try:
                             # Wait indefinitely or until stop() is called
                             while self._process.poll() is None and self._is_running:
                                  QThread.msleep(50) # Use Qt's sleep to yield event loop
                             if self._is_running: # Process finished naturally
                                 process_return_code = self._process.poll() # Get final code
                             else: # If stop() was called
                                 process_return_code = self._process.poll() # Get code if it exited quickly after stop
                                 print("Process poll after stop signal.")
                        except Exception as wait_err:
                             print(f"Error waiting for process: {wait_err}")

                    # Ensure threads finish cleanly AFTER process wait
                    if stdout_thread: stdout_thread.quit(); stdout_thread.wait(500) # Add timeout
                    if stderr_thread: stderr_thread.quit(); stderr_thread.wait(500) # Add timeout
                    # --- End Stream Output ---


                    self._process = None # Clear process reference
                    if process_return_code is not None:
                         print(f"Manual command '{command}' finished with exit code: {process_return_code}")
                         # Append exit code message only if non-zero AND stderr didn't contain it
                         if process_return_code != 0 and self._is_running:
                              stderr_full_output_bytes = b"".join(stderr_lines) # Use accumulated bytes
                              # Don't decode here, just check if any bytes were accumulated
                              emitted_any_stderr = bool(stderr_full_output_bytes)
                              # Decode only for the string check
                              stderr_str_for_check = _decode_output(stderr_full_output_bytes) if emitted_any_stderr else ""

                              # Add exit code if:
                              # 1. No stderr was produced OR
                              # 2. Stderr was produced, but doesn't contain the exit code number
                              if not emitted_any_stderr or str(process_return_code) not in stderr_str_for_check:
                                   self.cli_error_signal.emit(f"Command exited with code: {process_return_code}".encode('utf-8'))
                    elif self._is_running:
                        # This case might happen if the process was stopped externally
                        # or Popen failed silently before the loop.
                         print("Process finished or was stopped without a return code available.")
                         # Optionally emit a generic error if this state is unexpected
                         # self.cli_error_signal.emit(f"Command '{command}' ended unexpectedly.".encode('utf-8'))

                else: print("Process reference was None after Popen.")


            except FileNotFoundError:
                if self._is_running:
                    cmd_name = run_args[0] if isinstance(run_args, list) else command.split()[0]
                    self.cli_error_signal.emit(f"Error: Command not found: '{cmd_name}'. Check PATH or command spelling.".encode('utf-8'))
            except Exception as e:
                if self._is_running:
                    import traceback; traceback.print_exc()
                    self.cli_error_signal.emit(f"Error executing command '{command}': {type(e).__name__} - {e}".encode('utf-8'))
            finally:
                # Ensure cleanup if Popen started but error occurred before wait/threads finish
                if self._process and self._process.poll() is None:
                    if self._is_running: # If error happened but worker not stopped, try stopping now
                        print("Forcing stop due to error during execution.")
                        self.stop()
                # Ensure threads are cleaned up (redundant if already done, but safe)
                if stdout_thread and stdout_thread.isRunning(): stdout_thread.quit(); stdout_thread.wait(100)
                if stderr_thread and stderr_thread.isRunning(): stderr_thread.quit(); stderr_thread.wait(100)
                self._process = None
            # --- End Subprocess execution ---

        if self._is_running: self.command_finished.emit()
        else: print("Manual command worker stopped before emitting final finished signal.")