# ========================================
# 文件名: PowerAgent/gui/settings_dialog.py
# (MODIFIED - Added CheckBox for Auto Include UI Info)
# ---------------------------------------
# gui/settings_dialog.py
# -*- coding: utf-8 -*-

import platform
import os
from PySide6.QtWidgets import (
    QDialog, QLineEdit, QPushButton, QVBoxLayout, QFormLayout,
    QDialogButtonBox, QCheckBox, QLabel, QHBoxLayout,
    QComboBox, QSizePolicy, QSpacerItem, QGroupBox, QMessageBox,
    QSpinBox
)
from PySide6.QtCore import QStandardPaths, QCoreApplication, Qt, QSize
from PySide6.QtGui import QIcon

# Import constants needed for paths/names
from constants import SETTINGS_APP_NAME, ORG_NAME
# Import config functions/state
from core import config

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("应用程序设置")
        self.setModal(True)
        self.setMinimumWidth(500) # Increased width slightly for new options

        # Load current global settings initially to populate fields
        self.load_initial_values()

        # --- Widgets ---
        self.url_input = QLineEdit(self._current_api_url)
        self.url_input.setPlaceholderText("例如: https://api.openai.com/v1") # Example with /v1

        self.key_input = QLineEdit(self._current_api_key)
        self.key_input.setPlaceholderText("输入您的 API 密钥")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.model_input = QLineEdit(self._current_model_id_string)
        self.model_input.setPlaceholderText("例如: gpt-4-turbo,claude-3-opus (逗号分隔)")

        self.show_hide_button = QPushButton()
        self.show_hide_button.setCheckable(True); self.show_hide_button.setChecked(False)
        self.show_hide_button.setFlat(True) # Make it look like an icon button
        self.show_hide_button.setToolTip("显示/隐藏 API 密钥")
        self.show_hide_button.setIconSize(QSize(16, 16)); self._update_visibility_icon(False)
        self.show_hide_button.clicked.connect(self.toggle_api_key_visibility)
        # Adjust size policy to hug the icon
        self.show_hide_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


        key_layout = QHBoxLayout(); key_layout.setContentsMargins(0, 0, 0, 0); key_layout.setSpacing(3)
        key_layout.addWidget(self.key_input, 1); key_layout.addWidget(self.show_hide_button)

        self.theme_combobox = QComboBox()
        self.theme_combobox.addItem("系统默认 (System)", "system"); self.theme_combobox.addItem("暗色 (Dark)", "dark"); self.theme_combobox.addItem("亮色 (Light)", "light")
        current_theme_index = self.theme_combobox.findData(self._current_theme)
        self.theme_combobox.setCurrentIndex(current_theme_index if current_theme_index != -1 else 0)

        self.auto_startup_checkbox = QCheckBox("系统登录时启动")
        self.auto_startup_checkbox.setChecked(self._current_auto_startup)

        self.include_cli_context_checkbox = QCheckBox("自动将近期 CLI 输出作为上下文发送给 AI")
        self.include_cli_context_checkbox.setChecked(self._current_include_cli_context)
        self.include_cli_context_checkbox.setToolTip(
            "启用后，每次向 AI 发送消息时，会自动附带左侧 CLI 输出的**全部**内容。\n"
            "这有助于 AI 理解当前状态，但也可能显著增加 API Token 消耗，尤其是在 CLI 输出很长时。"
        )

        self.include_timestamp_checkbox = QCheckBox("在系统提示词中包含当前日期时间")
        self.include_timestamp_checkbox.setChecked(self._current_include_timestamp)
        self.include_timestamp_checkbox.setToolTip(
            "启用后，每次向 AI 发送消息时，会在系统提示词中加入当前的日期和时间（精确到秒）。\n"
            "这可能对需要时间信息的任务有帮助，但会略微增加提示词长度。"
        )

        # --- Multi-Step Options ---
        self.enable_multi_step_checkbox = QCheckBox("启用 AI 连续操作模式 (实验性)")
        self.enable_multi_step_checkbox.setChecked(self._current_enable_multi_step)
        self.enable_multi_step_checkbox.setToolTip(
            "**实验性功能:** 启用后，AI 可以执行多步骤任务。\n"
            "工作流程:\n"
            "1. AI 返回一个操作 (<cmd>, <keyboard>, <gui_action>, <get_ui_info>)。\n" # Added get_ui_info
            "2. 应用执行该操作。\n"
            "3. 应用将操作结果/获取的信息作为系统消息添加到历史记录中。\n"
            "4. 应用**自动再次调用 AI**。\n"
            "5. AI 根据上一步的结果决定下一步操作或提供最终文本回复。\n"
            "**风险:** 可能导致意外行为、API 成本增加或陷入循环（有最大次数限制）。\n"
            "禁用此选项将恢复为单次问答模式。"
        )

        self.max_iterations_spinbox = QSpinBox()
        self.max_iterations_spinbox.setMinimum(1)   # Minimum 1 iteration
        self.max_iterations_spinbox.setMaximum(20)  # Set a reasonable maximum
        self.max_iterations_spinbox.setValue(self._current_multi_step_max_iterations)
        self.max_iterations_spinbox.setToolTip(
            "设置“连续操作模式”下，AI 自动连续执行操作的最大次数。\n"
            "用于防止无限循环和控制 API 成本。\n"
            "推荐值: 3-10。"
        )
        # Enable/disable based on multi-step checkbox state initially and on toggle
        self.max_iterations_spinbox.setEnabled(self._current_enable_multi_step)
        self.enable_multi_step_checkbox.toggled.connect(self.max_iterations_spinbox.setEnabled)

        # <<< MODIFICATION START: Add CheckBox for Auto UI Info >>>
        self.auto_include_ui_checkbox = QCheckBox("自动附加活动窗口 UI 结构信息 (实验性, 仅 Windows)")
        self.auto_include_ui_checkbox.setChecked(self._current_auto_include_ui_info)
        self.auto_include_ui_checkbox.setToolTip(
            "**实验性功能 (仅 Windows):** 启用后，每次向 AI 发送消息时，会自动尝试获取当前活动窗口的 UI 元素结构信息，并将其附加到上下文中。\n"
            "这可以帮助 AI 更精确地定位 GUI 元素 (使用 <gui_action>)，但也可能：\n"
            "- 显著增加 API Token 消耗。\n"
            "- 增加 AI 响应延迟。\n"
            "- 在某些复杂窗口中获取信息失败或不准确。\n"
            "禁用时，AI 只能基于文本历史和通用知识猜测 UI 元素，或通过 <get_ui_info> 主动请求。"
        )
        # Disable this checkbox if not on Windows or if uiautomation is not available
        is_gui_available = platform.system() == "Windows" and getattr(config, 'UIAUTOMATION_AVAILABLE_FOR_GUI', False)
        self.auto_include_ui_checkbox.setEnabled(is_gui_available)
        if not is_gui_available:
             self.auto_include_ui_checkbox.setToolTip(self.auto_include_ui_checkbox.toolTip() + "\n\n(此选项在此系统或配置下不可用)")
        # <<< MODIFICATION END >>>


        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red; padding-top: 5px;"); self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True); self.error_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.error_label.setVisible(False)

        # --- Layout ---
        api_groupbox = QGroupBox("API 配置"); api_layout = QFormLayout(api_groupbox)
        api_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows); api_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight); api_layout.setSpacing(10)
        api_layout.addRow("API URL:", self.url_input); api_layout.addRow("API 密钥:", key_layout)
        api_layout.addRow("模型 ID (逗号分隔):", self.model_input) # Clarified label

        # UI & Behavior Group
        ui_groupbox = QGroupBox("界面与行为"); ui_layout = QVBoxLayout(ui_groupbox)
        ui_layout.setSpacing(10)

        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("界面主题:"))
        theme_layout.addWidget(self.theme_combobox, 1)
        ui_layout.addLayout(theme_layout)

        ui_layout.addWidget(self.auto_startup_checkbox)
        ui_layout.addWidget(self.include_cli_context_checkbox)
        ui_layout.addWidget(self.include_timestamp_checkbox)

        # AI Behavior Sub-Group (Optional visual grouping)
        ai_behavior_group = QGroupBox("AI 行为 (实验性)")
        ai_behavior_layout = QVBoxLayout(ai_behavior_group)
        ai_behavior_layout.setSpacing(8) # Slightly less spacing inside

        ai_behavior_layout.addWidget(self.enable_multi_step_checkbox)

        iterations_layout = QHBoxLayout()
        iterations_layout.setContentsMargins(15, 0, 0, 0) # Indent spinbox relative to checkbox
        iterations_layout.addWidget(QLabel("连续操作最大次数:")) # Label next to spinbox
        iterations_layout.addWidget(self.max_iterations_spinbox)
        iterations_layout.addStretch(1) # Push spinbox to the left
        ai_behavior_layout.addLayout(iterations_layout)

        # <<< MODIFICATION START: Add Auto UI Info checkbox to AI group >>>
        ai_behavior_layout.addWidget(self.auto_include_ui_checkbox)
        # <<< MODIFICATION END >>>

        ui_layout.addWidget(ai_behavior_group) # Add the sub-group to the main UI layout

        # --- Reset Button ---
        self.reset_button = QPushButton("恢复默认设置并清除缓存")
        self.reset_button.setObjectName("reset_button")
        self.reset_button.setToolTip("将所有设置恢复为默认值，并清除聊天历史、命令历史和保存的工作目录。\n此操作无法撤销，需要确认。")
        self.reset_button.clicked.connect(self.handle_reset_settings)
        reset_layout = QHBoxLayout(); reset_layout.addWidget(self.reset_button); reset_layout.addStretch(1)

        # --- Standard Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(api_groupbox)
        main_layout.addWidget(ui_groupbox)
        main_layout.addLayout(reset_layout) # Reset button above error label
        main_layout.addWidget(self.error_label) # Error label at bottom before buttons
        # Removed the expanding spacer, let the groups take available space
        # main_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        main_layout.addWidget(button_box)

    def load_initial_values(self):
        """Loads current config values into internal variables for UI population."""
        current_config_values = config.get_current_config()
        self._current_api_key = current_config_values.get("api_key", config.DEFAULT_API_KEY)
        self._current_api_url = current_config_values.get("api_url", config.DEFAULT_API_URL)
        self._current_model_id_string = current_config_values.get("model_id_string", config.DEFAULT_MODEL_ID_STRING)
        self._current_auto_startup = current_config_values.get("auto_startup", config.DEFAULT_AUTO_STARTUP_ENABLED)
        self._current_theme = current_config_values.get("theme", config.DEFAULT_APP_THEME)
        self._current_include_cli_context = current_config_values.get("include_cli_context", config.DEFAULT_INCLUDE_CLI_CONTEXT)
        self._current_include_timestamp = current_config_values.get("include_timestamp_in_prompt", config.DEFAULT_INCLUDE_TIMESTAMP)
        self._current_enable_multi_step = current_config_values.get("enable_multi_step", config.DEFAULT_ENABLE_MULTI_STEP)
        self._current_multi_step_max_iterations = current_config_values.get("multi_step_max_iterations", config.DEFAULT_MULTI_STEP_MAX_ITERATIONS)
        # <<< MODIFICATION START: Load auto UI info value >>>
        self._current_auto_include_ui_info = current_config_values.get("auto_include_ui_info", config.DEFAULT_AUTO_INCLUDE_UI_INFO)
        # <<< MODIFICATION END >>>


    def update_fields_from_config(self):
        """Updates the UI fields based on the current config module state (e.g., after reset)."""
        self.load_initial_values() # Reload from config module first
        self.url_input.setText(self._current_api_url)
        self.key_input.setText(self._current_api_key)
        self.model_input.setText(self._current_model_id_string)
        self.auto_startup_checkbox.setChecked(self._current_auto_startup)
        current_theme_index = self.theme_combobox.findData(self._current_theme)
        self.theme_combobox.setCurrentIndex(current_theme_index if current_theme_index != -1 else 0)
        self.include_cli_context_checkbox.setChecked(self._current_include_cli_context)
        self.include_timestamp_checkbox.setChecked(self._current_include_timestamp)
        self.enable_multi_step_checkbox.setChecked(self._current_enable_multi_step)
        self.max_iterations_spinbox.setValue(self._current_multi_step_max_iterations)
        self.max_iterations_spinbox.setEnabled(self._current_enable_multi_step) # Ensure enabled state is correct
        # <<< MODIFICATION START: Update auto UI info checkbox >>>
        self.auto_include_ui_checkbox.setChecked(self._current_auto_include_ui_info)
        # Also re-check enabled state based on platform/library availability
        is_gui_available = platform.system() == "Windows" and getattr(config, 'UIAUTOMATION_AVAILABLE_FOR_GUI', False)
        self.auto_include_ui_checkbox.setEnabled(is_gui_available)
        # <<< MODIFICATION END >>>

        # Reset API Key visibility if key is now empty
        if not self._current_api_key:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_hide_button.setChecked(False)
            self._update_visibility_icon(False)
        # No need to clear error label here, validation handles that

    def _update_visibility_icon(self, visible: bool):
        """Updates the icon for the show/hide API key button."""
        icon_name_on = "visibility"; icon_name_off = "visibility_off"
        # Try to get themed icons
        icon = QIcon.fromTheme(icon_name_on if visible else icon_name_off)
        if icon.isNull():
            # Fallback text/emoji if icons not found
            self.show_hide_button.setText("👁️" if visible else "🚫")
            self.show_hide_button.setIcon(QIcon()) # Clear icon if using text
        else:
            self.show_hide_button.setIcon(icon)
            self.show_hide_button.setText("") # Clear text if using icon

    def toggle_api_key_visibility(self, checked):
        """Slot to change API key echo mode and button icon."""
        if checked:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._update_visibility_icon(checked)

    def handle_reset_settings(self):
        """Handles the reset button click with confirmation."""
        reply = QMessageBox.warning(
            self, "确认重置",
            "您确定要将所有设置恢复为默认值并清除所有缓存数据（包括API密钥、模型列表、聊天记录、命令历史、保存的目录和所有行为设置）吗？\n\n此操作无法撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel # Default button is Cancel
        )
        if reply == QMessageBox.StandardButton.Yes:
            print("User confirmed reset. Resetting settings and clearing cache...")
            try:
                # Call the config reset function
                config.reset_to_defaults_and_clear_cache()
                print("Config module reset executed.")
                # Update the dialog fields to reflect the reset defaults
                self.update_fields_from_config()
                print("Settings dialog fields updated to reflect reset.")
                # Hide any previous validation errors
                self.error_label.setVisible(False)
                # Inform the user
                QMessageBox.information(self, "重置完成", "设置已恢复为默认值，缓存已清除。\n您可能需要重新配置API密钥和模型ID才能使用AI功能。")
            except Exception as e:
                 print(f"Error during reset process: {e}")
                 QMessageBox.critical(self, "重置错误", f"恢复默认设置时发生错误:\n{e}")
        else:
            print("User cancelled reset.")


    def validate_and_accept(self):
        """Validate inputs before accepting the dialog."""
        api_key = self.key_input.text().strip()
        api_url = self.url_input.text().strip()
        model_id_string = self.model_input.text().strip()

        # Clear previous errors
        self.error_label.setText(""); self.error_label.setVisible(False)
        # Reset stylesheets to default (important if previously marked red)
        default_style = ""; self.url_input.setStyleSheet(default_style); self.key_input.setStyleSheet(default_style); self.model_input.setStyleSheet(default_style)

        errors = []
        # Validate API Key/URL/Model only if ANY of them are filled
        # If user intends to use API, all three are generally required. If all empty, it's fine.
        if api_key or api_url or model_id_string:
            if not api_url: errors.append("API URL")
            if not api_key: errors.append("API 密钥")
            if not model_id_string: errors.append("模型 ID")
            # Basic URL format check (very simple)
            if api_url and not (api_url.startswith("http://") or api_url.startswith("https://")):
                errors.append("API URL 格式无效 (应以 http:// 或 https:// 开头)")


        if errors:
            error_msg = "请修正以下错误:\n- " + "\n- ".join(errors); self.error_label.setText(error_msg); self.error_label.setVisible(True)
            # Highlight the fields with errors
            error_style = "border: 1px solid red;"; first_error_field = None
            if "API URL" in errors or "API URL 格式无效" in errors: self.url_input.setStyleSheet(error_style); first_error_field = first_error_field or self.url_input
            if "API 密钥" in errors: self.key_input.setStyleSheet(error_style); first_error_field = first_error_field or self.key_input
            if "模型 ID" in errors: self.model_input.setStyleSheet(error_style); first_error_field = first_error_field or self.model_input
            # Set focus to the first field with an error
            if first_error_field: first_error_field.setFocus()
            print(f"Settings validation failed: {error_msg}")
            return # Don't accept yet

        # Validation passed
        self.accept()

    def get_values(self):
        """Returns all configured values from the dialog widgets."""
        selected_theme_data = self.theme_combobox.currentData()
        # Ensure theme data is one of the valid strings
        valid_themes = ["dark", "light", "system"]
        selected_theme = selected_theme_data if selected_theme_data in valid_themes else config.DEFAULT_APP_THEME

        # <<< MODIFICATION START: Return auto UI info checkbox state >>>
        return (
            self.key_input.text().strip(),
            self.url_input.text().strip(),
            self.model_input.text().strip(),
            self.auto_startup_checkbox.isChecked(),
            selected_theme,
            self.include_cli_context_checkbox.isChecked(),
            self.include_timestamp_checkbox.isChecked(),
            self.enable_multi_step_checkbox.isChecked(),
            self.max_iterations_spinbox.value(), # Get value from spinbox
            self.auto_include_ui_checkbox.isChecked(), # Get state of the new checkbox
        )
        # <<< MODIFICATION END >>>