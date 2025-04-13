# ========================================
# 文件名: PowerAgent/gui/main_window_updates.py
# (MODIFIED - Updated add_chat_message to handle 'ai_command' role formatting)
# ----------------------------------------
# gui/main_window_updates.py
# -*- coding: utf-8 -*-

import os
import platform
import re
import json
import html
from typing import TYPE_CHECKING
from collections import deque

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor, QPalette, QIcon, QFont, QBrush

# Import necessary components from the project
from constants import APP_NAME, get_color
from core import config # For theme, CWD, models
from core.worker_utils import decode_output
from .stylesheets import STYLESHEET_TEMPLATE, MINIMAL_STYLESHEET_SYSTEM_THEME

# Type hinting for MainWindow without causing circular import at runtime
if TYPE_CHECKING:
    from .main_window import MainWindow
    from .ui_components import StatusIndicatorWidget


class UpdatesMixin:
    """Mixin containing UI update/display logic for MainWindow."""

    def _get_icon(self: 'MainWindow', theme_name: str, fallback_filename: str, text_fallback: str = None) -> QIcon:
        # Helper to get themed icons or fallbacks (same logic as before)
        icon = QIcon.fromTheme(theme_name)
        if icon.isNull():
            assets_dir = os.path.join(self.application_base_dir, "assets")
            icon_path = os.path.join(assets_dir, fallback_filename)
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
            # Log warning only if fallback also doesn't exist
            if icon.isNull():
                 print(f"Warning: Icon theme '{theme_name}' not found and fallback '{fallback_filename}' does not exist in {assets_dir}.")
                 # Optionally return a text-based icon or empty icon here if needed
                 # if text_fallback: return QIcon() # Placeholder
        return icon

    def set_window_icon(self: 'MainWindow'):
        # Sets the main application window icon (same logic as before)
        try:
            # Try app name specific icon first
            icon = self._get_icon(APP_NAME.lower(), "icon.png", None)
            # Fallback to generic terminal icon
            if icon.isNull(): icon = self._get_icon("utilities-terminal", "app.ico", None)
            # Set icon if found
            if not icon.isNull(): self.setWindowIcon(icon)
            else: print("Could not find a suitable window icon via theme or fallback.")
        except Exception as e: print(f"Error setting window icon: {e}")

    def _get_os_fonts(self: 'MainWindow'):
        # Helper to get platform-specific monospace fonts (same logic)
        mono_font_family = "Consolas, Courier New"
        mono_font_size = 10
        label_font_size = 9
        if platform.system() == "Windows": pass # Use defaults
        elif platform.system() == "Darwin": # macOS
            mono_font_family, mono_font_size, label_font_size = "Menlo", 11, 9
        elif platform.system() == "Linux":
             mono_font_family, mono_font_size, label_font_size = "Monospace", 10, 9
        return mono_font_family, mono_font_size, label_font_size

    def apply_theme_specific_styles(self: 'MainWindow'):
        # Applies the QSS stylesheet based on the current theme (dark, light, system)
        if self._closing: return
        theme = config.APP_THEME
        print(f"Applying styles for theme: {theme}")
        mono_font_family, mono_font_size, label_font_size = self._get_os_fonts()
        qss = ""
        app_instance = QApplication.instance()
        if not app_instance: print("Warning: QApplication instance not found during style application."); return

        palette = app_instance.palette() # Get the current palette (set by setup_palette)
        # Get border color for system theme from palette
        border_color_role = QPalette.ColorRole.Mid # Try Mid role
        border_color = palette.color(border_color_role)
        if not border_color.isValid(): border_color = palette.color(QPalette.ColorRole.Dark) # Fallback to Dark
        if not border_color.isValid(): border_color = QColor(180, 180, 180) # Final fallback
        border_color_name = border_color.name() # Get hex string #RRGGBB

        if theme == "system":
            # Use minimal stylesheet, relying mostly on the system palette
            qss = MINIMAL_STYLESHEET_SYSTEM_THEME.format(
                mono_font_family=mono_font_family, mono_font_size=mono_font_size,
                label_font_size=label_font_size, border=border_color_name
            )
            print("Applied system theme (minimal QSS). Relies on global palette.")
        else: # "dark" or "light"
            # Get specific colors from constants module for the theme
            cli_bg=get_color("cli_bg", theme); cli_output_color=get_color("cli_output", theme)
            prompt_color=get_color("prompt", theme); border_color_const=get_color("border", theme)
            text_main_color=get_color("text_main", theme); status_label_color=get_color("status_label", theme)

            # Get standard palette colors for general UI elements
            window_bg=palette.color(QPalette.ColorRole.Window).name()
            base_bg=palette.color(QPalette.ColorRole.Base).name()
            highlight_bg=palette.color(QPalette.ColorRole.Highlight).name()
            highlighted_text=palette.color(QPalette.ColorRole.HighlightedText).name()
            button_bg=palette.color(QPalette.ColorRole.Button).name()
            button_text_color=palette.color(QPalette.ColorRole.ButtonText).name()
            tooltip_bg=palette.color(QPalette.ColorRole.ToolTipBase).name()
            tooltip_text=palette.color(QPalette.ColorRole.ToolTipText).name()
            # Disabled colors from palette
            text_disabled=palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name()
            button_disabled_bg=palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button).name()
            border_disabled=palette.color(QPalette.ColorGroup.Disabled, border_color_role).name() # Use same role as normal border
            # Calculate pressed color based on button background
            button_pressed_bg=QColor(button_bg).darker(115).name() # Slightly darker

            # Format the full stylesheet template
            qss = STYLESHEET_TEMPLATE.format(
                window_bg=window_bg, base_bg=base_bg, text_main=text_main_color.name(),
                cli_bg=cli_bg.name(), cli_output=cli_output_color.name(), prompt_color=prompt_color.name(),
                border=border_color_const.name(), highlight_bg=highlight_bg,
                mono_font_family=mono_font_family, mono_font_size=mono_font_size, label_font_size=label_font_size,
                button_bg=button_bg, button_text=button_text_color, highlighted_text=highlighted_text,
                button_pressed_bg=button_pressed_bg, button_disabled_bg=button_disabled_bg,
                text_disabled=text_disabled, border_disabled=border_disabled,
                tooltip_bg=tooltip_bg, tooltip_text=tooltip_text, status_label_color=status_label_color.name()
            )
            print(f"Theme '{theme}' styles applied via full QSS.")

        # Apply the generated stylesheet to the main window
        self.setStyleSheet(qss)
        self.update() # Force repaint if necessary
        self.update_prompt() # Update prompt as its colors might change

    def load_and_apply_state(self: 'MainWindow'):
        # Applies loaded history to chat display after UI is ready
        if self._closing: return
        print(f"Applying {len(self.conversation_history)} loaded history items to display...")
        # Use a copy to iterate while modifying the original deque
        history_copy = list(self.conversation_history)

        if self.chat_history_display:
            self.chat_history_display.clear() # Clear display first
            self.conversation_history.clear() # Clear internal deque before re-adding
            # Re-add messages using the standard method to ensure formatting
            for role, message in history_copy:
                # Use the updated add_chat_message which handles formatting
                self.add_chat_message(role, message, add_to_internal_history=True)
            print("Loaded history applied to display and internal history deque.")
        else:
            # If display isn't ready, just ensure internal history deque is loaded
            # (This was already done in load_state, so this is defensive)
            self.conversation_history = deque(history_copy, maxlen=self.conversation_history.maxlen)
            print("Warning: Chat history display not found during state application. Internal history already loaded.")

        # Update other UI elements based on loaded state if necessary
        self.update_model_selector() # Ensure model selector reflects loaded config
        self.update_prompt() # Ensure prompt reflects loaded CWD

    def update_prompt(self: 'MainWindow'):
        # Updates the CLI prompt label with the current directory
        if self._closing or not self.cli_prompt_label:
            return
        shell_prefix = "PS" if platform.system() == "Windows" else "$"
        display_path = self.current_directory

        # Make drive letter uppercase on Windows for consistency
        if platform.system() == "Windows" and len(display_path) >= 2 and display_path[1] == ':':
            display_path = display_path[0].upper() + display_path[1:]

        # Replace home directory path with '~' for brevity
        try:
            home_dir = os.path.expanduser("~")
            # Normalize home_dir case on Windows for comparison
            home_dir_compare = home_dir
            if platform.system() == "Windows" and len(home_dir_compare) >= 2 and home_dir_compare[1] == ':':
                home_dir_compare = home_dir_compare[0].upper() + home_dir_compare[1:]

            # Check if path starts with home directory
            if display_path.startswith(home_dir_compare):
                if display_path == home_dir_compare:
                    # Path is exactly the home directory
                    display_path = "~"
                elif display_path.startswith(home_dir_compare + os.path.sep):
                    # Path is inside the home directory
                    display_path = "~" + display_path[len(home_dir):] # Use original home_dir length
        except Exception as e:
            print(f"Error processing path for prompt display: {e}") # Log error but continue

        prompt_text = f"{shell_prefix} {display_path}> "
        self.cli_prompt_label.setText(prompt_text)

    def update_model_selector(self: 'MainWindow'):
        """Updates the model selection QComboBox based on the configuration."""
        if self._closing or not self.model_selector_combo:
            return

        print("Updating model selector...")
        saved_selected_model = config.CURRENTLY_SELECTED_MODEL_ID # Use config value

        self.model_selector_combo.blockSignals(True) # Prevent signals during update
        self.model_selector_combo.clear()

        # Get model list from config
        model_id_string = config.MODEL_ID_STRING
        model_list = []
        if model_id_string:
            model_list = [m.strip() for m in model_id_string.split(',') if m.strip()]

        if not model_list:
            placeholder_text = "未配置模型"
            self.model_selector_combo.addItem(placeholder_text)
            self.model_selector_combo.setEnabled(False)
            if config.CURRENTLY_SELECTED_MODEL_ID != "":
                config.CURRENTLY_SELECTED_MODEL_ID = ""
            print("Model selector updated: No models configured.")
        else:
            self.model_selector_combo.addItems(model_list)
            self.model_selector_combo.setEnabled(True)
            found_index = self.model_selector_combo.findText(saved_selected_model)
            if saved_selected_model and found_index != -1:
                self.model_selector_combo.setCurrentIndex(found_index)
                print(f"Model selector updated: Restored selection '{saved_selected_model}'.")
            else:
                default_model = model_list[0]
                self.model_selector_combo.setCurrentIndex(0)
                print(f"Model selector updated: Saved model '{saved_selected_model}' not found/invalid. Defaulting to '{default_model}'.")
                config.CURRENTLY_SELECTED_MODEL_ID = default_model

        self.model_selector_combo.blockSignals(False) # Re-enable signals

    def update_status_indicator(self: 'MainWindow', busy: bool):
        """Updates the custom status indicator widget's state."""
        if self._closing or not self.status_indicator:
            return
        if hasattr(self.status_indicator, 'setBusy') and callable(self.status_indicator.setBusy):
             self.status_indicator.setBusy(busy)
        else:
             print(f"Warning: status_indicator is not a StatusIndicatorWidget or does not have setBusy method. Type: {type(self.status_indicator)}")

    # ============================================================= #
    # <<< MODIFIED add_chat_message METHOD >>>
    # ============================================================= #
    def add_chat_message(
        self: 'MainWindow',
        role: str,
        message: str,
        add_to_internal_history: bool = True,
        elapsed_time: float | None = None # Time for AI responses
    ):
        """Adds message to the chat display, parsing actions and formatting timestamp/commands."""
        if self._closing or not self.chat_history_display:
            if add_to_internal_history:
                 message_for_history = message.strip()
                 # Ensure the deque exists before appending
                 if not hasattr(self, 'conversation_history'): self.conversation_history = deque(maxlen=50)
                 if not self.conversation_history or self.conversation_history[-1] != (role, message_for_history):
                     self.conversation_history.append((role, message_for_history))
            return

        target_widget = self.chat_history_display
        role_lower = role.lower()
        # Handle role display name (e.g., "AI Command" -> "AI Command")
        role_display = "AI Command" if role_lower == "ai command" else role.capitalize() # Specific handling for "AI Command"
        prefix_text = f"{role_display}: "
        message_content = message.rstrip() # Process this content

        # Move cursor to end safely
        try:
            cursor = target_widget.textCursor()
            at_end = cursor.atEnd()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            target_widget.setTextCursor(cursor)
        except RuntimeError:
            print("Warning: Could not get/set text cursor for chat display.")
            return

        # --- Setup Text Formats ---
        current_theme = config.APP_THEME
        default_text_color = target_widget.palette().color(QPalette.ColorRole.Text)
        default_font_size = target_widget.font().pointSize()
        if default_font_size <= 0: default_font_size = 10 # Fallback font size

        # Prefix Format (Bold, Role Color)
        prefix_format = QTextCharFormat()
        # <<< MODIFIED: Correct role lookup for color >>>
        valid_color_roles = ['user', 'model', 'system', 'error', 'help', 'prompt', 'ai_command', 'keyboard_action']
        prefix_color_role_key = role_lower if role_lower in valid_color_roles else 'system' # Default to system color
        prefix_color = get_color(prefix_color_role_key, current_theme)
        # <<< END MODIFICATION >>>
        if not isinstance(prefix_color, QColor): prefix_color = default_text_color
        prefix_format.setForeground(prefix_color)
        prefix_font = prefix_format.font(); prefix_font.setBold(True); prefix_format.setFont(prefix_font)

        # Message Format (Normal Weight, Role Color for some, default otherwise)
        message_format = QTextCharFormat()
        message_color = default_text_color
        # <<< MODIFIED: Use specific ai_command color for message text >>>
        if role_lower == 'ai command':
             message_color = get_color('ai_command', current_theme) # Use specific color for the command text itself
        elif role_lower in ['system', 'error', 'help', 'prompt']:
             message_color = prefix_color # Inherit color from prefix for these non-command roles
        elif role_lower == 'model':
             message_color = get_color('model', current_theme) # Explicit model color
        elif role_lower == 'user':
             message_color = get_color('user', current_theme) # Explicit user color
        # <<< END MODIFICATION >>>
        if not isinstance(message_color, QColor): message_color = default_text_color
        message_format.setForeground(message_color)
        message_font = message_format.font(); message_font.setBold(False); message_format.setFont(message_font)

        # --- Keyboard Action Format (with Background) ---
        kb_action_format = QTextCharFormat()
        kb_action_color = get_color('keyboard_action', current_theme)
        kb_action_bg_color = get_color('keyboard_action_bg', current_theme)
        if not isinstance(kb_action_color, QColor): kb_action_color = get_color('prompt', current_theme)
        if not isinstance(kb_action_bg_color, QColor): kb_action_bg_color = QColor(Qt.GlobalColor.transparent)
        kb_action_format.setForeground(kb_action_color)
        kb_action_format.setBackground(QBrush(kb_action_bg_color))
        kb_font = kb_action_format.font(); kb_font.setBold(False); kb_action_format.setFont(kb_font)

        # --- Timestamp Format ---
        timestamp_format = QTextCharFormat()
        timestamp_color = get_color('timestamp_color', current_theme)
        if not isinstance(timestamp_color, QColor): timestamp_color = QColor("gray")
        timestamp_format.setForeground(timestamp_color)
        timestamp_font = timestamp_format.font()
        timestamp_font.setPointSize(max(6, default_font_size - 1))
        timestamp_format.setFont(timestamp_font)

        # --- Insert Prefix ---
        try:
            cursor.setCharFormat(prefix_format)
            cursor.insertText(prefix_text)
        except RuntimeError: print("Warning: Could not insert chat prefix."); return

        # --- Insert Message Content ---
        last_match_end = 0
        try:
            # Parse for Keyboard Actions ONLY if role is 'Model' (or potentially other AI roles if needed)
            if role_lower == 'model':
                func_pattern = re.compile(
                    r"""(<function\s+
                        call=[\"'](keyboard_\w+|clipboard_paste)[\"'] # Include clipboard_paste
                        \s+
                        args=[\"'](.*?)[\"']
                        \s*
                        /?
                        >
                        (?:</function>)?
                        )""", re.VERBOSE | re.DOTALL | re.IGNORECASE
                )
                for match in func_pattern.finditer(message_content):
                    start, end = match.span(1)
                    text_before = message_content[last_match_end:start]
                    if text_before:
                        cursor.setCharFormat(message_format) # Use standard message format for text before
                        cursor.insertText(text_before)

                    func_name = match.group(2); args_json_str_html = match.group(3)
                    display_action_str = f"[Keyboard Action: {func_name}]" # Default display
                    try:
                        args_json_str = html.unescape(args_json_str_html); args_dict = json.loads(args_json_str)
                        if func_name == "clipboard_paste":
                            text_to_paste = args_dict.get('text', '')
                            display_text = text_to_paste[:30] + ('...' if len(text_to_paste) > 30 else '')
                            display_action_str = f" 📋 Paste: '{display_text}' " # Use clipboard icon
                        elif func_name == "keyboard_press": display_action_str = f" ⌨️ Press: {args_dict.get('key', 'N/A').capitalize()} "
                        elif func_name == "keyboard_hotkey": display_action_str = f" ⌨️ Hotkey: {'+'.join(k.capitalize() for k in args_dict.get('keys', []))} "
                        else: display_action_str = f" ⌨️ Unknown Action: {func_name} "
                    except Exception as parse_err:
                        print(f"Warning: Error processing action tag for display: {parse_err}")
                        display_action_str = f" ⌨️ Error Parsing Action: {func_name} "

                    cursor.setCharFormat(kb_action_format) # Apply special format for action display
                    cursor.insertText(display_action_str)
                    last_match_end = end
            # --- Handle AI Command Echo ---
            elif role_lower == 'ai command':
                 # The message itself is the command, apply the message format (which uses ai_command color)
                 cursor.setCharFormat(message_format)
                 cursor.insertText(message_content)
                 last_match_end = len(message_content) # Processed the whole message

            # Insert any remaining text (or the whole message if not 'Model' or 'AI Command')
            text_after = message_content[last_match_end:]
            if text_after:
                cursor.setCharFormat(message_format) # Use standard message format
                cursor.insertText(text_after)

            # --- Insert Timestamp (if provided for 'Model') ---
            if role_lower == 'model' and elapsed_time is not None and elapsed_time >= 0:
                timestamp_text = f" (耗时: {elapsed_time:.2f} 秒)"
                cursor.setCharFormat(timestamp_format)
                cursor.insertText(timestamp_text)

            # Insert the final newline using the standard message format
            cursor.setCharFormat(message_format)
            cursor.insertText('\n')

        except RuntimeError: print("Warning: Could not insert chat message content."); return

        # --- Add to internal history deque if requested ---
        if add_to_internal_history:
             message_for_history = message.strip()
             # Ensure the deque exists before appending
             if not hasattr(self, 'conversation_history'): self.conversation_history = deque(maxlen=50)
             if not self.conversation_history or self.conversation_history[-1] != (role, message_for_history):
                 self.conversation_history.append((role, message_for_history))

        # --- Scroll to bottom ---
        if at_end:
            scrollbar = target_widget.verticalScrollBar()
            if scrollbar:
                try:
                    QApplication.processEvents()
                    scrollbar.setValue(scrollbar.maximum())
                    target_widget.ensureCursorVisible()
                except RuntimeError: print("Warning: Could not scroll/ensure cursor visible for chat display.")
    # ============================================================= #
    # <<< END MODIFIED add_chat_message METHOD >>>
    # ============================================================= #


    # ============================================================= #
    # <<< add_cli_output METHOD (Modified slightly for echo) >>>
    # ============================================================= #
    def add_cli_output(self: 'MainWindow', message_bytes: bytes, message_type: str = "output"):
        # Adds message (decoded) to the CLI output display (left pane)
        if self._closing or not self.cli_output_display: return

        target_widget = self.cli_output_display
        decoded_message = decode_output(message_bytes).rstrip()
        if not decoded_message: return # Don't add empty lines

        # Move cursor to end safely
        try:
            cursor = target_widget.textCursor(); at_end = cursor.atEnd()
            cursor.movePosition(QTextCursor.MoveOperation.End); target_widget.setTextCursor(cursor)
        except RuntimeError: print("Warning: Could not get/set CLI text cursor."); return

        current_theme = config.APP_THEME
        prefix_format = QTextCharFormat(); message_format = QTextCharFormat()
        prefix_to_insert = None; message_to_insert = decoded_message;
        prefix_color = None; message_color = None; prefix_bold = False

        # Check for our specific echo formats first
        # Matches "User CWD> " or "Model CWD> " at the start
        user_echo_match = re.match(r"^(User\s+.*?>\s)", decoded_message)
        model_echo_match = re.match(r"^(Model\s+.*?>\s)", decoded_message) # Updated prompt symbol

        if user_echo_match and message_type == "user": # Manual command echo with CWD
            prefix_to_insert = user_echo_match.group(1)
            message_to_insert = decoded_message[len(prefix_to_insert):] # The actual command
            prefix_color = get_color('user', current_theme)
            message_color = get_color('cli_output', current_theme) # Color for the command part
            prefix_bold = True # Make prefix bold
        elif model_echo_match and message_type == "output": # AI command echo with CWD
            prefix_to_insert = model_echo_match.group(1)
            message_to_insert = decoded_message[len(prefix_to_insert):] # The actual command
            prefix_color = get_color('model', current_theme)
            message_color = get_color('ai_command', current_theme) # Use AI command color for the command itself
            prefix_bold = True # Make prefix bold
        else:
            # No prefix matched, determine color based on message_type only
            if message_type == "error":
                message_color = get_color('cli_error', current_theme)
            elif message_type == "system": # Handle 'system' type if used for CLI
                message_color = get_color('system', current_theme)
            else: # Default for regular output (stdout)
                message_color = get_color('cli_output', current_theme)


        # --- Adjust colors for system theme using palette ---
        if current_theme == "system":
            sys_palette = target_widget.palette()
            # Adjust message color based on type for system theme
            if message_type == "error":
                 sys_error_color = sys_palette.color(QPalette.ColorRole.BrightText) # Try BrightText for error
                 message_color = sys_error_color if sys_error_color.isValid() and sys_error_color.name() != "#000000" else QColor("red")
            elif message_type == "system":
                 sys_system_color = sys_palette.color(QPalette.ColorRole.ToolTipText) # Try ToolTipText for system messages
                 message_color = sys_system_color if sys_system_color.isValid() else sys_palette.color(QPalette.ColorRole.Text)
            # Check if message_color defaulted to the dark theme's standard output color (or our special AI command color)
            elif isinstance(message_color, QColor) and (message_color.name() == get_color('cli_output', "dark").name() or message_color.name() == get_color('ai_command', "dark").name()):
                 message_color = sys_palette.color(QPalette.ColorRole.Text) # Use standard text color

            # Adjust prefix color for system theme (if needed, keep user/model colors for now)
            # if isinstance(prefix_color, QColor): ...

        # Ensure colors are valid QColor objects before use
        default_cli_output_color = get_color('cli_output', current_theme)
        if not isinstance(prefix_color, QColor): prefix_color = default_cli_output_color # Fallback for prefix
        if not isinstance(message_color, QColor): message_color = default_cli_output_color # Fallback for message


        # Insert text safely
        try:
            if prefix_to_insert: # If a User/Model prefix was found
                # Insert Prefix
                prefix_format.setForeground(prefix_color)
                prefix_font = prefix_format.font(); prefix_font.setBold(prefix_bold); prefix_format.setFont(prefix_font)
                cursor.setCharFormat(prefix_format); cursor.insertText(prefix_to_insert)

                # Insert Message Part (command)
                message_format.setForeground(message_color)
                message_font = message_format.font(); message_font.setBold(False); message_format.setFont(message_font) # Command part not bold
                cursor.setCharFormat(message_format); cursor.insertText(message_to_insert + "\n")
            else:
                # Insert the whole message with a single color (error, system, regular output)
                message_format.setForeground(message_color)
                message_font = message_format.font(); message_font.setBold(False); message_format.setFont(message_font) # Not bold
                cursor.setCharFormat(message_format); cursor.insertText(decoded_message + "\n")
        except RuntimeError: print("Warning: Could not insert CLI text."); return

        # Scroll safely if we were at the end
        if at_end:
            scrollbar = target_widget.verticalScrollBar()
            if scrollbar:
                try:
                    QApplication.processEvents() # Update layout first
                    scrollbar.setValue(scrollbar.maximum())
                    target_widget.ensureCursorVisible()
                except RuntimeError: print("Warning: Could not scroll/ensure CLI cursor visible.")
    # ============================================================= #
    # <<< END add_cli_output METHOD >>>
    # ============================================================= #