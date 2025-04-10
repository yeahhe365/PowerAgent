# ========================================
# 文件名: PowerAgent/gui/main_window_handlers.py
# (MODIFIED - Removed eventFilter method)
# ----------------------------------------
# gui/main_window_handlers.py
# -*- coding: utf-8 -*-

import re
import os
import platform
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton
# <<< MODIFICATION: Removed QEvent import (no longer needed) >>>
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QKeySequence # Keep QKeySequence for type hinting

# Import necessary components from the project
from core import config
from .settings_dialog import SettingsDialog # Settings dialog interaction

# Type hinting for MainWindow without causing circular import at runtime
if TYPE_CHECKING:
    from .main_window import MainWindow


class HandlersMixin:
    """Mixin containing user interaction handlers for MainWindow."""

    # <<< MODIFICATION: Added debug print back to handle_send_message for confirmation >>>
    @Slot()
    def handle_send_message(self: 'MainWindow'):
        # --- Debug Print 9: Confirm handle_send_message is called ---
        print("[handle_send_message Debug 9] Function called.")
        # Handles sending chat messages to the AI
        if self._closing:
             print("[handle_send_message Debug] Returning: _closing is True.")
             return
        if not self.chat_input:
             print("[handle_send_message Debug] Returning: self.chat_input is None.")
             return
        if not self.model_selector_combo:
             print("[handle_send_message Debug] Returning: self.model_selector_combo is None.")
             return

        user_prompt = self.chat_input.toPlainText().strip()
        if not user_prompt:
             print("[handle_send_message Debug] Returning: user_prompt is empty.")
             # Keep input field focus if prompt was empty and Enter was pressed
             if self.chat_input:
                 self.chat_input.setFocus()
             return

        print("[handle_send_message Debug] Clearing input and proceeding...")
        self.chat_input.clear() # Clear input immediately

        # Handle slash commands first
        if user_prompt.startswith("/"):
            self.handle_slash_command(user_prompt)
            return

        # Check if API is configured and a model is selected
        selected_model_id = self.model_selector_combo.currentText()
        is_placeholder = selected_model_id == "未配置模型" or not selected_model_id

        if not config.API_KEY or not config.API_URL or not config.MODEL_ID_STRING or is_placeholder:
             if is_placeholder:
                 self.add_chat_message("Error", "请先在工具栏选择一个有效的 AI 模型。如果列表为空，请使用“设置”配置模型 ID。")
             else:
                 self.add_chat_message("Error", "API 未配置。请使用“设置”按钮或 /settings 命令进行配置。")
             # Restore focus if API not configured
             if self.chat_input:
                 self.chat_input.setFocus()
             return

        # Stop any previous API worker if it's running
        self.stop_api_worker()

        # Add user's message to display and history
        self.add_chat_message("User", user_prompt, add_to_internal_history=True)
        # Create a copy of history for the worker thread
        history_for_worker = list(self.conversation_history)

        # Add CLI context if enabled and CLI output exists
        if config.INCLUDE_CLI_CONTEXT and self.cli_output_display:
            full_cli_text = self.cli_output_display.toPlainText().strip()
            if full_cli_text:
                # Format context message
                context_msg_content = (
                    f"--- Current CLI Output (Full) ---\n"
                    f"{full_cli_text}\n"
                    f"--- End CLI Output ---"
                )
                context_role = "user" # Use 'user' role for context message
                if len(history_for_worker) >= 1:
                    # Insert before the last element (which is the user prompt)
                    history_for_worker.insert(-1, (context_role, context_msg_content))
                else: # Fallback if history was empty (shouldn't happen here)
                    history_for_worker.append((context_role, context_msg_content))
                    history_for_worker.append(("User", user_prompt)) # Re-add user prompt
                print(f"[MainWindow] Added CLI context ({len(full_cli_text)} chars) to history for worker.")

        # Set UI to busy state and start the API worker thread
        self.set_busy_state(True, "api")
        print(f"Starting ApiWorkerThread for model: {selected_model_id}...")
        # Starting the worker thread is handled in the WorkersMixin or main window logic
        self.start_api_worker(selected_model_id, history_for_worker, user_prompt)


    def handle_slash_command(self: 'MainWindow', command: str):
        # (No changes in this method)
        if self._closing: return
        command_lower = command.lower().strip()
        parts = command.split(maxsplit=1)
        cmd_base = parts[0].lower()
        arg = parts[1].strip() if len(parts) == 2 else None
        print(f"Processing slash command: {command}")

        if cmd_base == "/exit":
            self.close()
        elif cmd_base == "/clear":
            self.handle_clear_chat()
        elif cmd_base == "/clear_cli":
            self.handle_clear_cli()
        elif cmd_base == "/clear_all":
            self.handle_clear_chat()
            self.handle_clear_cli()
            self.add_chat_message("System", "聊天和命令行显示已清除。", add_to_internal_history=False)
        elif cmd_base == "/settings":
            self.open_settings_dialog()
        elif cmd_base == "/save":
            self.save_state()
            self.add_chat_message("System", "当前状态 (历史, CWD, 选择的模型) 已保存。", add_to_internal_history=False)
        elif cmd_base == "/help":
            self.show_help()
        elif cmd_base == "/cwd":
            self.add_chat_message("System", f"当前工作目录: {self.current_directory}", add_to_internal_history=False)
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
                    try:
                        lines_to_show = int(arg)
                        lines_to_show = max(1, lines_to_show)
                    except ValueError:
                        self.add_chat_message("Error", f"无效的行数: '{arg}'。请输入一个数字。", add_to_internal_history=False)
                        return
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
        else:
            self.add_chat_message("Error", f"未知命令: {command}。输入 /help 获取帮助。", add_to_internal_history=False)

    @Slot()
    def handle_clear_chat(self: 'MainWindow'):
        # (No changes in this method)
        if self._closing: return
        print("Clear Chat action triggered.")
        if self.chat_history_display:
            self.chat_history_display.clear()
        self.conversation_history.clear()
        self.add_chat_message("System", "聊天历史已清除。", add_to_internal_history=False)
        self.save_state();
        print("Chat history display and internal history deque cleared and state saved.")

    @Slot()
    def handle_clear_cli(self: 'MainWindow'):
        # (No changes in this method)
        if self._closing or not self.cli_output_display:
            return
        print("Clear CLI action triggered.")
        self.cli_output_display.clear()
        print("CLI output display cleared.")
        if self.cli_input:
            self.cli_input.setFocus()

    @Slot()
    def handle_manual_command(self: 'MainWindow'):
        # (No changes in this method)
        if self._closing or not self.cli_input: return
        command = self.cli_input.text().strip();
        if not command: return
        if not self.cli_command_history or self.cli_command_history[-1] != command:
            self.cli_command_history.append(command)
        self.cli_history_index = -1
        self.cli_input.clear()
        command_lower = command.lower()
        is_windows = platform.system() == "Windows"
        if (is_windows and (command_lower == "cls" or command_lower == "clear")) or \
           (not is_windows and command_lower == "clear"):
            print(f"Intercepted '{command}' command. Clearing CLI display directly.")
            self.handle_clear_cli()
            return
        self.stop_manual_worker()
        echo_message_bytes = f"User {self.current_directory}: {command}".encode('utf-8')
        self.add_cli_output(echo_message_bytes, "user")
        self.set_busy_state(True, "manual")
        print(f"Starting ManualCommandThread for: {command}")
        self.start_manual_worker(command)


    def keyPressEvent(self: 'MainWindow', event: QKeySequence):
        # (No changes in this method)
        focused_widget = QApplication.focusWidget()
        if focused_widget == self.cli_input:
            key = event.key(); modifiers = event.modifiers()
            if key == Qt.Key.Key_Up and not modifiers:
                if not self.cli_command_history: event.accept(); return
                if self.cli_history_index == -1:
                    self.cli_history_index = len(self.cli_command_history) - 1
                elif self.cli_history_index > 0:
                    self.cli_history_index -= 1
                else:
                    event.accept(); return
                if 0 <= self.cli_history_index < len(self.cli_command_history):
                    self.cli_input.setText(self.cli_command_history[self.cli_history_index])
                    self.cli_input.end(False)
                event.accept(); return
            elif key == Qt.Key.Key_Down and not modifiers:
                if self.cli_history_index == -1: event.accept(); return
                if self.cli_history_index < len(self.cli_command_history) - 1:
                    self.cli_history_index += 1;
                    self.cli_input.setText(self.cli_command_history[self.cli_history_index]);
                    self.cli_input.end(False)
                else:
                    self.cli_history_index = -1; self.cli_input.clear()
                event.accept(); return
            elif self.cli_history_index != -1 and key not in (
                 Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
                 Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                 Qt.Key.Key_Home, Qt.Key.Key_End ):
                 self.cli_history_index = -1
        if hasattr(super(type(self), self), 'keyPressEvent'):
             super(type(self), self).keyPressEvent(event)


    # ============================================================= #
    # <<< REMOVED: eventFilter method is no longer needed >>>
    # ============================================================= #
    # def eventFilter(self: 'MainWindow', watched, event):
    #     # ... (code removed) ...
    #     pass
    # ============================================================= #
    # <<< END REMOVED >>>
    # ============================================================= #


    @Slot(str)
    def handle_model_selection_changed(self: 'MainWindow', selected_model: str):
        # (No changes in this method)
        if self._closing or not self.model_selector_combo:
            return
        if not selected_model or selected_model == "未配置模型" or self.model_selector_combo.signalsBlocked():
            return
        current_config_selection = config.CURRENTLY_SELECTED_MODEL_ID
        if selected_model != current_config_selection:
            print(f"Model selection changed to: '{selected_model}'")
            config.CURRENTLY_SELECTED_MODEL_ID = selected_model
            self.save_state()
            self.add_chat_message("System", f"已切换模型至: {selected_model}", add_to_internal_history=False)
        else:
            pass

    @Slot()
    def open_settings_dialog(self: 'MainWindow'):
        # (No changes in this method)
        if self.settings_dialog_open or self._closing: return
        self.settings_dialog_open = True
        print("Opening settings dialog...")
        dialog = SettingsDialog(self)
        current_theme_before = config.APP_THEME
        current_config_before = config.get_current_config()
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            print("Settings dialog accepted.")
            (api_key, api_url, model_id_string, auto_startup, new_theme,
             include_cli_context, include_timestamp) = dialog.get_values()
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
                new_model_list = [m.strip() for m in model_id_string.split(',') if m.strip()]
                current_selected_model = config.CURRENTLY_SELECTED_MODEL_ID
                new_selected_model = current_selected_model
                if not current_selected_model or current_selected_model not in new_model_list:
                    new_selected_model = new_model_list[0] if new_model_list else ""
                print(f"  Saving - New Model List: {new_model_list}, Effective Selected Model: {new_selected_model}")
                config.save_config(
                    api_key, api_url, model_id_string, auto_startup, new_theme,
                    include_cli_context, include_timestamp,
                    selected_model_id=new_selected_model
                )
                print(f"Configuration saved. New theme: {new_theme}, AutoStart: {auto_startup}, ModelList: {model_id_string}, SelectedModel: {new_selected_model}, CLI Context: {include_cli_context}, Timestamp: {include_timestamp}")
            else:
                print("Settings dialog accepted, but no changes detected in configuration values.")
            self.update_model_selector()
            theme_changed = new_theme != current_theme_before
            if theme_changed:
                print("Theme changed, applying new theme styles...")
                app = QApplication.instance()
                from .palette import setup_palette
                if app: setup_palette(app, new_theme)
                self.apply_theme_specific_styles()
            current_config_after_dialog = config.get_current_config()
            should_reload_state = was_reset_likely or (not current_config_after_dialog['api_key'] and current_config_before['api_key'])
            if should_reload_state:
                print("Reset or API key removal detected. Re-loading state and syncing CWD.")
                self.load_state()
                try:
                    if os.path.isdir(self.current_directory):
                        os.chdir(self.current_directory)
                        print(f"Process CWD synced to loaded/reset state: {self.current_directory}")
                    else:
                         print(f"Warning: Loaded/reset directory '{self.current_directory}' not found after settings change. Using initial directory.")
                         self.current_directory = self.initial_directory
                         try: os.chdir(self.current_directory)
                         except Exception as e_chdir_fallback:
                             print(f"CRITICAL: Could not change to initial directory '{self.current_directory}': {e_chdir_fallback}")
                             self.current_directory = os.getcwd()
                             print(f"Using OS CWD as final fallback: {self.current_directory}")
                         self.save_state()
                except Exception as e:
                    print(f"CRITICAL: Error setting process CWD after settings reset/change to '{self.current_directory}': {e}")
                self.load_and_apply_state()
                self.update_model_selector()
            elif config_changed or theme_changed:
                 print("Configuration or theme changed, reapplying styles and updating model selector.")
                 self.apply_theme_specific_styles()
                 self.update_model_selector()
            self.update_prompt()
            print("Settings dialog processing finished.")
        else:
            print("Settings dialog cancelled.")
        self.settings_dialog_open = False
        self.activateWindow(); self.raise_()