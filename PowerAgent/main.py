# main.py
# -*- coding: utf-8 -*-

import sys
import os
import platform
import ctypes
import logging # Import standard logging
import datetime # For fallback logger timestamp
import threading # For fallback logger thread name
import traceback # For fallback exception hook

# --- Define Fallback Logger and Hook FIRST ---
# Define these before the main try block so they are always available
# if initial logging setup fails in any way.
class FallbackLogger:
    def _log(self, level, msg, *args, exc_info=None, **kwargs):
        # Basic formatting, similar to the target format
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        thread_name = threading.current_thread().name
        log_line = f"{timestamp} - {level:<8} - FallbackLogger              - {thread_name:<10} - {msg % args if args else msg}"
        print(log_line, file=sys.stderr)
        if exc_info:
            # Manually print traceback if requested
            effective_exc_info = sys.exc_info() if isinstance(exc_info, bool) else exc_info
            if effective_exc_info[0]: # Check if there's an actual exception
                traceback_lines = traceback.format_exception(*effective_exc_info)
                for line in traceback_lines:
                    print(line.strip(), file=sys.stderr)

    def debug(self, msg, *args, **kwargs): self._log("DEBUG", msg, *args, **kwargs)
    def info(self, msg, *args, **kwargs): self._log("INFO", msg, *args, **kwargs)
    def warning(self, msg, *args, **kwargs): self._log("WARNING", msg, *args, **kwargs)
    def error(self, msg, *args, **kwargs): self._log("ERROR", msg, *args, **kwargs)
    def critical(self, msg, *args, **kwargs): self._log("CRITICAL", msg, *args, **kwargs)
    def exception(self, msg, *args, **kwargs): self._log("EXCEPTION", msg, *args, exc_info=True, **kwargs)

# Define the fallback exception hook function using the FallbackLogger
def fallback_excepthook(exc_type, exc_value, exc_traceback):
    # Instantiate a fallback logger *specifically for the hook*
    # This avoids potential issues if the global 'logger' variable isn't assigned yet
    hook_logger = FallbackLogger()
    hook_logger.critical("Unhandled exception caught (Fallback Handler):", exc_info=(exc_type, exc_value, exc_traceback))

# Initialize logger variable, will be assigned later
logger = None

# --- Early Logging Setup ---
# Attempt to set up logging as the very first operational step
try:
    # Ensure 'core' directory is correctly located relative to 'main.py'
    from core.logging_config import setup_logging, handle_exception

    # Configure logging
    setup_logging()

    # Set the global exception handler *after* logging is configured
    sys.excepthook = handle_exception

    # Get the logger for the main module *after* calling setup_logging
    logger = logging.getLogger(__name__)
    logger.info("Logging initialized successfully using core.logging_config.")

except ImportError as log_imp_err:
    # Fallback if logging_config cannot be imported
    print(f"CRITICAL: Failed to import logging configuration: {log_imp_err}", file=sys.stderr)
    print("CRITICAL: Logging will fallback to basic print statements.", file=sys.stderr)
    # Assign the fallback logger and hook
    logger = FallbackLogger()
    sys.excepthook = fallback_excepthook
    logger.critical(f"Using FallbackLogger due to ImportError: {log_imp_err}")

except Exception as log_setup_err:
    # Fallback if setup_logging itself fails
    print(f"CRITICAL: Failed during logging setup process: {log_setup_err}", file=sys.stderr)
    print("CRITICAL: Logging setup failed. Check core/logging_config.py and file permissions.", file=sys.stderr)
    # Assign the fallback logger and hook (FallbackLogger class is defined above now)
    logger = FallbackLogger()
    sys.excepthook = fallback_excepthook
    logger.critical(f"Using FallbackLogger due to setup Exception: {log_setup_err}. Check permissions/config.")


# --- Continue with other imports AFTER attempting logging setup ---
# Use the assigned logger (either real or fallback) from here on.
# These imports should happen regardless of logging success/failure,
# but failures here will now be logged by the assigned excepthook.
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QCoreApplication, QSettings # QSettings might be used later
    from PySide6.QtGui import QFont
    from constants import APP_NAME, ORG_NAME, SETTINGS_APP_NAME, get_color
    from gui.main_window import MainWindow
    from gui.palette import setup_palette
    from core import config # Config module might also need logging later
except ImportError as e:
     # Use the logger (either real or fallback) to log this critical error
     logger.critical(f"Failed to import essential application modules: {e}. Please check installation and paths.", exc_info=True)
     sys.exit(1) # Exit if essential modules cannot be imported


# --- Determine Application Base Directory ---
# Using logger here ensures we log the determined path or errors
application_base_dir = None
try:
    if getattr(sys, 'frozen', False):
        # Running as a bundled executable (e.g., PyInstaller)
        application_base_dir = os.path.dirname(sys.executable)
        logger.info(f"Application is frozen (executable). Base directory: {application_base_dir}")
    else:
        # Running as a Python script
        # sys.argv[0] is the path of the script invoked
        main_script_path = os.path.abspath(sys.argv[0])
        application_base_dir = os.path.dirname(main_script_path)
        logger.info(f"Application running as script. Main script: {main_script_path}. Base directory: {application_base_dir}")
except Exception as path_err:
     logger.error(f"Could not reliably determine application base directory: {path_err}", exc_info=True)
     # Fallback to directory containing this main.py file
     application_base_dir = os.path.dirname(os.path.abspath(__file__))
     logger.warning(f"Falling back to application base directory: {application_base_dir}")

# Log the final determined path (already logged above based on condition)


# --- Main Execution Block ---
if __name__ == "__main__":

    # Log start message
    logger.info(f"--- Starting {APP_NAME} ---")
    logger.info(f"PID: {os.getpid()}")
    logger.info(f"Operating System: {platform.system()} {platform.release()} ({platform.version()}) Machine: {platform.machine()}")
    logger.info(f"Python Version: {sys.version.replace(os.linesep, ' ')}") # Avoid newlines in log
    try:
        # Import PySide6 dynamically to log version safely
        import PySide6
        qt_version = getattr(PySide6.QtCore, 'qVersion', lambda: "N/A")()
        pyside_version = getattr(PySide6, '__version__', 'N/A')
        logger.info(f"PySide6 Version: {pyside_version}, Qt Version: {qt_version}")
    except ImportError:
        logger.error("PySide6 module not found!")
    except Exception as qt_ver_err:
        logger.warning(f"Could not determine PySide6/Qt versions: {qt_ver_err}")


    # --- Platform Specific Setup ---
    if platform.system() == "Windows":
        myappid = f"{ORG_NAME}.{APP_NAME}.{SETTINGS_APP_NAME}.1.0" # Keep consistent AppUserModelID
        try:
            # ctypes should have been imported earlier
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            logger.info(f"Windows AppUserModelID set to: {myappid}")
        except AttributeError:
            logger.warning("Could not set AppUserModelID (ctypes or shell32 method might be missing/different).")
        except NameError:
             logger.warning("Could not set AppUserModelID (ctypes was not imported successfully).")
        except Exception as e:
            # Log the exception details but keep the level as warning
            logger.warning(f"Could not set AppUserModelID due to an error: {e}", exc_info=False) # Set exc_info=False for brevity

    # Set Organization and Application name EARLY for QSettings etc.
    try:
        QCoreApplication.setOrganizationName(ORG_NAME)
        QCoreApplication.setApplicationName(SETTINGS_APP_NAME) # Use the specific name for settings
        logger.info(f"Qt Organization Name: '{QCoreApplication.organizationName()}', Application Name: '{QCoreApplication.applicationName()}'")
    except Exception as qt_err:
         logger.error(f"Failed to set Qt Organization/Application Name: {qt_err}", exc_info=True)


    # --- Load Configuration EARLY ---
    # Configuration loading is critical, log steps and outcome
    logger.info("Loading application configuration...")
    try:
        # config.load_config() should ideally also contain logging statements
        load_success, load_message = config.load_config()
        log_level = logging.INFO if load_success else logging.WARNING
        logger.log(log_level, f"Configuration load status: Success={load_success}, Message='{load_message}'")
        # Log key config values at DEBUG level if needed, be careful with sensitive data
        # logger.debug(f"Loaded config - Theme: {config.APP_THEME}, AutoStart: {config.AUTO_STARTUP_ENABLED}")
    except Exception as config_load_err:
         logger.error(f"An unhandled error occurred during configuration loading: {config_load_err}", exc_info=True)
         # Depending on severity, you might want to exit or proceed with defaults
         logger.warning("Proceeding with potentially default configuration due to loading error.")


    # --- QApplication Setup ---
    logger.debug("Creating QApplication instance.")
    # It's good practice to wrap QApplication instantiation in a try-except block
    try:
        app = QApplication(sys.argv)
    except Exception as app_err:
        logger.critical(f"Failed to create QApplication instance: {app_err}", exc_info=True)
        sys.exit(1) # Cannot proceed without QApplication


    # --- Set Default Font ---
    try:
        default_font = QFont()
        default_font.setPointSize(10) # Or load from config if desired
        app.setFont(default_font)
        logger.info(f"Default application font set: Family='{default_font.family()}', Size={default_font.pointSize()}pt")
    except Exception as font_err:
         # Font setting is less critical, log as error but continue
         logger.error(f"Failed to set default application font: {font_err}", exc_info=True)


    # --- Apply Initial Theme/Style ---
    try:
        current_theme = getattr(config, 'APP_THEME', 'system') # Safely get theme from config
        logger.info(f"Applying initial application theme: '{current_theme}'")
        # setup_palette should ideally also contain logging
        setup_palette(app, current_theme)
    except Exception as theme_err:
         # Palette/Theme errors might impact usability, log as error
         logger.error(f"Failed to apply initial theme/palette ('{current_theme}'): {theme_err}", exc_info=True)


    # --- Create and Show Main Window ---
    main_window = None # Initialize before try block
    try:
        logger.info("Creating MainWindow instance...")
        # MainWindow initialization should also contain logging statements
        main_window = MainWindow(application_base_dir=application_base_dir)
        logger.info("Showing MainWindow...")
        main_window.show()
        logger.info("MainWindow shown successfully.")
    except Exception as mw_err:
        # Failure to create the main window is critical
        logger.critical(f"CRITICAL: Failed to create or show MainWindow: {mw_err}", exc_info=True)
        # Ensure QApplication exits cleanly if the window fails
        if app:
            app.quit()
        sys.exit(1)


    # --- Start Event Loop ---
    exit_code = -1 # Default error code if loop fails unexpectedly
    try:
        logger.info("Starting Qt application event loop...")
        exit_code = app.exec()
        # This log message executes after the loop finishes (window closed)
        logger.info(f"Qt application event loop finished. Exit code: {exit_code}")
    except Exception as loop_err:
         # Catching errors here is a last resort; ideally, errors are handled within the application
         logger.critical(f"CRITICAL: Unhandled exception during Qt application event loop: {loop_err}", exc_info=True)
         exit_code = 1 # Indicate an error exit
    finally:
        # This block executes regardless of whether the try block completed successfully or raised an exception
        logger.info(f"--- Exiting {APP_NAME} (Final Exit Code: {exit_code}) ---")
        # Ensure Python exits with the determined exit code
        sys.exit(exit_code)