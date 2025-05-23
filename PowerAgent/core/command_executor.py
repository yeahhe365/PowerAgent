# core/command_executor.py
# -*- coding: utf-8 -*-

"""
Handles the execution of shell commands, including 'cd'.
Reads stdout/stderr *after* the process completes (NO LIVE STREAMING).
"""

import subprocess
import os
import platform
import base64
import traceback
import time
import io
import logging # Import logging
from typing import Callable, List
from PySide6.QtCore import QThread, Signal, QObject

# Import utility using relative path
try:
    from .worker_utils import decode_output
except ImportError:
    logging.error("Failed to import .worker_utils in command_executor.", exc_info=True)
    def decode_output(b): return repr(b) # Fallback

# --- Get Logger ---
logger = logging.getLogger(__name__)

def execute_command_streamed( # Function name kept for compatibility
    command: str,
    cwd: str,
    stop_flag_func: Callable[[], bool],
    output_signal: Signal,
    error_signal: Signal,
    directory_changed_signal: Signal,
    is_manual_command: bool
) -> tuple[str, int | None]:
    """
    Executes a shell command, handling 'cd' directly. Reads output after completion. Logs the process.

    Args:
        command: The command string to execute.
        cwd: The current working directory for execution.
        stop_flag_func: A callable that returns True if execution should stop.
        output_signal: Signal to emit stdout bytes. (Emits: bytes)
        error_signal: Signal to emit stderr bytes or error messages. (Emits: bytes)
        directory_changed_signal: Signal to emit when 'cd' changes directory. (Emits: str, bool)
        is_manual_command: Passed to directory_changed_signal to indicate source.

    Returns:
        tuple: (final_cwd, exit_code, stdout_summary, stderr_summary)
    """
    command_source = "Manual" if is_manual_command else "AI"
    logger.info(f"Executing command ({command_source}): '{command[:100]}{'...' if len(command)>100 else ''}' in CWD: {cwd}")

    current_cwd = cwd
    exit_code = None
    stdout_summary = ""
    stderr_summary = ""
    process: subprocess.Popen | None = None
    process_pid = -1

    # --- Signal Emission Helpers with Logging ---
    def _emit_error(message: str):
        logger.debug(f"Emitting error signal: {message}")
        try: error_signal.emit(f"Error: {message}".encode('utf-8'))
        except RuntimeError: logger.warning("Cannot emit error signal, target likely deleted.")
        except Exception as e: logger.error("Unexpected error emitting error signal.", exc_info=True)

    def _emit_output_bytes(b_message: bytes, is_stderr: bool):
        target_signal = error_signal if is_stderr else output_signal
        signal_name = "error_signal (stderr)" if is_stderr else "output_signal (stdout)"
        logger.debug(f"Emitting {signal_name} with {len(b_message)} bytes.")
        try: target_signal.emit(b_message)
        except RuntimeError: logger.warning(f"Cannot emit {signal_name}, target likely deleted.")
        except Exception as e: logger.error(f"Unexpected error emitting {signal_name}.", exc_info=True)

    def _emit_dir_changed(new_dir: str):
         logger.debug(f"Emitting directory_changed signal: NewDir={new_dir}, IsManual={is_manual_command}")
         try: directory_changed_signal.emit(new_dir, is_manual_command)
         except RuntimeError: logger.warning("Cannot emit directory_changed signal, target likely deleted.")
         except Exception as e: logger.error("Unexpected error emitting directory_changed signal.", exc_info=True)
    # --- End Signal Helpers ---


    # --- Handle 'cd' command directly ---
    command = command.strip()
    if command.lower().startswith('cd '):
        logger.info("Handling 'cd' command directly.")
        original_dir = current_cwd
        try:
            path_part = command[3:].strip()
            # Handle quotes
            if len(path_part) >= 2 and ((path_part.startswith('"') and path_part.endswith('"')) or \
                                       (path_part.startswith("'") and path_part.endswith("'"))):
                path_part = path_part[1:-1]
                logger.debug(f"'cd': Path part after removing quotes: '{path_part}'")

            if not path_part or path_part == '~':
                target_dir = os.path.expanduser("~")
                logger.debug(f"'cd': Targeting home directory: {target_dir}")
            else:
                target_dir_expanded = os.path.expanduser(path_part)
                if not os.path.isabs(target_dir_expanded):
                    target_dir = os.path.abspath(os.path.join(current_cwd, target_dir_expanded))
                    logger.debug(f"'cd': Relative path '{target_dir_expanded}' resolved to absolute: {target_dir}")
                else:
                    target_dir = target_dir_expanded
                    logger.debug(f"'cd': Path part '{path_part}' resolved to absolute: {target_dir}")

            target_dir = os.path.normpath(target_dir)
            logger.debug(f"'cd': Final normalized target directory: {target_dir}")

            if os.path.isdir(target_dir):
                current_cwd = target_dir
                logger.info(f"'cd': Directory successfully changed to: {current_cwd}")
                # Check stop flag before emitting signal
                if not stop_flag_func(): _emit_dir_changed(current_cwd)
                else: logger.warning("'cd': Directory changed, but stop flag set before signal emission.")
            else:
                error_msg = f"Directory not found: '{target_dir}' (Resolved from '{path_part}')"
                logger.error(f"'cd' failed: {error_msg}"); _emit_error(error_msg)
        except Exception as e:
            logger.error(f"Error processing 'cd' command: {e}", exc_info=True)
            _emit_error(f"Error processing 'cd' command: {e}")
        logger.debug("'cd' command handling finished.")
        return current_cwd, None, stdout_summary, stderr_summary # Exit code is None for 'cd'
    # --- End 'cd' handling ---

    # --- Pre-Execution Checks ---
    if stop_flag_func():
        logger.warning("Execution skipped: Stop flag was set before start.")
        return current_cwd, exit_code, stdout_summary, stderr_summary
    if not command:
        logger.info("Empty command received, nothing to execute.")
        return current_cwd, exit_code, stdout_summary, stderr_summary

    # --- Execute other commands using Popen ---
    stdout_data = b""
    stderr_data = b""
    try:
        run_args = None; use_shell = False; creationflags = 0; preexec_fn = None
        os_name = platform.system()
        logger.debug(f"Preparing command for OS: {os_name}")

        # --- Prepare command arguments ---
        if os_name == "Windows":
            try:
                logger.debug("Using PowerShell with EncodedCommand.")
                # Construct the PowerShell command to handle errors and suppress progress
                ps_command_safe_no_progress = f"$ProgressPreference = 'SilentlyContinue'; try {{ {command} }} catch {{ Write-Error $_; exit 1 }}"
                logger.debug(f"PowerShell Script (Original): {ps_command_safe_no_progress[:200]}...")
                encoded_bytes = ps_command_safe_no_progress.encode('utf-16le')
                encoded_ps_command = base64.b64encode(encoded_bytes).decode('ascii')
                run_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_ps_command]
                creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                logger.debug(f"PowerShell Encoded Command (first 100 chars): {encoded_ps_command[:100]}...")
            except Exception as encode_err:
                 logger.error(f"Error encoding command for PowerShell: {encode_err}", exc_info=True)
                 _emit_error(f"Error encoding command for PowerShell: {encode_err}"); return current_cwd, None, stdout_summary, stderr_summary
        else: # Linux / macOS
            shell_path = os.environ.get("SHELL", "/bin/sh")
            logger.debug(f"Using Shell: {shell_path}")
            run_args = [shell_path, "-c", command]
            try: preexec_fn = os.setsid # Try to start in new session to allow group kill
            except AttributeError: logger.warning("os.setsid not available on this platform."); preexec_fn = None
        # --- End argument preparation ---

        if run_args is None: logger.error("Could not determine run arguments for subprocess."); return current_cwd, None, stdout_summary, stderr_summary
        if stop_flag_func(): logger.warning("Execution skipped: Stop flag set before Popen."); return current_cwd, exit_code, stdout_summary, stderr_summary

        logger.info(f"Executing Popen: {run_args}")
        process = subprocess.Popen(
            run_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=current_cwd, shell=use_shell,
            creationflags=creationflags, preexec_fn=preexec_fn
        )
        process_pid = process.pid
        logger.info(f"Process started with PID: {process_pid}")

        # --- Wait for process completion OR stop signal ---
        termination_initiated = False
        while process.poll() is None:
            if stop_flag_func():
                logger.warning(f"Stop signal received for PID {process_pid}. Terminating process...")
                termination_initiated = True
                # --- Termination Logic ---
                try:
                    if platform.system() == "Windows":
                        kill_cmd = ['taskkill', '/PID', str(process_pid), '/T', '/F']; kill_flags = subprocess.CREATE_NO_WINDOW
                        logger.debug(f"Attempting Windows termination: {kill_cmd}")
                        result = subprocess.run(kill_cmd, check=False, capture_output=True, creationflags=kill_flags, timeout=5)
                        if result.returncode == 0: logger.info(f"Process {process_pid} tree terminated successfully via taskkill.")
                        else: logger.warning(f"Taskkill may have failed for PID {process_pid}. ExitCode: {result.returncode}, Stderr: {result.stderr.decode(errors='ignore')}")
                    else: # Linux/macOS
                        import signal
                        pgid_to_kill = -1
                        try:
                            pgid_to_kill = os.getpgid(process_pid)
                            logger.debug(f"Attempting Linux/macOS termination: Sending SIGKILL to process group {pgid_to_kill}.")
                            os.killpg(pgid_to_kill, signal.SIGKILL)
                            logger.info(f"Sent SIGKILL to process group {pgid_to_kill}.")
                        except ProcessLookupError:
                            logger.warning(f"Process {process_pid} not found for getpgid/killpg, likely finished or already killed.")
                        except Exception as kill_err:
                            logger.error(f"Error during killpg for PGID {pgid_to_kill} (PID {process_pid}). Falling back to kill PID.", exc_info=True)
                            try:
                                logger.debug(f"Fallback: Sending SIGKILL to process PID {process_pid}.")
                                os.kill(process_pid, signal.SIGKILL)
                                logger.info(f"Sent SIGKILL to process PID {process_pid}.")
                            except ProcessLookupError: logger.warning(f"Fallback kill failed: Process {process_pid} not found.")
                            except Exception as final_kill_err: logger.error(f"Fallback kill for PID {process_pid} also failed.", exc_info=True)
                except ProcessLookupError: logger.warning(f"Process {process_pid} not found during termination attempt.")
                except Exception as e: logger.error(f"Error during process termination logic for PID {process_pid}.", exc_info=True)
                # --- End Termination Logic ---
                exit_code = -999 # Use a specific code for manual stop
                break # Exit the waiting loop

            # Use QThread.msleep for better Qt integration if available, else time.sleep
            try: QThread.msleep(100)
            except: time.sleep(0.1)

        # --- Process Finished or Terminated ---
        if exit_code is None: # If not stopped manually, get the final exit code
            exit_code = process.poll()
            logger.info(f"Process PID {process_pid} finished naturally. Exit code: {exit_code}")
        else:
             logger.info(f"Process PID {process_pid} was terminated manually. Exit code set to: {exit_code}")


        # --- Read Remaining Output AFTER process exit ---
        logger.debug(f"Reading final stdout/stderr for PID {process_pid}...")
        try:
            # Use communicate() for safety and to avoid potential deadlocks
            stdout_data, stderr_data = process.communicate(timeout=10) # Increased timeout slightly
            logger.debug(f"Communicate successful. Stdout bytes: {len(stdout_data)}, Stderr bytes: {len(stderr_data)}")
        except subprocess.TimeoutExpired:
             logger.warning(f"Timeout expired during communicate() for PID {process_pid}. Killing process.")
             process.kill()
             stdout_data, stderr_data = process.communicate() # Try again after kill
             logger.debug(f"Communicate after kill. Stdout bytes: {len(stdout_data)}, Stderr bytes: {len(stderr_data)}")
        except Exception as comm_err:
             logger.error(f"Error during process.communicate() for PID {process_pid}.", exc_info=True)
             # Attempt manual reads as fallback
             try:
                 logger.debug(f"Attempting fallback read() for PID {process_pid}...")
                 if process.stdout: stdout_data = process.stdout.read()
                 if process.stderr: stderr_data = process.stderr.read()
                 logger.debug(f"Fallback read. Stdout bytes: {len(stdout_data)}, Stderr bytes: {len(stderr_data)}")
             except Exception as read_err:
                 logger.error(f"Error during fallback read() for PID {process_pid}.", exc_info=True)

        # --- Emit Final Output ---
        if stdout_data:
            logger.info(f"Emitting final stdout ({len(stdout_data)} bytes) for PID {process_pid}.")
            _emit_output_bytes(stdout_data, is_stderr=False)
        if stderr_data:
            logger.info(f"Emitting final stderr ({len(stderr_data)} bytes) for PID {process_pid}.")
            _emit_output_bytes(stderr_data, is_stderr=True)

        # --- Check Final Return Code and Emit Error if Needed ---
        if exit_code is not None and exit_code != 0 and exit_code != -999:
             logger.warning(f"Command PID {process_pid} exited with non-zero code: {exit_code}.")
             emitted_any_stderr = bool(stderr_data)
             # Decode stderr for checking if exit code message is already present
             # stderr_str_for_check = decode_output(stderr_data) if emitted_any_stderr else "" # decode_output is already called for stderr_summary
             # Avoid duplicate error messages
             exit_code_str = str(exit_code)
             # Check more robustly if the exit code is part of the error message (e.g., "exited with code 1")
             if not emitted_any_stderr or (exit_code_str not in stderr_summary and f"code {exit_code_str}" not in stderr_summary.lower()):
                  exit_msg = f"Command exited with code: {exit_code}"
                  logger.info(f"Emitting explicit exit code error message for PID {process_pid}: {exit_msg}")
                  _emit_error(exit_msg)
             else:
                  logger.info(f"Non-zero exit code message for PID {process_pid} suppressed as stderr likely contained relevant info.")

        # --- Summarize STDOUT ---
        stdout_decoded = decode_output(stdout_data)
        MAX_STDOUT_LEN = 2000 # Max characters for STDOUT summary
        if len(stdout_decoded) > MAX_STDOUT_LEN:
            half_len = MAX_STDOUT_LEN // 2
            stdout_summary = f"{stdout_decoded[:half_len]}\n[... STDOUT TRUNCATED ...]\n{stdout_decoded[-half_len:]}"
            logger.debug(f"STDOUT summary truncated to {len(stdout_summary)} chars.")
        else:
            stdout_summary = stdout_decoded
            logger.debug(f"STDOUT summary (full): {len(stdout_summary)} chars.")

        stderr_summary = decode_output(stderr_data)
        logger.debug(f"STDERR summary (full): {len(stderr_summary)} chars.")


    except FileNotFoundError as fnf_err:
        cmd_name = run_args[0] if run_args else "N/A"; fnf_msg = f"Command or execution shell not found: '{cmd_name}'. {fnf_err}"; logger.error(fnf_msg); _emit_error(fnf_msg); return current_cwd, None, "", fnf_msg
    except PermissionError as pe:
        perm_msg = f"Permission denied executing command: {pe}"; logger.error(perm_msg, exc_info=False); _emit_error(perm_msg); return current_cwd, None, "", perm_msg
    except Exception as exec_err:
        pid_info = f"PID {process_pid}" if process_pid != -1 else "PID N/A"
        logger.critical(f"Unhandled error during command execution ({pid_info}).", exc_info=True)
        _emit_error(f"Unexpected execution error: {exec_err}"); exit_code = -1 # Indicate error
    finally:
        # --- Final Process Cleanup ---
        if process and process.poll() is None:
            logger.warning(f"Process PID {process_pid} still running in finally block. Attempting final kill.")
            try: process.kill(); process.wait(timeout=1)
            except Exception as final_kill_err: logger.error(f"Error during final process kill/wait for PID {process_pid}.", exc_info=True)

        # Close pipes explicitly (less critical now with communicate, but can be good practice)
        if process:
             if process.stdout:
                 try: process.stdout.close()
                 except Exception as e: logger.debug(f"Error closing stdout for PID {process_pid}: {e}")
             if process.stderr:
                 try: process.stderr.close()
                 except Exception as e: logger.debug(f"Error closing stderr for PID {process_pid}: {e}")
        # Final wait attempt
        if process:
            try:
                final_exit_code = process.wait(timeout=0.5)
                if exit_code is None: exit_code = final_exit_code # Update exit code if not set yet
                logger.debug(f"Final process wait completed for PID {process_pid}. Exit code: {final_exit_code}.")
            except subprocess.TimeoutExpired: logger.warning(f"Process PID {process_pid} did not exit cleanly after final wait timeout.")
            except Exception as wait_err: logger.error(f"Error during final process wait for PID {process_pid}.", exc_info=True)

        logger.info(f"Finished executing command logic for PID {process_pid} ('{command[:50]}{'...' if len(command)>50 else ''}'). Final exit code: {exit_code}")

    return current_cwd, exit_code, stdout_summary, stderr_summary