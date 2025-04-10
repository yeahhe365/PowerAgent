# ========================================
# 文件名: PowerAgent/gui/settings_dialog.py
# (MODIFIED)
# ---------------------------------------
# gui/settings_dialog.py
# -*- coding: utf-8 -*-

import platform
import os
from PySide6.QtWidgets import (
    QDialog, QLineEdit, QPushButton, QVBoxLayout, QFormLayout,
    QDialogButtonBox, QCheckBox, QLabel, QHBoxLayout,
    QComboBox, QSizePolicy, QSpacerItem, QGroupBox, QMessageBox,
    QSpinBox # Keep import even if unused now, in case needed later
)
from PySide6.QtCore import QStandardPaths, QCoreApplication, Qt, QSize
from PySide6.QtGui import QIcon

# Import constants needed for tooltips/paths
from constants import SETTINGS_APP_NAME, ORG_NAME
# Import config functions/state
from core import config

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("应用程序设置")
        self.setModal(True)
        self.setMinimumWidth(500)

        # Load current global settings initially to populate fields
        self.load_initial_values()

        # --- Widgets ---
        # (API Inputs - unchanged creation, except model tooltip and placeholder)
        self.url_input = QLineEdit(self._current_api_url)
        self.url_input.setPlaceholderText("例如: https://api.openai.com")
        self.url_input.setToolTip("输入您的 AI 服务 API 端点 URL")

        self.key_input = QLineEdit(self._current_api_key)
        self.key_input.setPlaceholderText("输入您的 API 密钥")
        self.key_input.setToolTip("输入您的 AI 服务 API 密钥 (保密)")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)

        # <<< MODIFIED: Use _current_model_id_string and update placeholder/tooltip >>>
        self.model_input = QLineEdit(self._current_model_id_string)
        self.model_input.setPlaceholderText("例如: gpt-4-turbo,claude-3 (逗号分隔)") # Moved hint here
        self.model_input.setToolTip("输入一个或多个 AI 模型 ID，用英文逗号分隔")
        # <<< END MODIFICATION >>>

        self.show_hide_button = QPushButton()
        self.show_hide_button.setCheckable(True); self.show_hide_button.setChecked(False)
        self.show_hide_button.setToolTip("显示/隐藏 API 密钥"); self.show_hide_button.setFlat(True)
        self.show_hide_button.setIconSize(QSize(16, 16)); self._update_visibility_icon(False)
        self.show_hide_button.clicked.connect(self.toggle_api_key_visibility)

        key_layout = QHBoxLayout(); key_layout.setContentsMargins(0, 0, 0, 0); key_layout.setSpacing(3)
        key_layout.addWidget(self.key_input, 1); key_layout.addWidget(self.show_hide_button)

        # (Theme, Autostart - unchanged creation)
        self.theme_combobox = QComboBox()
        self.theme_combobox.addItem("系统默认 (System)", "system"); self.theme_combobox.addItem("暗色 (Dark)", "dark"); self.theme_combobox.addItem("亮色 (Light)", "light")
        self.theme_combobox.setToolTip("选择应用程序界面主题。\n更改后需要应用设置。")
        current_theme_index = self.theme_combobox.findData(self._current_theme)
        self.theme_combobox.setCurrentIndex(current_theme_index if current_theme_index != -1 else 0)

        self.auto_startup_checkbox = QCheckBox("系统登录时启动")
        self.auto_startup_checkbox.setChecked(self._current_auto_startup)
        self.auto_startup_checkbox.setToolTip(self._get_autostart_tooltip())

        # --- MODIFIED: CLI Context Widget (Checkbox Only) ---
        self.include_cli_context_checkbox = QCheckBox("自动将近期 CLI 输出作为上下文发送给 AI")
        self.include_cli_context_checkbox.setChecked(self._current_include_cli_context)
        self.include_cli_context_checkbox.setToolTip(
            "启用后，每次向 AI 发送消息时，会自动附带左侧 CLI 输出的**全部**内容。\n"
            "这有助于 AI 理解当前状态，但也可能显著增加 API Token 消耗，尤其是在 CLI 输出很长时。"
        )

        # <<< MODIFICATION START: Add Timestamp Checkbox >>>
        self.include_timestamp_checkbox = QCheckBox("在系统提示词中包含当前日期时间")
        self.include_timestamp_checkbox.setChecked(self._current_include_timestamp)
        self.include_timestamp_checkbox.setToolTip(
            "启用后，每次向 AI 发送消息时，会在系统提示词中加入当前的日期和时间（精确到秒）。\n"
            "这可能对需要时间信息的任务有帮助，但会略微增加提示词长度。"
        )
        # <<< MODIFICATION END >>>


        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red; padding-top: 5px;"); self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True); self.error_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.error_label.setVisible(False)

        # --- Layout ---
        api_groupbox = QGroupBox("API 配置"); api_layout = QFormLayout(api_groupbox)
        api_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows); api_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight); api_layout.setSpacing(10)
        api_layout.addRow("API URL:", self.url_input); api_layout.addRow("API 密钥:", key_layout)
        # <<< MODIFIED: Changed Label text for model input row >>>
        api_layout.addRow("模型 ID:", self.model_input) # Removed "(逗号分隔)" from label
        # <<< END MODIFICATION >>>

        ui_groupbox = QGroupBox("界面与行为"); ui_layout = QVBoxLayout(ui_groupbox) # Use QVBoxLayout for better control
        ui_layout.setSpacing(10)

        # Theme layout
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("界面主题:"))
        theme_layout.addWidget(self.theme_combobox, 1) # Allow combobox to expand
        ui_layout.addLayout(theme_layout)

        # Autostart checkbox
        ui_layout.addWidget(self.auto_startup_checkbox)

        # CLI Context Checkbox (now directly in the VBox)
        ui_layout.addWidget(self.include_cli_context_checkbox)

        # <<< MODIFICATION START: Add Timestamp Checkbox to layout >>>
        ui_layout.addWidget(self.include_timestamp_checkbox)
        # <<< MODIFICATION END >>>

        # --- Reset Button ---
        self.reset_button = QPushButton("恢复默认设置并清除缓存")
        self.reset_button.setObjectName("reset_button") # Assign object name for potential lookup
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
        main_layout.addWidget(ui_groupbox) # Add the whole groupbox
        main_layout.addLayout(reset_layout)
        main_layout.addWidget(self.error_label)
        main_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        main_layout.addWidget(button_box)

    def load_initial_values(self):
        """Loads current config values into internal variables for UI population."""
        current_config_values = config.get_current_config()
        self._current_api_key = current_config_values.get("api_key", "")
        self._current_api_url = current_config_values.get("api_url", "")
        # <<< MODIFIED: Load model_id_string >>>
        self._current_model_id_string = current_config_values.get("model_id_string", "")
        # <<< END MODIFICATION >>>
        self._current_auto_startup = current_config_values.get("auto_startup", False)
        self._current_theme = current_config_values.get("theme", "system")
        self._current_include_cli_context = current_config_values.get("include_cli_context", config.DEFAULT_INCLUDE_CLI_CONTEXT)
        # <<< MODIFICATION START: Load initial timestamp value >>>
        self._current_include_timestamp = current_config_values.get("include_timestamp_in_prompt", config.DEFAULT_INCLUDE_TIMESTAMP)
        # <<< MODIFICATION END >>>


    def update_fields_from_config(self):
        """Updates the UI fields based on the current config module state (e.g., after reset)."""
        # Reload values from the config module
        self.load_initial_values()
        # Update UI elements
        self.url_input.setText(self._current_api_url)
        self.key_input.setText(self._current_api_key)
        # <<< MODIFIED: Update model_input with string >>>
        self.model_input.setText(self._current_model_id_string)
        # <<< END MODIFICATION >>>
        self.auto_startup_checkbox.setChecked(self._current_auto_startup)
        current_theme_index = self.theme_combobox.findData(self._current_theme)
        self.theme_combobox.setCurrentIndex(current_theme_index if current_theme_index != -1 else 0)
        self.include_cli_context_checkbox.setChecked(self._current_include_cli_context)
        # <<< MODIFICATION START: Update timestamp checkbox after reset >>>
        self.include_timestamp_checkbox.setChecked(self._current_include_timestamp)
        # <<< MODIFICATION END >>>

        # Ensure password visibility is reset if key was cleared
        if not self._current_api_key:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_hide_button.setChecked(False)
            self._update_visibility_icon(False)


    def _update_visibility_icon(self, visible: bool):
        # Logic remains the same
        icon_name_on = "visibility"; icon_name_off = "visibility_off"
        icon = QIcon.fromTheme(icon_name_off if not visible else icon_name_on)
        if icon.isNull(): self.show_hide_button.setText("👁️" if not visible else "🚫"); self.show_hide_button.setIcon(QIcon())
        else: self.show_hide_button.setIcon(icon); self.show_hide_button.setText("")

    def _get_autostart_tooltip(self) -> str:
        # Logic remains the same
        startup_tooltip = "启用/禁用在您登录时自动启动应用程序。\n更改可能需要重启应用程序或重新登录才能完全生效。\n\n实现机制:\n"
        try:
            if platform.system() == "Windows": key_path = f"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\{SETTINGS_APP_NAME}"; startup_tooltip += f"- Windows 注册表: {key_path}"
            elif platform.system() == "Linux":
                autostart_dir_base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.ConfigLocation); autostart_path = os.path.join(autostart_dir_base, "autostart", f"{SETTINGS_APP_NAME}.desktop") if autostart_dir_base else ""
                startup_tooltip += f"- Linux 桌面条目: {autostart_path}" if autostart_path else "- Linux 桌面条目: (~/.config/autostart/...)"
            elif platform.system() == "Darwin": plist_path = os.path.expanduser(f"~/Library/LaunchAgents/com.{ORG_NAME}.{SETTINGS_APP_NAME}.plist"); startup_tooltip += f"- macOS 启动代理: {plist_path}"
            else: startup_tooltip += f"- 未为 {platform.system()} 实现"
        except Exception as e: print(f"Error generating autostart tooltip details: {e}"); startup_tooltip += "- 无法确定具体路径。"
        return startup_tooltip

    def toggle_api_key_visibility(self, checked):
        # Logic remains the same
        if checked: self.key_input.setEchoMode(QLineEdit.EchoMode.Normal); self.show_hide_button.setToolTip("隐藏 API 密钥")
        else: self.key_input.setEchoMode(QLineEdit.EchoMode.Password); self.show_hide_button.setToolTip("显示 API 密钥")
        self._update_visibility_icon(checked)

    def handle_reset_settings(self):
        """Handles the reset button click."""
        reply = QMessageBox.warning(
            self, "确认重置",
            "您确定要将所有设置恢复为默认值并清除所有缓存数据（包括API密钥、模型列表、聊天记录、命令历史和保存的目录）吗？\n\n此操作无法撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )
        if reply == QMessageBox.StandardButton.Yes:
            print("User confirmed reset. Resetting settings and clearing cache...")
            try:
                config.reset_to_defaults_and_clear_cache()
                print("Config module reset executed.")
                self.update_fields_from_config() # Update dialog fields
                print("Settings dialog fields updated to reflect reset.")
                QMessageBox.information(self, "重置完成", "设置已恢复为默认值，缓存已清除。\n您可能需要重新配置API密钥和模型ID才能使用AI功能。") # Updated message
            except Exception as e:
                 print(f"Error during reset process: {e}")
                 QMessageBox.critical(self, "重置错误", f"恢复默认设置时发生错误:\n{e}")
        else:
            print("User cancelled reset.")


    def validate_and_accept(self):
        """Validate inputs before accepting the dialog."""
        # <<< MODIFIED: Validate model_id_string >>>
        api_key = self.key_input.text().strip()
        api_url = self.url_input.text().strip()
        model_id_string = self.model_input.text().strip()
        # <<< END MODIFICATION >>>

        self.error_label.setText(""); self.error_label.setVisible(False)
        default_style = ""; self.url_input.setStyleSheet(default_style); self.key_input.setStyleSheet(default_style); self.model_input.setStyleSheet(default_style)
        errors = []
        if not api_url: errors.append("API URL")
        if not api_key: errors.append("API 密钥")
        # <<< MODIFIED: Validate model_id_string is not empty >>>
        if not model_id_string: errors.append("模型 ID")
        # Optionally add more complex validation for comma separation here if desired
        # <<< END MODIFICATION >>>

        if errors:
            error_msg = "以下必填字段不能为空:\n- " + "\n- ".join(errors); self.error_label.setText(error_msg); self.error_label.setVisible(True)
            error_style = "border: 1px solid red;"; first_error_field = None
            if "API URL" in errors: self.url_input.setStyleSheet(error_style); first_error_field = first_error_field or self.url_input
            if "API 密钥" in errors: self.key_input.setStyleSheet(error_style); first_error_field = first_error_field or self.key_input
            # <<< MODIFIED: Highlight model input on error >>>
            if "模型 ID" in errors: self.model_input.setStyleSheet(error_style); first_error_field = first_error_field or self.model_input
            # <<< END MODIFICATION >>>
            if first_error_field: first_error_field.setFocus()
            print(f"Settings validation failed: {error_msg}")
            return
        self.accept()

    # <<< MODIFIED: Return model_id_string >>>
    def get_values(self):
        """Returns all configured values from the dialog."""
        selected_theme = self.theme_combobox.currentData()
        valid_themes = ["dark", "light", "system"]; selected_theme = selected_theme if selected_theme in valid_themes else "system"
        return (
            self.key_input.text().strip(),
            self.url_input.text().strip(),
            self.model_input.text().strip(), # Return the comma-separated string
            self.auto_startup_checkbox.isChecked(),
            selected_theme,
            self.include_cli_context_checkbox.isChecked(),
            self.include_timestamp_checkbox.isChecked(), # Timestamp value added here
        )
    # <<< END MODIFICATION >>>