# gui/main_window.py
# -*- coding: utf-8 -*-

import sys
import os
import time
import platform
import traceback
import logging # Import logging
from collections import deque

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QApplication, QComboBox, QFrame,
    QLineEdit, QTextEdit, QLabel, QPushButton, QMessageBox # Added QMessageBox
)
from PySide6.QtCore import Qt, Slot, QSettings, QCoreApplication, QStandardPaths, QSize, QEvent, QThread
from PySide6.QtGui import (
    QTextCursor, QPalette, QFont, QIcon, QColor,
    QAction, QKeySequence
)

# --- Project Imports ---
from constants import APP_NAME, get_color
from core import config
from core.workers import ApiWorkerThread, ManualCommandThread
from .palette import setup_palette
from .ui_components import create_ui_elements, StatusIndicatorWidget

# --- Mixin Imports ---
from .main_window_handlers import HandlersMixin
from .main_window_updates import UpdatesMixin
from .main_window_state import StateMixin
from .main_window_workers import WorkersMixin

# --- Get Logger ---
logger = logging.getLogger(__name__)

# --- Main Window Class ---
class MainWindow(QMainWindow, HandlersMixin, UpdatesMixin, StateMixin, WorkersMixin):

    def __init__(self, application_base_dir=None, parent=None):
        logger.info("--- MainWindow Initializing ---")
        # Initialize QMainWindow first
        super().__init__(parent)

        # --- 1. Determine Base Directory ---
        # (Logic remains the same)
        start_time = time.monotonic() # Time the init process
        try:
            if application_base_dir:
                self.application_base_dir = application_base_dir
                logger.debug("Using provided application base directory.")
            elif getattr(sys, 'frozen', False):
                self.application_base_dir = os.path.dirname(sys.executable)
                logger.debug("Running as frozen executable.")
            else:
                try:
                     main_script_path = os.path.abspath(sys.argv[0])
                     self.application_base_dir = os.path.dirname(main_script_path)
                     logger.debug("Running as script, determined from sys.argv[0].")
                except Exception:
                     logger.warning("Could not determine base directory from sys.argv[0], falling back to __file__.", exc_info=False)
                     # Fallback: determine based on the directory of main_window.py
                     self.application_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                     logger.debug("Fallback to parent of current file directory.")
            logger.info(f"Application Base Directory set to: {self.application_base_dir}")
        except Exception as e:
             logger.error("Failed to determine application base directory!", exc_info=True)
             # Attempt a reasonable fallback
             self.application_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
             logger.warning(f"Using fallback base directory: {self.application_base_dir}")


        # --- 1.5 Get Launch Directory EARLY ---
        try:
            # This gets the directory where the script/exe was *launched from*
            self.launch_directory = os.getcwd()
            logger.info(f"Detected Launch Directory (Initial CWD): {self.launch_directory}")
        except OSError as e:
            logger.critical(f"Failed to get current working directory: {e}. Falling back to app base dir.", exc_info=True)
            self.launch_directory = self.application_base_dir # Fallback

        # --- 2. Define and Ensure 'Space' Directory ---
        self.initial_directory = os.path.normpath(os.path.join(self.application_base_dir, "Space"))
        logger.info(f"Reference 'Space' directory path: {self.initial_directory}")
        try:
            os.makedirs(self.initial_directory, exist_ok=True)
            logger.info(f"Ensured reference 'Space' directory exists.")
        except OSError as e:
            logger.warning(f"Failed to create reference 'Space' directory '{self.initial_directory}': {e}.")

        # --- 3. Initialize State Variables ---
        logger.debug("Initializing state variables...")
        self.current_directory = self.launch_directory # Initial state set to launch dir
        logger.info(f"Initial internal CWD state set to Launch Directory: {self.current_directory}")

        self.conversation_history = deque(maxlen=50) # Chat history
        self.cli_command_history = deque(maxlen=100) # CLI input history
        self.cli_history_index = -1
        self.api_worker_thread: ApiWorkerThread | None = None
        self.manual_cmd_thread: ManualCommandThread | None = None
        self.settings_dialog_open = False
        self._closing = False
        logger.debug("State variables initialized.")

        # --- 4. Initialize UI Element Placeholders ---
        # (No logging needed here, just definitions)
        self.model_selector_combo: QComboBox | None = None
        self.status_indicator: StatusIndicatorWidget | None = None
        self.cli_prompt_label: QLabel | None = None
        self.cli_output_display: QTextEdit | None = None
        self.cli_input: QLineEdit | None = None
        self.chat_history_display: QTextEdit | None = None
        self.chat_input: QTextEdit | None = None
        self.send_button: QPushButton | None = None
        self.clear_chat_button: QPushButton | None = None
        self.clear_cli_button: QPushButton | None = None
        self.splitter: QSplitter | None = None
        self.status_bar = None

        # --- 5. Load State (History, etc.) ---
        # load_state() has its own logging
        logger.info("Loading initial state (Chat/CLI History, etc.)...")
        try:
            self.load_state() # Defined in StateMixin
            logger.info(f"State loaded. Internal CWD is now: {self.current_directory}")
        except Exception as e:
            logger.error("Error during initial state load.", exc_info=True)
            # load_state() has fallback logic, but log the error here too

        # --- 6. Sync Process CWD ---
        self._sync_process_cwd() # Method contains logging

        # --- 7. Basic Window Setup ---
        logger.debug("Setting up basic window properties (title, geometry, icon)...")
        self.setWindowTitle(APP_NAME)
        self.setGeometry(100, 100, 850, 585) # Default geometry
        self.set_window_icon() # Defined in UpdatesMixin (should add logging there)
        logger.debug("Basic window setup complete.")

        # --- 8. Setup UI Elements ---
        logger.info("Setting up UI elements...")
        try:
            self.setup_ui() # Calls create_ui_elements
            logger.info("UI elements created and assigned.")
            # Verify key widgets were created
            if not self.cli_input: logger.warning("cli_input widget was not created during setup_ui!")
            if not self.chat_input: logger.warning("chat_input widget was not created during setup_ui!")
            if not self.splitter: logger.warning("splitter widget was not created during setup_ui!")
        except Exception as ui_setup_err:
             logger.critical("CRITICAL error during UI setup!", exc_info=True)
             # Optionally show error to user and exit?
             QMessageBox.critical(self, "UI Setup Error", f"Failed to set up UI elements:\n{ui_setup_err}")
             sys.exit(1)

        # --- 9. Restore Splitter State ---
        logger.debug("Restoring splitter state...")
        try:
            settings = config.get_settings()
            splitter_state_value = settings.value("ui/splitter_state") # Fetch raw value
            if self.splitter and splitter_state_value:
                # Check type before restoring (should be bytes or bytearray)
                if isinstance(splitter_state_value, (bytes, bytearray)):
                    if self.splitter.restoreState(splitter_state_value):
                        logger.info("Restored splitter state from settings.")
                    else:
                        logger.warning("Failed to restore splitter state (restoreState returned False). Setting defaults.")
                        self._set_default_splitter_sizes()
                else:
                    logger.warning(f"Invalid splitter state type found in settings: {type(splitter_state_value)}. Setting defaults.")
                    self._set_default_splitter_sizes()
            elif self.splitter:
                logger.info("No splitter state found in settings or splitter invalid. Setting default sizes.")
                self._set_default_splitter_sizes()
            else:
                logger.warning("Splitter object not found after UI setup. Cannot restore/set state.")
        except Exception as e:
            logger.error("Error restoring or setting splitter sizes.", exc_info=True)
            if self.splitter: self._set_default_splitter_sizes() # Try setting defaults on error

        # --- 10. Post-UI Setup ---
        # apply_theme_specific_styles() and load_and_apply_state() should have own logging
        logger.info("Applying theme-specific styles...")
        self.apply_theme_specific_styles()
        logger.info("Loading and applying display state (history, etc.)...")
        self.load_and_apply_state()

        # --- Event Filter Installation ---
        logger.debug("Installing event filters for focus switching...")
        filter_installed = False
        if self.cli_input:
            self.cli_input.installEventFilter(self)
            logger.debug("Installed event filter on cli_input.")
            filter_installed = True
        else:
            logger.warning("cli_input not initialized, cannot install event filter.")

        if self.chat_input:
            self.chat_input.installEventFilter(self)
            logger.debug("Installed event filter on chat_input.")
            filter_installed = True
        else:
            logger.warning("chat_input not initialized, cannot install event filter.")
        if not filter_installed: logger.warning("No event filters installed for focus switching.")

        # --- 11. Set Initial Status ---
        # update_status_indicator() and update_model_selector() should have logging
        logger.debug("Updating initial status indicator and model selector...")
        self.update_status_indicator(False)
        self.update_model_selector()

        # --- 12. Add Welcome Message ---
        if not self.conversation_history:
             welcome_message = f"欢迎使用 {APP_NAME}！当前工作目录已设置为您的启动目录: '{self.current_directory}'。\n输入 '/help' 查看命令。"
             logger.info("Adding initial welcome message.")
             # add_chat_message should have its own logging
             self.add_chat_message("System", welcome_message, add_to_internal_history=False)
        else:
             logger.info(f"Skipping initial welcome message as {len(self.conversation_history)} history items were loaded.")

        # --- 13. Update Prompt & Focus ---
        logger.debug("Updating initial CLI prompt...")
        self.update_prompt() # Should have logging

        # <<< MODIFICATION: Set initial focus to chat input >>>
        if self.chat_input:
            logger.info("Setting initial focus to chat input.") # Changed log level to INFO for visibility
            self.chat_input.setFocus()
        elif self.cli_input: # Fallback to CLI if chat input somehow failed
             logger.warning("Chat input not available. Falling back to setting focus on CLI input.")
             self.cli_input.setFocus()
        else:
             logger.warning("Cannot set initial focus, neither chat_input nor cli_input are available.")
        # <<< END MODIFICATION >>>

        init_duration = time.monotonic() - start_time
        logger.info(f"--- MainWindow Initialization Finished ({init_duration:.3f}s) ---")

    def _sync_process_cwd(self):
        """Attempts to set the OS process CWD to self.current_directory with fallbacks."""
        logger.info(f"Attempting to sync OS process CWD to internal state: {self.current_directory}")
        target_dir_to_set = self.current_directory
        original_os_cwd = os.getcwd() # Get current OS CWD for comparison

        if original_os_cwd == target_dir_to_set:
            logger.info("OS process CWD already matches target directory. No change needed.")
            return

        try:
            if os.path.isdir(target_dir_to_set):
                os.chdir(target_dir_to_set)
                # Verify change
                if os.getcwd() == target_dir_to_set:
                    logger.info(f"Successfully set OS process CWD to: {target_dir_to_set}")
                else:
                     # This case is unlikely but possible with complex permissions/mounts
                     logger.error(f"OS chdir to '{target_dir_to_set}' reported success, but getcwd() returned '{os.getcwd()}'. CWD sync failed.")
                     # Revert internal state? Or keep internal state and log discrepancy? Let's log.
                     # self.current_directory = os.getcwd() # Option: Revert internal state
            else:
                logger.warning(f"Target directory '{target_dir_to_set}' is not valid or inaccessible. Falling back...")
                fallback_used = False
                # Try falling back to initial ('Space') directory
                if os.path.isdir(self.initial_directory):
                    logger.info(f"Attempting fallback to initial directory: {self.initial_directory}")
                    os.chdir(self.initial_directory)
                    if os.getcwd() == self.initial_directory:
                         logger.info(f"OS Process CWD set to fallback (Space dir): {self.initial_directory}")
                         self.current_directory = self.initial_directory # Update internal state
                         self.save_state() # Save the new fallback state
                         fallback_used = True
                    else:
                         logger.error(f"Fallback to '{self.initial_directory}' failed. getcwd() is '{os.getcwd()}'.")
                else:
                    logger.warning(f"Fallback 'Space' directory '{self.initial_directory}' also invalid or inaccessible.")

                # If Space fallback failed, try app base directory
                if not fallback_used:
                     if os.path.isdir(self.application_base_dir):
                         logger.info(f"Attempting fallback to application base directory: {self.application_base_dir}")
                         os.chdir(self.application_base_dir)
                         if os.getcwd() == self.application_base_dir:
                             logger.info(f"OS Process CWD set to fallback (app base dir): {self.application_base_dir}")
                             self.current_directory = self.application_base_dir
                             self.save_state()
                             fallback_used = True
                         else:
                             logger.error(f"Fallback to '{self.application_base_dir}' failed. getcwd() is '{os.getcwd()}'.")
                     else:
                          logger.warning(f"Application base directory '{self.application_base_dir}' also invalid or inaccessible.")

                # If all fallbacks fail, log the final state
                if not fallback_used:
                    final_cwd = os.getcwd()
                    logger.critical(f"All CWD sync attempts failed. OS process CWD remains at '{final_cwd}'.")
                    # Update internal state to match the final OS reality
                    if self.current_directory != final_cwd:
                         logger.warning(f"Updating internal CWD state from '{self.current_directory}' to match OS CWD '{final_cwd}'.")
                         self.current_directory = final_cwd
                         # Maybe save this unexpected state?
                         # self.save_state()
        except OSError as e:
            logger.critical(f"OSError occurred during CWD sync to '{target_dir_to_set}'.", exc_info=True)
            final_cwd = os.getcwd()
            logger.warning(f"Using OS CWD '{final_cwd}' due to exception during sync.")
            if self.current_directory != final_cwd:
                 self.current_directory = final_cwd
                 # self.save_state() # Save the state resulting from the error?
        except Exception as e:
             logger.critical("Unexpected error during CWD sync.", exc_info=True)
             final_cwd = os.getcwd()
             logger.warning(f"Using OS CWD '{final_cwd}' due to unexpected exception.")
             if self.current_directory != final_cwd:
                 self.current_directory = final_cwd
                 # self.save_state()

        # Update prompt regardless of success/failure to reflect final internal state
        self.update_prompt()
        logger.info("CWD synchronization process finished.")


    def setup_ui(self):
        """Creates and arranges all UI widgets by calling the external setup function."""
        logger.info("Calling create_ui_elements...")
        create_ui_elements(self) # External function, assumed to work or raise error
        logger.info("create_ui_elements finished.")


    def _set_default_splitter_sizes(self):
        """Helper to set default splitter sizes."""
        if self.splitter:
            try:
                # Use a reasonable default split ratio, e.g., 55% CLI, 45% Chat
                default_width = self.geometry().width() # Use current width
                if default_width < 100: # Prevent division by zero or tiny sizes
                     logger.warning(f"Window width ({default_width}) too small for default splitter sizes. Skipping.")
                     return
                cli_width = int(default_width * 0.55)
                chat_width = default_width - cli_width
                logger.info(f"Setting default splitter sizes: CLI={cli_width}, Chat={chat_width}")
                self.splitter.setSizes([cli_width, chat_width])
            except Exception as e:
                logger.error("Could not set default splitter sizes.", exc_info=True)
        else:
            logger.warning("Cannot set default splitter sizes: splitter widget not found.")

    def eventFilter(self, watched, event):
        """Handles Tab key presses on cli_input and chat_input for focus switching."""
        if not self.cli_input or not self.chat_input:
             # Log this only once or rarely if it occurs often
             # logger.debug("Event filter called but input widgets not ready.")
             return super().eventFilter(watched, event)

        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()

            is_tab = key == Qt.Key.Key_Tab
            is_shift_tab = key == Qt.Key.Key_Backtab or (is_tab and (modifiers & Qt.KeyboardModifier.ShiftModifier))
            is_plain_tab = is_tab and not (modifiers & Qt.KeyboardModifier.ShiftModifier)

            # --- Handle Plain Tab (Forward) ---
            if is_plain_tab:
                if watched == self.cli_input:
                    logger.debug("Tab pressed on CLI input, focusing chat input.")
                    self.chat_input.setFocus()
                    return True # Event handled
                elif watched == self.chat_input:
                    logger.debug("Tab pressed on Chat input, focusing CLI input.")
                    self.cli_input.setFocus()
                    return True # Event handled

            # --- Handle Shift+Tab (Backward) ---
            elif is_shift_tab:
                 if watched == self.cli_input:
                     logger.debug("Shift+Tab pressed on CLI input, focusing chat input.")
                     self.chat_input.setFocus()
                     return True # Event handled
                 elif watched == self.chat_input:
                     logger.debug("Shift+Tab pressed on Chat input, focusing CLI input.")
                     self.cli_input.setFocus()
                     return True # Event handled

        # Pass unhandled events to the base class
        return super().eventFilter(watched, event)


    def show_help(self):
        """Displays help information in the chat window."""
        logger.info("Displaying help information in chat window.")
        # (Help text content remains the same)
        help_title = f"--- {APP_NAME} 帮助 ---"
        core_info = f"""
**主要操作:**
1.  **与 AI 对话 (上方聊天窗口):**
    - 从工具栏选择要使用的 AI 模型。
    - 输入你的任务请求 (例如: "列出当前目录的 python 文件", "创建 temp 目录", "模拟按下 CTRL+C 组合键")。
    - AI 会回复，并将建议的 `<cmd>命令</cmd>` 或 `<function>键盘动作</function>` 在下方 CLI 窗口回显后自动执行。
    - (可选) 如果在设置中启用“自动将近期 CLI 输出作为上下文发送给 AI”，则左侧 CLI 输出的**全部**内容会自动作为上下文发送。
    - 输入以 `/` 开头的命令执行特殊操作。
2.  **执行手动命令 (下方命令行窗口):**
    - 应用程序启动时，默认工作目录是您**启动程序时所在的目录**。
    - 输入标准的 Shell 命令 (如 `dir`, `ls -l`, `cd ..`, `python script.py`)。
    - 按 Enter 执行。命令和工作目录会回显在下方 CLI 窗口。
    - 使用 `↑` / `↓` 键浏览命令历史。
    - 使用 `cd <目录>` 更改工作目录 (使用 `/cwd` 命令查看当前目录)。
    - 使用 `cls` (Win) 或 `clear` (Linux/Mac) 清空此窗口。
    - **按 `Tab` 键可在命令行和聊天输入框之间切换焦点。**
"""
        commands_title = "**常用聊天命令:**"
        cmd_help = "/help          显示此帮助信息。"
        cmd_settings = "/settings      打开设置 (API密钥, 模型列表, 主题, CLI上下文等)。"
        cmd_clear = "/clear         清除聊天窗口及历史记录。"
        cmd_clear_cli = "/clear_cli     清除命令行窗口的输出。"
        cmd_clear_all = "/clear_all     同时清除聊天和命令行窗口。"
        cmd_cwd = "/cwd           在聊天中显示当前完整工作目录。"
        cmd_copy_cli = "/copy_cli      复制左侧 CLI 窗口的全部输出到剪贴板。"
        cmd_show_cli = "/show_cli [N]  在聊天中显示左侧 CLI 输出的最后 N 行 (默认 10)。"
        cmd_save = "/save          手动保存当前状态 (历史, 工作目录, 选择的模型)。"
        cmd_exit = "/exit          退出 {APP_NAME}。"
        toolbar_info_title = "**工具栏说明:**"
        toolbar_desc = (f"- 左侧: 设置按钮。\n- 右侧: 模型选择下拉框 | 状态指示灯(🟢空闲/🔴忙碌)。")
        help_text = (f"{help_title}\n\n{core_info}\n\n"
                     f"{commands_title}\n"
                     f" {cmd_help}\n"
                     f" {cmd_settings}\n"
                     f" {cmd_clear}\n"
                     f" {cmd_clear_cli}\n"
                     f" {cmd_clear_all}\n"
                     f" {cmd_cwd}\n"
                     f" {cmd_copy_cli}\n"
                     f" {cmd_show_cli}\n"
                     f" {cmd_save}\n"
                     f" {cmd_exit}\n\n"
                     f"{toolbar_info_title}\n{toolbar_desc}\n")
        # add_chat_message should have logging
        self.add_chat_message("Help", help_text, add_to_internal_history=False)


    def closeEvent(self, event):
        """Handles window close: stop threads, save state gracefully."""
        logger.info("Close event triggered.")
        if self._closing:
            logger.warning("Close event ignored: Already closing.")
            event.ignore(); return

        self._closing = True
        logger.info("Initiating application shutdown sequence...")

        # Stop workers (methods should have own logging)
        logger.info("Stopping API worker thread (if running)...")
        api_stopped = self.stop_api_worker()
        logger.info("Stopping Manual Command worker thread (if running)...")
        manual_stopped = self.stop_manual_worker()

        # Wait for threads (optional, with timeout)
        wait_timeout_ms = 500; threads_to_wait = []
        if api_stopped and self.api_worker_thread: threads_to_wait.append(self.api_worker_thread)
        if manual_stopped and self.manual_cmd_thread: threads_to_wait.append(self.manual_cmd_thread)

        if threads_to_wait:
            logger.info(f"Waiting up to {wait_timeout_ms}ms for {len(threads_to_wait)} worker thread(s) to finish...")
            start_wait_time = time.monotonic(); all_finished = False
            while time.monotonic() - start_wait_time < wait_timeout_ms / 1000.0:
                 # Use isFinished() for QThread state check
                 all_finished = all(thread.isFinished() for thread in threads_to_wait)
                 if all_finished: break
                 QApplication.processEvents(); QThread.msleep(50)

            if all_finished: logger.info("All worker threads finished gracefully.")
            else: logger.warning("Worker thread(s) did not finish within timeout.")
        else:
             logger.info("No active worker threads needed waiting.")

        # Save final state
        logger.info("Saving final application state before closing...")
        self.save_state() # Method has logging

        logger.info("Accepting close event. Exiting application.")
        event.accept()