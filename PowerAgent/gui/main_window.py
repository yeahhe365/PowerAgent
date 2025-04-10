# ========================================
# 文件名: PowerAgent/gui/main_window.py
# (MODIFIED - Added missing imports for type hints)
# ---------------------------------------
# gui/main_window.py
# -*- coding: utf-8 -*-

import sys
import os
import time
import platform
import traceback # Keep for potential direct use or debugging
from collections import deque

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QApplication, QComboBox, QFrame,
    QLineEdit, QTextEdit, QLabel, QPushButton # Keep widgets accessed directly
)
from PySide6.QtCore import Qt, Slot, QSettings, QCoreApplication, QStandardPaths, QSize, QEvent, QThread
from PySide6.QtGui import (
    QTextCursor, QPalette, QFont, QIcon, QColor,
    QAction, QKeySequence # Keep necessary QtGui
)

# --- Project Imports ---
from constants import APP_NAME, get_color # Keep constants
from core import config # Keep config
# --- MODIFICATION START: Add imports for type hints ---
from core.workers import ApiWorkerThread, ManualCommandThread
# --- MODIFICATION END ---
# Moved to mixins
# from core.worker_utils import decode_output
# from .settings_dialog import SettingsDialog
from .palette import setup_palette # Keep palette
from .ui_components import create_ui_elements, StatusIndicatorWidget # Keep ui_components
# Moved to mixins
# from .stylesheets import STYLESHEET_TEMPLATE, MINIMAL_STYLESHEET_SYSTEM_THEME

# --- Mixin Imports ---
from .main_window_handlers import HandlersMixin
from .main_window_updates import UpdatesMixin
from .main_window_state import StateMixin
from .main_window_workers import WorkersMixin

# --- Main Window Class ---
class MainWindow(QMainWindow, HandlersMixin, UpdatesMixin, StateMixin, WorkersMixin):

    def __init__(self, application_base_dir=None, parent=None):
        # Initialize QMainWindow first
        super().__init__(parent)
        # Initialize Mixins (implicitly done via super() resolution order)

        # --- 1. Determine Base Directory ---
        if application_base_dir: self.application_base_dir = application_base_dir
        elif getattr(sys, 'frozen', False): self.application_base_dir = os.path.dirname(sys.executable)
        else:
            try: main_script_path = os.path.abspath(sys.argv[0]); self.application_base_dir = os.path.dirname(main_script_path)
            except Exception: self.application_base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"[MainWindow] Using Application Base Directory: {self.application_base_dir}")

        # --- 2. Set Initial CWD ---
        self.initial_directory = self.application_base_dir
        self.current_directory = self.initial_directory # Default before loading state

        # --- 3. Initialize State Variables ---
        # Ensure these are initialized *before* load_state is called
        self.conversation_history = deque(maxlen=50) # Chat history
        self.cli_command_history = deque(maxlen=100) # CLI input history
        self.cli_history_index = -1
        # Type hints require the classes to be imported
        self.api_worker_thread: ApiWorkerThread | None = None
        self.manual_cmd_thread: ManualCommandThread | None = None
        self.settings_dialog_open = False
        self._closing = False

        # --- 4. Initialize UI Element Placeholders ---
        # These will be populated by create_ui_elements
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
        self.status_bar = None # Will be set by self.statusBar()

        # --- 5. Load State (including CWD) ---
        # load_state is now in StateMixin
        try:
            self.load_state()
            # Sync Process CWD after loading state
            if os.path.isdir(self.current_directory):
                os.chdir(self.current_directory)
                print(f"Successfully set initial process working directory to: {self.current_directory}")
            else:
                print(f"Warning: Loaded/Initial directory '{self.current_directory}' not found. Falling back to current OS CWD.")
                self.current_directory = os.getcwd() # Get current OS CWD
                try:
                    os.chdir(self.current_directory)
                    print(f"Process CWD set to fallback: {self.current_directory}")
                except Exception as e_chdir_fallback:
                    print(f"CRITICAL: Could not set process directory even to fallback '{self.current_directory}': {e_chdir_fallback}")
            # Save the potentially updated CWD back if it fell back
            # self.save_state() # Let's avoid saving immediately after fallback on init

        except Exception as e:
            print(f"Warning: Error during initial state load or CWD sync: {e}")
            traceback.print_exc()
            # Fallback to OS CWD if load_state or initial chdir failed
            self.current_directory = os.getcwd()
            try:
                os.chdir(self.current_directory)
                print(f"Using fallback process working directory due to error: {self.current_directory}")
            except Exception as e2:
                print(f"CRITICAL: Could not set process directory even to OS CWD fallback: {e2}")

        # --- 6. Basic Window Setup ---
        self.setWindowTitle(APP_NAME)
        self.setGeometry(100, 100, 850, 585) # Adjusted default width slightly
        # set_window_icon is now in UpdatesMixin
        self.set_window_icon()

        # --- 7. Setup UI Elements ---
        self.setup_ui() # Call the method that creates UI elements

        # --- 8. Restore Splitter State ---
        try:
            settings = config.get_settings()
            splitter_state = settings.value("ui/splitter_state")
            if self.splitter and splitter_state and isinstance(splitter_state, (bytes, bytearray)):
                if self.splitter.restoreState(splitter_state):
                    print("Restored splitter state from settings.")
                else:
                    print("Warning: Failed to restore splitter state. Using default.")
                    self._set_default_splitter_sizes()
            elif self.splitter:
                 self._set_default_splitter_sizes()
                 print(f"Set default splitter sizes.")
            else:
                 print("Warning: Splitter object not found after UI setup.")
        except Exception as e:
            print(f"Error restoring or setting splitter sizes: {e}")
            if self.splitter: self._set_default_splitter_sizes()

        # --- 9. Post-UI Setup ---
        # apply_theme_specific_styles is in UpdatesMixin
        self.apply_theme_specific_styles()
        # load_and_apply_state (display history) is in UpdatesMixin
        self.load_and_apply_state()

        # --- 10. Set Initial Status ---
        # update_status_indicator is in UpdatesMixin
        self.update_status_indicator(False)
        # update_model_selector is in UpdatesMixin
        self.update_model_selector()

        # --- 11. Add Welcome Message ---
        if not self.conversation_history:
             # add_chat_message is in UpdatesMixin
             self.add_chat_message("System", f"欢迎使用 {APP_NAME}！输入 '/help' 查看命令。")
             print("[MainWindow] Added initial welcome message as history was empty.")
        else:
             print("[MainWindow] Skipping initial welcome message as history was loaded.")

        # --- 12. Update Prompt & Focus ---
        # update_prompt is in UpdatesMixin
        self.update_prompt()
        if self.cli_input:
            self.cli_input.setFocus()

    def setup_ui(self):
        """Creates and arranges all UI widgets by calling the external setup function."""
        # This function delegates the actual creation to ui_components.py
        create_ui_elements(self)

    def _set_default_splitter_sizes(self):
        """Helper to set default splitter sizes (remains in MainWindow)."""
        if self.splitter:
            try:
                default_width = self.geometry().width()
                cli_width = int(default_width * 0.55) # Adjust ratio if needed
                chat_width = default_width - cli_width
                self.splitter.setSizes([cli_width, chat_width])
            except Exception as e:
                 print(f"Warning: Could not set default splitter sizes: {e}")

    def show_help(self):
        # Displays help information in the chat window (kept in MainWindow for now)
        help_title = f"--- {APP_NAME} 帮助 ---"
        core_info = """
**主要操作:**
1.  **与 AI 对话 (上方聊天窗口):**
    - 从工具栏选择要使用的 AI 模型。
    - 输入你的任务请求 (例如: "列出当前目录的 python 文件", "创建 temp 目录", "按 CTRL+C")。
    - AI 会回复，并将建议的 `<cmd>命令</cmd>` 或 `<function>` 键盘动作在下方 CLI 窗口回显后自动执行。
    - (可选) 如果在设置中启用“自动将近期 CLI 输出作为上下文发送给 AI”，则左侧 CLI 输出的**全部**内容会自动作为上下文发送。
    - 输入 `/` 开头的命令执行特殊操作。
2.  **执行手动命令 (下方命令行窗口):**
    - 输入标准的 Shell 命令 (如 `dir`, `ls -l`, `cd ..`, `python script.py`)。
    - 按 Enter 执行。命令和工作目录会回显在上方。
    - 使用 `↑` / `↓` 键浏览命令历史。
    - 使用 `cd <目录>` 更改工作目录 (使用 `/cwd` 命令查看当前目录)。
    - 使用 `cls` (Win) 或 `clear` (Linux/Mac) 清空此窗口。
"""
        commands_title = "**常用聊天命令:**"
        cmd_help = "/help          显示此帮助。"
        cmd_settings = "/settings      打开设置 (API密钥, 模型列表, 主题, CLI上下文等)。"
        cmd_clear = "/clear         清除聊天窗口及历史。"
        cmd_clear_cli = "/clear_cli     清除命令行窗口。"
        cmd_clear_all = "/clear_all     清除聊天和命令行窗口。"
        cmd_cwd = "/cwd           在聊天中显示当前完整目录。"
        cmd_copy_cli = "/copy_cli      复制左侧 CLI 的全部输出到剪贴板。"
        cmd_show_cli = "/show_cli [N]  在聊天中显示左侧 CLI 输出的最后 N 行 (默认 10)。"
        cmd_save = "/save          手动保存当前状态 (历史, CWD, 选择的模型)。"
        cmd_exit = "/exit          退出 {APP_NAME}。"
        toolbar_info_title = "**工具栏提示:**"
        toolbar_desc = (f"- 左侧: 设置按钮。\n- 右侧: 模型选择下拉框 | 状态灯(🟢空闲/🔴忙碌)。")
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
        # add_chat_message is in UpdatesMixin
        self.add_chat_message("Help", help_text, add_to_internal_history=False)

    def closeEvent(self, event):
        # Handles window close: stop threads, save state gracefully (kept in MainWindow)
        if self._closing: event.ignore(); return # Prevent recursive close calls
        self._closing = True # Set flag to prevent further actions
        print("Close event triggered. Initiating shutdown...")

        # stop_api_worker and stop_manual_worker are in WorkersMixin
        api_stopped = self.stop_api_worker()
        manual_stopped = self.stop_manual_worker()

        # Wait briefly for threads to finish if they were running
        wait_timeout_ms = 500 # Max wait time in milliseconds
        threads_to_wait = []
        # Access thread attributes directly here (MainWindow owns them)
        if api_stopped and self.api_worker_thread: threads_to_wait.append(self.api_worker_thread)
        if manual_stopped and self.manual_cmd_thread: threads_to_wait.append(self.manual_cmd_thread)

        if threads_to_wait:
            print(f"Waiting up to {wait_timeout_ms}ms for {len(threads_to_wait)} worker thread(s) to finish...")
            start_wait_time = time.monotonic()
            all_finished = False
            while time.monotonic() - start_wait_time < wait_timeout_ms / 1000.0:
                 # Check isRunning() directly on thread attributes
                 all_finished = all(not thread.isRunning() for thread in threads_to_wait)
                 if all_finished: break
                 QApplication.processEvents() # Allow signals to process
                 QThread.msleep(50) # Small sleep
            if all_finished: print("All worker threads finished gracefully.")
            else: print("Warning: Worker thread(s) did not finish within the timeout.")

        print("Saving final state before closing...")
        # save_state is in StateMixin
        self.save_state() # Save history, CWD, selection etc.

        print("Exiting application.")
        event.accept() # Allow the window to close