# gui/main_window_handlers.py
# -*- coding: utf-8 -*-

import re
import os
import platform
import logging # Import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QKeySequence, QKeyEvent # Correct type hint for keyPressEvent

# Import necessary components from the project
from core import config
from .settings_dialog import SettingsDialog # Settings dialog interaction

# Type hinting for MainWindow without causing circular import at runtime
if TYPE_CHECKING:
    from .main_window import MainWindow

# --- Get Logger ---
logger = logging.getLogger(__name__)

class HandlersMixin:
    """Mixin containing user interaction handlers for MainWindow."""

    @Slot()
    def handle_send_stop_button_click(self: 'MainWindow'):
        """Handles clicks on the combined Send/Stop button."""
        logger.debug("Send/Stop button clicked.")
        if self._closing:
            logger.warning("Ignoring Send/Stop click: application is closing.")
            return

        # Check if the API worker is currently running
        api_worker_running = self.api_worker_thread and self.api_worker_thread.isRunning()
        logger.debug(f"API worker running state: {api_worker_running}")

        if api_worker_running:
            # Worker is running, so the button click means "Stop"
            logger.info("Send/Stop button clicked: Stopping API worker...")
            self.stop_api_worker() # stop_api_worker should log details
        else:
            # Worker is not running, so the button click means "Send"
            logger.info("Send/Stop button clicked: Triggering send message...")
            self.handle_send_message() # handle_send_message logs details

    @Slot()
    def handle_send_message(self: 'MainWindow'):
        """Handles sending chat messages to the AI. Called by handle_send_stop_button_click when idle."""
        logger.info("Handling send message request...")
        if self._closing: logger.warning("Ignoring send message: application is closing."); return
        if not self.chat_input: logger.error("Cannot send message: chat_input is None."); return
        if not self.model_selector_combo: logger.error("Cannot send message: model_selector_combo is None."); return

        # Safeguard check if already busy (should ideally be handled by button state)
        if self.api_worker_thread and self.api_worker_thread.isRunning():
             logger.warning("Ignoring send message request: API worker is already running.")
             return

        try:
            user_prompt = self.chat_input.toPlainText().strip()
            if not user_prompt:
                 logger.info("Ignoring send message: user prompt is empty.")
                 if self.chat_input: self.chat_input.setFocus() # Set focus back if empty
                 return

            # Log user prompt (truncated)
            logger.info(f"User prompt received (length {len(user_prompt)}): '{user_prompt[:80]}{'...' if len(user_prompt) > 80 else ''}'")

            self.chat_input.clear(); logger.debug("Chat input cleared.")

            # --- Handle Slash Commands ---
            if user_prompt.startswith("/"):
                logger.info(f"Detected slash command: {user_prompt}")
                self.handle_slash_command(user_prompt) # This method logs details
                return

            # --- Prepare for API Call ---
            selected_model_id = self.model_selector_combo.currentText()
            is_placeholder = selected_model_id == "未配置模型" or not selected_model_id or self.model_selector_combo.count() == 0
            api_configured = bool(config.API_KEY and config.API_URL and config.MODEL_ID_STRING)
            logger.debug(f"Selected model: '{selected_model_id}', Is placeholder: {is_placeholder}, API Configured: {api_configured}")

            # Check configuration validity
            if not api_configured or is_placeholder:
                 if is_placeholder:
                     err_msg = "请先在工具栏选择一个有效的 AI 模型。如果列表为空，请使用“设置”配置模型 ID。"
                     logger.warning(f"Cannot send message: Model not selected or invalid ('{selected_model_id}').")
                 else:
                     err_msg = "API 未配置。请使用“设置”按钮或 /settings 命令进行配置。"
                     logger.warning("Cannot send message: API Key/URL/Model list not configured.")
                 self.add_chat_message("Error", err_msg, add_to_internal_history=False)
                 if self.chat_input: self.chat_input.setFocus()
                 return

            # Add user message to display and internal history (add_chat_message logs details)
            self.add_chat_message("User", user_prompt, add_to_internal_history=True)

            # --- Prepare History and Context for Worker ---
            # Create a copy for the worker thread
            history_for_worker = list(self.conversation_history)
            logger.debug(f"Prepared history for worker (length: {len(history_for_worker)}).")

            # Add CLI context if enabled
            include_context = getattr(config, 'INCLUDE_CLI_CONTEXT', False) # Safely get config
            if include_context and self.cli_output_display:
                full_cli_text = self.cli_output_display.toPlainText().strip()
                if full_cli_text:
                    context_role = "system"
                    max_context_len = 5000 # Configurable?
                    truncated_cli_text = full_cli_text[-max_context_len:]
                    context_prefix = f"--- 当前 CLI 输出 (最后 {len(truncated_cli_text)} 字符) ---\n" if len(full_cli_text) > max_context_len else "--- 当前 CLI 输出 (完整) ---\n"
                    context_msg_content = (f"{context_prefix}{truncated_cli_text}\n--- CLI 输出结束 ---")

                    # Insert context before the *last* user message in the copied history
                    last_user_index = -1
                    for i in range(len(history_for_worker) - 1, -1, -1):
                        if history_for_worker[i][0].lower() == 'user': last_user_index = i; break

                    if last_user_index != -1:
                        history_for_worker.insert(last_user_index, (context_role, context_msg_content))
                        logger.info(f"Added CLI context ({len(truncated_cli_text)} chars) before last user message.")
                    else:
                        history_for_worker.insert(0, (context_role, context_msg_content))
                        logger.info(f"Added CLI context ({len(truncated_cli_text)} chars) at the beginning (no prior user message).")
                else:
                    logger.debug("CLI context inclusion enabled, but CLI output is empty.")
            elif include_context:
                 logger.warning("CLI context inclusion enabled, but cli_output_display widget not found.")

            # --- Start Worker ---
            logger.info(f"Starting ApiWorkerThread for model: {selected_model_id}...")
            # Set busy state (method logs details)
            self.set_busy_state(True, "api")
            # Start worker (method logs details)
            self.start_api_worker(selected_model_id, history_for_worker, user_prompt)

        except Exception as e:
            logger.error("Error occurred during handle_send_message.", exc_info=True)
            self.add_chat_message("Error", f"发送消息时出错: {e}", add_to_internal_history=False)
            # Attempt to reset busy state on error
            self.set_busy_state(False, "api")

    def handle_slash_command(self: 'MainWindow', command: str):
        """Handles commands starting with '/'."""
        logger.info(f"Handling slash command: {command}")
        if self._closing: logger.warning("Ignoring slash command: application is closing."); return

        command_lower = command.lower().strip()
        parts = command.split(maxsplit=1)
        cmd_base = parts[0].lower()
        arg = parts[1].strip() if len(parts) == 2 else None
        logger.debug(f"Parsed command base: '{cmd_base}', Argument: '{arg}'")

        try:
            if cmd_base == "/exit":
                logger.info("Executing /exit command.")
                self.close() # Trigger the closeEvent handler
            elif cmd_base == "/clear":
                logger.info("Executing /clear command.")
                self.handle_clear_chat() # Method logs details
            elif cmd_base == "/clear_cli":
                logger.info("Executing /clear_cli command.")
                self.handle_clear_cli() # Method logs details
            elif cmd_base == "/clear_all":
                logger.info("Executing /clear_all command.")
                if self.chat_history_display: self.chat_history_display.clear()
                if self.cli_output_display: self.cli_output_display.clear()
                self.conversation_history.clear()
                logger.debug("Stopping workers before clearing state...")
                self.stop_api_worker()
                self.stop_manual_worker()
                logger.info("Chat and CLI displays/history cleared by /clear_all.")
                self.save_state() # Save the cleared state
            elif cmd_base == "/settings":
                logger.info("Executing /settings command.")
                self.open_settings_dialog() # Method logs details
            elif cmd_base == "/save":
                logger.info("Executing /save command.")
                self.save_state() # StateMixin method logs details
                self.add_chat_message("System", "当前状态 (历史, CWD, 选择的模型) 已保存。", add_to_internal_history=False)
            elif cmd_base == "/help":
                logger.info("Executing /help command.")
                self.show_help() # Method logs details
            elif cmd_base == "/cwd":
                logger.info("Executing /cwd command.")
                self.add_chat_message("System", f"当前工作目录: {self.current_directory}", add_to_internal_history=False)
            elif cmd_base == "/copy_cli":
                logger.info("Executing /copy_cli command.")
                if self.cli_output_display:
                    full_cli_text = self.cli_output_display.toPlainText()
                    if full_cli_text:
                        try:
                            clipboard = QApplication.clipboard()
                            if clipboard:
                                clipboard.setText(full_cli_text)
                                logger.info(f"Copied {len(full_cli_text)} chars from CLI output to clipboard.")
                                self.add_chat_message("System", "左侧 CLI 输出已复制到剪贴板。", add_to_internal_history=False)
                            else:
                                logger.error("Cannot copy CLI output: QApplication clipboard unavailable.")
                                self.add_chat_message("Error", "无法访问剪贴板。", add_to_internal_history=False)
                        except Exception as e:
                            logger.error("Error copying CLI output to clipboard.", exc_info=True)
                            self.add_chat_message("Error", f"复制到剪贴板时出错: {e}", add_to_internal_history=False)
                    else:
                        logger.info("CLI output is empty, nothing to copy.")
                        self.add_chat_message("System", "左侧 CLI 输出为空。", add_to_internal_history=False)
                else:
                    logger.error("Cannot copy CLI output: cli_output_display widget not found.")
                    self.add_chat_message("Error", "无法访问 CLI 输出区域。", add_to_internal_history=False)
            elif cmd_base == "/show_cli":
                logger.info("Executing /show_cli command.")
                if self.cli_output_display:
                    lines_to_show = 10 # Default
                    if arg:
                        try:
                             lines_to_show = max(1, int(arg))
                             logger.debug(f"Argument provided, will show last {lines_to_show} lines.")
                        except ValueError:
                             logger.warning(f"Invalid line count argument for /show_cli: '{arg}'")
                             self.add_chat_message("Error", f"无效的行数: '{arg}'。请输入一个数字。", add_to_internal_history=False); return
                    full_cli_text = self.cli_output_display.toPlainText()
                    lines = full_cli_text.strip().splitlines()
                    last_n_lines = lines[-lines_to_show:]
                    if last_n_lines:
                        header = f"--- 左侧 CLI 输出 (最后 {len(last_n_lines)} 行) ---"
                        cli_content_message = header + "\n" + "\n".join(last_n_lines)
                        logger.info(f"Showing last {len(last_n_lines)} lines of CLI output in chat.")
                        self.add_chat_message("System", cli_content_message, add_to_internal_history=False)
                    else:
                        logger.info("CLI output is empty, cannot show lines.")
                        self.add_chat_message("System", "左侧 CLI 输出为空。", add_to_internal_history=False)
                else:
                    logger.error("Cannot show CLI output: cli_output_display widget not found.")
                    self.add_chat_message("Error", "无法访问 CLI 输出区域。", add_to_internal_history=False)
            else:
                logger.warning(f"Unknown slash command received: {command}")
                self.add_chat_message("Error", f"未知命令: {command}。输入 /help 获取帮助。", add_to_internal_history=False)
        except Exception as e:
            logger.error(f"Error occurred while handling slash command '{command}'.", exc_info=True)
            self.add_chat_message("Error", f"处理命令 '{command}' 时出错: {e}", add_to_internal_history=False)


    @Slot()
    def handle_clear_chat(self: 'MainWindow'):
        """Handles the '/clear' command or button click."""
        logger.info("Handling clear chat request...")
        if self._closing: logger.warning("Ignoring clear chat: application is closing."); return

        logger.info("Stopping API worker before clearing chat...")
        self.stop_api_worker() # Method logs details

        if self.chat_history_display:
             self.chat_history_display.clear()
             logger.debug("Chat history display cleared.")
        else:
             logger.warning("Cannot clear chat display: chat_history_display widget not found.")

        if self.conversation_history:
            history_len_before = len(self.conversation_history)
            self.conversation_history.clear()
            logger.info(f"Internal conversation history deque cleared (was {history_len_before} items).")
        else:
            logger.debug("Internal conversation history already empty or not initialized.")

        self.save_state() # Persist the cleared history state (method logs details)
        logger.info("Clear chat operation finished.")


    @Slot()
    def handle_clear_cli(self: 'MainWindow'):
        """Handles the Clear CLI button click or /clear_cli command."""
        logger.info("Handling clear CLI request...")
        if self._closing: logger.warning("Ignoring clear CLI: application is closing."); return
        if not self.cli_output_display: logger.error("Cannot clear CLI: cli_output_display widget not found."); return

        logger.info("Stopping manual command worker before clearing CLI...")
        self.stop_manual_worker() # Method logs details

        self.cli_output_display.clear()
        logger.info("CLI output display cleared.")

        if self.cli_input:
            logger.debug("Setting focus back to CLI input after clearing.")
            self.cli_input.setFocus()

    @Slot()
    def handle_manual_command(self: 'MainWindow'):
        """Handles executing commands entered manually in the CLI input."""
        logger.debug("Handling manual command input (Enter pressed)...")
        if self._closing: logger.warning("Ignoring manual command: application is closing."); return
        if not self.cli_input: logger.error("Cannot handle manual command: cli_input widget not found."); return

        try:
            command = self.cli_input.text().strip()
            if not command:
                logger.debug("Manual command input is empty, ignoring.")
                return # Ignore empty input

            logger.info(f"Manual command entered: '{command}'")

            # Add to history (only if different from last command)
            if not self.cli_command_history or self.cli_command_history[-1] != command:
                self.cli_command_history.append(command)
                logger.debug(f"Added command to CLI history (new length: {len(self.cli_command_history)}).")
                # Optional: Limit deque size explicitly if needed, though maxlen handles it
                # while len(self.cli_command_history) > 100: self.cli_command_history.popleft()
            else:
                logger.debug("Command is same as last in history, not adding again.")

            self.cli_history_index = -1 # Reset history navigation index
            self.cli_input.clear() # Clear input field
            logger.debug("CLI input cleared and history index reset.")

            command_lower = command.lower()
            is_windows = platform.system() == "Windows"

            # --- Handle 'cls'/'clear' directly in UI thread ---
            if (is_windows and command_lower == "cls") or (not is_windows and command_lower == "clear"):
                logger.info(f"Intercepted '{command}' command. Clearing CLI display directly.")
                self.handle_clear_cli() # This method logs details
                return

            # --- Stop previous worker and Execute Command ---
            logger.info("Stopping previous manual command worker (if any)...")
            self.stop_manual_worker() # Method logs details

            # Echo the command with CWD to the CLI output (method logs details)
            echo_message = f"User {self.current_directory}> {command}"
            self.add_cli_output(echo_message.encode('utf-8'), "user")

            logger.info(f"Starting ManualCommandThread for: {command}")
            self.set_busy_state(True, "manual") # Method logs details
            self.start_manual_worker(command) # Method logs details

        except Exception as e:
            logger.error("Error occurred during handle_manual_command.", exc_info=True)
            # Optionally inform the user via UI
            self.add_cli_output(f"Error handling command: {e}".encode('utf-8'), "error")
            # Reset busy state if an error occurred before starting worker
            if not (self.manual_cmd_thread and self.manual_cmd_thread.isRunning()):
                 self.set_busy_state(False, "manual")


    # Use QKeyEvent type hint for better accuracy
    def keyPressEvent(self: 'MainWindow', event: QKeyEvent):
        """Handles key presses, specifically Up/Down arrows in CLI input for history."""
        # Check if the focus is specifically on the CLI input.
        focused_widget = QApplication.focusWidget()
        if focused_widget == self.cli_input:
            key = event.key()
            modifiers = event.modifiers()

            # Handle Up Arrow for history navigation
            if key == Qt.Key.Key_Up and not modifiers:
                logger.debug("Up arrow key pressed in CLI input.")
                if not self.cli_command_history: logger.debug("No CLI history available."); event.accept(); return
                current_index = self.cli_history_index
                new_index = -1 # Default if starting navigation or at beginning

                if current_index == -1: # Starting navigation from the end
                    new_index = len(self.cli_command_history) - 1
                    logger.debug(f"Starting CLI history navigation at index {new_index}.")
                elif current_index > 0: # Moving further back
                    new_index = current_index - 1
                    logger.debug(f"Moving CLI history navigation back to index {new_index}.")
                else: # Already at the beginning (index 0)
                    logger.debug("Already at the beginning of CLI history.")
                    event.accept(); return

                # Update input field if index changed and is valid
                if new_index != current_index and 0 <= new_index < len(self.cli_command_history):
                    self.cli_history_index = new_index
                    history_command = self.cli_command_history[self.cli_history_index]
                    logger.debug(f"Setting CLI input text to history item: '{history_command}'")
                    self.cli_input.setText(history_command)
                    self.cli_input.end(False) # Move cursor to end
                event.accept(); return

            # Handle Down Arrow for history navigation
            elif key == Qt.Key.Key_Down and not modifiers:
                logger.debug("Down arrow key pressed in CLI input.")
                if self.cli_history_index == -1: logger.debug("Not currently navigating CLI history."); event.accept(); return # Not navigating

                current_index = self.cli_history_index
                new_index = -1 # Default if moving past end

                if current_index < len(self.cli_command_history) - 1: # If not at the most recent item yet
                    new_index = current_index + 1
                    logger.debug(f"Moving CLI history navigation forward to index {new_index}.")
                    history_command = self.cli_command_history[new_index]
                    logger.debug(f"Setting CLI input text to history item: '{history_command}'")
                    self.cli_input.setText(history_command)
                    self.cli_input.end(False)
                    self.cli_history_index = new_index
                else: # Reached the end or beyond, clear input and stop navigating
                    logger.debug("Reached end of CLI history navigation. Clearing input.")
                    self.cli_input.clear()
                    self.cli_history_index = -1 # Reset index
                event.accept(); return

            # If any other key is pressed while navigating history, stop navigating
            elif self.cli_history_index != -1:
                # Check for common navigation/modifier keys to allow normal editing while technically "navigating"
                is_nav_or_modifier = key in (
                    Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
                    Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
                    Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End
                    # Add Backspace, Delete, Enter? Decide if these should reset navigation.
                    # Qt.Key.Key_Backspace, Qt.Key.Key_Delete, Qt.Key.Key_Return, Qt.Key.Key_Enter
                )
                if not is_nav_or_modifier:
                    logger.debug(f"Non-navigation key ({key}) pressed while navigating history. Resetting history index.")
                    self.cli_history_index = -1 # Reset index on other input

        # --- Important: Pass event to base class ---
        try:
            # Call the superclass implementation for default processing
            super(HandlersMixin, self).keyPressEvent(event) # Call the mixin's super specifically
            # logger.debug(f"keyPressEvent ({event.key()}) passed to superclass.")
        except Exception as e:
            logger.error(f"Error calling super().keyPressEvent: {e}", exc_info=False)
            event.ignore() # Ensure event is not accepted if super call fails


    @Slot(str)
    def handle_model_selection_changed(self: 'MainWindow', selected_model: str):
        """Handles changes in the model selection QComboBox."""
        logger.debug(f"Model selection changed signal received: '{selected_model}'")
        if self._closing: logger.warning("Ignoring model selection change: application is closing."); return
        if not self.model_selector_combo: logger.error("Cannot handle model selection: model_selector_combo is None."); return

        # Ignore placeholder text or signals being blocked during update
        if not selected_model or selected_model == "未配置模型" or self.model_selector_combo.signalsBlocked():
             logger.debug(f"Model selection ignored: Placeholder or signals blocked.")
             return

        current_config_selection = config.CURRENTLY_SELECTED_MODEL_ID
        if selected_model != current_config_selection:
            logger.info(f"Model selection changed from '{current_config_selection}' to '{selected_model}'. Updating config.")
            config.CURRENTLY_SELECTED_MODEL_ID = selected_model
            self.save_state() # Persist the change (method logs details)
            self.add_chat_message("System", f"已切换模型至: {selected_model}", add_to_internal_history=False)
        else:
            logger.debug(f"Model selection unchanged ('{selected_model}'). No action needed.")

    @Slot()
    def open_settings_dialog(self: 'MainWindow'):
        """Opens the settings dialog and handles applying changes."""
        logger.info("Opening settings dialog...")
        if self.settings_dialog_open: logger.warning("Settings dialog already open."); return
        if self._closing: logger.warning("Ignoring open settings dialog: application is closing."); return

        self.settings_dialog_open = True
        try:
            # Pass self as parent so dialog is centered/modal
            dialog = SettingsDialog(self) # SettingsDialog init might have logging
            # Get state *before* showing the dialog
            current_theme_before = config.APP_THEME
            current_config_before = config.get_current_config() # Method logs details
            logger.debug(f"Config before opening dialog: {current_config_before}")

            result = dialog.exec() # Show the dialog modally
            logger.info(f"Settings dialog finished with result code: {result} (Accepted={QDialog.DialogCode.Accepted})")

            if result == QDialog.DialogCode.Accepted:
                logger.info("Settings dialog accepted. Processing changes...")
                # Get values from dialog
                (api_key, api_url, model_id_string, auto_startup, new_theme,
                 include_cli_context, include_timestamp, enable_multi_step,
                 max_iterations, auto_include_ui_info) = dialog.get_values() # Method should be simple getter

                # Log retrieved values (mask sensitive)
                logger.debug("Values retrieved from dialog:")
                logger.debug(f"  API Key Provided: {bool(api_key)}")
                logger.debug(f"  API URL: {api_url}")
                logger.debug(f"  Model IDs: {model_id_string}")
                logger.debug(f"  Auto Startup: {auto_startup}")
                logger.debug(f"  Theme: {new_theme}")
                logger.debug(f"  Include CLI Context: {include_cli_context}")
                logger.debug(f"  Include Timestamp: {include_timestamp}")
                logger.debug(f"  Enable Multi-Step: {enable_multi_step}")
                logger.debug(f"  Max Iterations: {max_iterations}")
                logger.debug(f"  Auto Include UI Info: {auto_include_ui_info}")

                # Check if config actually changed
                config_changed = (
                    api_key != current_config_before.get('api_key', '') or
                    api_url != current_config_before.get('api_url', '') or
                    model_id_string != current_config_before.get('model_id_string', '') or
                    auto_startup != current_config_before.get('auto_startup', False) or
                    new_theme != current_config_before.get('theme', 'system') or
                    include_cli_context != current_config_before.get('include_cli_context', config.DEFAULT_INCLUDE_CLI_CONTEXT) or
                    include_timestamp != current_config_before.get('include_timestamp_in_prompt', config.DEFAULT_INCLUDE_TIMESTAMP) or
                    enable_multi_step != current_config_before.get('enable_multi_step', config.DEFAULT_ENABLE_MULTI_STEP) or
                    max_iterations != current_config_before.get('multi_step_max_iterations', config.DEFAULT_MULTI_STEP_MAX_ITERATIONS) or
                    auto_include_ui_info != current_config_before.get('auto_include_ui_info', config.DEFAULT_AUTO_INCLUDE_UI_INFO)
                )
                logger.info(f"Configuration changed: {config_changed}")

                # Check if reset button was likely pressed
                was_reset_likely = not api_key and current_config_before.get('api_key', '')
                if was_reset_likely: logger.info("API key cleared, assuming settings were reset.")

                if config_changed:
                    logger.info("Configuration change detected, saving new settings...")
                    # Determine the effective selected model after potential changes
                    new_model_list = [m.strip() for m in model_id_string.split(',') if m.strip()]
                    current_selected_model_before_save = config.CURRENTLY_SELECTED_MODEL_ID # Use current global state
                    new_selected_model = current_selected_model_before_save
                    # If current selection is no longer valid or wasn't set, pick the first one
                    if not current_selected_model_before_save or current_selected_model_before_save not in new_model_list:
                        new_selected_model = new_model_list[0] if new_model_list else ""
                        logger.info(f"Selected model '{current_selected_model_before_save}' no longer valid or unset. Defaulting to '{new_selected_model}'.")
                    logger.debug(f"Effective selected model for save: {new_selected_model}")

                    # Save configuration (method logs details)
                    config.save_config(
                        api_key=api_key, api_url=api_url, model_id_string=model_id_string,
                        auto_startup=auto_startup, theme=new_theme, include_cli_context=include_cli_context,
                        include_timestamp=include_timestamp, enable_multi_step=enable_multi_step,
                        multi_step_max_iterations=max_iterations, auto_include_ui_info=auto_include_ui_info,
                        selected_model_id=new_selected_model
                    )
                else:
                    logger.info("Settings dialog accepted, but no configuration value changes detected.")

                # --- UI Updates after save/no change ---
                theme_changed = new_theme != current_theme_before
                logger.info(f"Theme changed: {theme_changed}")

                # Update model selector regardless of change
                logger.debug("Updating model selector after settings change.")
                self.update_model_selector() # Method logs details

                if theme_changed:
                    logger.info("Theme changed, applying new theme styles...")
                    app = QApplication.instance()
                    if app:
                        from .palette import setup_palette # Local import okay here
                        setup_palette(app, new_theme) # Method logs details
                        self.apply_theme_specific_styles() # Method logs details
                    else:
                         logger.error("Cannot apply theme: QApplication instance not found.")

                # Handle state reload if settings were reset
                if was_reset_likely:
                    logger.info("Settings reset detected. Reloading state and syncing CWD.")
                    self.load_state() # Method logs details
                    self._sync_process_cwd() # Method logs details
                    self.load_and_apply_state() # Method logs details
                    self.update_model_selector() # Ensure selector reflects cleared models
                elif config_changed or theme_changed:
                    # If only config/theme changed, ensure styles are up-to-date
                    logger.info("Configuration or theme changed, reapplying styles for consistency.")
                    self.apply_theme_specific_styles() # Method logs details

                logger.debug("Updating CLI prompt after settings change.")
                self.update_prompt() # Method logs details
                logger.info("Settings dialog processing finished.")

            else: # Dialog cancelled
                logger.info("Settings dialog cancelled.")

        except Exception as e:
            logger.error("Error occurred during settings dialog handling.", exc_info=True)
            # Show error message to user?
            QMessageBox.critical(self, "Settings Error", f"An error occurred while handling settings:\n{e}")
        finally:
            # Reset flag and ensure window is active
            self.settings_dialog_open = False
            logger.debug("Settings dialog closed. Activating main window.")
            self.activateWindow()
            self.raise_()