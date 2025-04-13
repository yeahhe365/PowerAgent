# ========================================
# 文件名: PowerAgent/gui/main_window.py
# (MODIFIED - Added event filter for Tab key focus switching between CLI and Chat inputs)
# ---------------------------------------
# gui/main_window.py
# -*- coding: utf-8 -*-

import sys
import os
import time
import platform
import traceback
from collections import deque

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QApplication, QComboBox, QFrame,
    QLineEdit, QTextEdit, QLabel, QPushButton
)
# <<< MODIFICATION START: Import QEvent >>>
from PySide6.QtCore import Qt, Slot, QSettings, QCoreApplication, QStandardPaths, QSize, QEvent, QThread
# <<< MODIFICATION END >>>
from PySide6.QtGui import (
    QTextCursor, QPalette, QFont, QIcon, QColor,
    QAction, QKeySequence # Keep QKeySequence for HandlersMixin keyPressEvent type hint
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

# --- Main Window Class ---
class MainWindow(QMainWindow, HandlersMixin, UpdatesMixin, StateMixin, WorkersMixin):

    def __init__(self, application_base_dir=None, parent=None):
        # Initialize QMainWindow first
        super().__init__(parent)

        # --- 1. Determine Base Directory ---
        # (Logic remains the same as before)
        if application_base_dir: self.application_base_dir = application_base_dir
        elif getattr(sys, 'frozen', False): self.application_base_dir = os.path.dirname(sys.executable)
        else:
            try: main_script_path = os.path.abspath(sys.argv[0]); self.application_base_dir = os.path.dirname(main_script_path)
            except Exception: self.application_base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"[MainWindow] Using Application Base Directory: {self.application_base_dir}")

        # --- 1.5 Get Launch Directory EARLY ---
        try:
            # This gets the directory where the script/exe was *launched from*
            self.launch_directory = os.getcwd()
            print(f"[MainWindow] Detected Launch Directory (Initial CWD): {self.launch_directory}")
        except OSError as e:
            print(f"CRITICAL: Failed to get current working directory: {e}. Falling back to app base dir.")
            self.launch_directory = self.application_base_dir # Fallback

        # --- 2. Define and Ensure 'Space' Directory ---
        # (Logic remains the same as before)
        self.initial_directory = os.path.normpath(os.path.join(self.application_base_dir, "Space"))
        print(f"[MainWindow] Reference 'Space' directory path: {self.initial_directory}")
        try:
            os.makedirs(self.initial_directory, exist_ok=True)
            print(f"[MainWindow] Ensured reference 'Space' directory exists: {self.initial_directory}")
        except OSError as e:
            print(f"Warning: Failed to create reference 'Space' directory '{self.initial_directory}': {e}.")

        # --- 3. Initialize State Variables ---
        # Set current_directory initially to the LAUNCH directory captured above.
        self.current_directory = self.launch_directory
        print(f"[MainWindow] Initializing internal CWD state to Launch Directory: {self.current_directory}")

        self.conversation_history = deque(maxlen=50) # Chat history
        self.cli_command_history = deque(maxlen=100) # CLI input history
        self.cli_history_index = -1
        self.api_worker_thread: ApiWorkerThread | None = None
        self.manual_cmd_thread: ManualCommandThread | None = None
        self.settings_dialog_open = False
        self._closing = False

        # --- 4. Initialize UI Element Placeholders ---
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
        try:
            print("[MainWindow] Loading state (Chat/CLI History, Selected Model)...")
            self.load_state() # Defined in StateMixin (Should NO LONGER load CWD)
            print(f"[MainWindow] State loaded. CWD remains: {self.current_directory}")
        except Exception as e:
            print(f"Warning: Error during initial state load: {e}")
            traceback.print_exc()

        # --- 6. Sync Process CWD ---
        self._sync_process_cwd() # Call the helper method

        # --- 7. Basic Window Setup ---
        self.setWindowTitle(APP_NAME)
        self.setGeometry(100, 100, 850, 585)
        self.set_window_icon() # Defined in UpdatesMixin

        # --- 8. Setup UI Elements ---
        self.setup_ui() # Calls create_ui_elements which assigns widgets to self

        # --- 9. Restore Splitter State ---
        try:
            settings = config.get_settings()
            splitter_state = settings.value("ui/splitter_state")
            if self.splitter and splitter_state and isinstance(splitter_state, (bytes, bytearray)):
                if self.splitter.restoreState(splitter_state): print("[MainWindow] Restored splitter state from settings.")
                else: print("[MainWindow] Warning: Failed to restore splitter state."); self._set_default_splitter_sizes()
            elif self.splitter: self._set_default_splitter_sizes(); print(f"[MainWindow] Set default splitter sizes.")
            else: print("[MainWindow] Warning: Splitter object not found after UI setup.")
        except Exception as e:
            print(f"[MainWindow] Error restoring or setting splitter sizes: {e}")
            if self.splitter: self._set_default_splitter_sizes()

        # --- 10. Post-UI Setup ---
        self.apply_theme_specific_styles() # Defined in UpdatesMixin
        self.load_and_apply_state()      # Defined in UpdatesMixin (displays history etc.)

        # <<< MODIFICATION START: Install event filter for Tab key >>>
        # Ensure this happens AFTER setup_ui has created the widgets
        if self.cli_input:
            self.cli_input.installEventFilter(self)
            print("[MainWindow] Installed event filter on cli_input.")
        else:
            print("[MainWindow] Warning: cli_input not initialized, cannot install event filter.")

        if self.chat_input:
            self.chat_input.installEventFilter(self)
            print("[MainWindow] Installed event filter on chat_input.")
        else:
            print("[MainWindow] Warning: chat_input not initialized, cannot install event filter.")
        # <<< MODIFICATION END >>>

        # --- 11. Set Initial Status ---
        self.update_status_indicator(False) # Defined in UpdatesMixin
        self.update_model_selector()      # Defined in UpdatesMixin

        # --- 12. Add Welcome Message ---
        if not self.conversation_history:
             welcome_message = f"欢迎使用 {APP_NAME}！当前工作目录已设置为您的启动目录: '{self.current_directory}'。\n输入 '/help' 查看命令。"
             self.add_chat_message("System", welcome_message, add_to_internal_history=False)
             print(f"[MainWindow] Added initial welcome message (CWD: {self.current_directory}).")
        else:
             print("[MainWindow] Skipping initial welcome message as history was loaded.")

        # --- 13. Update Prompt & Focus ---
        self.update_prompt() # Defined in UpdatesMixin (Will show the launch directory)
        if self.cli_input:
            self.cli_input.setFocus() # Initial focus on CLI input

    def _sync_process_cwd(self):
        """Attempts to set the OS process CWD to self.current_directory with fallbacks."""
        # (No changes needed in this method body)
        print(f"[MainWindow] Attempting to sync OS process CWD to: {self.current_directory}")
        target_dir_to_set = self.current_directory
        try:
            if os.path.isdir(target_dir_to_set):
                os.chdir(target_dir_to_set)
                print(f"[MainWindow] Successfully set OS process CWD to: {target_dir_to_set}")
            else:
                print(f"Warning: Launch directory '{target_dir_to_set}' is not valid or inaccessible. Falling back...")
                if os.path.isdir(self.initial_directory):
                    self.current_directory = self.initial_directory
                    os.chdir(self.current_directory)
                    print(f"[MainWindow] OS Process CWD set to fallback (Space dir): {self.current_directory}")
                    self.save_state()
                else:
                    print(f"Warning: Fallback 'Space' directory '{self.initial_directory}' also invalid. Falling back to app base.")
                    if os.path.isdir(self.application_base_dir):
                         self.current_directory = self.application_base_dir
                         os.chdir(self.current_directory)
                         print(f"[MainWindow] OS Process CWD set to fallback (app base dir): {self.current_directory}")
                         self.save_state()
                    else:
                        print(f"CRITICAL: App base directory '{self.application_base_dir}' also invalid. Using OS default CWD.")
                        final_cwd = os.getcwd(); self.current_directory = final_cwd
                        print(f"[MainWindow] OS Process CWD remains at default: {self.current_directory}")
        except OSError as e:
            print(f"CRITICAL: OSError occurred during CWD sync to '{target_dir_to_set}': {e}")
            traceback.print_exc()
            final_cwd = os.getcwd(); self.current_directory = final_cwd
            print(f"[MainWindow] Using OS CWD due to exception during sync: {self.current_directory}")
        self.update_prompt()

    def setup_ui(self):
        """Creates and arranges all UI widgets by calling the external setup function."""
        # (No changes needed here)
        create_ui_elements(self)

    def _set_default_splitter_sizes(self):
        """Helper to set default splitter sizes."""
        # (No changes needed here)
        if self.splitter:
            try:
                default_width = self.geometry().width(); cli_width = int(default_width * 0.55)
                chat_width = default_width - cli_width; self.splitter.setSizes([cli_width, chat_width])
            except Exception as e: print(f"[MainWindow] Warning: Could not set default splitter sizes: {e}")

    # ============================================================= #
    # <<< MODIFICATION START: Add eventFilter for Tab key >>>
    # ============================================================= #
    def eventFilter(self, watched, event):
        """Handles Tab key presses on cli_input and chat_input for focus switching."""
        # Ensure the widgets we care about actually exist before proceeding
        if not self.cli_input or not self.chat_input:
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
                    # print("Tab pressed on CLI input, focusing chat input") # Debug
                    self.chat_input.setFocus()
                    return True # Event handled, stop further processing
                elif watched == self.chat_input:
                    # print("Tab pressed on Chat input, focusing CLI input") # Debug
                    self.cli_input.setFocus()
                    return True # Event handled

            # --- Handle Shift+Tab (Backward) ---
            elif is_shift_tab:
                 if watched == self.cli_input:
                     # print("Shift+Tab pressed on CLI input, focusing chat input") # Debug
                     # Moving from CLI with Shift+Tab should go to Chat Input
                     self.chat_input.setFocus()
                     return True # Event handled
                 elif watched == self.chat_input:
                     # print("Shift+Tab pressed on Chat input, focusing CLI input") # Debug
                     # Moving from Chat with Shift+Tab should go to CLI Input
                     self.cli_input.setFocus()
                     return True # Event handled

        # If the event wasn't handled (not Tab/Shift+Tab or not on the watched widgets),
        # pass it to the base class implementation. This allows standard key processing
        # (like character input, Enter, Backspace) in the input fields.
        return super().eventFilter(watched, event)
    # ============================================================= #
    # <<< MODIFICATION END >>>
    # ============================================================= #

    # ============================================================= #
    # <<< MODIFICATION START: Updated Help Text to include Tab info >>>
    # ============================================================= #
    def show_help(self):
        """Displays help information in the chat window."""
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
        self.add_chat_message("Help", help_text, add_to_internal_history=False)
    # ============================================================= #
    # <<< MODIFICATION END >>>
    # ============================================================= #

    def closeEvent(self, event):
        # Handles window close: stop threads, save state gracefully
        # (No changes needed here)
        if self._closing: event.ignore(); return
        self._closing = True
        print("[MainWindow] Close event triggered. Initiating shutdown...")

        api_stopped = self.stop_api_worker()
        manual_stopped = self.stop_manual_worker()

        wait_timeout_ms = 500; threads_to_wait = []
        if api_stopped and self.api_worker_thread: threads_to_wait.append(self.api_worker_thread)
        if manual_stopped and self.manual_cmd_thread: threads_to_wait.append(self.manual_cmd_thread)

        if threads_to_wait:
            print(f"[MainWindow] Waiting up to {wait_timeout_ms}ms for {len(threads_to_wait)} worker thread(s)...")
            start_wait_time = time.monotonic(); all_finished = False
            while time.monotonic() - start_wait_time < wait_timeout_ms / 1000.0:
                 all_finished = all(not thread.isRunning() for thread in threads_to_wait)
                 if all_finished: break
                 QApplication.processEvents(); QThread.msleep(50) # Use QThread.msleep for better Qt integration
            if all_finished: print("[MainWindow] All worker threads finished gracefully.")
            else: print("[MainWindow] Warning: Worker thread(s) did not finish within timeout.")

        print("[MainWindow] Saving final state before closing...")
        self.save_state() # Defined in StateMixin

        print("[MainWindow] Exiting application.")
        event.accept()

# Note: The HandlersMixin (in main_window_handlers.py) contains the keyPressEvent
# which handles Up/Down arrows in the CLI input. That logic remains separate and correct.
# The eventFilter added here specifically handles the Tab/Shift+Tab focus switching
# between the two designated input widgets.