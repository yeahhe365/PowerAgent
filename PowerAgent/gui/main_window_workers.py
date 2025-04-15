# gui/main_window_workers.py
# -*- coding: utf-8 -*-

import os
import time
import traceback
import logging # Import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Slot, QThread
from PySide6.QtGui import QIcon


# Import necessary components from the project
from core import config
from core.workers import ApiWorkerThread, ManualCommandThread

# Type hinting for MainWindow without causing circular import at runtime
if TYPE_CHECKING:
    from .main_window import MainWindow

# --- Get Logger ---
logger = logging.getLogger(__name__)

class WorkersMixin:
    """Mixin containing worker interaction logic for MainWindow."""

    def is_busy(self: 'MainWindow') -> bool:
        """Checks if either the API or Manual command worker is active."""
        api_running = self.api_worker_thread and self.api_worker_thread.isRunning()
        manual_running = self.manual_cmd_thread and self.manual_cmd_thread.isRunning()
        # logger.debug(f"is_busy check: API running={api_running}, Manual running={manual_running}") # Too verbose
        return api_running or manual_running

    def start_api_worker(self: 'MainWindow', model_id: str, history: list, prompt: str):
        """Creates, connects, and starts the API worker thread."""
        logger.info(f"Attempting to start ApiWorkerThread for model: {model_id}")
        if self.api_worker_thread and self.api_worker_thread.isRunning():
            logger.warning("Tried to start API worker while one was already running. Ignoring.")
            return

        try:
            # Log parameters being passed (mask sensitive)
            logger.debug("ApiWorkerThread Parameters:")
            logger.debug("  Model ID: %s", model_id)
            logger.debug("  History Length: %d", len(history))
            logger.debug("  Prompt Length: %d", len(prompt))
            # logger.debug("  Prompt Preview: %s", prompt[:80] + "...") # Be careful with prompt content
            logger.debug("  CWD: %s", self.current_directory)

            self.api_worker_thread = ApiWorkerThread(
                api_key=config.API_KEY, # API Key is handled internally by worker
                api_url=config.API_URL,
                model_id=model_id,
                history=history,
                prompt=prompt,
                cwd=self.current_directory
            )
            logger.debug("ApiWorkerThread instance created.")

            # --- Connect signals ---
            logger.debug("Connecting signals for ApiWorkerThread...")
            self.api_worker_thread.api_result.connect(self.handle_api_result)
            self.api_worker_thread.cli_output_signal.connect(lambda b: self.add_cli_output(b, "output"))
            self.api_worker_thread.cli_error_signal.connect(lambda b: self.add_cli_output(b, "error"))
            self.api_worker_thread.directory_changed_signal.connect(self.handle_directory_change)
            self.api_worker_thread.task_finished.connect(lambda: self.handle_task_finished("api"))
            self.api_worker_thread.ai_command_echo_signal.connect(
                lambda cmd: self.add_chat_message(role="AI Command", message=cmd, add_to_internal_history=False)
            )
            logger.debug("ApiWorkerThread signals connected.")

            self.api_worker_thread.start()
            logger.info("ApiWorkerThread started successfully.")
        except Exception as e:
             logger.critical("Failed to create or start ApiWorkerThread!", exc_info=True)
             # Attempt to reset busy state if failed to start
             self.set_busy_state(False, "api")
             # Inform user?
             self.add_chat_message("Error", f"无法启动 AI 任务: {e}", add_to_internal_history=False)


    def start_manual_worker(self: 'MainWindow', command: str):
        """Creates, connects, and starts the Manual command worker thread."""
        logger.info(f"Attempting to start ManualCommandThread for command: '{command}'")
        if self.manual_cmd_thread and self.manual_cmd_thread.isRunning():
            logger.warning("Tried to start manual worker while one was already running. Ignoring.")
            return

        try:
            logger.debug("ManualCommandThread Parameters:")
            logger.debug("  Command: %s", command)
            logger.debug("  CWD: %s", self.current_directory)

            self.manual_cmd_thread = ManualCommandThread(command, self.current_directory)
            logger.debug("ManualCommandThread instance created.")

            # --- Connect signals ---
            logger.debug("Connecting signals for ManualCommandThread...")
            self.manual_cmd_thread.cli_output_signal.connect(lambda b: self.add_cli_output(b, "output"))
            self.manual_cmd_thread.cli_error_signal.connect(lambda b: self.add_cli_output(b, "error"))
            self.manual_cmd_thread.directory_changed_signal.connect(self.handle_directory_change)
            self.manual_cmd_thread.command_finished.connect(lambda: self.handle_task_finished("manual"))
            logger.debug("ManualCommandThread signals connected.")

            self.manual_cmd_thread.start()
            logger.info("ManualCommandThread started successfully.")
        except Exception as e:
             logger.critical("Failed to create or start ManualCommandThread!", exc_info=True)
             # Attempt to reset busy state if failed to start
             self.set_busy_state(False, "manual")
              # Inform user?
             self.add_cli_output(f"无法启动命令任务: {e}".encode('utf-8'), "error")


    def set_busy_state(self: 'MainWindow', busy: bool, task_type: str):
        """Updates UI element states and the status indicator based on task activity."""
        logger.info(f"Setting busy state: Busy={busy}, TaskType='{task_type}'")
        if self._closing: logger.warning("Skipping set_busy_state during close sequence."); return

        try:
            # Determine the *next* overall busy state
            # Check current running state *before* applying the new state
            is_api_currently_busy = self.api_worker_thread and self.api_worker_thread.isRunning()
            is_manual_currently_busy = self.manual_cmd_thread and self.manual_cmd_thread.isRunning()

            # Calculate if API *will be* busy after this change
            next_api_busy = (is_api_currently_busy and not (task_type == "api" and not busy)) or \
                            (task_type == "api" and busy)
            # Calculate if Manual *will be* busy after this change
            next_manual_busy = (is_manual_currently_busy and not (task_type == "manual" and not busy)) or \
                               (task_type == "manual" and busy)

            logger.debug(f"Busy state calculation: CurrentAPI={is_api_currently_busy}, CurrentManual={is_manual_currently_busy} -> NextAPI={next_api_busy}, NextManual={next_manual_busy}")

            # --- Update Enabled State of UI Elements ---
            logger.debug("Updating UI element enabled states...")
            if self.chat_input: self.chat_input.setEnabled(not next_api_busy)
            if self.clear_chat_button: self.clear_chat_button.setEnabled(not next_api_busy)
            can_enable_model_selector = not next_api_busy and \
                                        self.model_selector_combo and \
                                        self.model_selector_combo.count() > 0 and \
                                        self.model_selector_combo.itemText(0) != "未配置模型"
            if self.model_selector_combo: self.model_selector_combo.setEnabled(can_enable_model_selector); logger.debug(f"ModelSelector enabled: {can_enable_model_selector}")

            if self.cli_input: self.cli_input.setEnabled(not next_manual_busy); logger.debug(f"CliInput enabled: {not next_manual_busy}")
            if self.clear_cli_button: self.clear_cli_button.setEnabled(not next_manual_busy)

            # --- Update Send/Stop Button Appearance and Tooltip ---
            if self.send_button:
                logger.debug("Updating Send/Stop button...")
                if next_api_busy:
                    stop_icon = self._get_icon("process-stop", "stop.png", "⏹️")
                    self.send_button.setText("停止")
                    self.send_button.setIcon(stop_icon if not stop_icon.isNull() else QIcon())
                    self.send_button.setToolTip("停止当前正在运行的 AI 任务")
                    self.send_button.setEnabled(True) # Stop button is always enabled when busy
                    logger.debug("Set button to STOP state.")
                else:
                    send_icon = self._get_icon("mail-send", "send.png", "▶️")
                    self.send_button.setText("发送")
                    self.send_button.setIcon(send_icon if not send_icon.isNull() else QIcon())
                    self.send_button.setToolTip("向 AI 发送消息 (Shift+Enter 换行)")
                    api_configured = bool(config.API_KEY and config.API_URL and config.MODEL_ID_STRING and self.model_selector_combo and self.model_selector_combo.currentText() != "未配置模型")
                    self.send_button.setEnabled(api_configured)
                    logger.debug(f"Set button to SEND state (Enabled: {api_configured}).")
            else:
                logger.warning("Send/Stop button not found, cannot update state.")


            # --- Update Status Indicator ---
            indicator_busy_state = next_api_busy or next_manual_busy
            logger.debug(f"Updating status indicator to busy={indicator_busy_state}")
            self.update_status_indicator(indicator_busy_state) # Method logs details

            # --- Set Focus ---
            # Set focus back only when transitioning from busy to not busy *overall*
            is_currently_busy_overall = is_api_currently_busy or is_manual_currently_busy
            is_next_busy_overall = next_api_busy or next_manual_busy
            if is_currently_busy_overall and not is_next_busy_overall:
                 logger.info(f"Task '{task_type}' finished, transitioning to idle state. Setting focus...")
                 QApplication.processEvents() # Allow UI to update before setting focus
                 focused = False
                 # Prioritize focus based on which task just finished
                 if task_type == "api" and self.chat_input and self.chat_input.isEnabled():
                     self.chat_input.setFocus(); focused = True; logger.debug("Set focus to chat input.")
                 elif task_type == "manual" and self.cli_input and self.cli_input.isEnabled():
                     self.cli_input.setFocus(); focused = True; logger.debug("Set focus to CLI input.")
                 # Fallback focus logic if primary target isn't available/enabled
                 elif not focused and self.chat_input and self.chat_input.isEnabled():
                      self.chat_input.setFocus(); logger.debug("Set focus to chat input (fallback).")
                 elif not focused and self.cli_input and self.cli_input.isEnabled():
                      self.cli_input.setFocus(); logger.debug("Set focus to CLI input (fallback).")
                 else:
                      logger.warning("Could not set focus after task finished - no suitable input widget enabled.")
            elif not busy: # Task finished, but another might still be running
                 logger.debug(f"Task '{task_type}' finished, but another task is still running. Not setting focus.")
            # Else: Transitioning to busy state, focus handled elsewhere (e.g., user input)

        except Exception as e:
            logger.error("Error occurred during set_busy_state.", exc_info=True)


    @Slot(str, float)
    def handle_api_result(self: 'MainWindow', reply: str, elapsed_time: float):
        """Handles the text result from the API worker thread."""
        logger.info(f"Handling API result (Elapsed: {elapsed_time:.2f}s). Reply preview: '{reply[:100]}...'")
        if self._closing: logger.warning("Ignoring API result: application is closing."); return

        try:
            # Add the result using the "Model" role (method logs details)
            self.add_chat_message("Model", reply, add_to_internal_history=True, elapsed_time=elapsed_time)
            logger.debug("API result added to chat display.")
        except Exception as e:
            logger.error("Error handling API result.", exc_info=True)


    @Slot(str, bool)
    def handle_directory_change(self: 'MainWindow', new_directory: str, is_manual_command: bool):
        """Handles directory change signaled by workers (after 'cd' command)."""
        source = "Manual Command Worker" if is_manual_command else "API Worker"
        logger.info(f"Handling directory change signal from {source}: New directory='{new_directory}'")
        if self._closing: logger.warning("Ignoring directory change: application is closing."); return

        try:
            if os.path.isdir(new_directory):
                 old_directory = self.current_directory
                 normalized_new_dir = os.path.normpath(new_directory)
                 if old_directory != normalized_new_dir:
                     logger.info(f"Updating internal CWD state from '{old_directory}' to '{normalized_new_dir}'.")
                     self.current_directory = normalized_new_dir
                     # Attempt to change the actual process CWD (log inside method)
                     self._sync_process_cwd()
                     # Update UI prompt (log inside method)
                     self.update_prompt()
                     # Save the new state (log inside method)
                     self.save_state()
                 else:
                     logger.debug(f"Directory change signal received, but new directory ('{normalized_new_dir}') matches current internal state. No update needed.")
            else:
                logger.error(f"Directory change failed: Path '{new_directory}' received from worker is not a valid directory.")
                # Inform user via CLI error
                self._emit_cli_error(f"Worker reported invalid directory change: '{new_directory}'") # Use helper

        except Exception as e:
            logger.error("Error handling directory change signal.", exc_info=True)
            self._emit_cli_error(f"Error processing directory change: {e}")


    @Slot(str)
    def handle_task_finished(self: 'MainWindow', task_type: str):
        """Handles finished signal from worker threads (API or Manual)."""
        logger.info(f"{task_type.capitalize()} worker thread finished signal received.")
        if self._closing: logger.warning(f"Ignoring task finished signal for '{task_type}': application is closing."); return

        try:
            # Set UI state to not busy for the completed task type
            self.set_busy_state(False, task_type) # Method logs details

            # Clear the reference to the finished thread
            if task_type == "api":
                if self.api_worker_thread:
                    logger.debug("Clearing reference to finished ApiWorkerThread.")
                    self.api_worker_thread = None
                else:
                    logger.warning("Received API task finished signal, but no active thread reference found.")
            elif task_type == "manual":
                if self.manual_cmd_thread:
                    logger.debug("Clearing reference to finished ManualCommandThread.")
                    self.manual_cmd_thread = None
                else:
                    logger.warning("Received Manual task finished signal, but no active thread reference found.")
            else:
                 logger.warning(f"Received task finished signal for unknown task type: '{task_type}'")

        except Exception as e:
             logger.error(f"Error handling task finished signal for '{task_type}'.", exc_info=True)

    def stop_api_worker(self: 'MainWindow'):
        """Signals the API worker thread to stop."""
        logger.info("Attempting to stop API worker thread...")
        if self.api_worker_thread and self.api_worker_thread.isRunning():
            logger.debug("API worker is running, calling stop().")
            try:
                self.api_worker_thread.stop() # Call the thread's stop method (thread logs internally)
                logger.info("API worker stop signal sent.")
                return True # Indicate that stop was called
            except Exception as e:
                 logger.error("Error trying to call stop() on API worker.", exc_info=True)
                 return False
        elif self.api_worker_thread:
             logger.info("API worker thread exists but is not running.")
             return False
        else:
            logger.info("No active API worker thread found to stop.")
            return False

    def stop_manual_worker(self: 'MainWindow'):
        """Signals the manual command worker thread to stop."""
        logger.info("Attempting to stop Manual Command worker thread...")
        if self.manual_cmd_thread and self.manual_cmd_thread.isRunning():
            logger.debug("Manual worker is running, calling stop().")
            try:
                self.manual_cmd_thread.stop() # Thread logs internally
                logger.info("Manual worker stop signal sent.")
                return True
            except Exception as e:
                logger.error("Error trying to call stop() on manual worker.", exc_info=True)
                return False
        elif self.manual_cmd_thread:
            logger.info("Manual worker thread exists but is not running.")
            return False
        else:
            logger.info("No active manual command worker thread found to stop.")
            return False

    # Helper to emit CLI error safely from this mixin if needed
    def _emit_cli_error(self: 'MainWindow', message: str):
         try:
             if not isinstance(message, str): message = str(message)
             logger.debug(f"Emitting direct CLI error from WorkersMixin: {message}")
             # Assuming MainWindow instance has access to cli_error_signal via ApiWorkerThread or similar mechanism
             # This is slightly indirect. A better approach might be a dedicated signal on MainWindow itself.
             # For now, let's assume we can access a signal. If ApiWorkerThread exists, use its signal.
             # If not, maybe log and skip?
             if self.cli_error_signal: # Check if the signal exists directly on the mixin/main window instance
                  self.cli_error_signal.emit(f"[Handler Error] {message}".encode('utf-8'))
             elif self.api_worker_thread and hasattr(self.api_worker_thread, 'cli_error_signal'):
                  self.api_worker_thread.cli_error_signal.emit(f"[Handler Error] {message}".encode('utf-8'))
             else:
                  logger.warning(f"Cannot emit CLI error from WorkersMixin - no suitable signal found. Message: {message}")

         except RuntimeError: logger.warning("Cannot emit direct CLI error, target likely deleted.")
         except Exception as e: logger.error("Error emitting direct CLI error.", exc_info=True)