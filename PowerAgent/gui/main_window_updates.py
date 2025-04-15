# gui/main_window_updates.py
# -*- coding: utf-8 -*-

import os
import platform
import re
import json
import html
import logging # Import logging
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

# --- Get Logger ---
logger = logging.getLogger(__name__)

class UpdatesMixin:
    """Mixin containing UI update/display logic for MainWindow."""

    def _get_icon(self: 'MainWindow', theme_name: str, fallback_filename: str, text_fallback: str = None) -> QIcon:
        """Helper to get themed icons or fallbacks."""
        # Logging might be too verbose here, consider only logging failures
        icon = QIcon.fromTheme(theme_name)
        if icon.isNull():
            # Log the attempt to use fallback
            # logger.debug(f"Theme icon '{theme_name}' not found. Trying fallback '{fallback_filename}'.")
            assets_dir = os.path.join(self.application_base_dir, "assets")
            icon_path = os.path.join(assets_dir, fallback_filename)
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                # logger.debug(f"Loaded fallback icon from: {icon_path}")
            else:
                # Log only if fallback also fails
                logger.warning(f"Icon theme '{theme_name}' not found and fallback '{fallback_filename}' does not exist in {assets_dir}.")
        return icon

    def set_window_icon(self: 'MainWindow'):
        """Sets the main application window icon."""
        logger.debug("Setting main window icon...")
        try:
            icon = self._get_icon(APP_NAME.lower(), "icon.png", None)
            if icon.isNull(): icon = self._get_icon("utilities-terminal", "app.ico", None)
            if not icon.isNull():
                self.setWindowIcon(icon)
                logger.info("Main window icon set.")
            else:
                logger.warning("Could not find a suitable window icon via theme or fallback.")
        except Exception as e:
             logger.error("Error setting window icon.", exc_info=True)

    def _get_os_fonts(self: 'MainWindow'):
        """Helper to get platform-specific monospace fonts."""
        # No logging needed here, just returns values
        mono_font_family = "Consolas, Courier New"; mono_font_size = 10; label_font_size = 9
        if platform.system() == "Darwin": mono_font_family, mono_font_size, label_font_size = "Menlo", 11, 9
        elif platform.system() == "Linux": mono_font_family, mono_font_size, label_font_size = "Monospace", 10, 9
        return mono_font_family, mono_font_size, label_font_size

    def apply_theme_specific_styles(self: 'MainWindow'):
        """Applies the QSS stylesheet based on the current theme."""
        if self._closing: logger.debug("Skipping apply_theme_specific_styles during close."); return
        theme = config.APP_THEME
        logger.info(f"Applying styles for theme: '{theme}'")
        mono_font_family, mono_font_size, label_font_size = self._get_os_fonts()
        qss = ""
        app_instance = QApplication.instance()
        if not app_instance:
             logger.error("Cannot apply styles: QApplication instance not found.")
             return

        try:
            palette = app_instance.palette()
            border_color_role = QPalette.ColorRole.Mid # Try Mid role
            border_color = palette.color(border_color_role)
            if not border_color.isValid(): border_color = palette.color(QPalette.ColorRole.Dark) # Fallback to Dark
            if not border_color.isValid(): border_color = QColor(180, 180, 180) # Final fallback
            border_color_name = border_color.name() # Get hex string #RRGGBB

            if theme == "system":
                logger.debug("Generating minimal QSS for system theme.")
                qss = MINIMAL_STYLESHEET_SYSTEM_THEME.format(
                    mono_font_family=mono_font_family, mono_font_size=mono_font_size,
                    label_font_size=label_font_size, border=border_color_name
                )
            else: # "dark" or "light"
                logger.debug(f"Generating full QSS for '{theme}' theme.")
                # Get specific colors from constants module
                cli_bg=get_color("cli_bg", theme); cli_output_color=get_color("cli_output", theme)
                prompt_color=get_color("prompt", theme); border_color_const=get_color("border", theme)
                text_main_color=get_color("text_main", theme); status_label_color=get_color("status_label", theme)
                # Get standard palette colors
                window_bg=palette.color(QPalette.ColorRole.Window).name()
                base_bg=palette.color(QPalette.ColorRole.Base).name()
                highlight_bg=palette.color(QPalette.ColorRole.Highlight).name()
                highlighted_text=palette.color(QPalette.ColorRole.HighlightedText).name()
                button_bg=palette.color(QPalette.ColorRole.Button).name()
                button_text_color=palette.color(QPalette.ColorRole.ButtonText).name()
                tooltip_bg=palette.color(QPalette.ColorRole.ToolTipBase).name()
                tooltip_text=palette.color(QPalette.ColorRole.ToolTipText).name()
                text_disabled=palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name()
                button_disabled_bg=palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button).name()
                border_disabled=palette.color(QPalette.ColorGroup.Disabled, border_color_role).name()
                button_pressed_bg=QColor(button_bg).darker(115).name() # Slightly darker

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

            logger.debug(f"Applying generated QSS (Length: {len(qss)}).")
            self.setStyleSheet(qss)
            self.update() # Force repaint if necessary
            self.update_prompt() # Update prompt as its colors might change
            logger.info(f"Styles applied successfully for theme '{theme}'.")
        except Exception as e:
             logger.error(f"Failed to apply styles for theme '{theme}'.", exc_info=True)


    def load_and_apply_state(self: 'MainWindow'):
        """Applies loaded history to chat display after UI is ready."""
        if self._closing: logger.debug("Skipping load_and_apply_state during close."); return
        logger.info(f"Applying loaded state to UI (History items: {len(self.conversation_history)})...")

        history_items_applied = 0
        try:
            # Use a copy to iterate while modifying the original deque
            history_copy = list(self.conversation_history)

            if self.chat_history_display:
                logger.debug("Clearing chat display and internal history before applying loaded state...")
                self.chat_history_display.clear() # Clear display first
                self.conversation_history.clear() # Clear internal deque before re-adding

                # Re-add messages using the standard method to ensure formatting
                for role, message in history_copy:
                    # add_chat_message should log its own details
                    self.add_chat_message(role, message, add_to_internal_history=True)
                    history_items_applied += 1
                logger.info(f"Applied {history_items_applied} loaded history items to display and internal deque.")
            else:
                # If display isn't ready, ensure internal history deque is loaded (already done in load_state)
                logger.warning("Chat history display not found during state application. Internal history deque should already be loaded.")
                # Verify internal deque content
                if len(self.conversation_history) == len(history_copy):
                     logger.debug("Internal history deque seems correctly loaded.")
                else:
                     logger.warning(f"Internal history deque length ({len(self.conversation_history)}) mismatch with loaded copy ({len(history_copy)}). Re-populating.")
                     self.conversation_history = deque(history_copy, maxlen=self.conversation_history.maxlen)


            # Update other UI elements based on loaded state
            logger.debug("Updating model selector based on loaded state...")
            self.update_model_selector() # Should have logging
            logger.debug("Updating CLI prompt based on loaded state...")
            self.update_prompt() # Should have logging

        except Exception as e:
            logger.error("Error applying loaded state to UI.", exc_info=True)
        logger.info("Finished applying loaded state to UI.")

    def update_prompt(self: 'MainWindow'):
        """Updates the CLI prompt label with the current directory."""
        if self._closing or not self.cli_prompt_label:
            # logger.debug("Skipping prompt update (closing or label not ready).") # Can be too verbose
            return

        logger.debug(f"Updating CLI prompt for directory: {self.current_directory}")
        try:
            shell_prefix = "PS" if platform.system() == "Windows" else "$"
            display_path = self.current_directory

            # Make drive letter uppercase on Windows
            if platform.system() == "Windows" and len(display_path) >= 2 and display_path[1] == ':':
                display_path = display_path[0].upper() + display_path[1:]

            # Replace home directory path with '~'
            try:
                home_dir = os.path.expanduser("~")
                home_dir_compare = home_dir # Use original case for comparison start
                if platform.system() == "Windows" and len(home_dir_compare) >= 2 and home_dir_compare[1] == ':':
                    home_dir_compare = home_dir_compare[0].upper() + home_dir_compare[1:]

                # Normalize path separators for reliable comparison
                normalized_display_path = os.path.normpath(display_path)
                normalized_home_dir = os.path.normpath(home_dir_compare)

                if normalized_display_path == normalized_home_dir:
                    display_path = "~"
                elif normalized_display_path.startswith(normalized_home_dir + os.path.sep):
                    display_path = "~" + display_path[len(home_dir):] # Use original length for slicing
                # else: logger.debug("Path is not home directory or subdirectory.") # Optional debug
            except Exception as e:
                logger.warning(f"Error processing path for prompt display (tilde replacement): {e}", exc_info=False)

            prompt_text = f"{shell_prefix} {display_path}> "
            self.cli_prompt_label.setText(prompt_text)
            logger.debug(f"CLI prompt label updated to: '{prompt_text}'")
        except Exception as e:
            logger.error("Failed to update CLI prompt label.", exc_info=True)


    def update_model_selector(self: 'MainWindow'):
        """Updates the model selection QComboBox based on the configuration."""
        if self._closing or not self.model_selector_combo:
             # logger.debug("Skipping model selector update (closing or combo not ready).")
             return

        logger.info("Updating model selector...")
        try:
            saved_selected_model = config.CURRENTLY_SELECTED_MODEL_ID # Get current value from config
            logger.debug(f"Current selected model in config: '{saved_selected_model}'")

            self.model_selector_combo.blockSignals(True) # Prevent signals during update
            current_text = self.model_selector_combo.currentText() # Get current UI selection
            logger.debug("Clearing model selector items.")
            self.model_selector_combo.clear()

            model_id_string = config.MODEL_ID_STRING
            model_list = []
            if model_id_string:
                model_list = [m.strip() for m in model_id_string.split(',') if m.strip()]
            logger.debug(f"Available models from config string: {model_list}")

            if not model_list:
                placeholder_text = "未配置模型"
                logger.warning(f"No models configured. Adding placeholder '{placeholder_text}' and disabling selector.")
                self.model_selector_combo.addItem(placeholder_text)
                self.model_selector_combo.setEnabled(False)
                # Ensure global config doesn't hold an invalid selection
                if config.CURRENTLY_SELECTED_MODEL_ID != "":
                    logger.debug("Clearing selected model ID in config as list is empty.")
                    config.CURRENTLY_SELECTED_MODEL_ID = ""
            else:
                logger.debug(f"Adding {len(model_list)} models to selector.")
                self.model_selector_combo.addItems(model_list)
                self.model_selector_combo.setEnabled(True)
                logger.debug(f"Attempting to restore selection '{saved_selected_model}'...")
                found_index = self.model_selector_combo.findText(saved_selected_model)

                if saved_selected_model and found_index != -1:
                    self.model_selector_combo.setCurrentIndex(found_index)
                    logger.info(f"Restored model selection to '{saved_selected_model}' (Index: {found_index}).")
                else:
                    default_model = model_list[0]
                    logger.warning(f"Saved model '{saved_selected_model}' not found/invalid in list. Defaulting to first model: '{default_model}'.")
                    self.model_selector_combo.setCurrentIndex(0)
                    # Update the global config state if the selection had to be changed
                    if config.CURRENTLY_SELECTED_MODEL_ID != default_model:
                         logger.info(f"Updating selected model ID in config to '{default_model}'.")
                         config.CURRENTLY_SELECTED_MODEL_ID = default_model

            logger.debug("Re-enabling model selector signals.")
            self.model_selector_combo.blockSignals(False)
            # Log if the actual UI selection changed
            new_text = self.model_selector_combo.currentText()
            if new_text != current_text: logger.info(f"Model selector UI text changed from '{current_text}' to '{new_text}'.")

        except Exception as e:
             logger.error("Failed to update model selector.", exc_info=True)
             # Attempt to re-enable signals in case of error
             if self.model_selector_combo: self.model_selector_combo.blockSignals(False)

    def update_status_indicator(self: 'MainWindow', busy: bool):
        """Updates the custom status indicator widget's state."""
        if self._closing or not self.status_indicator:
            # logger.debug("Skipping status indicator update.") # Too verbose
            return
        # logger.debug(f"Updating status indicator to busy={busy}") # Also verbose
        try:
            if hasattr(self.status_indicator, 'setBusy') and callable(self.status_indicator.setBusy):
                 self.status_indicator.setBusy(busy)
                 # logger.debug("Status indicator updated.")
            else:
                 logger.warning(f"status_indicator is not a StatusIndicatorWidget or does not have setBusy method. Type: {type(self.status_indicator)}")
        except Exception as e:
            logger.error("Failed to update status indicator.", exc_info=True)

    def add_chat_message(
        self: 'MainWindow',
        role: str,
        message: str,
        add_to_internal_history: bool = True,
        elapsed_time: float | None = None
    ):
        """Adds message to the chat display, parsing actions and formatting timestamp/commands."""
        role_lower = role.lower()
        # Truncate long messages for logging clarity
        log_message_preview = message[:100].replace('\n', '\\n') + ('...' if len(message) > 100 else '')
        logger.info(f"Adding chat message: Role='{role}', AddToHistory={add_to_internal_history}, Message='{log_message_preview}'")

        # --- Update Internal History First (if requested) ---
        internal_history_updated = False
        if add_to_internal_history:
             message_for_history = message.strip() # Use stripped for comparison/storage
             # Ensure the deque exists before appending
             if not hasattr(self, 'conversation_history'):
                 logger.warning("conversation_history deque not initialized before add_chat_message. Creating new.")
                 self.conversation_history = deque(maxlen=50)

             # Append only if history is empty or the new message differs from the last
             if not self.conversation_history or self.conversation_history[-1] != (role, message_for_history):
                 logger.debug(f"Appending message to internal history (Role: {role}).")
                 self.conversation_history.append((role, message_for_history))
                 internal_history_updated = True
             else:
                 logger.debug("Skipping append to internal history: Duplicate of last message.")
        else:
             logger.debug("Skipping append to internal history (add_to_internal_history=False).")


        # --- Update Display ---
        if self._closing: logger.debug("Skipping chat display update (closing)."); return
        if not self.chat_history_display: logger.error("Cannot add chat message: chat_history_display not found."); return

        target_widget = self.chat_history_display
        role_display = "AI Command" if role_lower == "ai command" else role.capitalize()
        prefix_text = f"{role_display}: "
        message_content = message.rstrip()

        # Move cursor to end safely
        try:
            cursor = target_widget.textCursor(); at_end = cursor.atEnd()
            cursor.movePosition(QTextCursor.MoveOperation.End); target_widget.setTextCursor(cursor)
        except RuntimeError as e: logger.warning(f"Could not get/set text cursor for chat display: {e}"); return
        except Exception as e: logger.error("Unexpected error moving chat cursor.", exc_info=True); return

        # --- Setup Text Formats ---
        # (Format setup logic remains the same)
        current_theme = config.APP_THEME; default_text_color = target_widget.palette().color(QPalette.ColorRole.Text); default_font_size = target_widget.font().pointSize(); default_font_size = max(10, default_font_size)
        prefix_format = QTextCharFormat(); valid_color_roles = ['user', 'model', 'system', 'error', 'help', 'prompt', 'ai_command', 'keyboard_action']; prefix_color_role_key = role_lower if role_lower in valid_color_roles else 'system'; prefix_color = get_color(prefix_color_role_key, current_theme);
        if not isinstance(prefix_color, QColor): prefix_color = default_text_color
        prefix_format.setForeground(prefix_color); prefix_font = prefix_format.font(); prefix_font.setBold(True); prefix_format.setFont(prefix_font)
        message_format = QTextCharFormat(); message_color = default_text_color
        if role_lower == 'ai command': message_color = get_color('ai_command', current_theme)
        elif role_lower in ['system', 'error', 'help', 'prompt']: message_color = prefix_color
        elif role_lower == 'model': message_color = get_color('model', current_theme)
        elif role_lower == 'user': message_color = get_color('user', current_theme)
        if not isinstance(message_color, QColor): message_color = default_text_color
        message_format.setForeground(message_color); message_font = message_format.font(); message_font.setBold(False); message_format.setFont(message_font)
        kb_action_format = QTextCharFormat(); kb_action_color = get_color('keyboard_action', current_theme); kb_action_bg_color = get_color('keyboard_action_bg', current_theme)
        if not isinstance(kb_action_color, QColor): kb_action_color = get_color('prompt', current_theme)
        if not isinstance(kb_action_bg_color, QColor): kb_action_bg_color = QColor(Qt.GlobalColor.transparent)
        kb_action_format.setForeground(kb_action_color); kb_action_format.setBackground(QBrush(kb_action_bg_color)); kb_font = kb_action_format.font(); kb_font.setBold(False); kb_action_format.setFont(kb_font)
        timestamp_format = QTextCharFormat(); timestamp_color = get_color('timestamp_color', current_theme)
        if not isinstance(timestamp_color, QColor): timestamp_color = QColor("gray")
        timestamp_format.setForeground(timestamp_color); timestamp_font = timestamp_format.font(); timestamp_font.setPointSize(max(6, default_font_size - 1)); timestamp_format.setFont(timestamp_font)

        # --- Insert Content Safely ---
        try:
            logger.debug("Inserting prefix...")
            cursor.insertText("\n") # Ensure separation from previous message
            cursor.setCharFormat(prefix_format); cursor.insertText(prefix_text)

            logger.debug("Parsing message content for actions/formatting...")
            last_match_end = 0
            # Parse Keyboard Actions only if role is 'Model'
            if role_lower == 'model':
                func_pattern = re.compile(r"""(<(function|keyboard)\s+.*?/>(?:</\2>)*)""", re.VERBOSE | re.DOTALL | re.IGNORECASE)
                for match in func_pattern.finditer(message_content):
                    start, end = match.span(1)
                    # Insert text before the match
                    text_before = message_content[last_match_end:start]
                    if text_before: cursor.setCharFormat(message_format); cursor.insertText(text_before)
                    # Process and insert the action tag representation
                    action_tag_full = match.group(1)
                    func_name_match = re.search(r"call=['\"]([^'\"]+)['\"]", action_tag_full, re.IGNORECASE)
                    func_name = func_name_match.group(1) if func_name_match else "unknown_action"
                    args_match = re.search(r"args=['\"](.*?)['\"]", action_tag_full, re.IGNORECASE | re.DOTALL)
                    args_json_str_html = args_match.group(1) if args_match else "{}"

                    display_action_str = f"[Action: {func_name}]" # Default display
                    try:
                        args_json_str = html.unescape(args_json_str_html); args_dict = json.loads(args_json_str)
                        if func_name == "clipboard_paste": text_to_paste = args_dict.get('text', ''); display_text = text_to_paste[:30] + ('...' if len(text_to_paste) > 30 else ''); display_action_str = f" 📋 Paste: '{display_text}' "
                        elif func_name == "keyboard_press": display_action_str = f" ⌨️ Press: {args_dict.get('key', 'N/A').capitalize()} "
                        elif func_name == "keyboard_hotkey": display_action_str = f" ⌨️ Hotkey: {'+'.join(k.capitalize() for k in args_dict.get('keys', []))} "
                        else: display_action_str = f" ⌨️ Unknown Action: {func_name} "
                    except Exception as parse_err: logger.warning(f"Error processing action tag '{func_name}' for display: {parse_err}", exc_info=False); display_action_str = f" ⌨️ Error Parsing Action: {func_name} "
                    logger.debug(f"Inserting formatted keyboard action: {display_action_str}")
                    cursor.setCharFormat(kb_action_format); cursor.insertText(display_action_str)
                    last_match_end = end
            # Handle AI Command Echo
            elif role_lower == 'ai command':
                 logger.debug("Inserting AI command echo text.")
                 cursor.setCharFormat(message_format); cursor.insertText(message_content)
                 last_match_end = len(message_content)

            # Insert any remaining text
            text_after = message_content[last_match_end:]
            if text_after: logger.debug("Inserting remaining message text."); cursor.setCharFormat(message_format); cursor.insertText(text_after)

            # Insert Timestamp (if provided)
            if role_lower == 'model' and elapsed_time is not None and elapsed_time >= 0:
                timestamp_text = f" (耗时: {elapsed_time:.2f} 秒)"
                logger.debug(f"Inserting timestamp: {timestamp_text}")
                cursor.setCharFormat(timestamp_format); cursor.insertText(timestamp_text)

            # Final newline (handled by initial insertText("\n") now)
            # cursor.insertText('\n')

        except Exception as insert_err:
             logger.error("Error inserting chat message content.", exc_info=True)
             # Attempt to insert a basic error message if insertion fails badly
             try: cursor.insertText(f"\n[Error displaying message: {insert_err}]\n")
             except: pass # Ignore errors during fallback insertion

        # --- Scroll to bottom ---
        if at_end:
            # logger.debug("Scrolling chat display to bottom.") # Too verbose
            scrollbar = target_widget.verticalScrollBar()
            if scrollbar:
                try:
                    # Give Qt a chance to process layout changes before scrolling
                    QApplication.processEvents()
                    scrollbar.setValue(scrollbar.maximum())
                    # target_widget.ensureCursorVisible() # Sometimes less reliable than setting scrollbar max
                except RuntimeError as scroll_err: logger.warning(f"Could not scroll chat display (RuntimeError): {scroll_err}")
                except Exception as scroll_err: logger.warning(f"Error scrolling chat display: {scroll_err}")

        logger.info("Finished adding chat message.")


    def add_cli_output(self: 'MainWindow', message_bytes: bytes, message_type: str = "output"):
        """Adds message (decoded) to the CLI output display. Logs the process."""
        # logger.debug(f"Adding CLI output: Type='{message_type}', Bytes={len(message_bytes)}") # Can be very verbose

        if self._closing: logger.debug("Skipping add_cli_output during close."); return
        if not self.cli_output_display: logger.error("Cannot add CLI output: cli_output_display not found."); return

        target_widget = self.cli_output_display
        try:
            decoded_message = decode_output(message_bytes).rstrip() # Use utility function
            if not decoded_message: logger.debug("Skipping empty CLI message."); return
            # logger.debug(f"Decoded CLI message: {decoded_message[:150]}...") # Still verbose
        except Exception as decode_err:
            logger.error(f"Failed to decode CLI message bytes (Type: {message_type})", exc_info=True)
            decoded_message = f"[Decode Error: {decode_err}]\n" + repr(message_bytes) # Show error and repr
            message_type = "error" # Treat decode errors as errors

        # Move cursor to end safely
        try:
            cursor = target_widget.textCursor(); at_end = cursor.atEnd()
            cursor.movePosition(QTextCursor.MoveOperation.End); target_widget.setTextCursor(cursor)
        except RuntimeError as e: logger.warning(f"Could not get/set CLI text cursor: {e}"); return
        except Exception as e: logger.error("Unexpected error moving CLI cursor.", exc_info=True); return

        # --- Determine Formatting ---
        # (Color/Format determination logic remains the same)
        current_theme = config.APP_THEME; prefix_format = QTextCharFormat(); message_format = QTextCharFormat(); prefix_to_insert = None; message_to_insert = decoded_message; prefix_color = None; message_color = None; prefix_bold = False
        user_echo_match = re.match(r"^(User\s+.*?>\s)", decoded_message); model_echo_match = re.match(r"^(Model\s+.*?>\s)", decoded_message)
        if user_echo_match and message_type == "user": prefix_to_insert = user_echo_match.group(1); message_to_insert = decoded_message[len(prefix_to_insert):]; prefix_color = get_color('user', current_theme); message_color = get_color('cli_output', current_theme); prefix_bold = True
        elif model_echo_match and message_type == "output": prefix_to_insert = model_echo_match.group(1); message_to_insert = decoded_message[len(prefix_to_insert):]; prefix_color = get_color('model', current_theme); message_color = get_color('ai_command', current_theme); prefix_bold = True
        else:
            if message_type == "error": message_color = get_color('cli_error', current_theme)
            elif message_type == "system": message_color = get_color('system', current_theme)
            else: message_color = get_color('cli_output', current_theme)
        # Adjust for system theme
        if current_theme == "system":
            sys_palette = target_widget.palette(); default_sys_color = sys_palette.color(QPalette.ColorRole.Text)
            if message_type == "error": sys_error_color = sys_palette.color(QPalette.ColorRole.BrightText); message_color = sys_error_color if sys_error_color.isValid() and sys_error_color.name() != "#000000" else QColor("red")
            elif message_type == "system": sys_system_color = sys_palette.color(QPalette.ColorRole.ToolTipText); message_color = sys_system_color if sys_system_color.isValid() else default_sys_color
            elif isinstance(message_color, QColor) and (message_color.name() == get_color('cli_output', "dark").name() or message_color.name() == get_color('ai_command', "dark").name()): message_color = default_sys_color
        # Ensure valid colors
        default_cli_output_color = get_color('cli_output', current_theme); prefix_color = prefix_color if isinstance(prefix_color, QColor) else default_cli_output_color; message_color = message_color if isinstance(message_color, QColor) else default_cli_output_color

        # --- Insert Text Safely ---
        try:
            # logger.debug("Inserting CLI text...") # Too verbose
            if prefix_to_insert: # User/Model echo with CWD
                prefix_format.setForeground(prefix_color); prefix_font = prefix_format.font(); prefix_font.setBold(prefix_bold); prefix_format.setFont(prefix_font)
                cursor.setCharFormat(prefix_format); cursor.insertText(prefix_to_insert)
                message_format.setForeground(message_color); message_font = message_format.font(); message_font.setBold(False); message_format.setFont(message_font)
                cursor.setCharFormat(message_format); cursor.insertText(message_to_insert + "\n")
            else: # Regular output, error, system
                message_format.setForeground(message_color); message_font = message_format.font(); message_font.setBold(False); message_format.setFont(message_font)
                cursor.setCharFormat(message_format); cursor.insertText(decoded_message + "\n")
            # logger.debug("CLI text inserted.") # Too verbose
        except Exception as insert_err:
             logger.error("Error inserting CLI text.", exc_info=True)
             try: cursor.insertText(f"\n[Error displaying CLI message: {insert_err}]\n")
             except: pass

        # --- Scroll Safely ---
        if at_end:
            scrollbar = target_widget.verticalScrollBar()
            if scrollbar:
                try:
                    QApplication.processEvents()
                    scrollbar.setValue(scrollbar.maximum())
                    # target_widget.ensureCursorVisible()
                except RuntimeError as scroll_err: logger.warning(f"Could not scroll CLI display (RuntimeError): {scroll_err}")
                except Exception as scroll_err: logger.warning(f"Error scrolling CLI display: {scroll_err}")
        # logger.debug("Finished adding CLI output.") # Too verbose