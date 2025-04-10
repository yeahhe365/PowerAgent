# ========================================
# 文件名: PowerAgent/gui/main_window_workers.py
# (NEW FILE - Contains worker interaction methods)
# ----------------------------------------
# gui/main_window_workers.py
# -*- coding: utf-8 -*-

import os
import time
import traceback
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Slot, QThread

# Import necessary components from the project
from core import config
from core.workers import ApiWorkerThread, ManualCommandThread

# Type hinting for MainWindow without causing circular import at runtime
if TYPE_CHECKING:
    from .main_window import MainWindow


class WorkersMixin:
    """Mixin containing worker interaction logic for MainWindow."""

    def is_busy(self: 'MainWindow') -> bool:
        # Checks if either the API or Manual command worker is active
        api_running = self.api_worker_thread and self.api_worker_thread.isRunning()
        manual_running = self.manual_cmd_thread and self.manual_cmd_thread.isRunning()
        return api_running or manual_running

    def start_api_worker(self: 'MainWindow', model_id: str, history: list, prompt: str):
        """Creates, connects, and starts the API worker thread."""
        if self.api_worker_thread and self.api_worker_thread.isRunning():
            print("Warning: Tried to start API worker while one was already running.")
            return

        self.api_worker_thread = ApiWorkerThread(
            api_key=config.API_KEY,
            api_url=config.API_URL,
            model_id=model_id, # Pass the selected model
            history=history, # Pass history (potentially with context)
            prompt=prompt, # Pass original prompt (worker mainly uses history now)
            cwd=self.current_directory
        )
        # Connect signals from the worker thread to handlers in the main window
        self.api_worker_thread.api_result.connect(self.handle_api_result)
        self.api_worker_thread.cli_output_signal.connect(lambda b: self.add_cli_output(b, "output"))
        self.api_worker_thread.cli_error_signal.connect(lambda b: self.add_cli_output(b, "error"))
        self.api_worker_thread.directory_changed_signal.connect(self.handle_directory_change)
        self.api_worker_thread.task_finished.connect(lambda: self.handle_task_finished("api"))
        self.api_worker_thread.start() # Start the thread execution

    def start_manual_worker(self: 'MainWindow', command: str):
        """Creates, connects, and starts the Manual command worker thread."""
        if self.manual_cmd_thread and self.manual_cmd_thread.isRunning():
            print("Warning: Tried to start manual worker while one was already running.")
            return

        self.manual_cmd_thread = ManualCommandThread(command, self.current_directory)
        # Connect signals
        self.manual_cmd_thread.cli_output_signal.connect(lambda b: self.add_cli_output(b, "output"))
        self.manual_cmd_thread.cli_error_signal.connect(lambda b: self.add_cli_output(b, "error"))
        self.manual_cmd_thread.directory_changed_signal.connect(self.handle_directory_change)
        self.manual_cmd_thread.command_finished.connect(lambda: self.handle_task_finished("manual"))
        self.manual_cmd_thread.start()


    def set_busy_state(self: 'MainWindow', busy: bool, task_type: str):
        """Updates UI element states (enabled/disabled) and the status indicator based on task activity."""
        if self._closing: return
        print(f"Setting busy state: {busy} for task type: {task_type}")

        # Determine the *next* busy state based on current and incoming tasks
        is_api_currently_busy = self.api_worker_thread and self.api_worker_thread.isRunning()
        is_manual_currently_busy = self.manual_cmd_thread and self.manual_cmd_thread.isRunning()

        # Calculate if API will be busy after this change
        next_api_busy = (is_api_currently_busy and not (task_type == "api" and not busy)) or \
                        (task_type == "api" and busy)
        # Calculate if Manual will be busy after this change
        next_manual_busy = (is_manual_currently_busy and not (task_type == "manual" and not busy)) or \
                           (task_type == "manual" and busy)

        # --- Update Enabled State of UI Elements ---
        if self.chat_input: self.chat_input.setEnabled(not next_api_busy)
        if self.send_button: self.send_button.setEnabled(not next_api_busy)
        if self.clear_chat_button: self.clear_chat_button.setEnabled(not next_api_busy)
        if self.cli_input: self.cli_input.setEnabled(not next_manual_busy)
        if self.clear_cli_button: self.clear_cli_button.setEnabled(not next_manual_busy)
        can_enable_model_selector = not next_api_busy and \
                                    self.model_selector_combo and \
                                    self.model_selector_combo.count() > 0 and \
                                    self.model_selector_combo.itemText(0) != "未配置模型"
        if self.model_selector_combo: self.model_selector_combo.setEnabled(can_enable_model_selector)


        # --- Update Status Indicator ---
        indicator_busy_state = next_api_busy or next_manual_busy
        self.update_status_indicator(indicator_busy_state)

        # --- Set Focus ---
        if not busy: # Only set focus when a task *finishes*
             QApplication.processEvents() # Allow UI to update before changing focus
             if not (next_api_busy or next_manual_busy): # If *no* tasks will be running
                 if task_type == "api" and self.chat_input and self.chat_input.isEnabled():
                     self.chat_input.setFocus()
                     print(f"Task '{task_type}' finished, setting focus to chat input.")
                 elif task_type == "manual" and self.cli_input and self.cli_input.isEnabled():
                     self.cli_input.setFocus()
                     print(f"Task '{task_type}' finished, setting focus to CLI input.")
             else:
                 print(f"Task '{task_type}' finished, but another task is running. Not setting focus.")

    @Slot(str, float)
    def handle_api_result(self: 'MainWindow', reply: str, elapsed_time: float):
        # Handles the text result from the API worker thread
        if self._closing: return
        time_str = f" (耗时: {elapsed_time:.2f} 秒)"
        message_with_time = f"{reply}{time_str}"
        self.add_chat_message("Model", message_with_time, add_to_internal_history=True)

    @Slot(str, bool)
    def handle_directory_change(self: 'MainWindow', new_directory: str, is_manual_command: bool):
        # Handles directory change signaled by workers (after 'cd' command)
        if self._closing: return
        if os.path.isdir(new_directory):
             old_directory = self.current_directory
             self.current_directory = os.path.normpath(new_directory) # Update internal CWD state
             # --- IMPORTANT: Change the process's actual CWD ---
             try:
                 os.chdir(self.current_directory)
                 print(f"Process working directory successfully changed to: {self.current_directory}")
             except Exception as e:
                 print(f"CRITICAL Error: Could not change process working directory to '{self.current_directory}': {e}")
                 error_msg = f"错误: 无法将进程工作目录更改为 '{self.current_directory}': {e}"
                 # Need access to add_cli_output
                 self.add_cli_output(error_msg.encode('utf-8'), "error")
             # --- End CWD Change ---
             self.update_prompt() # Update UI prompt
             source = "手动命令" if is_manual_command else "AI 命令"
             print(f"App directory state changed from '{old_directory}' to '{self.current_directory}' via {source}")
             self.save_state() # Save the new CWD state
        else:
            print(f"Warning: Directory change received for non-existent path '{new_directory}'")
            error_msg = f"Error: Directory not found: '{new_directory}'"
            # Need access to add_cli_output
            self.add_cli_output(error_msg.encode('utf-8'), "error") # Show error in CLI

    @Slot(str)
    def handle_task_finished(self: 'MainWindow', task_type: str):
        # Handles finished signal from worker threads (API or Manual)
        if self._closing: return
        print(f"{task_type.capitalize()} worker thread finished.")
        self.set_busy_state(False, task_type) # Set UI state to not busy
        # Clear the reference to the finished thread
        if task_type == "api":
            self.api_worker_thread = None
        elif task_type == "manual":
            self.manual_cmd_thread = None

    def stop_api_worker(self: 'MainWindow'):
        # Signals the API worker thread to stop
        if self.api_worker_thread and self.api_worker_thread.isRunning():
            print("Stopping API worker...")
            self.api_worker_thread.stop() # Call the thread's stop method
            return True # Indicate that stop was called
        return False # Worker wasn't running

    def stop_manual_worker(self: 'MainWindow'):
        # Signals the manual command worker thread to stop
        if self.manual_cmd_thread and self.manual_cmd_thread.isRunning():
            print("Stopping Manual Command worker...")
            self.manual_cmd_thread.stop() # Call the thread's stop method
            return True # Indicate that stop was called
        return False # Worker wasn't running