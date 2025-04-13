# ========================================
# 文件名: PowerAgent/core/command_executor.py
# (MODIFIED - Corrected PowerShell command encoding to UTF-16LE before Base64)
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
import io # For stream check exceptions
from typing import Callable
from PySide6.QtCore import QThread, Signal, QObject # Need QThread for msleep

# Import helpers from other new modules
from .stream_handler import StreamWorker
from .worker_utils import decode_output

# Type hints corrected in previous steps
def execute_command_streamed(
    command: str,
    cwd: str,
    stop_flag_func: Callable[[], bool],
    output_signal: Signal,
    error_signal: Signal,
    directory_changed_signal: Signal,
    is_manual_command: bool
) -> tuple[str, int | None]:
    """
    Executes a shell command, handling 'cd' directly and streaming output
    for other commands using subprocess.Popen. Checks stop_flag_func to allow interruption.

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
                error_signal.emit(f"Error: {message}".encode('utf-8')) # Emit errors as UTF-8 bytes
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
        print("[Executor] Execution skipped: Stop flag was set before start.")
        return current_cwd, exit_code

    command = command.strip()
    if not command:
        print("[Executor] Empty command received.")
        return current_cwd, exit_code

    # --- Handle 'cd' command directly ---
    if command.lower().startswith('cd '):
        original_dir = current_cwd
        try:
            path_part = command[3:].strip()
            if len(path_part) >= 2 and path_part.startswith('"') and path_part.endswith('"'): path_part = path_part[1:-1]
            elif len(path_part) >= 2 and path_part.startswith("'") and path_part.endswith("'"): path_part = path_part[1:-1]
            if not path_part or path_part == '~': target_dir = os.path.expanduser("~")
            else: target_dir = os.path.expanduser(path_part);
            if not os.path.isabs(target_dir): target_dir = os.path.abspath(os.path.join(current_cwd, target_dir))
            target_dir = os.path.normpath(target_dir)

            if os.path.isdir(target_dir):
                current_cwd = target_dir # Update the internal CWD
                print(f"[Executor] Changed directory via 'cd' to: {current_cwd}")
                if not stop_flag_func():
                    try:
                        directory_changed_signal.emit(current_cwd, is_manual_command)
                    except RuntimeError as e:
                        print(f"[Executor] Warning: Could not emit directory changed signal: {e}")
            else:
                error_msg = f"Directory not found: '{target_dir}' (Resolved from '{path_part}')"
                print(f"[Executor] 'cd' failed: {error_msg}")
                _emit_error(error_msg)

        except Exception as e:
            error_msg = f"Error processing 'cd' command: {e}"
            print(f"[Executor] 'cd' processing error: {error_msg}")
            traceback.print_exc()
            _emit_error(error_msg)

        return current_cwd, None

    # --- Execute other commands using Popen ---
    process: subprocess.Popen | None = None
    stdout_thread: QThread | None = None
    stderr_thread: QThread | None = None
    stderr_lines = [] # Collect stderr chunks for later analysis
    process_pid = -1 # Store PID for logging

    try:
        run_args = None; use_shell = False; creationflags = 0; preexec_fn = None
        os_name = platform.system()

        if os_name == "Windows":
            try:
                # Prepare the PowerShell command WITH error handling and no progress bar
                ps_command_safe_no_progress = f"$ProgressPreference = 'SilentlyContinue'; try {{ {command} }} catch {{ Write-Error $_; exit 1 }}"

                # ============================================================= #
                # <<< CRITICAL FIX: Encode to UTF-16LE before Base64 >>>
                # ============================================================= #
                encoded_bytes = ps_command_safe_no_progress.encode('utf-16le') # <--- CORRECT ENCODING
                # ============================================================= #
                # <<< END FIX >>>
                # ============================================================= #

                encoded_ps_command = base64.b64encode(encoded_bytes).decode('ascii')
                run_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_ps_command]
                creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                print(f"[Executor] PowerShell Encoded Command (first 100 chars): {encoded_ps_command[:100]}...") # Log encoded command start
            except Exception as encode_err:
                 err_msg = f"Error encoding command for PowerShell: {encode_err}"; print(f"[Executor] {err_msg}")
                 _emit_error(err_msg); return current_cwd, None
        else: # Linux / macOS
            shell_path = os.environ.get("SHELL", "/bin/sh")
            # For non-Windows shells, directly passing the command string is usually fine
            # as Popen handles encoding based on locale (often UTF-8).
            run_args = [shell_path, "-c", command]
            try: preexec_fn = os.setsid
            except AttributeError: print("[Executor] Warning: os.setsid not available. Process group termination might be unreliable."); preexec_fn = None

        if run_args is None: print("[Executor] Could not determine run arguments. Aborting execution."); return current_cwd, None

        if stop_flag_func():
            print("[Executor] Execution skipped: Stop flag was set before Popen.")
            return current_cwd, exit_code

        print(f"[Executor] Executing via Popen in CWD '{current_cwd}': {run_args}")
        try:
             process = subprocess.Popen(
                run_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=current_cwd, shell=use_shell,
                creationflags=creationflags, bufsize=0, preexec_fn=preexec_fn )
             process_pid = process.pid
             print(f"[Executor] Process started PID: {process_pid}")
        except FileNotFoundError: cmd_name = run_args[0]; fnf_msg = f"Command or execution shell not found: '{cmd_name}'."; print(f"[Executor] {fnf_msg}"); _emit_error(fnf_msg); return current_cwd, None
        except PermissionError as pe: perm_msg = f"Permission denied executing command: {pe}"; print(f"[Executor] {perm_msg}"); _emit_error(perm_msg); return current_cwd, None
        except Exception as popen_err: popen_err_msg = f"Error starting command '{command[:50]}...': {type(popen_err).__name__} - {popen_err}"; print(f"[Executor] {popen_err_msg}"); traceback.print_exc(); _emit_error(popen_err_msg); return current_cwd, None

        if process and process.stdout and process.stderr:
            # Stdout Reader Thread
            stdout_thread = QThread(); stdout_worker = StreamWorker(process.stdout, stop_flag_func); stdout_worker.output_ready.connect(lambda b: _emit_output_bytes(b, is_stderr=False))
            stdout_worker.moveToThread(stdout_thread); stdout_worker.finished.connect(stdout_thread.quit); stdout_worker.finished.connect(stdout_worker.deleteLater)
            stdout_thread.finished.connect(stdout_thread.deleteLater); stdout_thread.started.connect(stdout_worker.run); stdout_thread.start()
            print(f"[Executor PID {process_pid}] Stdout reader thread started.")

            # Stderr Reader Thread
            stderr_thread = QThread(); stderr_worker = StreamWorker(process.stderr, stop_flag_func, stderr_lines, filter_clixml=True); stderr_worker.output_ready.connect(lambda b: _emit_output_bytes(b, is_stderr=True))
            stderr_worker.moveToThread(stderr_thread); stderr_worker.finished.connect(stderr_thread.quit); stderr_worker.finished.connect(stderr_worker.deleteLater)
            stderr_thread.finished.connect(stderr_thread.deleteLater); stderr_thread.started.connect(stderr_worker.run); stderr_thread.start()
            print(f"[Executor PID {process_pid}] Stderr reader thread started.")

            try:
                while process.poll() is None:
                    if stop_flag_func():
                        print(f"[Executor PID {process_pid}] Stop signal received while waiting for process. Terminating...")
                        # --- Termination Logic ---
                        try:
                            if platform.system() == "Windows":
                                kill_cmd = ['taskkill', '/PID', str(process_pid), '/T', '/F']
                                kill_flags = subprocess.CREATE_NO_WINDOW
                                result = subprocess.run(kill_cmd, check=False, capture_output=True, creationflags=kill_flags)
                                if result.returncode == 0: print(f"  Process {process_pid} tree terminated via taskkill.")
                                else: print(f"  Taskkill failed for PID {process_pid}. Error: {result.stderr.decode(errors='ignore')}")
                            else: # Linux/macOS
                                import signal
                                try:
                                    pgid_to_kill = -1
                                    try:
                                        pgid_to_kill = os.getpgid(process_pid)
                                        if pgid_to_kill == os.getpid():
                                            print(f"  Warning: Target process {process_pid} has same PGID as executor. Killing PID directly.")
                                            pgid_to_kill = -1
                                    except ProcessLookupError:
                                        print(f"  Process {process_pid} not found for getpgid, likely already finished.")
                                        pgid_to_kill = -2

                                    if pgid_to_kill == -2: pass
                                    elif pgid_to_kill != -1:
                                        os.killpg(pgid_to_kill, signal.SIGKILL)
                                        print(f"  Sent SIGKILL to process group {pgid_to_kill} (PID {process_pid}).")
                                    else:
                                        os.kill(process_pid, signal.SIGKILL)
                                        print(f"  Sent SIGKILL to process PID {process_pid}.")

                                except ProcessLookupError: print(f"  Process group/PID {process_pid} not found during termination, likely already finished.")
                                except Exception as kill_err: print(f"  Error sending SIGKILL to process/group {process_pid}: {kill_err}")

                            process.wait(timeout=0.5)
                        except subprocess.TimeoutExpired: print(f"  Process {process_pid} did not terminate within timeout after signal.")
                        except ProcessLookupError: print(f"  Process {process_pid} lookup failed during termination attempt, likely already gone.")
                        except Exception as e: print(f"  Error during process termination for PID {process_pid}: {e}")
                        # --- End Termination Logic ---
                        exit_code = -999 # Use a specific code for manual stop
                        break
                    QThread.msleep(50) # Yield control while waiting

                if exit_code is None: # If not stopped manually
                    exit_code = process.poll()
                print(f"[Executor PID {process_pid}] Process finished or terminated. Exit code: {exit_code}")

                # Wait briefly for reader threads
                if stdout_thread and stdout_thread.isRunning():
                    stdout_thread.quit()
                    if not stdout_thread.wait(300): print(f"[Executor PID {process_pid}] Warning: Stdout reader thread did not finish cleanly.")
                if stderr_thread and stderr_thread.isRunning():
                    stderr_thread.quit()
                    if not stderr_thread.wait(300): print(f"[Executor PID {process_pid}] Warning: Stderr reader thread did not finish cleanly.")

            except Exception as wait_err:
                 print(f"[Executor PID {process_pid}] Error during process wait/termination loop: {wait_err}")
                 traceback.print_exc()
                 exit_code = -1
                 if process and process.poll() is None:
                     print(f"[Executor PID {process_pid}] Attempting final termination after wait error.")
                     try: process.kill()
                     except: pass
        else:
             print("[Executor] Process object invalid or streams unavailable after Popen attempt.")

        # Check Final Return Code
        if exit_code is not None and exit_code != 0 and exit_code != -999 and not stop_flag_func():
             print(f"[Executor PID {process_pid}] Command exited with non-zero code: {exit_code}. Checking stderr.")
             stderr_full_output_bytes = b"".join(stderr_lines); emitted_any_stderr = bool(stderr_full_output_bytes)
             stderr_str_for_check = decode_output(stderr_full_output_bytes) if emitted_any_stderr else ""
             if not emitted_any_stderr or str(exit_code) not in stderr_str_for_check:
                  exit_msg = f"Command exited with code: {exit_code}"; print(f"[Executor PID {process_pid}] Emitting exit code error message: {exit_msg}")
                  _emit_error(exit_msg)
             else:
                  print(f"[Executor PID {process_pid}] Non-zero exit code message suppressed as stderr likely contained relevant info.")

    except Exception as exec_err:
        pid_info = f"PID {process_pid}" if process_pid != -1 else "PID N/A"
        print(f"[Executor {pid_info}] Unhandled error during command execution logic: {exec_err}")
        traceback.print_exc()
        _emit_error(f"Unexpected execution error: {exec_err}")
        exit_code = -1

    finally:
        # Final check to kill process if needed
        if process and process.poll() is None and not stop_flag_func():
            print(f"[Executor PID {process_pid}] Warning: Process may still be running after logic finished. Attempting final kill.")
            try: process.kill()
            except Exception as final_kill_err: print(f"  Error during final process kill: {final_kill_err}")
        print(f"[Executor PID {process_pid}] Finished executing command: '{command[:50]}{'...' if len(command)>50 else ''}'")

    return current_cwd, exit_code