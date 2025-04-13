# ========================================
# 文件名: PowerAgent/gui/main_window_handlers.py
# (MODIFIED - Handle new max_iterations setting in open_settings_dialog)
# ----------------------------------------
# gui/main_window_handlers.py
# -*- coding: utf-8 -*-

import re
import os
import platform
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton
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

    # ============================================================= #
    # <<< Handler for the merged Send/Stop button >>>
    # ============================================================= #
    @Slot()
    def handle_send_stop_button_click(self: 'MainWindow'):
        """Handles clicks on the combined Send/Stop button."""
        if self._closing: return

        # Check if the API worker is currently running
        if self.api_worker_thread and self.api_worker_thread.isRunning():
            # Worker is running, so the button click means "Stop"
            print("[Handler] Send/Stop button clicked: Stopping API worker...")
            self.stop_api_worker() # Call the stop method (defined in WorkersMixin)
        else:
            # Worker is not running, so the button click means "Send"
            print("[Handler] Send/Stop button clicked: Sending message...")
            self.handle_send_message() # Call the original send message handler
    # ============================================================= #
    # <<< END >>>
    # ============================================================= #

    @Slot()
    def handle_send_message(self: 'MainWindow'):
        """Handles sending chat messages to the AI. Called by handle_send_stop_button_click when idle."""
        # print("[handle_send_message Debug 9] Function called.")
        if self._closing: print("[handle_send_message Debug] Returning: _closing is True."); return
        if not self.chat_input: print("[handle_send_message Debug] Returning: self.chat_input is None."); return
        if not self.model_selector_combo: print("[handle_send_message Debug] Returning: self.model_selector_combo is None."); return

        # Check if already busy (safeguard)
        if self.api_worker_thread and self.api_worker_thread.isRunning():
             print("[handle_send_message Debug] Warning: API worker is already running. Ignoring send request.")
             return

        user_prompt = self.chat_input.toPlainText().strip()
        if not user_prompt:
             # print("[handle_send_message Debug] Returning: user_prompt is empty.")
             if self.chat_input: self.chat_input.setFocus()
             return

        # print("[handle_send_message Debug] Clearing input and proceeding...")
        self.chat_input.clear()

        if user_prompt.startswith("/"):
            self.handle_slash_command(user_prompt)
            return

        selected_model_id = self.model_selector_combo.currentText()
        is_placeholder = selected_model_id == "未配置模型" or not selected_model_id

        if not config.API_KEY or not config.API_URL or not config.MODEL_ID_STRING or is_placeholder:
             if is_placeholder: self.add_chat_message("Error", "请先在工具栏选择一个有效的 AI 模型。如果列表为空，请使用“设置”配置模型 ID。") # Chinese
             else: self.add_chat_message("Error", "API 未配置。请使用“设置”按钮或 /settings 命令进行配置。") # Chinese
             if self.chat_input: self.chat_input.setFocus()
             return

        self.add_chat_message("User", user_prompt, add_to_internal_history=True)
        # Create a copy of the history deque for the worker thread
        # Pass the *current* state of the deque
        history_for_worker = list(self.conversation_history)

        if config.INCLUDE_CLI_CONTEXT and self.cli_output_display:
            full_cli_text = self.cli_output_display.toPlainText().strip()
            if full_cli_text:
                # Use a consistent role, e.g., 'system' or 'user', for the context block
                context_role = "system"
                # Truncate context if extremely long (e.g., last 5000 chars) to avoid huge prompts
                max_context_len = 5000
                truncated_cli_text = full_cli_text[-max_context_len:]
                context_prefix = "--- 当前 CLI 输出 (最后 {} 字符) ---\n".format(len(truncated_cli_text)) if len(full_cli_text) > max_context_len else "--- 当前 CLI 输出 (完整) ---\n"
                context_msg_content = (f"{context_prefix}{truncated_cli_text}\n--- CLI 输出结束 ---") # Chinese

                # Insert context before the *last* user message in the copied history
                last_user_index = -1
                for i in range(len(history_for_worker) - 1, -1, -1):
                    # Check role case-insensitively
                    if history_for_worker[i][0].lower() == 'user':
                        last_user_index = i
                        break

                if last_user_index != -1:
                    history_for_worker.insert(last_user_index, (context_role, context_msg_content))
                else:
                    # If no user message found (unlikely here), prepend context
                    history_for_worker.insert(0, (context_role, context_msg_content))

                print(f"[MainWindow] Added CLI context ({len(truncated_cli_text)} chars) to history for worker.")


        # Set busy state for "api" task (updates Send/Stop button)
        self.set_busy_state(True, "api")
        print(f"Starting ApiWorkerThread for model: {selected_model_id}...")
        # Pass the potentially modified history_for_worker
        self.start_api_worker(selected_model_id, history_for_worker, user_prompt) # Call start method (in WorkersMixin)


    def handle_slash_command(self: 'MainWindow', command: str):
        # (No changes needed in this method body)
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
            print("[Handler] Chat and CLI display cleared (no system message shown).")
        elif cmd_base == "/settings":
            self.open_settings_dialog()
        elif cmd_base == "/save":
            self.save_state()
            self.add_chat_message("System", "当前状态 (历史, CWD, 选择的模型) 已保存。", add_to_internal_history=False) # Chinese
        elif cmd_base == "/help":
            self.show_help()
        elif cmd_base == "/cwd":
            self.add_chat_message("System", f"当前工作目录: {self.current_directory}", add_to_internal_history=False) # Chinese
        elif cmd_base == "/copy_cli":
            if self.cli_output_display:
                full_cli_text = self.cli_output_display.toPlainText()
                if full_cli_text:
                    try:
                        clipboard = QApplication.clipboard()
                        if clipboard: clipboard.setText(full_cli_text); self.add_chat_message("System", "左侧 CLI 输出已复制到剪贴板。", add_to_internal_history=False) # Chinese
                        else: self.add_chat_message("Error", "无法访问剪贴板。", add_to_internal_history=False) # Chinese
                    except Exception as e: self.add_chat_message("Error", f"复制到剪贴板时出错: {e}", add_to_internal_history=False) # Chinese
                else: self.add_chat_message("System", "左侧 CLI 输出为空。", add_to_internal_history=False) # Chinese
            else: self.add_chat_message("Error", "无法访问 CLI 输出区域。", add_to_internal_history=False) # Chinese
        elif cmd_base == "/show_cli":
            if self.cli_output_display:
                lines_to_show = 10
                if arg:
                    try: lines_to_show = max(1, int(arg))
                    except ValueError: self.add_chat_message("Error", f"无效的行数: '{arg}'。请输入一个数字。", add_to_internal_history=False); return # Chinese
                full_cli_text = self.cli_output_display.toPlainText()
                lines = full_cli_text.strip().splitlines(); last_n_lines = lines[-lines_to_show:]
                if last_n_lines: header = f"--- 左侧 CLI 输出 (最后 {len(last_n_lines)} 行) ---"; cli_content_message = header + "\n" + "\n".join(last_n_lines); self.add_chat_message("System", cli_content_message, add_to_internal_history=False) # Chinese
                else: self.add_chat_message("System", "左侧 CLI 输出为空。", add_to_internal_history=False) # Chinese
            else: self.add_chat_message("Error", "无法访问 CLI 输出区域。", add_to_internal_history=False) # Chinese
        else:
            # Use Chinese error message
            self.add_chat_message("Error", f"未知命令: {command}。输入 /help 获取帮助。", add_to_internal_history=False) # Chinese

    @Slot()
    def handle_clear_chat(self: 'MainWindow'):
        """Handles the '/clear' command or button click."""
        if self._closing: return
        print("Clear Chat action triggered.")
        # Stop API worker if running before clearing
        self.stop_api_worker()

        if self.chat_history_display: self.chat_history_display.clear()
        self.conversation_history.clear()
        # No system message shown on clear
        print("Chat history display cleared (No system message shown).")
        self.save_state()
        print("Chat history display and internal history deque cleared and state saved.")


    @Slot()
    def handle_clear_cli(self: 'MainWindow'):
        # (No changes needed in this method)
        if self._closing or not self.cli_output_display: return
        print("Clear CLI action triggered.")
        # Stop manual worker if running before clearing
        self.stop_manual_worker()
        self.cli_output_display.clear()
        print("CLI output display cleared.")
        if self.cli_input: self.cli_input.setFocus()

    @Slot()
    def handle_manual_command(self: 'MainWindow'):
        # (No changes needed in this method)
        if self._closing or not self.cli_input: return
        command = self.cli_input.text().strip();
        if not command: return
        # Add to history only if different from the last command
        if not self.cli_command_history or self.cli_command_history[-1] != command:
            self.cli_command_history.append(command)
            # Keep history deque size limited (optional, if deque has maxlen this is auto)
            # while len(self.cli_command_history) > 100: self.cli_command_history.popleft()

        self.cli_history_index = -1 # Reset history navigation index
        self.cli_input.clear()
        command_lower = command.lower(); is_windows = platform.system() == "Windows"

        # Handle 'cls'/'clear' directly in the UI thread for immediate feedback
        if (is_windows and command_lower == "cls") or command_lower == "clear":
            print(f"Intercepted '{command}' command. Clearing CLI display directly.")
            self.handle_clear_cli() # Clears display and stops any running manual worker
            return

        # Stop any previous manual worker before starting a new one
        self.stop_manual_worker()

        # Echo the command with CWD to the CLI output
        # Use > prompt symbol consistently
        echo_message_bytes = f"User {self.current_directory}> {command}".encode('utf-8')
        self.add_cli_output(echo_message_bytes, "user") # Use 'user' type for coloring

        # Set busy state for manual task
        self.set_busy_state(True, "manual")
        print(f"Starting ManualCommandThread for: {command}")
        self.start_manual_worker(command)


    def keyPressEvent(self: 'MainWindow', event: QKeySequence):
        # (No changes in this method - handles CLI history navigation)
        focused_widget = QApplication.focusWidget()
        if focused_widget == self.cli_input:
            key = event.key(); modifiers = event.modifiers()
            if key == Qt.Key.Key_Up and not modifiers:
                if not self.cli_command_history: event.accept(); return
                if self.cli_history_index == -1: # If currently not navigating history
                    self.cli_history_index = len(self.cli_command_history) - 1 # Start from the last command
                elif self.cli_history_index > 0: # If already navigating, move further back
                    self.cli_history_index -= 1
                else: # At the beginning of history, do nothing more
                    event.accept(); return
                # Update input field if index is valid
                if 0 <= self.cli_history_index < len(self.cli_command_history):
                    self.cli_input.setText(self.cli_command_history[self.cli_history_index])
                    self.cli_input.end(False) # Move cursor to end
                event.accept(); return
            elif key == Qt.Key.Key_Down and not modifiers:
                if self.cli_history_index == -1: event.accept(); return # Not navigating history
                if self.cli_history_index < len(self.cli_command_history) - 1: # If not at the end yet
                    self.cli_history_index += 1
                    self.cli_input.setText(self.cli_command_history[self.cli_history_index])
                    self.cli_input.end(False)
                else: # Reached the end or beyond, clear input and stop navigating
                    self.cli_history_index = -1
                    self.cli_input.clear()
                event.accept(); return
            # If any other key is pressed while navigating history, stop navigating
            elif self.cli_history_index != -1 and key not in ( Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End ):
                self.cli_history_index = -1
        # Pass event to base class if not handled or not for cli_input
        if hasattr(super(type(self), self), 'keyPressEvent'):
             super(type(self), self).keyPressEvent(event)


    @Slot(str)
    def handle_model_selection_changed(self: 'MainWindow', selected_model: str):
        # (No changes in this method)
        if self._closing or not self.model_selector_combo: return
        # Ignore placeholder text or signals being blocked during update
        if not selected_model or selected_model == "未配置模型" or self.model_selector_combo.signalsBlocked(): return

        current_config_selection = config.CURRENTLY_SELECTED_MODEL_ID
        if selected_model != current_config_selection:
            print(f"Model selection changed to: '{selected_model}'")
            config.CURRENTLY_SELECTED_MODEL_ID = selected_model # Update in-memory config
            self.save_state() # Persist the change (saves all state including this)
            # Use Chinese message
            self.add_chat_message("System", f"已切换模型至: {selected_model}", add_to_internal_history=False) # Chinese
        else:
            pass # Selection didn't actually change value

    @Slot()
    def open_settings_dialog(self: 'MainWindow'):
        # <<< MODIFIED to handle multi_step_max_iterations >>>
        if self.settings_dialog_open or self._closing: return
        self.settings_dialog_open = True
        print("Opening settings dialog...")
        dialog = SettingsDialog(self)
        current_theme_before = config.APP_THEME
        current_config_before = config.get_current_config() # Get snapshot before dialog
        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            print("Settings dialog accepted.")
            # <<< MODIFICATION: Unpack new max_iterations value >>>
            (api_key, api_url, model_id_string, auto_startup, new_theme,
             include_cli_context, include_timestamp, enable_multi_step,
             max_iterations) = dialog.get_values() # Added max_iterations
            # <<< END MODIFICATION >>>

            # <<< MODIFICATION: Add max_iterations to change check >>>
            config_changed = (
                api_key != current_config_before['api_key'] or
                api_url != current_config_before['api_url'] or
                model_id_string != current_config_before['model_id_string'] or
                auto_startup != current_config_before['auto_startup'] or
                new_theme != current_config_before['theme'] or
                include_cli_context != current_config_before['include_cli_context'] or
                include_timestamp != current_config_before.get('include_timestamp_in_prompt', config.DEFAULT_INCLUDE_TIMESTAMP) or
                enable_multi_step != current_config_before.get('enable_multi_step', config.DEFAULT_ENABLE_MULTI_STEP) or
                max_iterations != current_config_before.get('multi_step_max_iterations', config.DEFAULT_MULTI_STEP_MAX_ITERATIONS) # Added check
            )
            # <<< END MODIFICATION >>>

            # Check if reset button was likely pressed (heuristic)
            reset_button = dialog.findChild(QPushButton, "reset_button")
            was_reset_likely = reset_button is not None and reset_button.isDown() # Check if it was pressed down *during* exec

            if config_changed:
                print("Configuration change detected, saving...")
                # Determine the selected model after potential changes to the list
                new_model_list = [m.strip() for m in model_id_string.split(',') if m.strip()]
                current_selected_model = config.CURRENTLY_SELECTED_MODEL_ID # Get currently selected model before save
                new_selected_model = current_selected_model
                # If current selection is no longer valid or wasn't set, pick the first one
                if not current_selected_model or current_selected_model not in new_model_list:
                    new_selected_model = new_model_list[0] if new_model_list else ""
                print(f"  Saving - New Model List: {new_model_list}, Effective Selected Model: {new_selected_model}")

                # <<< MODIFICATION: Call save_config with new max_iterations >>>
                config.save_config(
                    api_key, api_url, model_id_string, auto_startup, new_theme,
                    include_cli_context, include_timestamp, enable_multi_step,
                    max_iterations, # Pass the value from dialog
                    selected_model_id=new_selected_model
                )
                # <<< END MODIFICATION >>>

                # <<< MODIFICATION: Update print message >>>
                print(f"Configuration saved. New theme: {new_theme}, AutoStart: {auto_startup}, "
                      f"ModelList: {model_id_string}, SelectedModel: {new_selected_model}, "
                      f"CLI Context: {include_cli_context}, Timestamp: {include_timestamp}, "
                      f"MultiStep: {enable_multi_step}, MaxIterations: {max_iterations}") # Added MaxIterations
                # <<< END MODIFICATION >>>

            else:
                print("Settings dialog accepted, but no changes detected in configuration values.")

            # Update UI elements based on saved/current config
            self.update_model_selector() # Update dropdown based on new list/selection

            theme_changed = new_theme != current_theme_before
            if theme_changed:
                print("Theme changed, applying new theme styles...")
                app = QApplication.instance()
                from .palette import setup_palette
                if app: setup_palette(app, new_theme)
                self.apply_theme_specific_styles() # Apply QSS and update prompt colors etc.

            # Handle state reload if settings were reset or API key removed
            current_config_after_dialog = config.get_current_config()
            # Reload state if reset was pressed OR if API key went from present to absent
            should_reload_state = was_reset_likely or (current_config_before['api_key'] and not current_config_after_dialog['api_key'])
            if should_reload_state:
                print("Reset or API key removal detected. Re-loading state and syncing CWD.")
                self.load_state() # Load history, CWD etc. from potentially cleared settings
                self._sync_process_cwd() # Ensure process CWD matches the loaded/reset state
                self.load_and_apply_state() # Update UI displays (chat history)
                self.update_model_selector() # Reflect potentially cleared models
            elif config_changed or theme_changed:
                # If only config/theme changed (no reset/API key removal), just ensure styles are up-to-date
                print("Configuration or theme changed, reapplying styles and updating model selector if needed.")
                self.apply_theme_specific_styles() # Reapply potentially themed styles
                self.update_model_selector() # Ensure model selection is current

            self.update_prompt() # Ensure prompt reflects current CWD
            print("Settings dialog processing finished.")
        else:
            print("Settings dialog cancelled.")

        self.settings_dialog_open = False
        self.activateWindow() # Bring window to front after dialog closes
        self.raise_()