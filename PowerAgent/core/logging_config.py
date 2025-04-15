# core/logging_config.py
# -*- coding: utf-8 -*-

import logging
import logging.handlers
import os
import sys
import platform # Import platform for potential platform-specific logic later

def setup_logging(log_level=logging.INFO, console_log_level=logging.INFO, file_log_level=logging.DEBUG):
    """
    Configures logging for the application. Creates the log directory if needed.

    Args:
        log_level: The base level for the root logger (e.g., logging.INFO).
        console_log_level: The level for console output.
        file_log_level: The level for file output.
    """
    log_dir = None
    log_file_path = None

    # --- Determine Log Directory ---
    try:
        # Assume this script (logging_config.py) is in PowerAgent/core/
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(project_root, 'logs') # Standard logs directory name
        if not os.path.exists(log_dir):
            print(f"Log directory '{log_dir}' does not exist. Attempting to create...")
            os.makedirs(log_dir)
            print(f"Log directory '{log_dir}' created successfully.")
        # Define log file path
        log_file_path = os.path.join(log_dir, 'power_agent.log')

    except OSError as e:
        print(f"CRITICAL: Error creating log directory '{log_dir}': {e}", file=sys.stderr)
        # Fallback: Try logging to the project root directory if 'logs' fails
        try:
             project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
             log_file_path = os.path.join(project_root, 'power_agent_fallback.log')
             print(f"CRITICAL: Falling back to log file path: {log_file_path}", file=sys.stderr)
        except Exception as fallback_e:
             print(f"CRITICAL: Failed to set fallback log path in project root: {fallback_e}", file=sys.stderr)
             log_file_path = None # Disable file logging if fallback fails

    except Exception as e:
        print(f"CRITICAL: Unexpected error determining log path: {e}", file=sys.stderr)
        log_file_path = None # Disable file logging on unexpected errors

    # --- Logging Configuration Parameters ---
    log_format = '%(asctime)s - %(levelname)-8s - %(name)-25s - %(threadName)-10s - %(message)s'
    log_date_format = '%Y-%m-%d %H:%M:%S'
    log_file_max_bytes = 10 * 1024 * 1024  # 10 MB
    log_file_backup_count = 5

    # --- Get Root Logger ---
    # We configure the root logger directly for more control over handlers.
    root_logger = logging.getLogger()
    # Set the lowest level the root logger will handle. Handlers can have higher levels.
    root_logger.setLevel(min(log_level, console_log_level, file_log_level)) # Handle the lowest level specified

    # --- Clear Existing Handlers (Avoid Duplicates in interactive sessions/reloads) ---
    if root_logger.hasHandlers():
        print("Clearing existing logging handlers to prevent duplication.")
        # Iterate over a copy since we're modifying the list
        for handler in root_logger.handlers[:]:
            try:
                # Flush and close handler before removing
                handler.flush()
                handler.close()
            except Exception as e:
                 print(f"Warning: Error closing handler {handler}: {e}", file=sys.stderr)
            root_logger.removeHandler(handler)

    # --- Configure Formatter ---
    formatter = logging.Formatter(log_format, datefmt=log_date_format)

    # --- Configure RotatingFileHandler (If path is valid) ---
    if log_file_path:
        try:
            # Use RotatingFileHandler to limit log file size
            file_handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=log_file_max_bytes,
                backupCount=log_file_backup_count,
                encoding='utf-8' # Explicitly use utf-8
            )
            file_handler.setLevel(file_log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            # Use print for initial setup messages as logging might not be fully ready
            print(f"File logging configured: Path='{log_file_path}', Level={logging.getLevelName(file_log_level)}")
        except PermissionError as pe:
             print(f"ERROR: Permission denied for log file '{log_file_path}'. Check permissions. {pe}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR: Could not configure file logging to '{log_file_path}': {e}", file=sys.stderr)
    else:
        print("ERROR: Log file path could not be determined or created. File logging disabled.", file=sys.stderr)

    # --- Configure StreamHandler (Console Output) ---
    try:
        console_handler = logging.StreamHandler(sys.stderr) # Log to stderr
        console_handler.setLevel(console_log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        print(f"Console logging configured: Level={logging.getLevelName(console_log_level)}")
    except Exception as e:
        print(f"ERROR: Could not configure console logging: {e}", file=sys.stderr)

    # Check if any handlers were successfully added
    if not root_logger.hasHandlers():
         print("CRITICAL: No logging handlers could be configured. Logging will not work.", file=sys.stderr)

    print("Logging setup sequence finished.")


def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Global exception handler to log unhandled exceptions.
    To be used with sys.excepthook.
    """
    # Do not log KeyboardInterrupt (Ctrl+C)
    if issubclass(exc_type, KeyboardInterrupt):
        # Call the default excepthook to ensure clean exit behavior
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger = logging.getLogger("UnhandledException") # Use a specific logger name

    # Check if logging is actually configured before attempting to log
    # Check root logger level and if any handlers exist
    if logger.isEnabledFor(logging.CRITICAL) and logging.getLogger().hasHandlers():
        logger.critical("Unhandled exception caught by sys.excepthook:",
                        exc_info=(exc_type, exc_value, exc_traceback))
    else:
        # Fallback to printing directly to stderr if logging isn't ready
        print("CRITICAL UNHANDLED EXCEPTION (Logging not fully configured):", file=sys.stderr)
        # Manually print the traceback to stderr
        import traceback as tb
        tb.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)