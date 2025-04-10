# ========================================
# 文件名: PowerAgent/gui/main_window.py
# (MODIFIED)
# ---------------------------------------
# gui/main_window.py
# -*- coding: utf-8 -*-

import sys
import os
import json
import platform
import re
import time
from collections import deque

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter,
    QDialog, QApplication, QFrame, QLineEdit, QTextEdit,
    QMessageBox, QLabel, QPushButton, QComboBox # <<< Added QComboBox
)
from PySide6.QtCore import Qt, Slot, QSettings, QCoreApplication, QStandardPaths, QSize, QStringListModel, QEvent, QTimer,QThread
from PySide6.QtGui import (
    QTextCursor, QPalette, QFont, QIcon, QColor,
    QAction, QKeySequence, QTextCharFormat, QClipboard
)

# Import from other project modules
from constants import APP_NAME, get_color
from core import config # Now includes CLI context AND timestamp settings (modified)
from core.workers import ApiWorkerThread, ManualCommandThread, _decode_output
from .settings_dialog import SettingsDialog
from .palette import setup_palette
from .ui_components import create_ui_elements, StatusIndicatorWidget
from .stylesheets import STYLESHEET_TEMPLATE, MINIMAL_STYLESHEET_SYSTEM_THEME

# Keep imports for types used in method signatures, event filters, or direct manipulation.
# QFrame is still needed for separators.


class MainWindow(QMainWindow):

    def __init__(self, application_base_dir=None, parent=None):
        super().__init__(parent)

        # Determine Application Base Directory (same logic)
        if application_base_dir: self.application_base_dir = application_base_dir
        elif getattr(sys, 'frozen', False): self.application_base_dir = os.path.dirname(sys.executable)
        else:
            try: main_script_path = os.path.abspath(sys.argv[0]); self.application_base_dir = os.path.dirname(main_script_path)
            except Exception: self.application_base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"[MainWindow] Using Application Base Directory: {self.application_base_dir}")

        # Set initial CWD based on application dir FIRST
        self.initial_directory = self.application_base_dir
        self.current_directory = self.initial_directory

        # Initialize State Variables
        self.conversation_history = deque(maxlen=50) # Chat history for display AND API
        self.api_worker_thread = None
        self.manual_cmd_thread = None
        self.settings_dialog_open = False
        self.cli_command_history = deque(maxlen=100) # Only for CLI input history
        self.cli_history_index = -1
        self._closing = False

        # --- Initialize UI Element Placeholders ---
        # self.toolbar_cwd_label = None # <<< REMOVED >>>
        self.model_selector_combo: QComboBox = None # New Combo Box
        self.status_indicator: StatusIndicatorWidget = None
        self.cli_prompt_label = None
        self.cli_output_display = None; self.cli_input = None
        self.chat_history_display = None; self.chat_input = None
        self.send_button = None; self.clear_chat_button = None
        self.clear_cli_button = None # <<< ADDED: Placeholder for the new button >>>
        self.splitter = None
        self.status_bar = None
        # --- End UI Element Placeholders ---

        # Load state AFTER setting initial CWD (same logic)
        try:
            self.load_state()
            if os.path.isdir(self.current_directory):
                os.chdir(self.current_directory)
                print(f"Successfully set initial process working directory to: {self.current_directory}")
            else:
                print(f"Warning: Current directory '{self.current_directory}' (loaded or initial) not found. Falling back to CWD.")
                self.current_directory = os.getcwd()
                os.chdir(self.current_directory)
                print(f"Using current working directory as fallback: {self.current_directory}")
        except Exception as e:
            print(f"Warning: Could not change process directory to '{self.current_directory}': {e}")
            self.current_directory = os.getcwd()
            try: os.chdir(self.current_directory)
            except Exception as e2: print(f"CRITICAL: Could not set process directory even to fallback '{self.current_directory}': {e2}")
            print(f"Using fallback process working directory: {self.current_directory}")

        # Basic Window Setup
        self.setWindowTitle(APP_NAME)
        self.setGeometry(100, 100, 850, 585) # <<< Adjusted default width slightly >>>
        self.set_window_icon()

        # Setup UI Elements using the external function
        self.setup_ui() # UI must be set up before load_and_apply_state

        # --- Restore Splitter State ---
        try:
            settings = config.get_settings()
            splitter_state = settings.value("ui/splitter_state")
            if self.splitter and splitter_state and isinstance(splitter_state, (bytes, bytearray)):
                self.splitter.restoreState(splitter_state)
                print("Restored splitter state from settings.")
            elif self.splitter:
                 # Adjust default split based on new window width
                 default_width = self.geometry().width()
                 cli_width = int(default_width * 0.55)
                 chat_width = default_width - cli_width
                 self.splitter.setSizes([cli_width, chat_width])
                 print(f"Set default splitter sizes ({cli_width}/{chat_width}) during UI creation.")
            else:
                 print("Warning: Splitter object not found after UI setup.")
        except Exception as e:
            print(f"Could not restore or verify splitter sizes: {e}")

        # Post-UI Setup
        self.apply_theme_specific_styles() # Applies theme + initial styles
        self.load_and_apply_state() # Applies loaded history to display

        # Set initial status display
        self.update_status_indicator(False)
        self.update_model_selector()

        # Add welcome message
        if not self.conversation_history:
             self.add_chat_message("System", f"欢迎使用 {APP_NAME}！输入 '/help' 查看命令。")
             print("[MainWindow] Added initial welcome message as history was empty.")
        else:
             print("[MainWindow] Skipping initial welcome message as history was loaded.")

        # Update CLI prompt (CWD label in toolbar removed)
        self.update_prompt()
        if self.cli_input:
            self.cli_input.setFocus()

    def setup_ui(self):
        """Creates and arranges all UI widgets by calling the external setup function."""
        create_ui_elements(self)

    def eventFilter(self, watched, event):
        # Handles Shift+Enter in chat input (same logic)
        if watched == self.chat_input and event.type() == QEvent.Type.KeyPress:
            key = event.key(); modifiers = event.modifiers()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not (modifiers & Qt.KeyboardModifier.ShiftModifier):
                    self.handle_send_message()
                    return True
                else:
                    # Allow default behavior (insert newline)
                    pass
        return super().eventFilter(watched, event)

    def _get_icon(self, theme_name: str, fallback_filename: str, text_fallback: str = None) -> QIcon:
        # Helper to get themed icons or fallbacks (same logic)
        icon = QIcon.fromTheme(theme_name)
        if icon.isNull():
            assets_dir = os.path.join(self.application_base_dir, "assets"); icon_path = os.path.join(assets_dir, fallback_filename)
            if os.path.exists(icon_path): icon = QIcon(icon_path);
            if icon.isNull(): print(f"Warning: Icon theme '{theme_name}' not found and fallback '{fallback_filename}' does not exist in {assets_dir}.")
        return icon

    def set_window_icon(self):
        # Sets the main application window icon (same logic)
        try:
            icon = self._get_icon(APP_NAME.lower(), "icon.png", None)
            if icon.isNull(): icon = self._get_icon("utilities-terminal", "app.ico", None)
            if not icon.isNull(): self.setWindowIcon(icon)
            else: print("Could not find a suitable window icon via theme or fallback.")
        except Exception as e: print(f"Error setting window icon: {e}")

    # --- UI Update and Helper Methods ---

    def _get_os_fonts(self):
        # Helper to get platform-specific monospace fonts (same logic)
        mono_font_family = "Consolas, Courier New"
        mono_font_size = 10
        label_font_size = 9
        if platform.system() == "Windows": pass
        elif platform.system() == "Darwin": mono_font_family, mono_font_size, label_font_size = "Menlo", 11, 9
        elif platform.system() == "Linux": mono_font_family, mono_font_size, label_font_size = "Monospace", 10, 9
        return mono_font_family, mono_font_size, label_font_size

    def apply_theme_specific_styles(self):
        # Applies the QSS stylesheet based on the current theme
        if self._closing: return
        theme = config.APP_THEME
        print(f"Applying styles for theme: {theme}")
        mono_font_family, mono_font_size, label_font_size = self._get_os_fonts()
        qss = ""
        app_instance = QApplication.instance()
        if not app_instance: print("Warning: QApplication instance not found during style application."); return

        palette = app_instance.palette()
        border_color_role = QPalette.ColorRole.Mid; border_color = palette.color(border_color_role)
        if not border_color.isValid(): border_color = palette.color(QPalette.ColorRole.Dark)
        if not border_color.isValid(): border_color = QColor(180, 180, 180) # Fallback
        border_color_name = border_color.name()

        if theme == "system":
            qss = MINIMAL_STYLESHEET_SYSTEM_THEME.format(
                mono_font_family=mono_font_family, mono_font_size=mono_font_size,
                label_font_size=label_font_size, border=border_color_name
            )
            print("Applied system theme (minimal QSS). Relies on global palette.")
        else: # "dark" or "light"
            cli_bg=get_color("cli_bg", theme); cli_output_color=get_color("cli_output", theme); prompt_color=get_color("prompt", theme); border_color_const=get_color("border", theme)
            text_main_color=get_color("text_main", theme); status_label_color=get_color("status_label", theme)
            # cwd_label_color=get_color("cwd_label", theme) # <<< REMOVED CWD Label Color >>>
            window_bg=palette.color(QPalette.ColorRole.Window).name(); base_bg=palette.color(QPalette.ColorRole.Base).name(); highlight_bg=palette.color(QPalette.ColorRole.Highlight).name(); highlighted_text=palette.color(QPalette.ColorRole.HighlightedText).name()
            button_bg=palette.color(QPalette.ColorRole.Button).name(); button_text_color=palette.color(QPalette.ColorRole.ButtonText).name(); tooltip_bg=palette.color(QPalette.ColorRole.ToolTipBase).name(); tooltip_text=palette.color(QPalette.ColorRole.ToolTipText).name()
            text_disabled=palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name(); button_disabled_bg=palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button).name()
            border_disabled=palette.color(QPalette.ColorGroup.Disabled, border_color_role).name(); button_pressed_bg=QColor(button_bg).darker(115).name()

            # <<< REMOVED cwd_label_color from format string >>>
            qss = STYLESHEET_TEMPLATE.format(
                window_bg=window_bg, base_bg=base_bg, text_main=text_main_color.name(), cli_bg=cli_bg.name(), cli_output=cli_output_color.name(), prompt_color=prompt_color.name(),
                border=border_color_const.name(), highlight_bg=highlight_bg,
                mono_font_family=mono_font_family, mono_font_size=mono_font_size, label_font_size=label_font_size, button_bg=button_bg, button_text=button_text_color,
                highlighted_text=highlighted_text, button_pressed_bg=button_pressed_bg, button_disabled_bg=button_disabled_bg, text_disabled=text_disabled,
                border_disabled=border_disabled, tooltip_bg=tooltip_bg, tooltip_text=tooltip_text, status_label_color=status_label_color.name()
            )
            print(f"Theme '{theme}' styles applied via full QSS.")

        self.setStyleSheet(qss)
        self.update()
        # self.update_cwd_label() # <<< REMOVED Call >>>
        self.update_prompt()

    def load_and_apply_state(self):
        # Applies loaded history to chat display
        if self._closing: return
        print(f"Applying {len(self.conversation_history)} loaded history items to display...")
        history_copy = list(self.conversation_history)

        if self.chat_history_display:
            self.chat_history_display.clear()
            self.conversation_history.clear() # Clear internal before re-adding
            for role, message in history_copy:
                self.add_chat_message(role, message, add_to_internal_history=True)
            print("History applied to display and internal history deque.")
        else:
            self.conversation_history = deque(history_copy, maxlen=self.conversation_history.maxlen)
            print("Warning: Chat history display not found during state application. Internal history reloaded.")

        self.update_model_selector()
        # self.update_cwd_label() # <<< REMOVED Call >>>
        self.update_prompt()

    # <<< REMOVED get_short_cwd method >>>
    # def get_short_cwd(self, max_len=35): ...

    # <<< REMOVED update_cwd_label method >>>
    # def update_cwd_label(self): ...

    def update_prompt(self):
        # (Same logic, already has check)
        if self._closing: return
        if not self.cli_prompt_label: return
        shell_prefix = "PS" if platform.system() == "Windows" else "$"
        display_path = self.current_directory
        if platform.system() == "Windows" and len(display_path) >= 2 and display_path[1] == ':':
            display_path = display_path[0].upper() + display_path[1:]
        try:
            home_dir = os.path.expanduser("~")
            home_dir_compare = home_dir
            if platform.system() == "Windows" and len(home_dir_compare) >= 2 and home_dir_compare[1] == ':':
                home_dir_compare = home_dir_compare[0].upper() + home_dir_compare[1:]
            if display_path.startswith(home_dir_compare):
                if display_path == home_dir_compare: display_path = "~"
                elif display_path.startswith(home_dir_compare + os.path.sep): display_path = "~" + display_path[len(home_dir):]
        except Exception as e: print(f"Error processing path for prompt display: {e}")
        prompt_text = f"{shell_prefix} {display_path}> "
        self.cli_prompt_label.setText(prompt_text)
        self.cli_prompt_label.setToolTip(f"当前工作目录: {self.current_directory}")

    def update_model_selector(self):
        """Updates the model selection QComboBox based on the configuration."""
        if self._closing or not self.model_selector_combo:
            return

        print("Updating model selector...")
        current_text = self.model_selector_combo.currentText() # Store current selection before clearing
        self.model_selector_combo.blockSignals(True) # Prevent signals during population
        self.model_selector_combo.clear()

        model_id_string = config.MODEL_ID_STRING
        saved_selected_model = config.CURRENTLY_SELECTED_MODEL_ID
        model_list = []
        if model_id_string:
            model_list = [m.strip() for m in model_id_string.split(',') if m.strip()]

        if not model_list:
            placeholder_text = "未配置模型"
            self.model_selector_combo.addItem(placeholder_text)
            self.model_selector_combo.setEnabled(False)
            self.model_selector_combo.setToolTip("请在设置中配置模型 ID")
            # Update config if it somehow thought a model was selected
            if config.CURRENTLY_SELECTED_MODEL_ID != "":
                config.CURRENTLY_SELECTED_MODEL_ID = ""
                self.save_state() # Persist the fact that no model is selected now
            print("Model selector updated: No models configured.")
        else:
            self.model_selector_combo.addItems(model_list)
            self.model_selector_combo.setEnabled(True)
            self.model_selector_combo.setToolTip("点击选择要使用的 AI 模型")

            found_index = self.model_selector_combo.findText(saved_selected_model)

            if saved_selected_model and found_index != -1:
                # Saved selection is valid and exists in the new list
                self.model_selector_combo.setCurrentIndex(found_index)
                print(f"Model selector updated: Restored selection '{saved_selected_model}'.")
            else:
                # Saved selection is invalid or not found, default to the first item
                default_model = model_list[0]
                self.model_selector_combo.setCurrentIndex(0)
                print(f"Model selector updated: Saved selection '{saved_selected_model}' not found or invalid. Defaulting to first item '{default_model}'.")
                # Update the config and save this default selection
                config.CURRENTLY_SELECTED_MODEL_ID = default_model
                self.save_state() # Persist the new default selection

        self.model_selector_combo.blockSignals(False) # Re-enable signals

    def update_status_indicator(self, busy: bool):
        """Updates the custom status indicator widget's state."""
        if self._closing or not self.status_indicator:
            return
        self.status_indicator.setBusy(busy)

    def is_busy(self) -> bool:
        # (Same logic)
        api_running = self.api_worker_thread and self.api_worker_thread.isRunning()
        manual_running = self.manual_cmd_thread and self.manual_cmd_thread.isRunning()
        return api_running or manual_running

    def add_chat_message(self, role: str, message: str, add_to_internal_history: bool = True):
        # Adds message to the chat display (right pane) AND internal history deque
        if self._closing or not self.chat_history_display:
            if add_to_internal_history: # Still add to internal if UI not available but requested
                message_for_history = re.sub(r"\s*\([\u0041-\uFFFF]+:\s*[\d.]+\s*[\u0041-\uFFFF]+\)$", "", message).strip()
                if not self.conversation_history or self.conversation_history[-1] != (role, message_for_history):
                    self.conversation_history.append((role, message_for_history))
                    # print(f"Added to internal history only (UI skip): {role} - {len(message_for_history)} chars")
            return

        target_widget = self.chat_history_display
        role_lower = role.lower(); role_display = role.capitalize()
        prefix_text = f"{role_display}: "; message_text = message.rstrip() + '\n'

        try:
            cursor = target_widget.textCursor(); at_end = cursor.atEnd()
            cursor.movePosition(QTextCursor.MoveOperation.End); target_widget.setTextCursor(cursor)
        except RuntimeError: print("Warning: Could not get/set text cursor."); return

        current_theme = config.APP_THEME
        char_format = QTextCharFormat(); default_text_color = target_widget.palette().color(QPalette.ColorRole.Text)
        prefix_color = None; message_color = default_text_color

        if role_lower == 'user': prefix_color = get_color('user', current_theme)
        elif role_lower == 'model': prefix_color = get_color('model', current_theme)
        elif role_lower in ['system', 'error', 'help', 'prompt']:
            prefix_color = get_color(role_lower, current_theme); message_color = prefix_color
        else: prefix_color = get_color('system', current_theme); message_color = prefix_color # Default to system color

        if not isinstance(prefix_color, QColor): prefix_color = default_text_color
        if not isinstance(message_color, QColor): message_color = default_text_color

        try:
            char_format.setForeground(prefix_color); prefix_font = char_format.font(); prefix_font.setBold(True); char_format.setFont(prefix_font)
            cursor.setCharFormat(char_format); cursor.insertText(prefix_text)
            char_format.setForeground(message_color); message_font = char_format.font(); message_font.setBold(False); char_format.setFont(message_font)
            cursor.setCharFormat(char_format); cursor.insertText(message_text)
        except RuntimeError: print("Warning: Could not insert text."); return

        if add_to_internal_history:
            message_for_history = re.sub(r"\s*\([\u0041-\uFFFF]+:\s*[\d.]+\s*[\u0041-\uFFFF]+\)$", "", message).strip()
            # Check if the message (role + content) is already the last one to avoid duplicates
            if not self.conversation_history or self.conversation_history[-1] != (role, message_for_history):
                self.conversation_history.append((role, message_for_history))
                # print(f"Added to internal history: {role} - {len(message_for_history)} chars")

        if at_end:
            scrollbar = target_widget.verticalScrollBar()
            if scrollbar:
                try: QApplication.processEvents(); scrollbar.setValue(scrollbar.maximum()); target_widget.ensureCursorVisible()
                except RuntimeError: print("Warning: Could not scroll/ensure cursor visible.")


    def add_cli_output(self, message_bytes: bytes, message_type: str = "output"):
        # Adds message (decoded) to the CLI output display (left pane)
        if self._closing or not self.cli_output_display: return

        target_widget = self.cli_output_display
        decoded_message = _decode_output(message_bytes).rstrip()
        if not decoded_message: return

        try:
            cursor = target_widget.textCursor(); at_end = cursor.atEnd()
            cursor.movePosition(QTextCursor.MoveOperation.End); target_widget.setTextCursor(cursor)
        except RuntimeError: print("Warning: Could not get/set CLI text cursor."); return

        current_theme = config.APP_THEME
        prefix_format = QTextCharFormat(); message_format = QTextCharFormat()
        prefix_to_check = None; prefix_color = None; message_color = None

        # ================================================================= #
        # <<< MODIFIED: Handle User/Model <CWD>: prefixes for coloring >>>
        # ================================================================= #
        if message_type == "user": # Manual command echo with CWD
            user_prefix_match = re.match(r"^(User\s+.*?):\s", decoded_message)
            if user_prefix_match:
                prefix_to_check = user_prefix_match.group(1) + ":"
                prefix_color = get_color('user', current_theme)
            else:
                print(f"[Warning] User message did not match expected 'User <CWD>: command' format: {decoded_message[:50]}...")
                message_color = get_color('cli_output', current_theme)

        elif message_type == "output": # Could be AI command echo OR regular output
            # Check specifically for the AI command echo format first
            model_prefix_match = re.match(r"^(Model\s+.*?):\s", decoded_message)
            if model_prefix_match:
                prefix_to_check = model_prefix_match.group(1) + ":"
                prefix_color = get_color('model', current_theme)
            else:
                # If not AI command echo, treat as regular output
                message_color = get_color('cli_output', current_theme)
        # ================================================================= #
        # <<< END MODIFICATION >>>
        # ================================================================= #

        # Determine message color based on type (only if not set by prefix logic)
        if message_color is None:
            if message_type == "error":
                message_color = get_color('cli_error', current_theme)
            elif message_type == "system":
                message_color = get_color('system', current_theme)
            else: # Default color for the command part after a prefix
                message_color = get_color('cli_output', current_theme)

        # Override for system theme if needed (applies to message_color)
        if current_theme == "system":
            if message_type == "error":
                 message_color = target_widget.palette().color(QPalette.ColorRole.BrightText)
                 if not message_color.isValid() or message_color.name() == "#000000": message_color = QColor("red")
            elif message_type == "system":
                 message_color = target_widget.palette().color(QPalette.ColorRole.ToolTipText)
                 if not message_color.isValid(): message_color = target_widget.palette().color(QPalette.ColorRole.Text)
            elif message_color == get_color('cli_output', "dark"): # Check if using default fallback
                 message_color = target_widget.palette().color(QPalette.ColorRole.Text) # Use system text color

        # Insert text safely
        try:
            if prefix_to_check and decoded_message.startswith(prefix_to_check):
                # Insert Prefix (User or Model with CWD)
                if prefix_color: prefix_format.setForeground(prefix_color)
                prefix_font = prefix_format.font(); prefix_font.setBold(True); prefix_format.setFont(prefix_font)
                cursor.setCharFormat(prefix_format); cursor.insertText(prefix_to_check + " ")

                # Insert Message Part (command)
                message_part = decoded_message[len(prefix_to_check):].strip()
                if message_color: message_format.setForeground(message_color)
                message_font = message_format.font(); message_font.setBold(False); message_format.setFont(message_font)
                cursor.setCharFormat(message_format); cursor.insertText(message_part + "\n")
            else:
                # Insert the whole message with a single color (error, system, regular output)
                if message_color: message_format.setForeground(message_color)
                message_font = message_format.font(); message_font.setBold(False); message_format.setFont(message_font)
                cursor.setCharFormat(message_format); cursor.insertText(decoded_message + "\n")
        except RuntimeError: print("Warning: Could not insert CLI text."); return

        # Scroll safely
        if at_end:
            scrollbar = target_widget.verticalScrollBar()
            if scrollbar:
                try: QApplication.processEvents(); scrollbar.setValue(scrollbar.maximum()); target_widget.ensureCursorVisible()
                except RuntimeError: print("Warning: Could not scroll/ensure CLI cursor visible.")

    def show_help(self):
        # Help text updated slightly to reflect UI changes if any (like model selector)
        help_title = f"--- {APP_NAME} 帮助 ---"
        core_info = """
**主要操作:**
1.  **与 AI 对话 (上方聊天窗口):**
    - 从工具栏选择要使用的 AI 模型。
    - 输入你的任务请求 (例如: "列出当前目录的 python 文件", "创建 temp 目录")。
    - AI 会回复，并将建议的 `<cmd>命令</cmd>`（连同工作目录）回显在下方CLI窗口后自动执行。
    - (可选) 如果在设置中启用“自动将近期CLI输出作为上下文发送给AI”，则左侧CLI输出的**全部**内容会自动作为上下文发送给AI。
    - 输入 `/` 开头的命令执行特殊操作。
2.  **执行手动命令 (下方命令行窗口):**
    - 输入标准的 Shell 命令 (如 `dir`, `Get-ChildItem`, `cd ..`, `python script.py`)。
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
        cmd_cwd = "/cwd           在聊天中显示当前完整目录。"
        cmd_copy_cli = "/copy_cli      复制左侧 CLI 的全部输出到剪贴板。"
        cmd_show_cli = "/show_cli [N]  在聊天中显示左侧 CLI 输出的最后 N 行 (默认 10)。"
        cmd_exit = "/exit          退出 {APP_NAME}。"
        toolbar_info_title = "**工具栏提示:**"
        # <<< UPDATED Toolbar Description >>>
        toolbar_desc = (f"- 左侧: 设置按钮。\n- 右侧: 模型选择下拉框 | 状态灯(🟢空闲/🔴忙碌)。")
        help_text = f"{help_title}\n\n{core_info}\n\n{commands_title}\n {cmd_help}\n {cmd_settings}\n {cmd_clear}\n {cmd_clear_cli}\n {cmd_cwd}\n {cmd_copy_cli}\n {cmd_show_cli}\n {cmd_exit}\n\n{toolbar_info_title}\n{toolbar_desc}\n"
        self.add_chat_message("Help", help_text, add_to_internal_history=False)

    # --- Event Handling and Slots ---

    @Slot()
    def handle_send_message(self):
        # Handles sending chat messages (no change needed here for CLI echo)
        if self._closing or not self.chat_input or not self.model_selector_combo: return
        user_prompt = self.chat_input.toPlainText().strip()
        if not user_prompt: return
        self.chat_input.clear()

        if user_prompt.startswith("/"):
            self.handle_slash_command(user_prompt)
            return

        selected_model_id = self.model_selector_combo.currentText()
        is_placeholder = selected_model_id == "未配置模型" or not selected_model_id

        # Check API config AND selected model validity
        if not config.API_KEY or not config.API_URL or not config.MODEL_ID_STRING or is_placeholder:
             if is_placeholder:
                 self.add_chat_message("Error", "请先在工具栏选择一个有效的 AI 模型。如果列表为空，请使用“设置”配置模型 ID。")
             else:
                 self.add_chat_message("Error", "API 未配置。请使用“设置”按钮或 /settings 命令进行配置。")
             return

        self.stop_api_worker()

        # Add user's message FIRST
        self.add_chat_message("User", user_prompt, add_to_internal_history=True)
        history_for_worker = list(self.conversation_history) # Copy current history

        if config.INCLUDE_CLI_CONTEXT and self.cli_output_display:
            full_cli_text = self.cli_output_display.toPlainText().strip()
            if full_cli_text: # Check if CLI text is not empty
                cli_context_text = full_cli_text
                context_role = "user" # Using 'user' role for context message
                context_msg_content = (
                    f"--- 当前 CLI 输出 (完整) ---\n"
                    f"{cli_context_text}\n"
                    f"--- CLI 输出结束 ---"
                )
                if len(history_for_worker) >= 1:
                    history_for_worker.insert(-1, (context_role, context_msg_content))
                else: # Fallback
                    history_for_worker.append((context_role, context_msg_content))
                    history_for_worker.append(("User", user_prompt)) # Re-add user prompt

        self.set_busy_state(True, "api")
        print(f"Starting ApiWorkerThread for model: {selected_model_id}...")
        self.api_worker_thread = ApiWorkerThread(
            api_key=config.API_KEY,
            api_url=config.API_URL,
            model_id=selected_model_id, # Pass the selected model
            history=history_for_worker, # Pass the potentially modified history
            prompt=user_prompt,
            cwd=self.current_directory
        )
        # Connect signals (output type is 'output' for AI commands/results)
        self.api_worker_thread.api_result.connect(self.handle_api_result)
        self.api_worker_thread.cli_output_signal.connect(lambda b: self.add_cli_output(b, "output"))
        self.api_worker_thread.cli_error_signal.connect(lambda b: self.add_cli_output(b, "error"))
        self.api_worker_thread.directory_changed_signal.connect(self.handle_directory_change)
        self.api_worker_thread.task_finished.connect(lambda: self.handle_task_finished("api"))
        self.api_worker_thread.start()

    def handle_slash_command(self, command):
        if self._closing: return
        command_lower = command.lower(); parts = command.split(maxsplit=1); cmd_base = parts[0].lower(); arg = parts[1].strip() if len(parts) == 2 else None
        print(f"Processing slash command: {command}")

        if cmd_base == "/exit": self.close()
        elif cmd_base == "/clear": self.handle_clear_chat()
        elif cmd_base == "/clear_cli": self.handle_clear_cli()
        elif cmd_base == "/clear_all":
            self.handle_clear_chat()
            self.handle_clear_cli()
            self.add_chat_message("System", "聊天和命令行显示已清除。", add_to_internal_history=False)
        elif cmd_base == "/settings": self.open_settings_dialog()
        elif cmd_base == "/save": self.save_state(); self.add_chat_message("System", "当前状态 (历史, CWD, 选择的模型) 已保存。")
        elif cmd_base == "/help": self.show_help()
        elif cmd_base == "/cwd": self.add_chat_message("System", f"当前工作目录: {self.current_directory}")
        elif cmd_base == "/copy_cli":
            if self.cli_output_display:
                full_cli_text = self.cli_output_display.toPlainText()
                if full_cli_text:
                    try:
                        clipboard = QApplication.clipboard()
                        if clipboard:
                            clipboard.setText(full_cli_text)
                            self.add_chat_message("System", "左侧 CLI 输出已复制到剪贴板。", add_to_internal_history=False)
                        else:
                             self.add_chat_message("Error", "无法访问剪贴板。", add_to_internal_history=False)
                    except Exception as e:
                        self.add_chat_message("Error", f"复制到剪贴板时出错: {e}", add_to_internal_history=False)
                else:
                    self.add_chat_message("System", "左侧 CLI 输出为空。", add_to_internal_history=False)
            else:
                 self.add_chat_message("Error", "无法访问 CLI 输出区域。", add_to_internal_history=False)

        elif cmd_base == "/show_cli":
            if self.cli_output_display:
                lines_to_show = 10
                if arg:
                    try: lines_to_show = int(arg); lines_to_show = max(1, lines_to_show)
                    except ValueError: self.add_chat_message("Error", f"无效的行数: '{arg}'", add_to_internal_history=False); return

                full_cli_text = self.cli_output_display.toPlainText()
                lines = full_cli_text.strip().splitlines()
                last_n_lines = lines[-lines_to_show:]
                if last_n_lines:
                    header = f"--- 左侧 CLI 输出 (最后 {len(last_n_lines)} 行) ---"
                    cli_content_message = header + "\n" + "\n".join(last_n_lines)
                    self.add_chat_message("System", cli_content_message, add_to_internal_history=False)
                else:
                    self.add_chat_message("System", "左侧 CLI 输出为空。", add_to_internal_history=False)
            else:
                 self.add_chat_message("Error", "无法访问 CLI 输出区域。", add_to_internal_history=False)
        else: self.add_chat_message("Error", f"未知命令: {command}。输入 /help 获取帮助。")

    @Slot()
    def handle_clear_chat(self):
        # (Same logic, already has check)
        if self._closing: return
        print("Clear Chat action triggered.")
        if self.chat_history_display: self.chat_history_display.clear()
        self.conversation_history.clear()
        self.add_chat_message("System", "聊天历史已清除。", add_to_internal_history=False)
        self.save_state();
        print("Chat history display and internal history deque cleared and state saved.")

    @Slot()
    def handle_clear_cli(self):
        """Clears the CLI output display."""
        if self._closing:
            return
        print("Clear CLI action triggered.")
        if self.cli_output_display:
            self.cli_output_display.clear()
            print("CLI output display cleared.")
        else:
            print("Warning: CLI output display not found during clear action.")
        if self.cli_input:
            self.cli_input.setFocus()

    @Slot()
    def handle_manual_command(self):
        # Handles manual command input from CLI
        if self._closing or not self.cli_input: return
        command = self.cli_input.text().strip();
        if not command: return

        # Add to CLI command history (distinct from chat history)
        if not self.cli_command_history or self.cli_command_history[-1] != command:
            self.cli_command_history.append(command)
        self.cli_history_index = -1 # Reset history navigation index
        self.cli_input.clear()

        # Handle built-in clear command directly (using the new handler)
        command_lower = command.lower()
        if platform.system() == "Windows" and (command_lower == "cls" or command_lower == "clear"):
            print(f"Intercepted '{command}' command. Clearing CLI display directly.")
            self.handle_clear_cli() # Use the dedicated handler
            return
        elif platform.system() != "Windows" and command_lower == "clear":
            print(f"Intercepted '{command}' command. Clearing CLI display directly.")
            self.handle_clear_cli() # Use the dedicated handler
            return

        # Stop previous manual worker if any
        self.stop_manual_worker()

        # Echo command with CWD to CLI display (as User)
        echo_message_bytes = f"User {self.current_directory}: {command}".encode('utf-8')
        self.add_cli_output(echo_message_bytes, "user") # Pass "user" type for coloring

        # Set busy state and start worker thread
        self.set_busy_state(True, "manual")
        print(f"Starting ManualCommandThread for: {command}")
        self.manual_cmd_thread = ManualCommandThread(command, self.current_directory)
        # Connect signals (output type is 'output' for regular results)
        self.manual_cmd_thread.cli_output_signal.connect(lambda b: self.add_cli_output(b, "output"))
        self.manual_cmd_thread.cli_error_signal.connect(lambda b: self.add_cli_output(b, "error"))
        self.manual_cmd_thread.directory_changed_signal.connect(self.handle_directory_change)
        self.manual_cmd_thread.command_finished.connect(lambda: self.handle_task_finished("manual"))
        self.manual_cmd_thread.start()


    def keyPressEvent(self, event: QKeySequence):
        # Handles CLI history navigation (Up/Down arrows)
        focused_widget = QApplication.focusWidget()
        if focused_widget == self.cli_input:
            key = event.key(); modifiers = event.modifiers()
            if key == Qt.Key.Key_Up and not modifiers:
                if not self.cli_command_history: event.accept(); return
                if self.cli_history_index == -1: self.cli_history_index = len(self.cli_command_history) - 1
                elif self.cli_history_index > 0: self.cli_history_index -= 1
                else: event.accept(); return # Already at the oldest
                if 0 <= self.cli_history_index < len(self.cli_command_history):
                    self.cli_input.setText(self.cli_command_history[self.cli_history_index])
                    self.cli_input.end(False) # Move cursor to end
                event.accept(); return
            elif key == Qt.Key.Key_Down and not modifiers:
                if self.cli_history_index == -1: event.accept(); return # Not navigating
                if self.cli_history_index < len(self.cli_command_history) - 1:
                    self.cli_history_index += 1;
                    self.cli_input.setText(self.cli_command_history[self.cli_history_index]);
                    self.cli_input.end(False) # Move cursor to end
                else: # Reached the newest or beyond, clear input
                    self.cli_history_index = -1; self.cli_input.clear()
                event.accept(); return
            elif self.cli_history_index != -1 and key not in ( Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End ):
                 # If user types while navigating history, stop navigating
                 self.cli_history_index = -1
        super().keyPressEvent(event) # Pass event on if not handled

    @Slot(str)
    def handle_model_selection_changed(self, selected_model: str):
        """Handles the signal when the user changes the model in the QComboBox."""
        if self._closing or not self.model_selector_combo:
            return

        # Avoid acting on placeholder or during updates
        if not selected_model or selected_model == "未配置模型" or self.model_selector_combo.signalsBlocked():
            return

        current_config_selection = config.CURRENTLY_SELECTED_MODEL_ID
        if selected_model != current_config_selection:
            print(f"Model selection changed to: '{selected_model}'")
            config.CURRENTLY_SELECTED_MODEL_ID = selected_model
            self.save_state() # Save the state immediately to persist the new selection
            self.add_chat_message("System", f"已切换模型至: {selected_model}", add_to_internal_history=False)
        else:
            pass


    def set_busy_state(self, busy: bool, task_type: str):
        """Updates UI element states (enabled/disabled) and the status indicator."""
        if self._closing: return
        print(f"Setting busy state: {busy} for task type: {task_type}")

        is_api_task = task_type == "api"
        is_manual_task = task_type == "manual"

        is_api_currently_busy = self.api_worker_thread and self.api_worker_thread.isRunning()
        is_manual_currently_busy = self.manual_cmd_thread and self.manual_cmd_thread.isRunning()

        next_api_busy = (is_api_currently_busy and not (is_api_task and not busy)) or (is_api_task and busy)
        next_manual_busy = (is_manual_currently_busy and not (is_manual_task and not busy)) or (is_manual_task and busy)

        # --- Update Enabled State ---
        if self.chat_input: self.chat_input.setEnabled(not next_api_busy)
        if self.send_button: self.send_button.setEnabled(not next_api_busy)
        if self.clear_chat_button: self.clear_chat_button.setEnabled(not next_api_busy)
        if self.clear_cli_button: self.clear_cli_button.setEnabled(not next_manual_busy)
        if self.cli_input: self.cli_input.setEnabled(not next_manual_busy)
        if self.model_selector_combo: self.model_selector_combo.setEnabled(not next_api_busy and self.model_selector_combo.count() > 0 and self.model_selector_combo.itemText(0) != "未配置模型")

        indicator_busy_state = next_api_busy or next_manual_busy
        self.update_status_indicator(indicator_busy_state)

        # --- Set Focus ---
        if not busy: # Only set focus when a task *finishes*
             QApplication.processEvents() # Ensure UI updates before focus change
             if not (next_api_busy or next_manual_busy): # If *no* tasks are running
                 if task_type == "api" and self.chat_input and self.chat_input.isEnabled():
                     self.chat_input.setFocus()
                     print(f"Task '{task_type}' finished, setting focus to chat input.")
                 elif task_type == "manual" and self.cli_input and self.cli_input.isEnabled():
                     self.cli_input.setFocus()
                     print(f"Task '{task_type}' finished, setting focus to CLI input.")
             else:
                 print(f"Task '{task_type}' finished, but another task is running. Not setting focus.")


    @Slot(str, float)
    def handle_api_result(self, reply: str, elapsed_time: float):
        # Handles result from API worker thread
        if self._closing: return
        time_str = f" (耗时: {elapsed_time:.2f} 秒)"; message_with_time = f"{reply}{time_str}"
        self.add_chat_message("Model", message_with_time, add_to_internal_history=True)


    @Slot(str, bool)
    def handle_directory_change(self, new_directory: str, is_manual_command: bool):
        # Handles directory change signaled by workers
        if self._closing: return
        if os.path.isdir(new_directory):
             old_directory = self.current_directory
             self.current_directory = os.path.normpath(new_directory)
             try: os.chdir(self.current_directory); print(f"Process working directory successfully changed to: {self.current_directory}")
             except Exception as e:
                 print(f"Error changing process working directory to '{self.current_directory}': {e}")
                 error_msg = f"错误: 无法将进程工作目录更改为 '{self.current_directory}': {e}"
                 self.add_cli_output(error_msg.encode(), "error") # This error doesn't need [stderr] prefix either
             # self.update_cwd_label(); # <<< REMOVED Call >>>
             self.update_prompt() # Update prompt which shows CWD
             source = "手动命令" if is_manual_command else "AI 命令"
             print(f"App directory state changed from '{old_directory}' to '{self.current_directory}' via {source}")
             self.save_state()
        else:
            print(f"Warning: Directory change received for non-existent path '{new_directory}'")
            error_msg = f"Error: Directory not found: '{new_directory}'"
            self.add_cli_output(error_msg.encode(), "error") # This error doesn't need [stderr] prefix either

    @Slot(str)
    def handle_task_finished(self, task_type: str):
        # Handles finished signal from worker threads
        if self._closing: return
        print(f"{task_type.capitalize()}WorkerThread finished.")
        self.set_busy_state(False, task_type)
        if task_type == "api": self.api_worker_thread = None
        elif task_type == "manual": self.manual_cmd_thread = None


    @Slot()
    def open_settings_dialog(self):
        # Handles opening the settings dialog and processing the results
        if self.settings_dialog_open or self._closing: return
        self.settings_dialog_open = True
        print("Opening settings dialog...")
        dialog = SettingsDialog(self)
        current_theme_before = config.APP_THEME
        current_config_before = config.get_current_config() # Get full config before

        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            print("Settings dialog accepted.")
            # Unpack values
            (api_key, api_url, model_id_string, auto_startup, new_theme,
             include_cli_context, include_timestamp) = dialog.get_values()

            # Check for changes
            config_changed = (
                api_key != current_config_before['api_key'] or
                api_url != current_config_before['api_url'] or
                model_id_string != current_config_before['model_id_string'] or
                auto_startup != current_config_before['auto_startup'] or
                new_theme != current_config_before['theme'] or
                include_cli_context != current_config_before['include_cli_context'] or
                include_timestamp != current_config_before.get('include_timestamp_in_prompt', config.DEFAULT_INCLUDE_TIMESTAMP)
            )

            reset_button = dialog.findChild(QPushButton, "reset_button")
            was_reset_likely = reset_button is not None and reset_button.isDown()

            if config_changed:
                print("Configuration change detected, saving...")
                # Determine new selected model
                new_model_list = [m.strip() for m in model_id_string.split(',') if m.strip()]
                new_selected_model = config.CURRENTLY_SELECTED_MODEL_ID
                if not new_selected_model or new_selected_model not in new_model_list:
                    new_selected_model = new_model_list[0] if new_model_list else ""
                print(f"  Saving - New Model List: {new_model_list}, Selected: {new_selected_model}")

                # Save config
                config.save_config(
                    api_key, api_url, model_id_string, auto_startup, new_theme,
                    include_cli_context, include_timestamp,
                    selected_model_id=new_selected_model
                )
                print(f"Configuration saved. New theme: {new_theme}, AutoStart: {auto_startup}, ModelList: {model_id_string}, SelectedModel: {new_selected_model}, CLI Context: {include_cli_context}, Timestamp: {include_timestamp}")
            else:
                print("Settings dialog accepted, but no changes detected in values.")

            self.update_model_selector() # Update model display in toolbar

            theme_changed = new_theme != current_theme_before
            if theme_changed:
                print("Theme changed, applying new theme styles...")
                app = QApplication.instance()
                if app: setup_palette(app, new_theme)
                self.apply_theme_specific_styles()

            current_config_after_dialog = config.get_current_config()
            should_reload_state = was_reset_likely or (not current_config_after_dialog['api_key'] and current_config_before['api_key'])

            if should_reload_state:
                print("Reset or API key removal detected. Re-loading state and syncing CWD.")
                self.load_state() # This loads history, CWD, CLI history
                try:
                    if os.path.isdir(self.current_directory):
                        os.chdir(self.current_directory)
                        print(f"Process CWD synced to loaded/reset state: {self.current_directory}")
                    else:
                         print(f"Warning: Loaded/reset directory '{self.current_directory}' not found after settings change. Using initial directory.")
                         self.current_directory = self.initial_directory
                         try:
                             os.chdir(self.current_directory)
                             print(f"Using initial directory as fallback: {self.current_directory}")
                         except Exception as e_chdir_fallback:
                             print(f"CRITICAL: Could not even change to initial directory '{self.current_directory}': {e_chdir_fallback}")
                             self.current_directory = os.getcwd()
                             print(f"Using current OS CWD as final fallback: {self.current_directory}")
                         self.save_state() # Save the fallback CWD
                except Exception as e:
                    print(f"CRITICAL: Error setting process CWD after settings reset/change to '{self.current_directory}': {e}")
                self.load_and_apply_state() # Apply history etc.
                self.update_model_selector() # Refresh model selector after reset

            elif config_changed: # Check if other config changed (incl. model list)
                 print("Configuration changed, reapplying styles and updating model selector.")
                 self.apply_theme_specific_styles() # Reapply styles if other settings changed
                 self.update_model_selector() # Ensure model list is up-to-date

            elif theme_changed:
                print("Theme changed, styles already applied.")

            self.update_prompt() # Ensure CLI prompt is up-to-date
            print("CLI Prompt display updated after settings dialog.")

        else:
            print("Settings dialog cancelled.")

        self.settings_dialog_open = False
        self.activateWindow(); self.raise_()


    # --- State Management ---
    def save_state(self):
        """Saves chat history, CLI history, current directory, splitter state, and selected model."""
        if self._closing: print("Skipping save_state during close sequence."); return
        try:
            settings = config.get_settings()
            history_list = list(self.conversation_history)

            # Save UI/History State
            settings.beginGroup("state")
            settings.setValue("conversation_history", json.dumps(history_list))
            settings.setValue("current_directory", self.current_directory)
            settings.setValue("cli_history", json.dumps(list(self.cli_command_history)))
            settings.endGroup()

            # Save UI Geometry/Splitter State
            if self.splitter:
                settings.beginGroup("ui")
                settings.setValue("splitter_state", self.splitter.saveState())
                settings.endGroup()
            else:
                print("Warning: Could not find splitter to save state.")

            # Save currently selected model to config
            current_config_vals = config.get_current_config()
            current_selected_model = config.CURRENTLY_SELECTED_MODEL_ID

            # Call save_config, passing the current values and the updated selected model
            config.save_config(
                api_key=current_config_vals["api_key"],
                api_url=current_config_vals["api_url"],
                model_id_string=current_config_vals["model_id_string"],
                auto_startup=current_config_vals["auto_startup"],
                theme=current_config_vals["theme"],
                include_cli_context=current_config_vals["include_cli_context"],
                include_timestamp=current_config_vals["include_timestamp_in_prompt"],
                selected_model_id=current_selected_model # Pass the selection to be saved
            )

            settings.sync()
            print(f"State saved: Chat History({len(history_list)}), CWD({self.current_directory}), CLI History({len(self.cli_command_history)}), SelectedModel({current_selected_model})")

        except Exception as e:
            print(f"Error saving state: {e}")
            import traceback
            traceback.print_exc() # Print stack trace for debugging


    def load_state(self):
        # Loads state on startup (CWD, histories). Selected model is loaded by config.load_config()
        if self._closing: return
        print("Loading state (CWD, History, CLI History)...")
        try:
            settings = config.get_settings(); restored_cwd = self.initial_directory
            settings.beginGroup("state")
            saved_cwd = settings.value("current_directory");
            history_json = settings.value("conversation_history", "[]");
            cli_history_json = settings.value("cli_history", "[]");
            settings.endGroup()

            # Load CWD
            if saved_cwd and isinstance(saved_cwd, str):
                if os.path.isdir(saved_cwd): restored_cwd = saved_cwd
                else: print(f"Warning: Saved directory '{saved_cwd}' not found or invalid. Using initial directory.")
            else: print("No valid saved directory found. Using initial directory.")
            self.current_directory = os.path.normpath(restored_cwd); print(f"Effective internal CWD state after loading: {self.current_directory}")

            # Load Chat History
            loaded_history = []
            try:
                 if isinstance(history_json, (list, tuple)): history_list = history_json
                 else: history_list = json.loads(str(history_json))
                 if isinstance(history_list, list) and all(isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], str) and isinstance(item[1], str) for item in history_list): loaded_history = history_list; print(f"Loaded {len(loaded_history)} conversation history items.")
                 elif history_json != "[]": print("Warning: Saved conversation history format invalid.")
            except json.JSONDecodeError as e: print(f"Error decoding saved conversation history JSON: {e}. Content: '{history_json}'")
            except Exception as e: print(f"Error processing saved conversation history: {e}.")
            self.conversation_history = deque(loaded_history, maxlen=self.conversation_history.maxlen)

            # Load CLI History
            loaded_cli_history = []
            try:
                if isinstance(cli_history_json, list): cli_history_list = cli_history_json
                else: cli_history_list = json.loads(str(cli_history_json))
                if isinstance(cli_history_list, list) and all(isinstance(item, str) for item in cli_history_list): loaded_cli_history = cli_history_list; print(f"Loaded {len(loaded_cli_history)} CLI history items.")
                elif cli_history_json != "[]": print("Warning: Saved CLI history format invalid.")
            except json.JSONDecodeError as e: print(f"Error decoding saved CLI history JSON: {e}. Content: '{cli_history_json}'")
            except Exception as e: print(f"Error processing saved CLI history: {e}.")
            self.cli_command_history = deque(loaded_cli_history, maxlen=self.cli_command_history.maxlen); self.cli_history_index = -1

        except Exception as e:
            print(f"CRITICAL Error loading state: {e}. Resetting state variables.")
            self.conversation_history.clear(); self.cli_command_history.clear(); self.cli_history_index = -1
            self.current_directory = self.initial_directory

    # --- Thread Management ---
    def stop_api_worker(self):
        # Signals the API worker thread to stop
        if self.api_worker_thread and self.api_worker_thread.isRunning():
            print("Stopping API worker...")
            self.api_worker_thread.stop()
            return True
        return False

    def stop_manual_worker(self):
        # Signals the manual command worker thread to stop
        if self.manual_cmd_thread and self.manual_cmd_thread.isRunning():
            print("Stopping Manual Command worker...")
            self.manual_cmd_thread.stop()
            return True
        return False

    # --- Window Close Event ---
    def closeEvent(self, event):
        # Handles window close: stop threads, save state
        if self._closing: event.ignore(); return
        self._closing = True
        print("Close event triggered. Initiating shutdown...")

        api_stopped = self.stop_api_worker()
        manual_stopped = self.stop_manual_worker()

        wait_timeout_ms = 500; threads_to_wait = []
        if api_stopped and self.api_worker_thread: threads_to_wait.append(self.api_worker_thread)
        if manual_stopped and self.manual_cmd_thread: threads_to_wait.append(self.manual_cmd_thread)

        if threads_to_wait:
            print(f"Waiting up to {wait_timeout_ms}ms for {len(threads_to_wait)} worker thread(s) to finish...")
            start_wait_time = time.monotonic()
            all_finished = False
            while time.monotonic() - start_wait_time < wait_timeout_ms / 1000.0:
                 all_finished = all(not thread.isRunning() for thread in threads_to_wait)
                 if all_finished: break
                 QApplication.processEvents()
                 QThread.msleep(50)
            if all_finished: print("All worker threads finished gracefully.")
            else: print("Warning: Worker thread(s) did not finish within the timeout.")

        print("Saving final state before closing...")
        self.save_state() # This now includes saving the selected model via config.save_config

        print("Exiting application.")
        event.accept()