# ========================================
# 文件名: PowerAgent/core/command_executor.py
# (CORRECTED)
# ----------------------------------------
# core/command_executor.py
# -*- coding: utf-8 -*-

"""
Handles the execution of shell commands, including 'cd' and streaming output
from subprocesses using Popen and StreamWorker.
"""

import subprocess
import os
import platform
import base64
import traceback
import time # For small delays
# --- MODIFICATION START: Import typing.Callable and correct Signal type ---
from typing import Callable
# --- MODIFICATION END ---
from PySide6.QtCore import QThread, Signal, QObject # Need QThread for msleep

# Import helpers from other new modules
from .stream_handler import StreamWorker
from .worker_utils import decode_output

# --- MODIFICATION START: Correct type hints for signals and callable ---
def execute_command_streamed(
    command: str,
    cwd: str,
    stop_flag_func: Callable[[], bool], # Correct type hint for callable
    output_signal: Signal,             # Correct type hint for Signal instance
    error_signal: Signal,              # Correct type hint for Signal instance
    directory_changed_signal: Signal,  # Correct type hint for Signal instance
    is_manual_command: bool            # True if triggered manually, False if by AI
) -> tuple[str, int | None]:
# --- MODIFICATION END ---
    """
    Executes a shell command, handling 'cd' directly and streaming output
    for other commands using subprocess.Popen.

    Args:
        command: The command string to execute.
        cwd: The current working directory for execution.
        stop_flag_func: A callable that returns True if execution should stop.
        output_signal: Signal to emit stdout bytes. (Emits: bytes)
        error_signal: Signal to emit stderr bytes or error messages. (Emits: bytes)
        directory_changed_signal: Signal to emit when 'cd' successfully changes directory. (Emits: str, bool)
        is_manual_command: Passed to directory_changed_signal to indicate source.

    Returns:
        tuple: (final_cwd, exit_code)
               final_cwd: The potentially updated current working directory.
               exit_code: The integer exit code of the process, or None if not applicable (e.g., 'cd' or early exit).
    """

    current_cwd = cwd # Start with the passed CWD
    exit_code = None # Default exit code

    def _emit_error(message: str):
        """Helper to safely emit string errors via the error signal."""
        if not stop_flag_func():
            try:
                error_signal.emit(f"Error: {message}".encode('utf-8'))
            except RuntimeError as e:
                print(f"[Executor] Warning: Could not emit error signal: {e}")
            except Exception as e:
                 print(f"[Executor] Unexpected error emitting signal: {e}")

    def _emit_output_bytes(b_message: bytes, is_stderr: bool):
        """Helper to safely emit raw bytes via the correct signal."""
        if not stop_flag_func():
            target_signal = error_signal if is_stderr else output_signal
            try:
                target_signal.emit(b_message)
            except RuntimeError as e:
                 try: msg_repr = decode_output(b_message[:100]) + ('...' if len(b_message) > 100 else '')
                 except: msg_repr = repr(b_message[:100]) + ('...' if len(b_message) > 100 else '')
                 print(f"[Executor] Warning: Could not emit {'stderr' if is_stderr else 'stdout'} signal for bytes '{msg_repr}': {e}")
            except Exception as e:
                 print(f"[Executor] Unexpected error emitting signal: {e}")


    if stop_flag_func():
        print("[Executor] Execution skipped: Stop flag was set.")
        return current_cwd, exit_code

    command = command.strip()
    if not command:
        print("[Executor] Empty command received.")
        return current_cwd, exit_code

    # --- Handle 'cd' command directly ---
    if command.lower().startswith('cd '):
        original_dir = current_cwd
        try:
            path_part = command[3:].strip() # Get the part after 'cd '
            # Handle quoted paths robustly
            if len(path_part) >= 2 and path_part.startswith('"') and path_part.endswith('"'):
                 path_part = path_part[1:-1]
            elif len(path_part) >= 2 and path_part.startswith("'") and path_part.endswith("'"):
                 path_part = path_part[1:-1]

            if not path_part or path_part == '~':
                # Navigate to home directory
                target_dir = os.path.expanduser("~")
            else:
                 # Handle tilde expansion for user directories (e.g., ~user) if applicable
                 target_dir = os.path.expanduser(path_part)
                 # If the path is not absolute, join it with the current directory
                 if not os.path.isabs(target_dir):
                    target_dir = os.path.abspath(os.path.join(current_cwd, target_dir))

            # Normalize the path (e.g., resolve '..')
            target_dir = os.path.normpath(target_dir)

            if os.path.isdir(target_dir):
                current_cwd = target_dir # Update the internal CWD
                print(f"[Executor] Changed directory via 'cd' to: {current_cwd}")
                if not stop_flag_func():
                    try:
                        # Emit directory change with the correct source flag
                        directory_changed_signal.emit(current_cwd, is_manual_command)
                    except RuntimeError as e:
                        print(f"[Executor] Warning: Could not emit directory changed signal: {e}")
            else:
                error_msg = f"Directory not found: '{target_dir}' (Resolved from '{path_part}')"
                print(f"[Executor] 'cd' failed: {error_msg}")
                if not stop_flag_func(): _emit_error(error_msg)

        except Exception as e:
            error_msg = f"Error processing 'cd' command: {e}"
            print(f"[Executor] 'cd' processing error: {error_msg}")
            traceback.print_exc()
            if not stop_flag_func(): _emit_error(error_msg)

        # 'cd' command execution finishes here, return updated CWD and None exit code
        return current_cwd, None

    # --- Execute other commands using Popen ---
    process: subprocess.Popen | None = None
    stdout_thread: QThread | None = None
    stderr_thread: QThread | None = None
    stderr_lines = [] # Collect stderr chunks for later analysis
    process_pid = -1 # Store PID for logging

    try:
        run_args = None
        use_shell = False # Generally False when passing args list to Popen
        creationflags = 0
        preexec_fn = None # For setting process group on Linux/macOS
        os_name = platform.system()

        # Prepare command arguments based on OS
        if os_name == "Windows":
            try:
                # Use PowerShell with EncodedCommand for complex commands, disable progress bar
                ps_command_safe_no_progress = f"$ProgressPreference = 'SilentlyContinue'; try {{ {command} }} catch {{ Write-Error $_; exit 1 }}"
                encoded_bytes = ps_command_safe_no_progress.encode('utf-16le') # PS uses UTF-16LE
                encoded_ps_command = base64.b64encode(encoded_bytes).decode('ascii')
                run_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_ps_command]
                # CREATE_NEW_PROCESS_GROUP allows killing the entire process tree with taskkill /T
                # CREATE_NO_WINDOW hides the console window
                creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            except Exception as encode_err:
                 err_msg = f"Error encoding command for PowerShell: {encode_err}"
                 print(f"[Executor] {err_msg}")
                 if not stop_flag_func(): _emit_error(err_msg)
                 return current_cwd, None # Cannot proceed if encoding fails
        else: # Linux or macOS
            # Use user's preferred shell via SHELL env var or fallback to /bin/sh
            shell_path = os.environ.get("SHELL", "/bin/sh")
            # Execute the command string using the shell's -c argument
            run_args = [shell_path, "-c", command]
            # Set preexec_fn to os.setsid to start the process in a new session.
            # This allows killing the entire process group reliably with os.killpg.
            # Only necessary/available on Unix-like systems.
            try:
                preexec_fn = os.setsid
            except AttributeError:
                print("[Executor] Warning: os.setsid not available on this platform. Process group termination might be unreliable.")
                preexec_fn = None

        if run_args is None:
            print("[Executor] Could not determine run arguments. Aborting execution.")
            return current_cwd, None

        print(f"[Executor] Executing via Popen in CWD '{current_cwd}': {run_args}")

        # --- Start the subprocess ---
        try:
             process = subprocess.Popen(
                run_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=current_cwd,
                shell=use_shell, # Should be False here
                creationflags=creationflags, # Windows specific flags
                bufsize=0, # Unbuffered binary streams for direct reading
                preexec_fn=preexec_fn # Unix specific: Start in new session
             )
             process_pid = process.pid # Store PID immediately after start
             print(f"[Executor] Process started PID: {process_pid}")
        except FileNotFoundError:
             cmd_name = run_args[0]
             fnf_msg = f"Command or execution shell not found: '{cmd_name}'. Check PATH or command spelling."
             print(f"[Executor] {fnf_msg}")
             if not stop_flag_func(): _emit_error(fnf_msg)
             return current_cwd, None # Cannot proceed
        except PermissionError as pe:
             perm_msg = f"Permission denied executing command: {pe}"
             print(f"[Executor] {perm_msg}")
             if not stop_flag_func(): _emit_error(perm_msg)
             return current_cwd, None
        except Exception as popen_err:
             popen_err_msg = f"Error starting command '{command[:50]}...': {type(popen_err).__name__} - {popen_err}"
             print(f"[Executor] {popen_err_msg}")
             traceback.print_exc()
             if not stop_flag_func(): _emit_error(popen_err_msg)
             return current_cwd, None # Cannot proceed

        # --- Stream Output if Process Started Successfully ---
        if process and process.stdout and process.stderr:
            # Stdout Reader Thread
            stdout_thread = QThread()
            stdout_worker = StreamWorker(process.stdout, stop_flag_func)
            stdout_worker.output_ready.connect(lambda b: _emit_output_bytes(b, is_stderr=False))
            stdout_worker.moveToThread(stdout_thread)
            # Ensure cleanup connections
            stdout_worker.finished.connect(stdout_thread.quit)
            stdout_worker.finished.connect(stdout_worker.deleteLater)
            stdout_thread.finished.connect(stdout_thread.deleteLater)
            stdout_thread.started.connect(stdout_worker.run)
            stdout_thread.start()
            print(f"[Executor PID {process_pid}] Stdout reader thread started.")

            # Stderr Reader Thread
            stderr_thread = QThread()
            # Pass stderr_lines list, enable CLIXML filtering on Windows
            stderr_worker = StreamWorker(process.stderr, stop_flag_func, stderr_lines, filter_clixml=True)
            stderr_worker.output_ready.connect(lambda b: _emit_output_bytes(b, is_stderr=True))
            stderr_worker.moveToThread(stderr_thread)
            # Ensure cleanup connections
            stderr_worker.finished.connect(stderr_thread.quit)
            stderr_worker.finished.connect(stderr_worker.deleteLater)
            stderr_thread.finished.connect(stderr_thread.deleteLater)
            stderr_thread.started.connect(stderr_worker.run)
            stderr_thread.start()
            print(f"[Executor PID {process_pid}] Stderr reader thread started.")

            # --- Wait for Process and Threads ---
            try:
                while process.poll() is None: # While process is running
                    if stop_flag_func():
                        print(f"[Executor PID {process_pid}] Stop signal received while waiting for process. Terminating...")
                        # --- Termination Logic ---
                        try:
                            if platform.system() == "Windows":
                                # Use taskkill to terminate the process tree (/T) forcefully (/F)
                                kill_cmd = ['taskkill', '/PID', str(process_pid), '/T', '/F']
                                kill_flags = subprocess.CREATE_NO_WINDOW
                                result = subprocess.run(kill_cmd, check=False, capture_output=True, creationflags=kill_flags)
                                if result.returncode == 0: print(f"  Process {process_pid} tree terminated via taskkill.")
                                else: print(f"  Taskkill failed for PID {process_pid}. Error: {result.stderr.decode(errors='ignore')}")
                            else: # Linux/macOS
                                import signal
                                try:
                                    # Kill the entire process group using the session ID set by preexec_fn=os.setsid
                                    pgid = os.getpgid(process_pid)
                                    os.killpg(pgid, signal.SIGKILL) # Send SIGKILL for forceful termination
                                    print(f"  Sent SIGKILL to process group {pgid} (PID {process_pid}).")
                                except ProcessLookupError:
                                    print(f"  Process group/PID {process_pid} not found during termination, likely already finished.")
                                except Exception as kill_err:
                                     print(f"  Error sending SIGKILL to process group {process_pid}: {kill_err}")
                            # Wait briefly for termination signal to take effect
                            process.wait(timeout=0.5)
                        except subprocess.TimeoutExpired:
                            print(f"  Process {process_pid} did not terminate within timeout after signal.")
                        except ProcessLookupError: # Added specific catch for race conditions
                            print(f"  Process {process_pid} lookup failed during termination attempt, likely already gone.")
                        except Exception as e:
                            print(f"  Error during process termination for PID {process_pid}: {e}")
                        # --- End Termination Logic ---
                        break # Exit the wait loop after attempting termination
                    QThread.msleep(50) # Yield control while waiting

                # --- Process finished naturally or was terminated ---
                exit_code = process.poll() # Get final exit code
                print(f"[Executor PID {process_pid}] Process finished or terminated. Exit code: {exit_code}")

                # Wait briefly for reader threads to finish processing any final output
                if stdout_thread and stdout_thread.isRunning():
                    stdout_thread.quit()
                    if not stdout_thread.wait(300): # Wait max 300ms
                        print(f"[Executor PID {process_pid}] Warning: Stdout reader thread did not finish cleanly.")
                if stderr_thread and stderr_thread.isRunning():
                    stderr_thread.quit()
                    if not stderr_thread.wait(300):
                         print(f"[Executor PID {process_pid}] Warning: Stderr reader thread did not finish cleanly.")

            except Exception as wait_err:
                 print(f"[Executor PID {process_pid}] Error during process wait/termination loop: {wait_err}")
                 traceback.print_exc()
                 exit_code = -1 # Indicate an error occurred
                 # Ensure process is killed if wait failed
                 if process and process.poll() is None:
                     print(f"[Executor PID {process_pid}] Attempting final termination after wait error.")
                     try: process.kill()
                     except: pass

        else:
             print("[Executor] Process object invalid or streams unavailable after Popen attempt.")

        # --- Check Final Return Code (if process ran and wasn't stopped early) ---
        if exit_code is not None and exit_code != 0 and not stop_flag_func():
             print(f"[Executor PID {process_pid}] Command exited with non-zero code: {exit_code}. Checking stderr.")
             # Check if stderr likely contained the error message already
             stderr_full_output_bytes = b"".join(stderr_lines)
             emitted_any_stderr = bool(stderr_full_output_bytes)
             stderr_str_for_check = decode_output(stderr_full_output_bytes) if emitted_any_stderr else ""

             # Only emit the exit code error if stderr was empty OR if the exit code number
             # wasn't obviously part of the stderr text (simple heuristic)
             if not emitted_any_stderr or str(exit_code) not in stderr_str_for_check:
                  exit_msg = f"Command exited with code: {exit_code}"
                  print(f"[Executor PID {process_pid}] Emitting exit code error message: {exit_msg}")
                  _emit_error(exit_msg)
             else:
                  print(f"[Executor PID {process_pid}] Non-zero exit code message suppressed as stderr likely contained relevant info.")

    except Exception as exec_err:
        # Catch-all for unexpected errors during the execution setup/wait
        pid_info = f"PID {process_pid}" if process_pid != -1 else "PID N/A"
        print(f"[Executor {pid_info}] Unhandled error during command execution logic: {exec_err}")
        traceback.print_exc()
        if not stop_flag_func(): _emit_error(f"Unexpected execution error: {exec_err}")
        exit_code = -1 # Indicate error

    finally:
        # Ensure process is not left dangling if Popen succeeded but something failed later
        # and stop_flag_func wasn't triggered (which already attempts termination)
        if process and process.poll() is None and not stop_flag_func():
            print(f"[Executor PID {process_pid}] Warning: Process may still be running after execution logic finished unexpectedly. Attempting final kill.")
            try: process.kill()
            except Exception as final_kill_err:
                 print(f"  Error during final process kill: {final_kill_err}")
        # Threads should have been cleaned up already by wait() or deleteLater connections
        print(f"[Executor PID {process_pid}] Finished executing command: '{command[:50]}{'...' if len(command)>50 else ''}'")

    return current_cwd, exit_code